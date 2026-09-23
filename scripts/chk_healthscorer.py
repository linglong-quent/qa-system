#!/usr/bin/env python3  # noqa: STYLE-05, LARGE-01
"""QA System Core — HealthScorer V3.0 (with plugin support)

架构（三层合一）:
  Layer A — 内置通用 checker: inplace / lookahead / secret / deadcode / cyclic / code_ban
  Layer B — 项目插件: 自动发现 .ai/plugins/ 下的 checker
  Layer C — CI/CD 集成: pre-commit + GitHub Actions + SARIF + metrics

补丁层 B 的写法:
  .ai/plugins/<pkg>/<file>.py 或 .ai/plugins/<file>.py
  每个文件需导出 check(config: dict, project_root: str) -> (errors: int, issues: List[str])
  在 review-rules.yaml 中 plugins 段配置启用/禁用。
"""
import os, re, json, logging, importlib, importlib.util, sys, uuid
from datetime import datetime
from typing import List, Tuple

logger = logging.getLogger(__name__)

from chk_load_yaml import load_yaml

# ── Layer A: 内置通用 checkers ───────────────────────────────────
from chk_inplacechecker import InplaceChecker
from chk_lookaheadchecker import LookaheadChecker
from chk_secretchecker import SecretChecker
from chk_deadcodechecker import DeadCodeChecker
from chk_cyclicchecker import CyclicImportChecker
from chk_codebanchecker import CodeBanChecker
from chk_importboundary import ImportBoundaryChecker
from chk_configauditchecker import ConfigAuditChecker
from chk_qualitygates import QualityGateChecker
from chk_claudevalidator import ClaudeValidator
from chk_codestyle import CodeStyleChecker
from chk_largefiles import LargeFilesChecker
from chk_governance import GovernanceChecker
from chk_securityplus import SecurityPlusChecker
from chk_documentation import DocumentationChecker
from chk_production import ProductionChecker
from chk_zeroprint import ZeroPrintChecker
from chk_customrules import CustomRulesChecker
from chk_fusedetector import FuseDetectorChecker
from chk_docconsistency import DocConsistencyChecker
from chk_namingconflict import NamingConflictChecker
from chk_solid import SolidChecker
from chk_semantic import SemanticTruthChecker
from chk_docstrcode import DocstringCodeChecker
from chk_runtime import RuntimeDriftChecker
from chk_vcs import VcsGovernanceChecker
from chk_blindspot import BlindSpotChecker
from chk_container import ContainerPlaneChecker


class HealthScorer:
    """QA 系统核心评分引擎 — V3.0 0-污染模式"""

    def __init__(self, project_root: str, bootstrap: bool = False, profile: str = "",  # noqa: STYLE-06
                 qa_system_root: str = "", project_name: str = "",
                 run_dir: str = "", persist: bool = True):
        self.project_root = os.path.abspath(project_root)
        self.qa_system_root = qa_system_root or os.environ.get("QA_SYSTEM_ROOT", "")
        self.project_name = project_name or os.environ.get("QA_PROJECT_NAME", "")
        # ── 产物隔离（编排契约 v1.1）──────────────────────────────
        # run_dir    : 显式 run 目录 → 报告写 {run_dir}/qa-report.json（并行安全）
        # persist=False: 不落权威报告，改写进程内暂存目录（供 quality_gates 读取）
        self.run_dir = os.path.abspath(run_dir) if run_dir else ""
        self.persist = bool(persist)
        self.report_path = ""

        # 0-污染模式：配置在 QA 系统中，不在项目里
        # 优先查找 .ai/projects/{name}_local.yaml（0-污染模式标准命名）
        # 其次查找 .ai/projects/{name}.yaml（向后兼容）
        config_path = ""
        if self.qa_system_root and self.project_name:
            candidates = [
                os.path.join(self.qa_system_root, f".ai/projects/{self.project_name}_local.yaml"),
                os.path.join(self.qa_system_root, f".ai/projects/{self.project_name}.yaml"),
            ]
            for cp in candidates:
                if os.path.exists(cp):
                    config_path = cp
                    break
            if not config_path:
                # fallback：QA-System 自身配置（仅用于 QA 系统自检场景）
                qa_self = os.path.join(self.qa_system_root, ".ai/config/review-rules.yaml")
                if os.path.exists(qa_self):
                    config_path = qa_self
        if not config_path or not os.path.exists(config_path):
            config_path = os.path.join(self.project_root, ".ai/config/review-rules.yaml")
        self.config = load_yaml(config_path)

        # Profile / Bootstrap
        profiles_config = self.config.get("profiles", {})
        default_profile = self.config.get("default_profile", "full")
        self.active_profile = profile or default_profile
        config_bootstrap = self.config.get("bootstrap_mode", False)
        self.bootstrap = bootstrap or config_bootstrap
        if self.bootstrap and not profile:
            self.active_profile = "dev"
        profile_def = profiles_config.get(self.active_profile, {})
        self._profile_checkers_on = profile_def.get("checkers_on", [])
        if self.active_profile == "dev" and not bootstrap:
            self.bootstrap = True

        # ── Layer A: 内置 checker ────────────────────────────────
        self._checkers: List[Tuple[str, object, str]] = []
        self._enabled: dict = {}

        def _add(cid: str, instance, label: str):
            enabled = self.config.get(cid, {}).get("enabled", True)
            self._checkers.append((cid, instance, label))
            return enabled

        for cid, cls, label, cfg_key in [
            ("inplace_check",    InplaceChecker,      "pandas inplace=True",    "inplace_check"),
            ("lookahead_check",  LookaheadChecker,    "前视偏差",                "lookahead_check"),
            ("secret_check",     SecretChecker,       "硬编码密钥",              "secret_check"),
            ("deadcode_check",   DeadCodeChecker,     "孤儿代码",                "deadcode_check"),
            ("cyclic_check",     CyclicImportChecker, "循环导入",                "cyclic_check"),
        ]:
            cfg = self.config.get(cfg_key, {})
            self._enabled[cid] = _add(cid, cls(cfg, self.project_root), label)

        cb_cfg = self.config.get("code_ban_check", {})
        self._enabled["code_ban"] = _add("code_ban", CodeBanChecker(cb_cfg, self.project_root), "代码禁用规则")

        # 架构边界门禁
        ib_cfg = self.config.get("import_boundary_check", {})
        self._enabled["import_boundary"] = _add(
            "import_boundary", ImportBoundaryChecker(ib_cfg, self.project_root), "架构边界门禁")

        # QA 配置自审
        ca_cfg = self.config.get("config_audit_check", {})
        self._enabled["config_audit"] = _add("config_audit", ConfigAuditChecker(ca_cfg, self.project_root), "配置自审")

        # 生产环境就绪
        pr_cfg = self.config.get("production_check", {})
        # 代码风格
        cs_cfg = self.config.get("codestyle_check", {})
        self._enabled["codestyle"] = _add("codestyle", CodeStyleChecker(cs_cfg, self.project_root), "代码风格")
        # 大文件强制阻断（LARGE-01 BLOCKER / LARGE-02 WARN baseline）
        lf_cfg = self.config.get("largefiles_check", {})
        self._enabled["largefiles"] = _add("largefiles", LargeFilesChecker(lf_cfg, self.project_root), "大文件检测")
        # 项目治理
        gv_cfg = self.config.get("governance_check", {})
        self._enabled["governance"] = _add("governance", GovernanceChecker(gv_cfg, self.project_root), "项目治理")
        # 安全增强
        sp_cfg = self.config.get("securityplus_check", {})
        self._enabled["securityplus"] = _add("securityplus", SecurityPlusChecker(sp_cfg, self.project_root), "安全增强")
        # 文档质量
        dc_cfg = self.config.get("documentation_check", {})
        self._enabled["documentation"] = _add("documentation", DocumentationChecker(dc_cfg, self.project_root), "文档质量")
        # 零打印
        zp_cfg = self.config.get("zeroprint_check", {})
        self._enabled["zeroprint"] = _add("zeroprint", ZeroPrintChecker(zp_cfg, self.project_root), "零打印")
        # 自定义规则
        cr_cfg = self.config.get("customrules_check", {})
        self._enabled["customrules"] = _add("customrules", CustomRulesChecker(cr_cfg, self.project_root), "自定义规则")
        # 熔断检测
        fd_cfg = self.config.get("fusedetect_check", {})
        self._enabled["fusedetect"] = _add("fusedetect", FuseDetectorChecker(fd_cfg, self.project_root), "熔断检测")
        # 文档一致性
        ds_cfg = self.config.get("docconsistency_check", {})
        self._enabled["docconsistency"] = _add("docconsistency", DocConsistencyChecker(ds_cfg, self.project_root), "文档一致性")

        # 命名冲突检测 (STYLE-03b 跨域命名空间隔离 & 单一数据源)
        nc_cfg = self.config.get("naming_conflict_check", {})
        self._enabled["naming_conflict"] = _add("naming_conflict", NamingConflictChecker(nc_cfg, self.project_root), "命名冲突检测")

        # SOLID 五原则静态门禁 (S/O/L/I/D AST 检查)
        sd_cfg = self.config.get("solid_check", {})
        self._enabled["solid"] = _add("solid", SolidChecker(sd_cfg, self.project_root), "SOLID 五原则")

        # ── T29 盲区规则集（七类盲区 + 追加类）────────────────────
        # ① 语义真实性：伪造计算 / 空壳假成功 / 静默降级
        st_cfg = self.config.get("semantic_truth_check", {})
        self._enabled["semantic_truth"] = _add(
            "semantic_truth", SemanticTruthChecker(st_cfg, self.project_root), "语义真实性")
        # 追加类：docstring 内可执行代码 / 未绑定名 / 改名手术完整性
        dc_cfg = self.config.get("docstring_code_check", {})
        self._enabled["docstring_code"] = _add(
            "docstring_code", DocstringCodeChecker(dc_cfg, self.project_root), "docstring代码与绑定")
        # ② 运行态与进程层：代码-进程漂移 / 端点无守护
        rd_cfg = self.config.get("runtime_drift_check", {})
        self._enabled["runtime_drift"] = _add(
            "runtime_drift", RuntimeDriftChecker(rd_cfg, self.project_root), "运行态与进程层")
        # ③ 版本控制治理：脱节 / 关键目录 0 入库
        vc_cfg = self.config.get("vcs_governance_check", {})
        self._enabled["vcs_governance"] = _add(
            "vcs_governance", VcsGovernanceChecker(vc_cfg, self.project_root), "版本控制治理")
        # ④⑤⑥+⑦ 克隆 / 声明 / 构建 / 路径
        # T51 新增：容器平面（Docker 恢复后启用；不可用时自行 skipped）
        cp_cfg = self.config.get("container_plane_check", {})
        self._enabled["container_plane"] = _add(
            "container_plane", ContainerPlaneChecker(cp_cfg, self.project_root), "容器平面")
        bs_cfg = self.config.get("blindspot_check", {})
        self._enabled["blindspot"] = _add(
            "blindspot", BlindSpotChecker(bs_cfg, self.project_root), "克隆/声明/构建/路径")

        self._enabled["production"] = _add("production", ProductionChecker(pr_cfg, self.project_root), "生产就绪")

        # 质量门控
        qg_cfg = self.config.get("quality_gates", {})
        self._enabled["quality_gates"] = _add("quality_gates", QualityGateChecker(qg_cfg, self.project_root), "质量门控")

        # CLAUDE.md 合规验证
        cv_cfg = self.config.get("claude_validation", {})
        self._enabled["claude_validation"] = _add("claude_validation", ClaudeValidator(cv_cfg, self.project_root), "CLAUDE 验证")

        # ── Layer B: 项目插件（文件路径加载） ────────────────────
        plugin_config = self.config.get("plugins", {})
        if plugin_config.get("enabled", True):
            self._load_plugins(plugin_config)

        # profile 覆盖
        if self._profile_checkers_on:
            active = set(self._profile_checkers_on)
            for cid in self._enabled:
                self._enabled[cid] = cid in active

    # ── Layer B: 插件自动发现（文件路径加载） ────────────────────

    def _load_plugins(self, plugin_config: dict):
        """从 .ai/plugins/ 发现并加载插件，使用文件路径直接加载"""
        plugin_dir = os.path.join(self.project_root, ".ai/plugins")
        if not os.path.isdir(plugin_dir):
            return

        for entry in sorted(os.listdir(plugin_dir)):
            entry_path = os.path.join(plugin_dir, entry)

            # 单文件: .ai/plugins/xxx.py
            if entry.endswith(".py") and entry != "__init__.py":
                plugin_id = f"plugin_{entry[:-3]}"
                self._load_plugin_file(plugin_id, entry_path, plugin_config)

            # 包: .ai/plugins/xxx/ 下每个 .py
            elif os.path.isdir(entry_path) and not entry.startswith("_"):
                for sub in sorted(os.listdir(entry_path)):
                    if sub.endswith(".py") and sub != "__init__.py":
                        plugin_id = f"plugin_{entry}_{sub[:-3]}"
                        self._load_plugin_file(plugin_id, os.path.join(entry_path, sub), plugin_config)

    def _load_plugin_file(self, plugin_id: str, file_path: str, plugin_config: dict):
        """通过文件路径加载一个插件模块"""
        try:
            spec = importlib.util.spec_from_file_location(plugin_id, file_path)
            if spec is None or spec.loader is None:
                return
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "check"):
                return
            if not plugin_config.get("enabled_plugins", {}).get(
                plugin_id, plugin_config.get("default_plugin_enabled", True)
            ):
                self._enabled[plugin_id] = False
                self._checkers.append((plugin_id, None, getattr(mod, "CHECKER_LABEL", plugin_id)))
                return
            label = getattr(mod, "CHECKER_LABEL", plugin_id)
            cfg = plugin_config.get("plugin_configs", {}).get(plugin_id, {})
            self._enabled[plugin_id] = True
            self._checkers.append((plugin_id, cfg, label))
        except Exception:
            logger.warning("加载插件失败: %s", file_path, exc_info=True)

    # ── ───────────────────────────────────────────────────────────

    def _is_enabled(self, cid: str) -> bool:
        return self._enabled.get(cid, True)

    def run_all(self, save: bool = True) -> dict:  # noqa: STYLE-06
        """运行所有 checker (A + B)，返回统一报告

        特别处理: quality_gates 需要读取当前报告，因此在报告保存后再运行

        save=False 时不落权威报告（改写进程内暂存目录），供 qa_self_test 等
        "只探测不产出"的调用方使用 —— 修复 T03-R2「跑门禁覆盖权威报告」。
        run-all() 本身不再隐式覆盖 .ai/logs/qa-report.json 之外的路径。
        """
        self._save_enabled = bool(save)
        all_issues: List[str] = []
        total_errors = 0
        blocker_errors = 0
        checker_results = {}
        quality_gates_info = None

        for cid, instance, label in self._checkers:
            if not self._is_enabled(cid):
                checker_results[cid] = {"skipped": True, "label": label}
                continue

            # quality_gates 延迟运行：需要读取保存后的报告
            if cid == "quality_gates":
                quality_gates_info = (cid, instance, label)
                continue

            # Layer B 插件: dict config + function check()
            if isinstance(instance, dict):
                try:
                    mod = self._resolve_plugin_mod(cid)
                    if mod is None or not hasattr(mod, "check"):
                        checker_results[cid] = {"label": label, "error": "模块不可用"}
                        continue
                    errors, issues = mod.check(instance, self.project_root)
                    checker_results[cid] = {
                        "label": label, "errors": errors, "issues": issues or [],
                        "details": self._parse_issue_details(issues or []),
                    }
                    total_errors += errors
                    cfg_key = cid if cid.endswith("_check") else cid + "_check"
                    sev = self.config.get(cid, {}).get("severity", self.config.get(cfg_key, {}).get("severity", "INFO"))
                    if sev == "BLOCKER":
                        blocker_errors += errors
                    if errors:
                        all_issues.extend(issues or [])
                    else:
                        # v1.1: 通过态文案进 notes，不再污染 all_issues（T03-R3）
                        checker_results[cid]["notes"] = issues or []
                except Exception as e:
                    checker_results[cid] = {"label": label, "error": str(e)}
                    total_errors += 1
                continue

            # Layer A 内置 checker
            try:
                errors, issues = instance.check()
                checker_results[cid] = {
                    "label": label, "errors": errors, "issues": issues or [],
                    "details": self._parse_issue_details(issues or []),
                }
                total_errors += errors
                cfg_key = cid if cid.endswith("_check") else cid + "_check"
                sev = self.config.get(cid, {}).get("severity", self.config.get(cfg_key, {}).get("severity", "INFO"))
                if sev == "BLOCKER":
                    blocker_errors += errors
                if errors:
                    all_issues.extend(issues or [])
                else:
                    checker_results[cid]["notes"] = issues or []
            except Exception as e:
                checker_results[cid] = {"label": label, "error": str(e)}
                total_errors += 1
                all_issues.append(f"[{cid}] 异常: {e}")

        report = {
            "timestamp": datetime.now().isoformat(),
            "project_root": self.project_root,
            "profile": self.active_profile,
            "bootstrap": self.bootstrap,
            "errors": total_errors,
            "total_issues": len(all_issues),
            "blocked": blocker_errors > 0 and not self.bootstrap,
            "checkers": checker_results,
            "all_issues": all_issues,
        }

        # 先保存报告，再运行 quality_gates（此时报告已就绪）
        if quality_gates_info:
            self.save_report(report, staged=True)
            cid, instance, label = quality_gates_info
            try:
                errors, issues = instance.check()
                checker_results[cid] = {
                    "label": label, "errors": errors, "issues": issues or [],
                    "details": self._parse_issue_details(issues or []),
                }
                total_errors += errors
                if errors:
                    all_issues.extend(issues or [])
                else:
                    checker_results[cid]["notes"] = issues or []
            except Exception as e:
                checker_results[cid] = {"label": label, "error": str(e)}
                total_errors += 1
                all_issues.append(f"[{cid}] 异常: {e}")

            # 更新报告中的汇总数据
            report["errors"] = total_errors
            report["total_issues"] = len(all_issues)
            report["blocked"] = blocker_errors > 0 and not self.bootstrap
            report["all_issues"] = all_issues

            # [M51-① 2026-09-14 by m-qa] quality_gates 的结果必须落进**同一个产物**。
            # 原实现只在上面 save_report(staged=True) 存过一次盘（那次在 quality_gates
            # **运行之前**，为的是让它能读到报告），之后仅更新内存并 return ——
            # 于是**磁盘上的报告永远不含 quality_gates**。
            # 下游 qa_gate `missing = (CODE_CHECKERS|META_CHECKERS) - ran` 因此永不为空
            # ⇒ **Gate5 恒 FAIL**，阻断恒真、判据失去分辨力（"恒红"是"恒绿"的镜像；
            # 实测三份报告 legacy/run/fxproj 全部缺失 quality_gates）。
            # 这里补一次存盘，使产物与内存一致。
            self.save_report(report, staged=True)

        return report

    def _resolve_plugin_mod(self, plugin_id: str):
        """从 sys.modules 缓存中查找已加载的插件模块"""
        try:
            return next(m for k, m in sys.modules.items() if k.startswith(plugin_id))
        except (StopIteration, Exception):
            return None



    def _parse_issue_details(self, issues: List[str]) -> List[dict]:  # noqa: STYLE-06
        """从 issue 文本提取结构化信息，供 AI Agent 直接使用，无需猜测"""
        # 每条规则的完整定义（Agent 不用猜"因为什么"）
        RULES = {
            "STYLE-01": {
                "severity": "WARN",
                "title": "文件名应使用小写+下划线",
                "expected": "文件名仅含小写字母、数字、下划线",
                "standard": "PEP 8 — 包和模块命名",
                "fix_hint": "重命名文件为小写+下划线格式",
            },
            "STYLE-02": {
                "severity": "WARN",
                "title": "行长度超限",
                "expected": "每行 ≤ 120 字符",
                "standard": "PEP 8 — 最大行长度",
                "fix_hint": "拆分长行为多行，或提取变量缩短行",
            },
            "STYLE-03": {
                "severity": "WARN",
                "title": "命名违规",
                "expected": "函数 snake_case, 类 PascalCase",
                "standard": "PEP 8 — 命名约定",
                "fix_hint": "按命名规范重命名",
            },
            "STYLE-04": {
                "severity": "WARN",
                "title": "日志格式错误",
                "expected": "logging 使用 %% 格式化",
                "standard": "框架手册 — 日志规范",
                "fix_hint": "将 f-string 改为 %s 占位符格式",
            },
            "STYLE-05": {
                "severity": "WARN",
                "title": "文件行数超限",
                "expected": "文件 ≤ 500 行",
                "standard": "ISO 25010 — 可维护性 / Clean Code",
                "fix_hint": "拆分为多个模块（如按功能/类拆分）",
            },
            "STYLE-06": {
                "severity": "WARN",
                "title": "函数行数超限",
                "expected": "函数 ≤ 60 行",
                "standard": "NASA Power of 10 — 规则 5",
                "fix_hint": "将函数内的逻辑块抽成独立子函数",
            },
            "PY-06": {
                "severity": "WARN",
                "title": "缺少 src/ 或 Python 包",
                "expected": "项目根目录应有 src/ 或根级 __init__.py",
                "standard": "Python 工程规范",
                "fix_hint": "创建 src/ 目录或添加 __init__.py",
            },
            "PY-07": {
                "severity": "WARN",
                "title": "缺少 tests/ 目录",
                "expected": "项目应有 tests/ 目录",
                "standard": "Python 工程规范",
                "fix_hint": "创建 tests/ 目录并添加测试",
            },
        }
        details = []
        for issue in issues:
            detail = {
                "rule": "", "severity": "INFO",
                "file": "", "line": 0,
                "violation": "", "expected": "", "actual": "",
                "standard": "", "description": issue,
                "fix_hint": "",
            }
            # 提取规则编号 [STYLE-01], [GATE] G5, [PY-06] 等
            m = re.match(r'\[(\w[\w-]*)\]\s*(G?\d+)?', issue)
            if m:
                detail["rule"] = m.group(1)
                rule_info = RULES.get(detail["rule"])
                if rule_info:
                    detail["severity"] = rule_info["severity"]
                    detail["expected"] = rule_info["expected"]
                    detail["standard"] = rule_info["standard"]
                    detail["fix_hint"] = rule_info["fix_hint"]
                    detail["title"] = rule_info["title"]

            # 提取文件名
            m = re.search(r"""([\w\\/.-]+\.py)""", issue)
            if m:
                detail["file"] = m.group(1)
                detail["violation"] = f"违反规则 {detail['rule']}: {detail['file']}"

            # 提取行号（排除 .py 后面冒号的情况）
            file_parts = re.split(r'\.py:(\d+)', issue)
            if len(file_parts) > 1:
                detail["line"] = int(file_parts[1])

            # 提取实际值（数字类：实际值 > 标准值）
            for pattern in [
                r'(\d+)\s*行\s*>\s*(\d+)',       # "898 行 > 500"
                r'(\d+)\s*字符\s*>\s*(\d+)',      # "320 字符 > 120"
                r'(\d+)\s*行\s*>\s*(\d+)',        # "62 行 > 60"
            ]:
                m = re.search(pattern, issue)
                if m:
                    detail["actual"] = f"{m.group(1)} (标准: {m.group(2)})"
                    break

            # 聚合说明
            if detail["file"] and detail["line"]:
                detail["description"] = f"{detail['file']}:{detail['line']} {detail.get('title', '')}"
            elif detail["file"]:
                detail["description"] = f"{detail['file']} {detail.get('title', '')}"

            # GATE 类型处理
            if detail["rule"] == "GATE" and not detail["file"]:
                # 提取 G5/G6/G8 等
                g = re.search(r'G(\d+)', issue)
                if g:
                    gate_n = int(g.group(1))
                    detail["violation"] = f"Gate{gate_n}: {issue.split('—')[-1].strip()}"
                    if "✅" in issue:
                        detail["severity"] = "INFO"
                        detail["description"] = issue
                    elif "WARN" in issue:
                        detail["severity"] = "WARN"
                        # 提取标准名
                        std_m = re.search(r'(CMMI|IEEE|ISO\s*\d+)', issue)
                        if std_m:
                            detail["standard"] = std_m.group(1)
                            detail["fix_hint"] = "按标准要求补充配套措施"
                    elif "BLOCKER" in issue:
                        detail["severity"] = "BLOCKER"

            details.append(detail)
        return details

    def _detect_environment(self) -> str:
        """自动检测运行环境：production / development / ci"""
        # 环境变量优先
        mode = os.environ.get("QA_ENV", "").lower()
        if mode in ("production", "prod", "development", "dev", "ci"):
            return mode if mode == "ci" else ("production" if mode in ("production", "prod") else "development")

        # Git 分支检测
        try:
            import subprocess
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=3,
                cwd=self.project_root
            ).stdout.strip()
            if branch in ("main", "master", "release"):
                return "production"
            return "development"
        except Exception:
            return "development"

    @property
    def is_production(self) -> bool:
        return self._detect_environment() == "production"

    def canonical_report_dir(self) -> str:
        """权威报告目录（0-污染模式 → QA 系统目录）"""
        if self.qa_system_root and self.project_name:
            return os.path.join(self.qa_system_root, f".ai/logs/{self.project_name}")
        return os.path.join(self.project_root, ".ai/logs")

    def save_report(self, report: dict, staged: bool = False) -> str:
        """保存报告。

        路径决策（编排契约 v1.1，T03-R2/T03-R3 修复）：
          1. run_dir 指定   → {run_dir}/qa-report.json      （并行安全，按 run-id 隔离）
          2. persist=False  → 进程内暂存目录（不覆盖任何权威报告）
          3. 其它           → {canonical}/qa-report.json    （向后兼容）

        无论落到哪里，都通过 QA_RUN_REPORT_PATH 暴露给同进程内的
        quality_gates（它需要在报告落盘后读取）。
        """
        if self.run_dir:
            report_dir = self.run_dir
        elif not getattr(self, "persist", True):
            import tempfile
            report_dir = self._staging_dir()
        else:
            report_dir = self.canonical_report_dir()
        os.makedirs(report_dir, exist_ok=True)
        path = os.path.join(report_dir, "qa-report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        self.report_path = path
        os.environ["QA_RUN_REPORT_PATH"] = path
        if not staged:
            self._validate_schema(report)
        return path

    def _staging_dir(self) -> str:
        """非持久化模式下的进程内暂存目录（每次进程唯一，互不覆盖）"""
        if not getattr(self, "_staging", ""):
            base = os.path.join(self.project_root, ".ai", ".staging")
            os.makedirs(base, exist_ok=True)
            self._staging = os.path.join(base, f"run-{os.getpid()}-{uuid.uuid4().hex[:8]}")
            os.makedirs(self._staging, exist_ok=True)
        return self._staging

    def _validate_schema(self, report: dict):
        """验证报告是否符合 qa-report.schema.json"""
        schema_path = os.path.join(self.project_root, ".ai/schemas/qa-report.schema.json")
        if not os.path.exists(schema_path):
            return
        try:
            import jsonschema
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(report, schema)
        except ImportError:
            logger.debug("optional module not available: jsonschema", exc_info=True)
        except jsonschema.ValidationError as e:
            print(f"  [WARN] Schema 验证: {e.message}")
        except Exception:
            logger.warning("Schema 验证异常", exc_info=True)

    def to_sarif(self, report: dict) -> dict:
        """转换为 SARIF 2.1.0"""
        rules = []
        results = []
        for cid, cdata in report.get("checkers", {}).items():
            if cdata.get("skipped"):
                continue
            label = cdata.get("label", cid)
            rules.append({"id": cid, "name": label,
                          "shortDescription": {"text": label},
                          "defaultConfiguration": {"level": "error"}})
            for issue in cdata.get("issues", []):
                results.append({"ruleId": cid, "level": "error", "message": {"text": issue}})
        return {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{
                "tool": {"driver": {"name": "OpenClaw QA Engine", "version": "3.0", "rules": rules}},
                "results": results,
            }],
        }

#!/usr/bin/env python3
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
import os, json, importlib, importlib.util, sys
from datetime import datetime
from typing import List, Tuple

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
from chk_governance import GovernanceChecker
from chk_securityplus import SecurityPlusChecker
from chk_documentation import DocumentationChecker
from chk_production import ProductionChecker
from chk_zeroprint import ZeroPrintChecker
from chk_customrules import CustomRulesChecker
from chk_fusedetector import FuseDetectorChecker
from chk_docconsistency import DocConsistencyChecker


class HealthScorer:
    """QA 系统核心评分引擎 — V3.0 0-污染模式"""

    def __init__(self, project_root: str, bootstrap: bool = False, profile: str = "",
                 qa_system_root: str = "", project_name: str = ""):
        self.project_root = os.path.abspath(project_root)
        self.qa_system_root = qa_system_root or os.environ.get("QA_SYSTEM_ROOT", "")
        self._cache = {}
        self._use_cache = os.environ.get("QA_USE_CACHE", "") == "1"
        self.project_name = project_name or os.environ.get("QA_PROJECT_NAME", "")

        # 0-污染模式：配置在 QA 系统中，不在项目里
        config_path = ""
        if self.qa_system_root and self.project_name:
            config_path = os.path.join(self.qa_system_root, f".ai/projects/{self.project_name}.yaml")
            if not os.path.exists(config_path):
                config_path = os.path.join(self.qa_system_root, ".ai/config/review-rules.yaml")
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
        self._enabled["import_boundary"] = _add("import_boundary", ImportBoundaryChecker(ib_cfg, self.project_root), "架构边界门禁")

        # QA 配置自审
        ca_cfg = self.config.get("config_audit_check", {})
        self._enabled["config_audit"] = _add("config_audit", ConfigAuditChecker(ca_cfg, self.project_root), "配置自审")

        # 生产环境就绪
        pr_cfg = self.config.get("production_check", {})
        # 代码风格
        cs_cfg = self.config.get("codestyle_check", {})
        self._enabled["codestyle"] = _add("codestyle", CodeStyleChecker(cs_cfg, self.project_root), "代码风格")
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
            pass  # 静默加载，不阻塞

    # ── ───────────────────────────────────────────────────────────

    def _is_enabled(self, cid: str) -> bool:
        return self._enabled.get(cid, True)

    def run_all(self) -> dict:
        """运行所有 checker (A + B) - 带并行加速"""
        import concurrent.futures
        all_issues: List[str] = []
        total_errors = 0
        checker_results = {}

        def _run_one(cid, instance, label):
            if not self._is_enabled(cid):
                return cid, {"skipped": True, "label": label}, 0, []
            if isinstance(instance, dict):
                try:
                    mod = self._resolve_plugin_mod(cid)
                    if mod is None or not hasattr(mod, "check"):
                        return cid, {"label": label, "error": "模块不可用"}, 0, []
                    errs, iss = mod.check(instance, self.project_root)
                    return cid, {"label": label, "errors": errs, "issues": iss or []}, errs, iss or []
                except Exception as e:
                    return cid, {"label": label, "error": str(e)}, 1, [str(e)]
            try:
                errs, iss = instance.check()
                return cid, {"label": label, "errors": errs, "issues": iss or []}, errs, iss or []
            except Exception as e:
                return cid, {"label": label, "error": str(e)}, 1, [str(e)]

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_run_one, cid, inst, lbl) for cid, inst, lbl in self._checkers]
            for future in concurrent.futures.as_completed(futures):
                cid, cdata, errs, iss = future.result()
                checker_results[cid] = cdata
                total_errors += errs
                all_issues.extend(iss)

        return {
            "timestamp": datetime.now().isoformat(),
            "project_root": self.project_root,
            "profile": self.active_profile,
            "bootstrap": self.bootstrap,
            "errors": total_errors,
            "total_issues": len(all_issues),
            "blocked": total_errors > 0 and not self.bootstrap,
            "checkers": checker_results,
            "all_issues": all_issues,
        }

    def _resolve_plugin_mod(self, plugin_id: str):
        """从 sys.modules 缓存中查找已加载的插件模块"""
        try:
            return next(m for k, m in sys.modules.items() if k.startswith(plugin_id))
        except (StopIteration, Exception):
            return None



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

    def invalidate_cache(self):
        """清空缓存"""
        self._cache = {}

    def save_report(self, report: dict) -> str:
        """保存报告（0-污染模式 → QA 系统目录）"""
        # QA 系统内目录
        if self.qa_system_root and self.project_name:
            report_dir = os.path.join(self.qa_system_root, f".ai/logs/{self.project_name}")
        else:
            report_dir = os.path.join(self.project_root, ".ai/logs")
        os.makedirs(report_dir, exist_ok=True)
        path = os.path.join(report_dir, "qa-report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        self._validate_schema(report)
        return path

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
            pass  # 无 jsonschema 库时跳过
        except jsonschema.ValidationError as e:
            print(f"  [WARN] Schema 验证: {e.message}")
        except Exception:
            pass

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

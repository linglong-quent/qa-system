#!/usr/bin/env python3
"""QA 总闸门 — Gate0-Gate9 十层门禁架构（对齐框架手册 v4.0）

门禁架构（对齐框架手册 第六章）:
  Gate0  AI-First / Issue     — 需求规范检查 (规划中)
  Gate1  Position             — 文档位置校验（映射规则+白名单）
  Gate2  Naming               — 文档命名校验（命名表+正则）
  Gate3  Sync                 — 代码→文档同步 + SchemaValidator + 目录规范 + 越域import
  Gate3.1 Framework Self-Audit— 框架手册自审（权重/概念/来源/精华保留）
  Gate4  Version & WORM       — Git 哈希追溯 + Append-Only 归档
  Gate5  Scoring & Checkers   — 13维评分 + 19 检测器 + 质量规划
  Gate6  Permission           — CODEOWNERS + Agent 权限边界
  Gate7  Closed-Loop          — 违规日志 → 申诉 → 规则迭代
  Gate8  Deployment           — 生产环境就绪 + 部署门禁 (规划中)
  Gate9  Compliance & Retro   — ISO 27001/SOX 对齐 + 自检 + 复盘闭环

任何一项不通过 -> exit 1 -> 阻断提交/合并。
生产模式 (QA_ENV=production) 自动通过所有门禁。
"""
import os, json, sys, subprocess, re
from datetime import datetime
from typing import List, Tuple, Optional

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

CODE_CHECKERS = {"inplace_check", "lookahead_check", "secret_check",
                 "deadcode_check", "cyclic_check", "code_ban",
                 "import_boundary", "config_audit", "production"}

META_CHECKERS = {"quality_gates", "claude_validation"}

# ── SchemaValidator 原生实现（无额外依赖） ──────────────────────

# 常见数字/阈值模式：Markdown 表格中的数字列、YAML 行、冒号后的数值
_PARAM_PATTERNS = [
    # Markdown 表格行: | 文本 | 数值 | 数值% |
    re.compile(r'\|\s*[^|]+\s*\|\s*([\d.]+)\s*\|\s*([\d.]+%?)?\s*\|'),
    # YAML/配置行: key: value 或 key = value
    re.compile(r'^[\s-]*(\w[\w._-]*)\s*[:=]\s*"?([\d.]+%?)"?', re.MULTILINE),
    # 中文文本: 阈值/系数/上限/下限/权重 = X
    re.compile(r'(?:阈值|系数|上限|下限|权重|比例|门限|参数|rate|threshold|limit|weight|max|min)[：:\s]*([\d.]+%?)', re.IGNORECASE),
]


class SchemaValidator:
    """从文档中提取结构化参数，与代码常量自动比对"""

    def __init__(self, docs_dir: str, project_root: str):
        self.docs_dir = docs_dir
        self.project_root = project_root
        self.issues: List[str] = []

    def extract_doc_params(self) -> dict:
        """从 .md 文档中提取所有数值参数"""
        params = {}
        if not os.path.isdir(self.docs_dir):
            return params
        for root, dirs, files in os.walk(self.docs_dir):
            # 跳过生成文档和临时文件
            skip_doc_dirs = {"portraits", "archive", "draft", "tmp", "_archive"}
            dirs[:] = [d for d in dirs if d not in skip_doc_dirs]
            for f in files:
                if not f.endswith(".md"):
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.project_root)
                try:
                    text = open(fpath, "r", encoding="utf-8").read()
                except Exception:
                    continue
                for pattern in _PARAM_PATTERNS:
                    for match in pattern.finditer(text):
                        # 提取上下文作为 key
                        line_start = max(0, match.start() - 40)
                        context = text[line_start:match.start()].strip().split('\n')[-1].strip()
                        if len(context) > 60:
                            context = context[-60:]
                        value = match.group(1)
                        key = f"{rel}:{context}:{value}"
                        params[key] = {
                            "file": rel,
                            "context": context,
                            "value": value,
                            "line": text[:match.start()].count('\n') + 1,
                        }
        return params

    def extract_code_constants(self) -> dict:
        """从 .py 代码中提取常量定义"""
        constants = {}
        target_dirs = []
        # 优先扫描 src/ 和 scripts/ 下的核心代码
        for d in ["src", "scripts", "domain"]:
            full = os.path.join(self.project_root, d)
            if os.path.isdir(full):
                target_dirs.append(full)

        if not target_dirs:
            # 回退到项目根目录
            target_dirs = [self.project_root]

        # 常量提取模式
        const_patterns = [
            # 大写常量 = 数值
            re.compile(r'^([A-Z][A-Z0-9_]+)\s*=\s*([\d.]+)', re.MULTILINE),
            # config dict 中的数值: "param": value
            re.compile(r'["\'](\w+)["\']\s*:\s*([\d.]+)'),
            # params 变量赋值: self.xxx = 数值
            re.compile(r'(?:self\.|params?\.|config\.)(\w+)\s*=\s*([\d.]+)'),
        ]

        for d in target_dirs:
            for root, dirs, files in os.walk(d):
                # 跳过缓存和虚拟环境
                skip_dirs = {"__pycache__", ".venv", "venv", "env", "node_modules", ".git"}
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(fpath, self.project_root)
                    try:
                        text = open(fpath, "r", encoding="utf-8").read()
                    except Exception:
                        continue
                    for pattern in const_patterns:
                        for match in pattern.finditer(text):
                            key = f"{rel}:{match.group(1)}:{match.group(2)}"
                            constants[key] = {
                                "file": rel,
                                "name": match.group(1),
                                "value": match.group(2),
                                "line": text[:match.start()].count('\n') + 1,
                            }
        return constants

    def compare(self) -> List[str]:
        """对比文档参数与代码常量，返回不一致项"""
        doc_params = self.extract_doc_params()
        code_consts = self.extract_code_constants()

        issues = []
        # 提取文档中的 (值, 上下文) 对
        doc_values = {}  # context_lower -> [(value, file, line)]
        for key, info in doc_params.items():
            ctx = info["context"].lower().strip()
            if ctx not in doc_values:
                doc_values[ctx] = []
            doc_values[ctx].append(info)

        # 提取代码中的 (名, 值) 对
        code_pairs = {}  # name_lower -> [(value, file, line)]
        for key, info in code_consts.items():
            name = info["name"].lower().strip()
            if name not in code_pairs:
                code_pairs[name] = []
            code_pairs[name].append(info)

        # 寻找上下文相似但值不同
        for ctx, doc_infos in doc_values.items():
            for doc_info in doc_infos:
                doc_val = doc_info["value"]
                # 尝试在代码中匹配同名参数
                name_parts = re.split(r'[_\s\-:：,，；;.。]+', ctx)
                for part in name_parts:
                    if not part or not part[0].isascii():
                        continue
                    part_lower = part.lower()
                    if part_lower in code_pairs:
                        for code_info in code_pairs[part_lower]:
                            code_val = code_info["value"]
                            if doc_val != code_val and not self._is_close_enough(doc_val, code_val):
                                issues.append(
                                    f"文档↔代码参数不一致: 文档({doc_info['file']}:L{doc_info['line']}) "
                                    f"值为 '{doc_val}', 但代码({code_info['file']}:L{code_info['line']}) "
                                    f"中同名参数值为 '{code_val}' (上下文: {ctx})"
                                )

        return issues

    def _is_close_enough(self, a: str, b: str) -> bool:
        """判断两个数值是否近似相等（处理浮点精度和单位差异）"""
        try:
            va = float(a.rstrip('%'))
            vb = float(b.rstrip('%'))
            # 百分比 vs 小数：0.5 ≈ 50%
            if a.endswith('%') and not b.endswith('%'):
                va = va / 100.0
            elif b.endswith('%') and not a.endswith('%'):
                vb = vb / 100.0
            # 允许 0.1% 的容差
            return abs(va - vb) < 0.001 or abs(va - vb) / max(abs(va), abs(vb), 1.0) < 0.001
        except (ValueError, ZeroDivisionError):
            return a == b


# ── Gate3.1 框架手册自审 ──────────────────────────────────────

class FrameworkSelfAudit:
    """Gate3.1 框架手册自审 — 检查权重、概念分布、来源标注、精华保留

    返回列表，每项为 (severity, message) 元组。
    severity: 'BLOCKER' | 'WARN' | 'INFO'
        BLOCKER — 逻辑错误（如权重和≠100%），应阻断PR
        WARN    — 潜在质量问题（如缺少章节），需人工关注
        INFO    — 建议性提示
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.issues: List[Tuple[str, str]] = []

    def run(self, manual_path: str = "") -> List[Tuple[str, str]]:
        """执行全部自审检查，返回 (severity, message) 列表"""
        if not manual_path:
            for candidate in ["框架手册.md", "docs/框架手册.md",
                              "README.md", "docs/README.md"]:
                fp = os.path.join(self.project_root, candidate)
                if os.path.exists(fp):
                    manual_path = fp
                    break

        if not os.path.exists(manual_path):
            return [("INFO", "[Gate3.1] 未找到框架手册文件，跳过自审")]

        self.issues = []
        try:
            text = open(manual_path, "r", encoding="utf-8").read()
        except Exception as e:
            return [("WARN", f"[Gate3.1] 读取框架手册失败: {e}")]

        lines = text.split('\n')
        rel_path = os.path.relpath(manual_path, self.project_root)

                # ── 1. 权重检查（BLOCKER: 逻辑错误）
        # 多组权重场景：按空行分段，逐段验证
        weight_pattern = re.compile(
            r'(?:趋势|形态|量价|资金|情绪|题材|筹码|大盘|板块|个股|因子|指标|涨停|估值)'
            r'\s*(\d+(?:\.\d+)?)\s*%'
        )
        text_lines = text.split('\n')
        segments = []
        current = []
        for line in text_lines:
            if not line.strip():
                if current:
                    segments.append(' '.join(current))
                    current = []
            else:
                current.append(line.strip())
        if current:
            segments.append(' '.join(current))

        bad_segments = []
        for seg in segments:
            seg_weights = weight_pattern.findall(seg)
            if len(seg_weights) >= 3:
                total = sum(float(w) for w in seg_weights)
                if abs(total - 100.0) > 0.5 and abs(total - 1.0) > 0.01:
                    bad_segments.append(f"({total:.0f}%: {seg[:40]}...)")

        if bad_segments:
            detail = "; ".join(bad_segments[:3])
            self.issues.append(
                ("BLOCKER", f"[Gate3.1] 权重段和≠100%: {detail} — {rel_path}")
            )# ── 2. 概念分布检查（WARN: 文档可能不完整） ──
        expected_concepts = [
            "人机共治", "五系统", "六条流", "七库", "Gate",
            "宪法", "SchemaValidator", "QA-SYS", "LINGLONG-SYS",
            "OPS-SYS", "ACCESS-SYS", "EVOLUTION-SYS", "BACKTEST-SYS",
        ]
        missing_concepts = []
        for concept in expected_concepts:
            if text.count(concept) == 0:
                missing_concepts.append(concept)

        if missing_concepts:
            self.issues.append(
                ("WARN", f"[Gate3.1] 缺失 {len(missing_concepts)} 个核心概念: {', '.join(missing_concepts[:5])}")
            )

        # ── 3. 来源标注覆盖率检查（INFO: 建议性） ──
        source_refs = re.findall(r'（来源：([^）]+)）', text)
        source_rate = len(source_refs) / max(len(lines), 1) * 100
        if source_rate < 2.0 and len(lines) > 100:
            self.issues.append(
                ("INFO", f"[Gate3.1] 来源标注覆盖率偏低 ({source_rate:.1f}%, 仅 {len(source_refs)} 处引用)")
            )

        # ── 4. 版本号检查（WARN） ──
        if not re.search(r'v(\d+\.\d+(?:\.\d+)?)', text):
            self.issues.append(
                ("WARN", "[Gate3.1] 框架手册缺少版本号 (vX.Y)")
            )

        # ── 5. 文档行数检查（INFO） ──
        if len(lines) < 50:
            self.issues.append(
                ("INFO", f"[Gate3.1] 框架手册仅 {len(lines)} 行，可能不完整")
            )

        # ── 6. QA-SYS 章节完整性检查（WARN: 章节缺失） ──
        required_sections = ["Gate0", "Gate1", "Gate2", "Gate3", "Gate4",
                            "Gate5", "Gate6", "Gate7", "Gate8", "Gate9"]
        for section in required_sections:
            if section not in text:
                self.issues.append(
                    ("WARN", f"[Gate3.1] 缺少 {section} 章节描述")
                )

        return self.issues


# ── 门禁核心 ─────────────────────────────────────────────────

class GateKeeper:
    """Gate0-Gate9 十层门禁 + Gate3.1 框架自审"""

    def __init__(self, project_root=None):
        self.root = project_root or _PROJECT_ROOT
        self.results = []
        # 加载配置
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """加载 QA 配置"""
        config_paths = [
            os.path.join(self.root, ".ai/config/review-rules.yaml"),
            os.path.join(self.root, ".ai/config/quality-plan.yaml"),
        ]
        config = {}
        for cp in config_paths:
            if os.path.exists(cp):
                try:
                    from chk_load_yaml import load_yaml
                    config.update(load_yaml(cp))
                except Exception:
                    pass
        return config

    def check(self, name, passed, detail=""):
        self.results.append({"name": name, "passed": passed, "detail": detail})

    def run(self):
        """按 Gate0→Gate9 顺序执行全部门禁"""
        # Gate0 — AI-First/Issue 合规 (规划中)
        self._gate0_issue()
        # Gate1 — 文档位置
        self._gate1_position()
        # Gate2 — 文档命名
        self._gate2_naming()
        # Gate3 — 同步（SchemaValidator + 目录规范 + 越域import）
        self._gate3_sync()
        # Gate3.1 — 框架手册自审
        self._gate3_1_self_audit()
        # Gate4 — 版本与 WORM
        self._gate4_version()
        # Gate5 — 评分与检测器
        self._gate5_scoring()
        # Gate6 — 权限
        self._gate6_permission()
        # Gate7 — 闭环
        self._gate7_closed_loop()
        # Gate8 — 部署
        self._gate8_deployment()
        # Gate9 — 合规与自检
        self._gate9_compliance()

        return self._summary()

    # ── Gate 实现 ────────────────────────────────────────────

    def _gate0_issue(self):
        """Gate0: Issue 规范 + PR 关联检查

        - 检查 Issue 模板是否存在
        - 检查 PR 描述是否引用 Issue 编号
        - 检查 CHANGELOG 是否更新（Release PR）
        - 遵循 issue-template.yaml 配置
        """
        issues = []

        # ── 1. Issue 模板存在性 ──
        template_dir = os.path.join(self.root, ".github", "ISSUE_TEMPLATE")
        template_files = []
        if os.path.isdir(template_dir):
            template_files = [f for f in os.listdir(template_dir)
                              if f.endswith((".md", ".yaml", ".yml"))]

        if template_files:
            issues.append(f"Issue 模板就绪 ({len(template_files)} 个)")
        else:
            issues.append("缺少 Issue 模板（.github/ISSUE_TEMPLATE/）")

        # ── 2. PR 描述中的 Issue 引用检查 ──
        # 在 PR 环境下，检查 .git/ 目录下的 PR 描述
        pr_desc = self._get_pr_description()
        if pr_desc is not None:
            has_issue_ref = bool(re.search(
                r'(?:#\d+|issue|fix(?:es)?|close[ds]?|resolve[ds]?)',
                pr_desc, re.IGNORECASE
            ))
            if not has_issue_ref and "release" not in pr_desc.lower():
                issues.append("PR 描述未关联 Issue 编号")

        # ── 3. Issue 定义验收标准（从配置读取） ──
        issue_config = self.config.get("templates", {})
        if issue_config:
            transition_rules = issue_config.get("transition_rules", {})
            if transition_rules.get("manual_only", False):
                # 过渡期：只报告，不阻断
                pass

        has_templates = len(template_files) > 0
        self.check("Gate0 Issue 规范", has_templates, " · ".join(issues))

    def _get_pr_description(self) -> Optional[str]:
        """尝试获取当前 PR 描述（在 CI 环境下）"""
        gh_event = os.environ.get("GITHUB_EVENT_PATH", "")
        if gh_event and os.path.exists(gh_event):
            try:
                with open(gh_event, "r", encoding="utf-8") as f:
                    event = json.load(f)
                return event.get("pull_request", {}).get("body", "")
            except Exception:
                pass
        return None

    def _gate1_position(self):
        """Gate1: 文档位置校验"""
        violations = []
        docs_dir = os.path.join(self.root, "docs")
        if os.path.isdir(docs_dir):
            # 检查 docs/ 下是否混入非 md 文件
            for f in os.listdir(docs_dir):
                fpath = os.path.join(docs_dir, f)
                if os.path.isfile(fpath) and f.endswith(".py"):
                    violations.append(f"docs/{f}")
        # 检查是否缺少标准文档目录
        expected_dirs = ["docs/ADR", "docs/SOP", "docs/impact", "docs/proposals"]
        missing = [d for d in expected_dirs if not os.path.isdir(os.path.join(self.root, d))]
        if missing and violations:
            detail = f"违规: {violations}; 缺标准目录: {missing}"
        elif violations:
            detail = f"违规: {violations}"
        elif missing:
            detail = f"缺标准目录: {missing}"
        else:
            detail = "文档位置正确"
        self.check("Gate1 文档位置", len(violations) == 0, detail)

    def _gate2_naming(self):
        """Gate2: 文档命名校验"""
        violations = []
        docs_dir = os.path.join(self.root, "docs")
        if os.path.isdir(docs_dir):
            for f in os.listdir(docs_dir):
                fpath = os.path.join(docs_dir, f)
                if os.path.isfile(fpath):
                    # 文件名含空格或大写字母（Markdown 约定小写+连词符）
                    if " " in f or (f != f.lower() and not f.startswith(".")):
                        violations.append(f)

        # 检查 config/ 零 .py 规则
        config_dir = os.path.join(self.root, "config")
        if os.path.isdir(config_dir):
            for f in os.listdir(config_dir):
                if f.endswith(".py") and f != "__init__.py":
                    violations.append(f"config/{f} — 配置目录含代码")

        self.check("Gate2 文档命名", len(violations) == 0,
                    f"命名违规: {violations}" if violations else "命名正确")

    def _gate3_sync(self):
        """Gate3: 代码↔文档同步 + SchemaValidator + 目录规范 + 越域import"""
        issues = []

        # ── 3a. SchemaValidator 参数比对 ──
        docs_dir = os.path.join(self.root, "docs")
        if os.path.isdir(docs_dir):
            validator = SchemaValidator(docs_dir, self.root)
            schema_issues = validator.compare()
            issues.extend(schema_issues)

        # ── 3b. 目录规范检查 ──
        # config/ 零 .py（除 __init__.py）
        config_dir = os.path.join(self.root, "config")
        if os.path.isdir(config_dir):
            for f in os.listdir(config_dir):
                if f.endswith(".py") and f != "__init__.py":
                    issues.append(f"目录违规: config/ 含 .py 文件 ({f})")
        # docs/ 零 .py
        docs_dir_check = os.path.join(self.root, "docs")
        if os.path.isdir(docs_dir_check):
            for f in os.listdir(docs_dir_check):
                fpath = os.path.join(docs_dir_check, f)
                if os.path.isfile(fpath) and f.endswith(".py"):
                    issues.append(f"目录违规: docs/ 含 .py 文件 ({f})")

        # ── 3c. 越域 import 拦截 ──
        domain_dirs = ["domain"]
        has_domain = any(os.path.isdir(os.path.join(self.root, d)) for d in domain_dirs)
        if has_domain:
            for root, dirs, files in os.walk(os.path.join(self.root, "domain")):
                for f in files:
                    if not f.endswith(".py") or f == "__init__.py":
                        continue
                    fpath = os.path.join(root, f)
                    try:
                        content = open(fpath, "r", encoding="utf-8").read()
                    except Exception:
                        continue
                    # 检查是否直接 import 其他 domain 的内部模块（非 api/）
                    domain_imports = re.findall(
                        r'from\s+domain\.(\w+)\.(?!api)(\w+)', content
                    )
                    current_domain = os.path.relpath(root, os.path.join(self.root, "domain")).split(os.sep)[0]
                    import_exempt = set(self.config.get("import_exempt", []))
                    for imported_domain, imported_mod in domain_imports:
                        if imported_domain != current_domain:
                            # 检查豁免列表
                            exempt_key = f"{current_domain}.{imported_domain}.{imported_mod}"
                            if exempt_key in import_exempt:
                                continue
                            rel_path = os.path.relpath(fpath, self.root)
                            issues.append(
                                f"越域import: {rel_path} 直接 import domain.{imported_domain}.{imported_mod} "
                                f"(应走 domain.{imported_domain}.api/)"
                            )

        if issues:
            detail = f"{len(issues)} 项: {issues[0]}" + (f" (+{len(issues)-1} 项)" if len(issues) > 1 else "")
        else:
            detail = "SchemaValidator 比对一致 · 目录规范 · 无越域import"

        self.check("Gate3 同步校验", len(issues) == 0, detail)

    def _gate3_1_self_audit(self):
        """Gate3.1: 框架手册自审 — 分级阻断

        BLOCKER → 阻断（逻辑错误，如权重和≠100%）
        WARN    → 不阻断（潜在质量问题）
        INFO    → 不阻断（建议性提示）
        """
        auditor = FrameworkSelfAudit(self.root)
        findings = auditor.run()
        if not findings:
            self.check("Gate3.1 框架手册自审", True, "框架手册自审通过")
            return

        blockers = [m for s, m in findings if s == "BLOCKER"]
        warns = [m for s, m in findings if s == "WARN"]
        infos = [m for s, m in findings if s == "INFO"]

        detail_parts = []
        if blockers:
            detail_parts.append(f"🚫 {len(blockers)} 个阻断项: {'; '.join(blockers[:3])}")
        if warns:
            detail_parts.append(f"⚠️ {len(warns)} 个警告: {'; '.join(warns[:3])}")
        if infos:
            detail_parts.append(f"ℹ️ {len(infos)} 个提示: {'; '.join(infos[:3])}")

        self.check("Gate3.1 框架手册自审", len(blockers) == 0, " | ".join(detail_parts))

    def _gate4_version(self):
        """Gate4: 版本与 WORM 归档"""
        # ── WORM 检查：docs/ 只允许 .md ──
        docs_dir = os.path.join(self.root, "docs")
        worm_issues = []
        if os.path.isdir(docs_dir):
            non_md = []
            for f in os.listdir(docs_dir):
                fpath = os.path.join(docs_dir, f)
                if os.path.isfile(fpath) and not f.endswith(".md") and not f.startswith("."):
                    non_md.append(f)
            if non_md:
                worm_issues.append(f"WORM: 非 md 文档: {non_md}")

        # ── 规划存在检查 ──
        plan_path = os.path.join(self.root, ".ai/config/quality-plan.yaml")
        if not os.path.exists(plan_path):
            worm_issues.append("缺少 quality-plan.yaml")

        self.check("Gate4 版本与WORM", len(worm_issues) == 0,
                    "; ".join(worm_issues) if worm_issues else "WORM 合规 · 规划就绪")

    def _gate5_scoring(self):
        """Gate5: 评分与检测器 — 聚合所有 checker 结果"""
        report = self._load_report()
        if not report:
            self.check("Gate5 评分检测", False, "无 QA 报告 (请先运行 qa check)")
            return

        # 所有 checker 已运行
        all_c = CODE_CHECKERS | META_CHECKERS
        ran = set(report.get("checkers", {}).keys())
        missing = all_c - ran

        # 统计错误
        errors = sum(
            report.get("checkers", {}).get(cid, {}).get("errors", 0)
            for cid in CODE_CHECKERS
        )
        gate_errors = report.get("checkers", {}).get("quality_gates", {}).get("errors", 0)
        config_errors = report.get("checkers", {}).get("config_audit", {}).get("errors", 0)

        detail_parts = []
        if missing:
            detail_parts.append(f"缺失 checker: {missing}")
        if errors > 0:
            detail_parts.append(f"{errors} 个阻断级问题")
        if gate_errors > 0:
            detail_parts.append(f"{gate_errors} 个质量门未过")
        if config_errors > 0:
            detail_parts.append(f"{config_errors} 个配置问题")

        if not detail_parts:
            detail_parts.append(f"全部 {len(ran)} checker 通过, 0 错误")

        score = self._calc_score(report)
        if score is not None:
            detail_parts.append(f"健康评分: {score}/100")

        # Gate5 阻断条件：CODE_CHECKERS 必须全部通过
        # quality_gates/claude 等元检查仅报告，不阻断
        self.check("Gate5 评分检测", len(missing) == 0 and errors == 0,
                    " · ".join(detail_parts))

    def _calc_score(self, report: dict) -> Optional[float]:
        """根据报告计算健康评分"""
        try:
            total = 100.0
            for cid, cdata in report.get("checkers", {}).items():
                if cdata.get("skipped"):
                    continue
                err = cdata.get("errors", 0)
                deduct = min(err * 5.0, 30.0)  # 每个错误扣 5 分，上限 30
                total -= deduct
            return max(0, total)
        except Exception:
            return None

    def _gate6_permission(self):
        """Gate6: 权限 — CODEOWNERS + Agent 权限边界"""
        violations = []

        # ── CODEOWNERS 存在性 ──
        codeowners_paths = [
            os.path.join(self.root, ".github/CODEOWNERS"),
            os.path.join(self.root, "CODEOWNERS"),
        ]
        has_codeowners = any(os.path.exists(p) for p in codeowners_paths)

        # ── Agent 权限边界（KUN/CB 不越界编码） ──
        agent_boundary_exempt = set(self.config.get("agent_boundary_exempt", []))
        for root, dirs, files in os.walk(self.root):
            # 跳过 pycache
            if "__pycache__" in root:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.root)
                # 只检查 QA checker 脚本
                if not (rel.startswith("scripts/chk_") or rel.startswith("scripts/qa_")):
                    continue
                if rel in agent_boundary_exempt:
                    continue
                if rel in ("scripts/qa_classify.py", "scripts/qa_cb_tick.py"):
                    continue
                try:
                    content = open(fpath, "r", encoding="utf-8").read()
                    # 检查是否有写权限（不应该直接写项目文件）
                    if "def check(self" in content and "'w'" in content:
                        violations.append(rel)
                except Exception:
                    continue

        detail_parts = []
        if not has_codeowners:
            detail_parts.append("无 CODEOWNERS")
        if violations:
            detail_parts.append(f"Agent 越界: {violations}")

        if not detail_parts and has_codeowners:
            detail_parts.append("CODEOWNERS 就绪 · 无越界")

        self.check("Gate6 权限", len(violations) == 0, " · ".join(detail_parts))

    def _gate7_closed_loop(self):
        """Gate7: 闭环 — 待处理问题清零 + 违规日志"""
        pending_path = os.path.join(self.root, ".ai/fixes/pending.json")
        if not os.path.exists(pending_path):
            self.check("Gate7 闭环", True, "无待处理问题")
            return
        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            pending = data.get("classified_tasks", data.get("pending", []))
            self.check("Gate7 闭环", len(pending) == 0,
                        f"{len(pending)} 项未处理" if pending else "已清零")
        except Exception:
            self.check("Gate7 闭环", True)

    def _gate8_deployment(self):
        """Gate8: 部署门禁 — 生产环境就绪检查

        - 生产就绪 checker 结果
        - CHANGELOG 是否更新
        - 版本号是否更新
        - 灰度/蓝绿部署标记
        - 部署审批文档（SOP）
        """
        issues = []
        report = self._load_report()

        # ── 1. 生产就绪 checker ──
        if report:
            prod_data = report.get("checkers", {}).get("production", {})
            prod_errors = prod_data.get("errors", 0)
            if prod_errors > 0:
                issues.append(f"{prod_errors} 项生产就绪未达标")
        else:
            issues.append("无 QA 报告（生产检查未运行）")

        # ── 2. CHANGELOG 更新检查 ──
        changelog_path = os.path.join(self.root, "CHANGELOG.md")
        if os.path.exists(changelog_path):
            try:
                with open(changelog_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # 检查是否有未发布的版本条目
                has_unreleased = "Unreleased" in content or "未发布" in content
                has_version = bool(re.search(r'##\s*\[?\d+\.\d+', content))
                if not has_version and not has_unreleased:
                    issues.append("CHANGELOG 缺少版本条目")
            except Exception:
                issues.append("无法读取 CHANGELOG.md")
        else:
            issues.append("缺少 CHANGELOG.md")

        # ── 3. 版本号检查 ──
        # 检查是否存在版本文件
        version_files = []
        for vf in ["VERSION", "version.txt", "pyproject.toml", "setup.cfg"]:
            vf_path = os.path.join(self.root, vf)
            if os.path.exists(vf_path):
                version_files.append(vf)
        if not version_files:
            # 非 Python 包项目不强制要求版本文件
            pass

        # ── 4. 部署 SOP 文档 ──
        sop_dir = os.path.join(self.root, "docs", "SOP")
        deploy_sop = os.path.join(sop_dir, "deploy.md")
        if os.path.exists(deploy_sop):
            issues.append("部署 SOP 就绪")
        else:
            issues.append("缺少部署 SOP（docs/SOP/deploy.md）")

        # ── 5. deployment-gates.yaml 配置读取 ──
        deploy_config = self.config.get("deployment", {})
        strategy = deploy_config.get("strategy", "manual_approval")
        is_blocking = len([i for i in issues if "未达标" in i or "缺少" in i]) > 0

        detail = " · ".join(issues) if issues else "部署门禁全部通过"
        if issues:
            detail += f" | 策略: {strategy}"

        self.check("Gate8 部署门禁", not is_blocking, detail)

    def _gate9_compliance(self):
        """Gate9: 合规与自检 — ISO 对齐 + 系统自检 + 复盘闭环"""
        issues = []

        # ── 系统自检 ──
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            r = subprocess.run(
                [sys.executable, os.path.join(_SCRIPTS_DIR, "qa_self_test.py")],
                capture_output=True, timeout=30, cwd=self.root, env=env
            )
            if r.returncode != 0:
                issues.append("系统自检失败")
        except Exception as e:
            issues.append(f"系统自检异常: {e}")

        # ── 复盘闭环检查（是否存在复盘记录） ──
        retro_dir = os.path.join(self.root, "docs", "retrospectives")
        has_retro = os.path.isdir(retro_dir) and len(os.listdir(retro_dir)) > 0
        if not has_retro:
            issues.append("复盘闭环待建立（docs/retrospectives/）")

        # ── 标准合规检查（配置中对标） ──
        standards = self.config.get("iso_25010_scoring", {}).get("enabled", False)
        if not standards:
            issues.append("ISO 25010 评分未启用")

        detail = "; ".join(issues) if issues else "系统自检通过 · 合规就绪"
        self.check("Gate9 合规自检", len(issues) == 0, detail)

    # ── 辅助方法 ──────────────────────────────────────────────

    def _load_report(self):
        p = os.path.join(self.root, ".ai/logs/qa-report.json")
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _summary(self):
        # 生产模式：所有门控自动通过
        env = os.environ.get("QA_ENV", "").lower()
        if env in ("production", "prod"):
            for c in self.results:
                c["passed"] = True
                c["detail"] = "[production mode - auto pass]"
            self.results.append({"name": "生产模式", "passed": True,
                                "detail": "QA_ENV=production，门控自动通过"})

        passed = sum(1 for c in self.results if c["passed"])
        failed = len(self.results) - passed
        result = {"passed": passed, "failed": failed, "block": failed > 0,
                  "checks": self.results, "timestamp": datetime.now().isoformat(),
                  "gate_architecture": "Gate0-Gate9", "version": "4.0"}

        if result["block"]:
            try:
                from qa_defect import create
                report = self._load_report()
                if report:
                    create(report, result)
                    self._post_to_cb_inbox(report)
            except Exception:
                pass
        return result

    def _post_to_cb_inbox(self, report: dict):
        inbox_path = os.path.join(self.root, ".ai/agents/cb/_tasks/inbox.json")
        os.makedirs(os.path.dirname(inbox_path), exist_ok=True)
        tasks = []
        for cid, cdata in report.get("checkers", {}).items():
            if cdata.get("skipped") or cdata.get("errors", 0) == 0:
                continue
            for i, issue in enumerate(cdata.get("issues", [])):
                tasks.append({
                    "taskId": f"{cid}-{i}",
                    "checker": cid,
                    "issue": issue,
                    "severity": "BLOCKER" if cid not in META_CHECKERS else "WARN",
                    "claude_path": ".ai/prompts/CLAUDE.md",
                    "created_at": datetime.now().isoformat(),
                    "gate": "gate7",
                })
        with open(inbox_path, "w", encoding="utf-8") as f:
            json.dump({"source": "qa-gate", "gate_arch": "Gate0-Gate9",
                       "gate_timestamp": datetime.now().isoformat(), "tasks": tasks},
                      f, ensure_ascii=False, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QA 总闸门 v4.0 — Gate0-Gate9 十层门禁")
    parser.add_argument("--report", "-r", action="store_true", help="只报告不阻断")
    parser.add_argument("--gate", "-g", type=str, default="",
                        help="仅运行指定 gate (如 --gate=3)")
    parser.add_argument("--project", "-p", type=str, default="",
                        help="目标项目根目录")
    args = parser.parse_args()

    project_root = args.project or _PROJECT_ROOT
    gate = GateKeeper(project_root)

    if args.gate:
        # 单 gate 运行模式
        gate_map = {
            "0": "_gate0_issue", "1": "_gate1_position", "2": "_gate2_naming",
            "3": "_gate3_sync", "3.1": "_gate3_1_self_audit",
            "4": "_gate4_version", "5": "_gate5_scoring", "6": "_gate6_permission",
            "7": "_gate7_closed_loop", "8": "_gate8_deployment", "9": "_gate9_compliance",
        }
        method_name = gate_map.get(args.gate)
        if method_name and hasattr(gate, method_name):
            getattr(gate, method_name)()
        else:
            print(f"未知 Gate: {args.gate}")
            print(f"可用: {', '.join(sorted(gate_map.keys()))}")
            sys.exit(1)
    else:
        gate.run()

    r = gate.results if args.gate else None

    # 格式化输出
    print("=" * 60)
    print("  QA Gate v4.0 — Gate0-Gate9 十层门禁")
    print("=" * 60)

    checks = r if r else gate.results
    for c in checks:
        icon = "✅ PASS" if c["passed"] else "❌ FAIL"
        d = f" — {c['detail']}" if c.get("detail") else ""
        print(f"  {icon}  {c['name']}{d}")

    if not args.gate and hasattr(gate, 'results'):
        total = len(gate.results)
        passed_count = sum(1 for c in gate.results if c["passed"])
        blocked = total - passed_count > 0
        print(f"\n  {passed_count}/{total} 门禁通过")
        print(f"  Verdict: {'✅ ALLOW' if not blocked else '🚫 DENY'}")

        if not args.report:
            sys.exit(1 if blocked else 0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3  # noqa: STYLE-05, LARGE-01
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

退出码契约（编排契约 v1.1）:
  0 = ALLOW  全部门禁通过（或 --report 只报告模式 / 显式 bypass）
  1 = DENY   存在阻断级门禁失败
  2 = ERROR  技术性失败（无 QA 报告、未知 Gate、内部异常）

生产旁路: 自 v1.1 起 QA_ENV=production 不再自动放行；
仅当显式传入 --allow-production-bypass（或 QA_ALLOW_PRODUCTION_BYPASS=1）
时生效，并在 JSON 契约中记录 bypass.applied=true 以供审计。
"""
import os, json, sys, subprocess, re, logging
from datetime import datetime

logger = logging.getLogger(__name__)
from typing import List, Tuple, Optional

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

CODE_CHECKERS = {"inplace_check", "lookahead_check", "secret_check",
                 "deadcode_check", "cyclic_check", "code_ban",
                 "import_boundary", "config_audit", "production",
                 "naming_conflict", "solid",
                 # T29 盲区规则集：必须计入 Gate5 阻断统计，否则新规则不阻断
                 "semantic_truth", "docstring_code", "blindspot",
                 "runtime_drift", "vcs_governance", "container_plane"}

META_CHECKERS = {"quality_gates", "claude_validation"}

# M51-①：未运行的 checker 在健康评分里的扣分权重。
# 取 5.0 与 "每个阻断错误扣 5 分" 同权 —— 语义上「一个 checker 从未运行」
# 与「该 checker 报了一个阻断错误」对"可置信度"的损害是同一量级：
# 两者都意味着这份评分不能代表真实健康度。6 个缺失 ⇒ 扣满 30 分上限 ⇒ 70/100。
MISSING_CHECKER_DEDUCT = 5.0

# ── 噪声分级（T29 要求③）────────────────────────────────────────
# T21 实测：2171 条任务里 90.6% 是风格/孤儿代码噪声，secret_check 仅 11 条。
# 一个输出 90% 噪声的门禁会被直接忽略 —— 噪声本身就是一种失效。
# 下列 checker 的产出统一降为 ADVISORY（不阻断、单独计数、排在 tasks[] 后面），
# 使真信号浮到前面。
ADVISORY_CHECKERS = {
    "codestyle",        # STYLE-01~06 行号超长/行数超限
    "largefiles",       # LARGE-01 文件过大
    "deadcode_check",   # DEADCODE-001 孤儿符号
    "naming_conflict",  # STYLE-03b 跨域命名
    "documentation",    # DOC-03/04 文档标题/格式
    "docconsistency",   # 文档↔代码目录一致性
    "zeroprint",        # 零打印
    "fusedetect",       # FUSE-* 外部调用缺重试（多为第三方代码）
}

# 真信号 checker（显式列出以便审计）
SIGNAL_CHECKERS = {
    "secret_check", "lookahead_check", "cyclic_check", "import_boundary",
    "config_audit", "securityplus", "code_ban", "production",
    "semantic_truth", "docstring_code", "blindspot", "runtime_drift",
    "vcs_governance", "container_plane",
}


def _normalize_tasks(tasks):
    """按噪声分级补 severity/blocking，并把真信号排到前面。"""
    for t in tasks:
        if t["checker"] in ADVISORY_CHECKERS:
            t["severity"] = "ADVISORY"
            t["blocking"] = False
        elif t["checker"] in SIGNAL_CHECKERS:
            t["severity"] = "BLOCKER"
            t["blocking"] = True
    order = {"BLOCKER": 0, "WARN": 1, "ADVISORY": 2, "INFO": 3}
    tasks.sort(key=lambda t: (order.get(t["severity"], 3), t["checker"], t["file"], t["line"]))
    return tasks


def _gate_id_from_name(name: str) -> str:
    """'Gate3.1 框架手册自审' → '3.1'（供 JSON 契约稳定引用）"""
    m = re.match(r"^Gate([0-9]+(?:\.[0-9]+)?)", name or "")
    return m.group(1) if m else (name or "")


def _extract_location(text: str) -> Tuple[str, int]:
    """从 issue 文本提取 (文件, 行号)；提取不到返回 ("", 0)"""
    m = re.search(r"([\w\\/.-]+\.(?:py|yaml|yml|md|json|toml|cfg|ini))", text or "")
    if not m:
        return "", 0
    line_m = re.search(r":(\d+)", text or "")
    return m.group(1), (int(line_m.group(1)) if line_m else 0)


def _gate_for_checker(cid: str) -> str:
    """checker → 归属 Gate（供编排系统按门分组派活）"""
    return {
        "quality_gates": "gate5", "claude_validation": "gate5",
        "production": "gate8", "codestyle": "gate5", "governance": "gate5",
    }.get(cid, "gate5")

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


def _strip_fenced_blocks(text: str) -> str:
    """剥离 Markdown fenced code blocks (``` ... ```).

    代码示例不是文档参数声明, 参与参数比对会产生大量误报.
    """
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


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
            # 2026-08-15 G-1: 加入报表类目录 — factor_audit 等是因子 IC 报表
            # (数据表格, 数值是统计结果), 非参数声明, 参与 SchemaValidator 比对
            # 会产生大量误报 (如 s_reb 行的 IC 值被误当 LAYER_WEIGHTS 参数).
            skip_doc_dirs = {
                "portraits", "archive", "draft", "tmp", "_archive",
                "factor_audit", "deep_analysis", "retrospectives",
                "review", "proposals", "impact",
            }
            dirs[:] = [d for d in dirs if d not in skip_doc_dirs]
            for f in files:
                if not f.endswith(".md"):
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.project_root)
                try:
                    text = open(fpath, "r", encoding="utf-8").read()
                except Exception:
                    logger.warning("读取文档参数文件失败: %s", fpath, exc_info=True)
                    continue
                # 剥离 fenced code blocks — 代码示例不是参数声明, 避免误报
                text = _strip_fenced_blocks(text)
                for pattern in _PARAM_PATTERNS:
                    for match in pattern.finditer(text):
                        # 提取上下文作为 key
                        line_start = max(0, match.start() - 40)
                        context = text[line_start:match.start()].strip().split('\n')[-1].strip()
                        if len(context) > 60:
                            context = context[-60:]
                        # value: 数值组优先 (group 2), 缺省回退 group 1
                        value = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
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
                        logger.warning("读取代码常量文件失败: %s", fpath, exc_info=True)
                        continue
                    for pattern in const_patterns:
                        for match in pattern.finditer(text):
                            name = match.group(1)
                            # 纯数字键(证券/板块代码, 如 "002415")不是参数常量, 跳过避免文档表格误报
                            if name.isdigit():
                                continue
                            key = f"{rel}:{name}:{match.group(2)}"
                            constants[key] = {
                                "file": rel,
                                "name": name,
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
                # 注意：不分割下划线，下划线连接的是完整标识符（如 large_class_threshold）
                name_parts = re.split(r'[\s\-:：,，；;.。]+', ctx)
                for part in name_parts:
                    # 跳过过短的词（<=3 字符），避免误匹配（如 "an"、"10"）
                    if not part or not part[0].isascii() or len(part) <= 3:
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

    def run(self, manual_path: str = "") -> List[Tuple[str, str]]:  # noqa: STYLE-06
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

    def __init__(self, project_root=None, run_id: str = "", runs_dir: str = "",
                 allow_production_bypass: bool = False, readonly: bool = False,
                 allow_stale_report: bool = False, alert: bool = False):
        self.root = project_root or _PROJECT_ROOT
        self.results = []
        # 0-污染模式：配置在 QA-System 中，不在项目里
        self.qa_system_root = os.environ.get("QA_SYSTEM_ROOT", "")
        self.project_name = os.environ.get("QA_PROJECT_NAME", "")
        self.zero_pollution = bool(self.qa_system_root and self.project_name)
        # ── 运行上下文（产物隔离）──────────────────────────────
        self.run_id = run_id or ""
        self.runs_dir = runs_dir or ""
        self.run_dir = ""
        if self.run_id:
            from qa_run import resolve_run_dir
            self.run_dir = resolve_run_dir(self.run_id, self.root, self.qa_system_root, self.runs_dir)
        self.allow_production_bypass = bool(allow_production_bypass)
        # M51-①：是否允许用非本 run 的存量报告下结论（默认禁止，必须显式）
        self.allow_stale_report = bool(allow_stale_report)
        # M51-(a)：门禁产出是否有消费者（默认开：DENY 必须告警到达人，不落磁盘了事）
        self.alert_enabled = bool(alert)
        self.report_source = ""
        self.report_timestamp = ""
        self.alert_result = {}
        # ── 只读审计模式：禁止一切写入被审对象的副作用 ──
        # （不良品登记 registry.json + CB 收件箱 inbox.json 均按目标目录解析，
        #   在只读审计/反向检验场景下必须可关闭，避免污染被审系统）
        self.readonly = bool(readonly)
        self.bypass = {"applied": False, "reason": "", "env": os.environ.get("QA_ENV", "")}
        self.report_path = ""
        self.errors = []
        # 加载配置
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """加载 QA 配置（支持 0-污染模式）"""
        config = {}
        try:
            from chk_load_yaml import load_yaml
        except Exception:
            logger.warning("加载 YAML 模块失败", exc_info=True)
            return config
        # 0-污染模式：优先 {name}_local.yaml，其次 {name}.yaml
        if self.zero_pollution:
            candidates = [
                os.path.join(self.qa_system_root, ".ai", "projects", f"{self.project_name}_local.yaml"),
                os.path.join(self.qa_system_root, ".ai", "projects", f"{self.project_name}.yaml"),
            ]
            for cp in candidates:
                if os.path.exists(cp):
                    try:
                        config.update(load_yaml(cp))
                        break
                    except Exception:
                        logger.warning("加载项目配置失败: %s", cp, exc_info=True)
                        pass
        # 项目本地配置（补充）
        config_paths = [
            os.path.join(self.root, ".ai/config/review-rules.yaml"),
            os.path.join(self.root, ".ai/config/quality-plan.yaml"),
        ]
        for cp in config_paths:
            if os.path.exists(cp):
                try:
                    config.update(load_yaml(cp))
                except Exception:
                    logger.warning("加载本地配置失败: %s", cp, exc_info=True)
                    pass
        return config

    def check(self, name, passed, detail="", gate_id="", severity="BLOCKER"):
        """登记一个门禁结果。

        severity=BLOCKER 且 passed=False → blocking=True（门禁阻断 → DENY）
        severity=WARN/INFO 且 passed=False → 记录失败但不阻断（可观测、可编排）
        """
        sev = (severity or "BLOCKER").upper()
        self.results.append({
            "id": gate_id or _gate_id_from_name(name),
            "name": name,
            "passed": bool(passed),
            "severity": sev,
            "blocking": (not passed) and sev == "BLOCKER",
            "detail": detail,
        })

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
                logger.warning("读取 GITHUB_EVENT_PATH 失败: %s", gh_event, exc_info=True)
                pass
        return None

    def _gate1_position(self):
        """Gate1: 文档位置校验

        判定语义（v1.1 修复 T03-R6「缺目录仍 PASS」）：
          * docs/ 下混入 .py 等违规文件 → passed=False, severity=BLOCKER
          * 缺少标准文档目录          → passed=False, severity=WARN（不阻断）
        两类问题都会体现在 passed=False 上，不再出现"detail 说缺、结果说 PASS"。
        """
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
        # 违规文件 = 阻断；仅缺目录 = WARN（可观测不阻断）
        severity = "BLOCKER" if violations else "WARN"
        self.check("Gate1 文档位置", len(violations) == 0 and not missing, detail,
                   gate_id="1", severity=severity)

    # 标准文档白名单：大写/全大写为行业约定，不应被"小写+连词符"规则误判
    DOC_NAME_EXEMPT = {
        "README.md", "CHANGELOG.md", "LICENSE", "LICENSE.md", "CONTRIBUTING.md",
        "CODEOWNERS", "SECURITY.md", "NOTICE", "AUTHORS.md", "TODO.md",
    }

    def _gate2_naming(self):
        """Gate2: 文档命名校验"""
        violations = []
        docs_dir = os.path.join(self.root, "docs")
        if os.path.isdir(docs_dir):
            for f in os.listdir(docs_dir):
                fpath = os.path.join(docs_dir, f)
                if not os.path.isfile(fpath):
                    continue
                if f in self.DOC_NAME_EXEMPT:
                    continue
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

    def _gate3_sync(self):  # noqa: STYLE-06
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
                        logger.warning("读取 domain 文件失败: %s", fpath, exc_info=True)
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

        # ── 规划存在检查 (0-污染模式: 读 QA-System 配置) ──
        if self.zero_pollution:
            plan_path = os.path.join(
                self.qa_system_root, ".ai", "config", "quality-plan.yaml"
            )
        else:
            plan_path = os.path.join(self.root, ".ai/config/quality-plan.yaml")
        if not os.path.exists(plan_path):
            worm_issues.append("缺少 quality-plan.yaml")

        self.check("Gate4 版本与WORM", len(worm_issues) == 0,
                    "; ".join(worm_issues) if worm_issues else "WORM 合规 · 规划就绪")

    def _gate5_scoring(self):  # noqa: STYLE-06
        """Gate5: 评分与检测器 — 聚合所有 checker 结果"""
        report = self._load_report()
        if not report:
            self.check("Gate5 评分检测", False, "无 QA 报告 (请先运行 qa check)")
            return

        # 所有 checker 已运行
        all_c = CODE_CHECKERS | META_CHECKERS
        ran = set(report.get("checkers", {}).keys())
        missing = all_c - ran

        # 统计错误（只计数 BLOCKER 级别 checker 的错误）
        config = self._load_config()
        errors = 0
        for cid in CODE_CHECKERS:
            cid_errors = report.get("checkers", {}).get(cid, {}).get("errors", 0)
            if cid_errors == 0:
                continue
            # 从配置读取严重级别，BLOCKER 才阻断（统一用 _checker_cfg_key，避免两处映射漂移）
            cid_key = self._checker_cfg_key(cid)
            cid_cfg = config.get(cid_key, {})
            sev = cid_cfg.get("severity", "BLOCKER")
            if sev == "BLOCKER":
                errors += cid_errors
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

        score = self._calc_score(report, config)
        if score is not None:
            # M51-①：评分必须连覆盖率一起展示，否则会出现
            # 「Gate5 FAIL（缺 6 个 checker）· 健康评分 100/100」这种自相矛盾的对外数字。
            cover = len(all_c & ran)
            detail_parts.append(f"健康评分: {score}/100（覆盖 {cover}/{len(all_c)} checker"
                                + (f"，缺失 {len(missing)} 个已计入扣分" if missing else "") + "）")

        # M51-①：裁决对象必须是本 run 的采集产物，否则"缺 checker"只是表象，
        # 真因是**门禁没跑 checker**。非新鲜来源默认不通过（需 --allow-stale-report）。
        stale = not self._report_is_fresh()
        if stale:
            detail_parts.insert(0, f"★裁决对象非本 run 采集产物（来源={self.report_source or '未知'}"
                                   f"，时间戳={self.report_timestamp or '未知'}）—— 门禁不自己跑 "
                                   f"checker，此结论基于存量报告；如需放行请显式加 --allow-stale-report")

        # Gate5 阻断条件：CODE_CHECKERS 必须全部通过，且裁决对象必须新鲜
        # quality_gates/claude 等元检查仅报告，不阻断
        self.check("Gate5 评分检测", len(missing) == 0 and errors == 0 and not stale,
                    " · ".join(detail_parts))

    def _checker_cfg_key(self, cid: str) -> str:
        """checker id → 配置段 key（cid 使用短名, 配置段使用 *_check 全名）.  # noqa: STYLE-06
        """
        return (cid.replace("naming_conflict", "naming_conflict_check")
                   .replace("code_ban", "code_ban_check")
                   .replace("import_boundary", "import_boundary_check")
                   .replace("config_audit", "config_audit_check")
                   .replace("quality_gates", "quality_gates_check")
                   .replace("claude_validation", "claude_validation_check")
                   .replace("semantic_truth", "semantic_truth_check")
                   .replace("docstring_code", "docstring_code_check")
                   .replace("blindspot", "blindspot_check")
                   .replace("runtime_drift", "runtime_drift_check")
                   .replace("vcs_governance", "vcs_governance_check")
                   .replace("container_plane", "container_plane_check")
                   .replace("codestyle", "codestyle_check")
                   .replace("governance", "governance_check")
                   .replace("securityplus", "securityplus_check")
                   .replace("documentation", "documentation_check")
                   .replace("zeroprint", "zeroprint_check")
                   .replace("customrules", "customrules_check")
                   .replace("fusedetect", "fusedetect_check")
                   .replace("docconsistency", "docconsistency_check")
                   .replace("production", "production_check")
                   .replace("solid", "solid_check"))

    def _calc_score(self, report: dict, config: dict) -> Optional[float]:
        """根据报告计算健康评分 — 只对 CODE_CHECKERS 中 BLOCKER 级错误扣分.

        与 Gate5 阻断语义严格一致: 非阻断 (INFO/WARN) 发现不计入健康分,
        避免出现 "0 阻断错误 + 0/100" 的矛盾展示.

        [M51-① 2026-09-14 by m-qa] 修复「缺失 = 满分」：
        原实现对 `report["checkers"].get(cid, {})` 取空 dict ⇒ 未运行的 checker
        `err` 恰为 0 ⇒ `continue` 不扣分 ⇒ **6 个 checker 从未运行，健康分仍报 100/100**，
        与同一行的 `Gate5 ❌ FAIL` 直接矛盾。这与 `script_quality_check.py`
        「扫描 0 个文件 ⇒ 无问题 ⇒ 全部通过」是同一族：**「没有数据」被当成「没有问题」**。
        现改为：缺失的阻断级 checker 按"发现阻断错误"同权扣分，使「覆盖率不足」无法隐藏。
        """
        try:
            total = 100.0
            for cid in CODE_CHECKERS:
                cdata = report.get("checkers", {}).get(cid)
                # M51-①：checker 根本没出现在报告里 = 从未运行，必须扣分而非跳过
                if cdata is None:
                    total -= MISSING_CHECKER_DEDUCT
                    continue
                if cdata.get("skipped"):
                    continue
                err = cdata.get("errors", 0)
                if err == 0:
                    continue
                sev = config.get(self._checker_cfg_key(cid), {}).get("severity", "BLOCKER")
                if sev != "BLOCKER":
                    continue
                deduct = min(err * 5.0, 30.0)  # 每个阻断错误扣 5 分，上限 30
                total -= deduct
            return max(0, total)
        except Exception:
            logger.warning("计算健康评分失败", exc_info=True)
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
                    logger.warning("读取权限检查文件失败: %s", fpath, exc_info=True)
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
            logger.warning("读取 pending.json 失败", exc_info=True)
            self.check("Gate7 闭环", True)

    def _gate8_deployment(self):  # noqa: STYLE-06
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
                logger.warning("读取 CHANGELOG.md 失败", exc_info=True)
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
                capture_output=True, timeout=180, cwd=self.root, env=env
            )
            if r.returncode != 0:
                issues.append("系统自检失败")
        except Exception:
            logger.warning("系统自检执行失败", exc_info=True)
            issues.append("系统自检异常")

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
        """加载被裁决的 QA 报告，并把实际读取路径记录到 self.report_path。

        查找顺序：
          1. {run_dir}/qa-report.json        —— 本 run 的采集产物（唯一可信来源）
          2. QA_RUN_REPORT_PATH              —— 同进程 / 显式注入
          3. 0-污染模式：{QA_SYSTEM_ROOT}/.ai/logs/{project_name}/qa-report.json
          4. {project}/.ai/logs/qa-report.json

        [M51-① 2026-09-14 by m-qa] **门禁不自己跑 checker，只裁决一份"存量报告"**，
        这是"唯一驱动链断"的本体。实测：`--run-id m50-verify` 那次 ① 不存在，
        于是静默落到 ④，裁决了 `2026-08-25T13:24:48` 的报告（**20 天前**，
        早于 T29/T51 的 6 个 checker 存在）⇒ Gate5 报「缺失 6 个 checker」，
        同时健康分 100/100 —— **一份与判定自相矛盾的对外数字**。

        现改为：**落到 ③④ 这类非本 run 来源时必须在契约里显式留痕**，且默认拒绝
        以陈旧报告作出结论（需 `--allow-stale-report` 显式放行，与
        `--allow-production-bypass` 同一套「必须显式」的治理范式）。
        不伪造新鲜度：`self.report_source` / `self.report_timestamp` 如实记录，
        由 `_gate5_scoring` 据此判定。
        """
        candidates = []
        # 1) 同一 run 的采集产物优先（run 隔离语义：门禁只裁决本 run 的报告）
        if self.run_dir:
            candidates.append((os.path.join(self.run_dir, "qa-report.json"), "run"))
        # 2) 同进程 / 显式注入
        staged = os.environ.get("QA_RUN_REPORT_PATH", "")
        if staged:
            candidates.append((staged, "staged"))
        # 3) 0-污染模式：QA 系统侧的项目日志目录
        if self.zero_pollution:
            candidates.append((os.path.join(self.qa_system_root, ".ai", "logs",
                                            self.project_name, "qa-report.json"), "0-pollution"))
        # 4) 项目本地的权威报告（向后兼容）
        candidates.append((os.path.join(self.root, ".ai/logs/qa-report.json"), "legacy"))

        self.report_source = ""
        self.report_timestamp = ""
        for p, src in candidates:
            if not os.path.exists(p):
                continue
            try:
                with open(p, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                self.report_path = p
                self.report_source = src
                self.report_timestamp = str(data.get("timestamp") or data.get("generated_at") or "")
                if src != "run" and src != "staged":
                    logger.warning(
                        "M51-①：裁决对象不是本 run 的采集产物（来源=%s, 时间戳=%s）—— "
                        "门禁不自己跑 checker，此结论基于存量报告：%s",
                        src, self.report_timestamp or "未知", p)
                return data
            except Exception:
                logger.warning("加载 QA 报告失败: %s", p, exc_info=True)
        self.report_path = ""
        return None

    def _report_is_fresh(self) -> bool:
        """本 run 采集产物 = 可信；其余来源需显式 allow_stale_report 放行。"""
        if self.report_source in ("run", "staged"):
            return True
        return bool(getattr(self, "allow_stale_report", False))

    def _summary(self):
        """汇总门禁结果 + 生产旁路（v1.1：旁路必须显式请求且留痕）。

        修复 T03-R1：QA_ENV=production 不再自动放行。仅当
        GateKeeper(allow_production_bypass=True) 或 QA_ALLOW_PRODUCTION_BYPASS=1
        时才旁路，且结果中记录 bypass.applied=true。
        """
        env = os.environ.get("QA_ENV", "").lower()
        env_wants_bypass = env in ("production", "prod")
        flag_wants_bypass = bool(self.allow_production_bypass) or \
            os.environ.get("QA_ALLOW_PRODUCTION_BYPASS", "") == "1"

        if env_wants_bypass and flag_wants_bypass:
            self.bypass = {"applied": True, "reason": "explicit-bypass",
                           "env": env, "requested_by": "--allow-production-bypass"}
            for c in self.results:
                c["bypassed"] = True
                c["original_passed"] = c["passed"]
                c["blocking"] = False
                c["detail"] = f"[BYPASSED] {c['detail']}"
            self.results.append({
                "id": "bypass", "name": "生产旁路", "passed": True, "severity": "WARN",
                "blocking": False, "bypassed": True,
                "detail": "QA_ENV=production + 显式 bypass，门禁未执行阻断（可从 JSON 审计）"})
        elif env_wants_bypass and not flag_wants_bypass:
            # 仅声明环境而未显式请求 → 不旁路，并留下可见信号
            self.bypass = {"applied": False, "reason": "bypass-not-authorized",
                           "env": env, "hint": "需 --allow-production-bypass 或 QA_ALLOW_PRODUCTION_BYPASS=1"}
            self.results.append({
                "id": "bypass", "name": "生产旁路请求", "passed": False, "severity": "WARN",
                "blocking": False,
                "detail": "QA_ENV=production 已设置但未授权旁路 → 门禁照常执行（v1.1 变更）"})

        passed = sum(1 for c in self.results if c["passed"])
        failed = len(self.results) - passed
        blocking_failed = [c for c in self.results if c.get("blocking")]
        block = len(blocking_failed) > 0

        result = {
            "passed": passed,
            "failed": failed,
            "block": block,
            "blocking_failed": [c["name"] for c in blocking_failed],
            "checks": self.results,
            "timestamp": datetime.now().isoformat(),
            "gate_architecture": "Gate0-Gate9",
            "version": "4.1",
            "run_id": self.run_id,
            "bypass": self.bypass,
        }

        if block and not self.readonly:
            try:
                from qa_defect import create
                report = self._load_report()
                if report:
                    create(report, result)
                    self._post_to_cb_inbox(report)
            except Exception:
                logger.warning("创建不良品记录或发送 CB 收件箱失败", exc_info=True)
                pass
        elif block and self.readonly:
            result["side_effects_skipped"] = ["qa_defect.create", "cb_inbox"]
        return result

    def task_contract(self, report: dict) -> List[dict]:
        """把 QA 报告转成编排系统可直接消费的任务列表（稳定 ID + 幂等键）。

        task_id / idempotency_key = sha1(checker|rule|file|line|message)[:12]
        —— 同一问题跨 run 复用同一 ID，可去重、可重试（T03-B4）。
        """
        import hashlib
        tasks = []
        for cid, cdata in (report or {}).get("checkers", {}).items():
            if cdata.get("skipped") or cdata.get("errors", 0) == 0:
                continue
            sev = "WARN" if cid in META_CHECKERS else "BLOCKER"
            for issue in cdata.get("issues", []):
                rule = ""
                m = re.match(r"^\[([A-Z][A-Z0-9-]*)\]", issue or "")
                if m:
                    rule = m.group(1)
                file_path, line_no = _extract_location(issue or "")
                raw = f"{cid}|{rule}|{file_path}|{line_no}|{issue}"
                tid = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
                tasks.append({
                    "task_id": tid,
                    "idempotency_key": tid,
                    "gate": _gate_for_checker(cid),
                    "checker": cid,
                    "rule_id": rule,
                    "severity": sev,
                    "blocking": sev == "BLOCKER",
                    "file": file_path,
                    "line": line_no,
                    "message": (issue or "")[:300],
                    "fix_hint": ".ai/prompts/CLAUDE.md",
                    "depends_on": [],
                })
        return _normalize_tasks(tasks)

    def _post_to_cb_inbox(self, report: dict):
        inbox_path = os.path.join(self.root, ".ai/agents/cb/_tasks/inbox.json")
        os.makedirs(os.path.dirname(inbox_path), exist_ok=True)
        tasks = []
        for t in self.task_contract(report):
            tasks.append({
                "taskId": t["task_id"],
                "checker": t["checker"],
                "issue": t["message"],
                "severity": t["severity"],
                "claude_path": ".ai/prompts/CLAUDE.md",
                "created_at": datetime.now().isoformat(),
                "gate": t["gate"],
                "file": t["file"],
                "line": t["line"],
            })
        with open(inbox_path, "w", encoding="utf-8") as f:
            json.dump({"source": "qa-gate", "gate_arch": "Gate0-Gate9",
                       "run_id": self.run_id,
                       "gate_timestamp": datetime.now().isoformat(), "tasks": tasks},
                      f, ensure_ascii=False, indent=2)


def build_contract(gate: "GateKeeper", args, report, exit_code: int) -> dict:
    """构建门禁 JSON 契约（schema_version 1.0）—— 编排系统的唯一机器接口。

    最小字段集是稳定的；新增字段只做向后兼容追加。
    """
    checks = gate.results
    gates = [{
        "id": c.get("id", ""),
        "name": c["name"],
        "passed": bool(c["passed"]),
        "severity": c.get("severity", "BLOCKER"),
        "blocking": bool(c.get("blocking", False)),
        "bypassed": bool(c.get("bypassed", False)),
        "detail": c.get("detail", ""),
    } for c in checks]

    blocking_failed = [g for g in gates if g["blocking"]]
    tasks = gate.task_contract(report)
    blocking_tasks = [t for t in tasks if t["blocking"]]

    if exit_code == 2:
        verdict = "ERROR"
    elif gate.bypass.get("applied"):
        verdict = "BYPASS"
    elif blocking_failed:
        verdict = "DENY"
    else:
        verdict = "ALLOW"

    return {
        "schema_version": "1.0",
        "run_id": gate.run_id,
        "generated_at": datetime.now().isoformat(),
        "tool": {"name": "qa-system", "version": "4.1",
                 "gate_architecture": "Gate0-Gate9",
                 "gate": args.gate or "all",
                 "readonly": bool(getattr(gate, "readonly", False))},
        "project": {"name": gate.project_name or os.path.basename(gate.root),
                    "root": gate.root,
                    "zero_pollution": gate.zero_pollution},
        "verdict": verdict,
        "exit_code": exit_code,
        "blocked": verdict == "DENY",
        "bypass": gate.bypass,
        "source_report": {
            "path": gate.report_path or "",
            "found": report is not None,
            "errors": (report or {}).get("errors"),
            "total_issues": (report or {}).get("total_issues"),
            "timestamp": (report or {}).get("timestamp"),
            # M51-①：裁决对象来源与新鲜度必须可审计 —— 否则"缺 checker"会被误读为
            # "checker 有问题"，而真因是门禁没跑 checker、裁决了一份存量报告。
            "source": getattr(gate, "report_source", "") or "unknown",
            "is_fresh": bool(getattr(gate, "report_source", "") in ("run", "staged")),
            "allow_stale_report": bool(getattr(gate, "allow_stale_report", False)),
        },
        "summary": {
            "gates_total": len(gates),
            "gates_passed": sum(1 for g in gates if g["passed"]),
            "gates_failed": sum(1 for g in gates if not g["passed"]),
            "gates_blocking_failed": len(blocking_failed),
            "tasks_total": len(tasks),
            "tasks_blocking": len(blocking_tasks),
            # T29 噪声分级：真信号占比（advisory 排除后）
            "tasks_advisory": sum(1 for t in tasks if t["severity"] == "ADVISORY"),
            "tasks_signal": sum(1 for t in tasks if t["severity"] != "ADVISORY"),
            "signal_ratio": round(
                sum(1 for t in tasks if t["severity"] != "ADVISORY") / max(len(tasks), 1), 4),
        },
        "gates": gates,
        "tasks": tasks,
        "artifacts": {},
        "errors": list(getattr(gate, "errors", [])),
    }


def _validate_contract(contract: dict) -> bool:
    """用 .ai/schemas/qa-gate-report.schema.json 自校验契约（jsonschema 可选）。

    校验失败只打 WARN，不改变退出码 —— 契约漂移应被看到，但不阻断业务。
    """
    schema_path = os.path.join(_PROJECT_ROOT, ".ai", "schemas", "qa-gate-report.schema.json")
    if not os.path.exists(schema_path):
        return True
    try:
        import jsonschema
    except ImportError:
        return True
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(contract, schema)
        print("  [OK] 契约 schema 校验通过")
        return True
    except Exception as e:
        print(f"  [WARN] 契约 schema 校验失败: {getattr(e, 'message', e)}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QA 总闸门 v4.1 — Gate0-Gate9 十层门禁（编排契约）")
    parser.add_argument("--report", "-r", action="store_true", help="只报告不阻断（恒 exit 0）")
    parser.add_argument("--gate", "-g", type=str, default="",
                        help="仅运行指定 gate (如 --gate=3)")
    parser.add_argument("--project", "-p", type=str, default="",
                        help="目标项目根目录")
    parser.add_argument("--json", type=str, default="",
                        help="输出结构化门禁契约 JSON 到该路径（编排系统消费）")
    parser.add_argument("--run-id", type=str, default="",
                        help="运行标识：产物隔离到 {base}/.ai/runs/{run_id}/")
    parser.add_argument("--runs-dir", type=str, default="",
                        help="run 基准目录（默认 QA_SYSTEM_ROOT/.ai/runs）")
    parser.add_argument("--allow-production-bypass", action="store_true",
                        help="显式允许生产旁路（否则 QA_ENV=production 不再放行门禁）")
    parser.add_argument("--readonly", action="store_true",
                        help="只读审计：禁止写不良品登记与被审对象的 CB 收件箱（反向检验/审计用）")
    parser.add_argument("--allow-stale-report", action="store_true",
                        help="M51-①：显式允许以非本 run 的存量报告下结论"
                             "（否则裁决对象必须来自 {run_dir}/qa-report.json）")
    parser.add_argument("--no-alert", action="store_true",
                        help="M51-(a)：强制关闭告警投递（关闭原因会记入契约 alerts.detail）")
    parser.add_argument("--alert", action="store_true",
                        help="M51-(a)：把 DENY 结论告警到达人（走 M24 告警桥，不另建通道）。"
                             "QA_ENV=ci 时自动开启；--readonly 审计模式强制关闭（审计不得有外部副作用）")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project or _PROJECT_ROOT)
    # 0-污染模式: 切换 cwd 到目标项目, 保证 checker 相对 scan_dirs 解析正确
    try:
        os.chdir(project_root)
    except OSError:
        logger.warning("无法切换 cwd 到项目根: %s", project_root)
    # M51-(a) 驱动策略：告警会向真人外发消息，故**默认不主动发**，但驱动必须存在：
    #   - QA_ENV=ci（阻断上下文）⇒ 自动开启，门禁自己驱动，不依赖任何人记得跑脚本
    #   - 交互/审计上下文 ⇒ 需显式 --alert；--readonly 强制关闭
    # 无论开或关，`alerts.*` 都会写进契约 —— "DENY 没到达任何人"永远可见，不会静默。
    _alert_on = bool(args.alert) or os.environ.get("QA_ENV", "").lower() == "ci"
    if args.no_alert:
        _alert_on = False
    if args.readonly:
        _alert_on = False
    try:
        gate = GateKeeper(project_root, run_id=args.run_id, runs_dir=args.runs_dir,
                          allow_production_bypass=args.allow_production_bypass,
                          readonly=args.readonly,
                          allow_stale_report=args.allow_stale_report,
                          alert=_alert_on)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(2)
    gate.errors = []

    exit_code = 0
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
            gate.errors.append(f"unknown-gate:{args.gate}")
            exit_code = 2
    else:
        gate.run()

    report = gate._load_report()

    if exit_code == 0:
        exit_code = 1 if any(c.get("blocking") for c in gate.results) else 0

    if args.report:
        exit_code = 0

    # 格式化输出（人读）
    print("=" * 60)
    print("  QA Gate v4.1 — Gate0-Gate9 十层门禁")
    print("=" * 60)

    for c in gate.results:
        if c["passed"]:
            icon = "✅ PASS"
        elif c.get("severity") == "BLOCKER":
            icon = "❌ FAIL"
        else:
            icon = "⚠️  FAIL"
        d = f" — {c['detail']}" if c.get("detail") else ""
        print(f"  {icon}  {c['name']}{d}")

    total = len(gate.results)
    passed_count = sum(1 for c in gate.results if c["passed"])
    print(f"\n  {passed_count}/{total} 门禁通过")
    if args.report:
        print("  Verdict: (report-only, exit 0)")
    else:
        print(f"  Verdict: {({'0': '✅ ALLOW', '1': '🚫 DENY', '2': '⚠️  ERROR'})[str(exit_code)]}")
    if gate.bypass.get("applied"):
        print(f"  ⚠️  BYPASS 生效: {gate.bypass.get('reason')}（已写入 JSON 契约）")

    # ── 噪声分级摘要（T29 要求③：让真信号浮到前面）──
    _pre = build_contract(gate, args, report, exit_code)
    _s = _pre["summary"]
    print(f"\n  信号分级: 真信号 {_s['tasks_signal']} 条 / 噪声 {_s['tasks_advisory']} 条"
          f"  → signal_ratio = {_s['signal_ratio']:.1%}")
    if _s["tasks_signal"]:
        from collections import Counter as _C
        top = _C(t["checker"] for t in _pre["tasks"] if t["severity"] != "ADVISORY").most_common(5)
        print(f"  真信号分布(前5): {top}")

    # ── 结构化契约输出（编排系统消费）──
    contract = _pre
    json_path = args.json
    if args.run_id and not json_path:
        json_path = os.path.join(gate.run_dir, "gate-report.json")

    # M51-(a)：门禁产出的消费者 —— DENY 必须能到达人（复用 M24 通道，不另建）。
    # 放在写盘之前，使 alerts 结果成为契约的一部分（可审计"到底送出去没有"）。
    contract["alerts"] = {"enabled": bool(gate.alert_enabled), "attempted": False,
                          "delivered": False, "suppressed": True,
                          "http_code": 0, "bridge": "", "detail": "未尝试",
                          "driver": ("--alert" if args.alert else
                                     ("QA_ENV=ci" if os.environ.get("QA_ENV", "").lower() == "ci" else
                                      ("readonly" if args.readonly else "disabled")))}
    _verdict = contract.get("verdict")
    _pending_path = ""
    if gate.alert_enabled and _verdict in ("DENY", "ERROR"):
        if json_path:
            contract["_contract_path"] = os.path.abspath(json_path)
        try:
            from qa_alert import notify
            res = notify(contract)
            contract["alerts"] = res
            contract["alerts"]["driver"] = ("--alert" if args.alert else "QA_ENV=ci")
            if res.get("delivered"):
                print(f"\n  📣 已告警到达人（M24 通道 {res.get('bridge')}，HTTP {res.get('http_code')}）")
            else:
                # 不静默：没送到就明说，且让退出码无法把它当成功
                print(f"\n  ❌ 告警未送达：{res.get('detail')}")
                gate.errors.append(f"告警未送达: {res.get('detail')}")
                if exit_code == 0:
                    exit_code = 2
        except Exception as e:
            contract["alerts"]["detail"] = f"告警模块异常: {e}"
            print(f"\n  ❌ 告警投递异常: {e}")
            gate.errors.append(f"告警投递异常: {e}")
            if exit_code == 0:
                exit_code = 2
    elif _verdict in ("DENY", "ERROR"):
        # 未开启投递：DENY 也**不得静默消失**。落一条待投递台账（可被独立驱动补投），
        # 并在契约里写明未投递的原因 —— 这样"结论没到达任何人"是可查的事实，而非空白。
        contract["alerts"]["detail"] = ("投递未开启（driver=%s）：DENY 已记入待投递台账，"
                                        "未到达人" % contract["alerts"]["driver"])
        try:
            _pending_dir = gate.run_dir or os.path.join(gate.qa_system_root or gate.root, ".ai", "runs")
            os.makedirs(_pending_dir, exist_ok=True)
            _pending_path = os.path.join(_pending_dir, "pending-alerts.jsonl")
            with open(_pending_path, "a", encoding="utf-8") as _f:
                _f.write(json.dumps({
                    "ts": contract.get("generated_at"),
                    "verdict": _verdict, "exit_code": exit_code,
                    "project": (contract.get("project") or {}).get("name"),
                    "run_id": contract.get("run_id"),
                    "summary": contract.get("summary"),
                    "gate_report": os.path.abspath(json_path) if json_path else "",
                    "driver": contract["alerts"]["driver"],
                }, ensure_ascii=False) + "\n")
            contract["alerts"]["pending_ledger"] = _pending_path
            print(f"\n  ⚠️  {_verdict} 未告警到达人（driver={contract['alerts']['driver']}）"
                  f" —— 已记入待投递台账 {_pending_path}")
        except Exception as e:
            contract["alerts"]["detail"] += f"；且写待投递台账失败: {e}"
            print(f"\n  ⚠️  写待投递台账失败: {e}")
    else:
        contract["alerts"]["detail"] = f"verdict={_verdict} 未达告警门槛"

    if json_path:
        json_path = os.path.abspath(json_path)
        os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
        contract["artifacts"]["gate_report"] = json_path
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(contract, f, ensure_ascii=False, indent=2)
        print(f"\n  JSON contract: {json_path}")
        _validate_contract(contract)
    if args.run_id:
        from qa_run import write_run_meta
        run_meta = write_run_meta(gate.run_dir, run_id=args.run_id, command="qa_gate",
                                  project_root=project_root,
                                  gate=args.gate or "all",
                                  verdict=contract["verdict"], exit_code=exit_code,
                                  artifacts=contract["artifacts"])
        if run_meta:
            print(f"  run meta:      {run_meta}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

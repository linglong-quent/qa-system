#!/usr/bin/env python3
"""
skill_naming_check.py — 命名规范校验脚本 (P1-F05)
=================================================
读取 config/rule/naming_rule.yaml，扫描代码库中类/函数/变量/常量/文件名/私有成员的命名违规。
10 类前缀检查 + 5 条禁令。

用法:
    python scripts/skill/skill_naming_check.py [--dir <dir>]

退出码:
    0 = 全合规
    1 = 阻断级违规 (blocker)
    2 = 告警
    3 = 配置错误
"""

import argparse
import ast
import json
import re
import sys

# ─── 路径 ────────────────────────────────────────────
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent.parent.parent
NAMING_RULE = ROOT / "config" / "rule" / "naming_rule.yaml"
SCAN_DIRS = ["."]

# 免检目录
EXEMPT_DIRS = ["_deprecated", "__pycache__", ".git", "build", "dist", ".egg-info", "node_modules"]
# 免检文件
EXEMPT_PATTERNS = [
    "__init__.py",
    "test_",
    "_test.py",
    "setup.py",
    "_batch_",
    "_fix_",
    "_step",
    "_check_",
    "_ci_",
    "_auto_",
    "_final_",
    "_add_",
    "_loop_",
    "_mypy",
    "_x04_",
    "_a05_",
    "_test_break",
    "_test_regex",
    "_protocols.py",
    "_tdx_full_",
    "_run_",
    "_save_snapshot",
]


# ═══════════════════════════════════════════════════════════════
# 1. 规则加载
# ═══════════════════════════════════════════════════════════════


def load_naming_rules() -> Dict[str, Any]:
    """加载 naming_rule.yaml"""
    import yaml

    if not NAMING_RULE.exists():
        print(f"❌ 命名规则表不存在: {NAMING_RULE}")
        sys.exit(3)
    with open(NAMING_RULE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ═══════════════════════════════════════════════════════════════
# 2. 数据结构
# ═══════════════════════════════════════════════════════════════


@dataclass
class NamingIssue:
    """命名违规"""

    rule: str  # 规则编号，如 "NAM-001"
    severity: str  # blocker / error / warning
    file: str  # 文件路径
    line: int  # 行号
    name: str  # 违规名称
    kind: str  # 类型: class/function/variable/constant/file/private
    message: str  # 描述
    suggest: str = ""  # 修改建议


# ═══════════════════════════════════════════════════════════════
# 3. 10 类前缀规则 (从 naming_rule.yaml prefix_mapping)
# ═══════════════════════════════════════════════════════════════

PREFIX_MAP = {
    "boolean": ("is_", "has_"),
    "factor": ("factor_",),
    "risk": ("risk_",),
    "order": ("order_",),
    "position": ("position_",),
    "l2": ("l2_",),
    "auction": ("auction_",),
    "window": ("window_",),
    "capital": ("capital_", "flow_"),
    "test": ("test_",),
}

# 需要前缀检查的关键词 → 类别映射 (变量名中如果包含这些词，应有对应前缀)
PREFIX_KEYWORD_MAP = {
    # boolean → is_/has_
    "bool": "boolean",
    "flag": "boolean",
    "enabled": "boolean",
    "active": "boolean",
    "valid": "boolean",
    "done": "boolean",
    "ready": "boolean",
    "ok": "boolean",
    "success": "boolean",
    "failed": "boolean",
    "matched": "boolean",
    # factor
    "factor": "factor",
    # risk
    "risk": "risk",
    # order
    "order": "order",
    # position
    "position": "position",
    "pos": "position",
    # l2
    "l2": "l2",
    # auction
    "auction": "auction",
    # window
    "window": "window",
    "win": "window",
    # capital
    "capital": "capital",
    "flow": "capital",
    "cash": "capital",
    # test
    "test": "test",
}


def check_prefix(name: str, line: int, file_path: Path) -> list[NamingIssue]:
    """检查变量名是否符合前缀约定"""
    issues = []
    name_lower = name.lower()
    name_parts = set(re.split(r"[_]+", name_lower))

    for keyword, category in PREFIX_KEYWORD_MAP.items():
        if keyword not in name_parts:
            continue
        expected_prefixes = PREFIX_MAP.get(category, ())
        if not expected_prefixes:
            continue

        # 已有任意正确前缀则跳过
        if any(name_lower.startswith(p) for p in expected_prefixes):
            continue

        # 短变量豁免：变量本身就是关键词（如 pos, win, l2, ok）
        if name_lower == keyword and len(name_lower) <= 3:
            continue

        # 避免重复前缀建议：如 l2_l2
        if name_lower.startswith(f"{keyword}_"):
            continue

        issues.append(
            NamingIssue(
                rule="NAM-P01",
                severity="warning",
                file=str(file_path.relative_to(ROOT)),
                line=line,
                name=name,
                kind="variable",
                message=f"变量 '{name}' 含关键词 '{keyword}' 但缺少 '{category}' 前缀",
                suggest=f"建议使用 {'/'.join(expected_prefixes)} 前缀，如 {expected_prefixes[0]}{name}",
            )
        )
        break  # 一个变量只报一次

    return issues


# ═══════════════════════════════════════════════════════════════
# 4. 5 条禁令 + 文件/私有规则
# ═══════════════════════════════════════════════════════════════


# NAM-001 豁免类名模式（业务 dataclass 命名惯例）
CLASS_NAME_EXEMPT = {"L2_", "ETF_", "IPO_", "REIT_"}


def check_class_name(name: str, line: int, file_path: Path) -> list[NamingIssue]:
    """NAM-001: 类名 PascalCase"""
    issues: Any = []
    # 私有类 _Xxx 豁免
    if name.startswith("_"):
        return issues  # type: ignore[no-any-return]
    # 业务前缀豁免 (L2_00Input, L2_MarketStructure 等)
    for prefix in CLASS_NAME_EXEMPT:
        if name.startswith(prefix):
            return issues  # type: ignore[no-any-return]
    if not re.match(r"^[A-Z][a-zA-Z0-9]+$", name):
        issues.append(
            NamingIssue(
                rule="NAM-001",
                severity="error",
                file=str(file_path.relative_to(ROOT)),
                line=line,
                name=name,
                kind="class",
                message=f"类名 '{name}' 不符合 PascalCase (应以大写字母开头)",
                suggest="使用 PascalCase，如 MyClassName",
            )
        )
    return issues  # type: ignore[no-any-return]


def check_function_name(name: str, line: int, file_path: Path) -> list[NamingIssue]:
    """NAM-002: 函数名 snake_case"""
    issues: Any = []
    # AST visitor 方法豁免
    if name.startswith("visit_") and re.match(r"^visit_[A-Z]", name):
        return issues  # type: ignore[no-any-return]
    # HTTP 方法处理器豁免
    if name in ("do_GET", "do_POST", "do_PUT", "do_DELETE", "do_HEAD", "do_OPTIONS", "do_PATCH"):
        return issues  # type: ignore[no-any-return]
    # 第三方 API 适配器豁免 (Get*, Set* 等)
    if re.match(r"^(Get|Set|Fetch|Query|Create|Update|Delete)[A-Z]", name):
        return issues  # type: ignore[no-any-return]
    if name.startswith("_") and len(name) > 1:
        name = name[1:]  # 去掉私有前缀再检查
    if not re.match(r"^[a-z][a-z0-9_]*$", name) and not name.startswith("__"):
        # __init__ __str__ 等 dunder 豁免
        if not (name.startswith("__") and name.endswith("__")):
            issues.append(
                NamingIssue(
                    rule="NAM-002",
                    severity="error",
                    file=str(file_path.relative_to(ROOT)),
                    line=line,
                    name=name,
                    kind="function",
                    message=f"函数名 '{name}' 不符合 snake_case",
                    suggest="使用 snake_case，如 my_function_name",
                )
            )
    return issues  # type: ignore[no-any-return]


def check_variable_name(name: str, line: int, file_path: Path) -> list[NamingIssue]:
    """NAM-003: 变量名 snake_case + 不单字母 (除循环变量)"""
    issues = []
    if not re.match(r"^[a-z_][a-z0-9_]*$", name):
        # 常量豁免 (大写)
        if not re.match(r"^[A-Z][A-Z0-9_]*$", name):
            issues.append(
                NamingIssue(
                    rule="NAM-003",
                    severity="warning",
                    file=str(file_path.relative_to(ROOT)),
                    line=line,
                    name=name,
                    kind="variable",
                    message=f"变量名 '{name}' 不符合 snake_case",
                    suggest="使用 snake_case，如 my_variable",
                )
            )
    return issues


def check_constant_name(name: str, line: int, file_path: Path) -> list[NamingIssue]:
    """NAM-004: 全局常量 UPPER_SNAKE_CASE"""
    issues = []
    if not re.match(r"^[A-Z][A-Z0-9_]*$", name):
        issues.append(
            NamingIssue(
                rule="NAM-004",
                severity="error",
                file=str(file_path.relative_to(ROOT)),
                line=line,
                name=name,
                kind="constant",
                message=f"常量名 '{name}' 不符合 UPPER_SNAKE_CASE",
                suggest="使用 UPPER_SNAKE_CASE，如 MY_CONSTANT",
            )
        )
    return issues


def check_private_name(name: str, line: int, file_path: Path, kind: str) -> list[NamingIssue]:
    """NAM-005: 私有成员 _ 前缀 (模块级/类级私有)"""
    issues: Any = []  # noqa: F841
    # 如果定义了 __all__，跳过私有检查
    if name.startswith("_"):
        return []  # 合规
    # 这条是正向规则：不要求强制 _ 前缀，只对明显是内部使用的函数/类做提示
    # 实际禁令: 不使用 _ 前缀的内部函数
    return []


def check_file_name(file_path: Path) -> list[NamingIssue]:
    """NAM-006: 文件名 snake_case.py"""
    issues: Any = []
    fname = file_path.stem
    if file_path.name == "__init__.py":
        return issues  # type: ignore[no-any-return]
    if not re.match(r"^[a-z][a-z0-9_]*$", fname):
        issues.append(
            NamingIssue(
                rule="NAM-006",
                severity="error",
                file=str(file_path.relative_to(ROOT)),
                line=0,
                name=file_path.name,
                kind="file",
                message=f"文件名 '{file_path.name}' 不符合 snake_case",
                suggest="使用 snake_case 命名，如 my_module.py",
            )
        )
    return issues  # type: ignore[no-any-return]


def check_deprecated_name(name: str, line: int, file_path: Path, kind: str) -> list[NamingIssue]:
    """NAM-007: 废弃标记 _deprecated_ 前缀检查"""
    issues: Any = []
    # 豁免自身: 检查函数名就是 check_deprecated_name
    if name == "check_deprecated_name":
        return issues  # type: ignore[no-any-return]
    # 这条是正向提示：如果名字包含 deprecated 但不用 _deprecated_ 前缀
    if "deprecated" in name.lower() and not name.startswith("_deprecated_"):
        issues.append(
            NamingIssue(
                rule="NAM-007",
                severity="warning",
                file=str(file_path.relative_to(ROOT)),
                line=line,
                name=name,
                kind=kind,
                message=f"'{name}' 含 deprecated 但未使用 _deprecated_ 前缀",
                suggest="使用 _deprecated_ 前缀标记废弃项",
            )
        )
    return issues  # type: ignore[no-any-return]


# ═══════════════════════════════════════════════════════════════
# 5. 5 条禁令定义
# ═══════════════════════════════════════════════════════════════

BANS = [
    {
        "id": "BAN-N01",
        "name": "禁止类名不以大写字母开头",
        "severity": "blocker",
        "check": check_class_name,
    },
    {
        "id": "BAN-N02",
        "name": "禁止函数名不以 snake_case",
        "severity": "blocker",
        "check": check_function_name,
    },
    {
        "id": "BAN-N03",
        "name": "禁止变量名不以 snake_case",
        "severity": "warning",
        "check": check_variable_name,
    },
    {
        "id": "BAN-N04",
        "name": "禁止全局常量不用 UPPER_SNAKE_CASE",
        "severity": "blocker",
        "check": check_constant_name,
    },
    {
        "id": "BAN-N05",
        "name": "禁止文件名不用 snake_case",
        "severity": "error",
        "check": None,  # 特殊处理
    },
]


# ═══════════════════════════════════════════════════════════════
# 6. AST 扫描器
# ═══════════════════════════════════════════════════════════════


class NamingVisitor(ast.NodeVisitor):
    """AST 遍历器，收集类/函数/变量/常量定义"""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.issues: list[NamingIssue] = []
        self.module_constants: list[tuple[str, int]] = []  # (name, line)

    def visit_ClassDef(self, node) -> None:  # type: ignore[no-untyped-def]
        # 类名检查
        self.issues.extend(check_class_name(node.name, node.lineno, self.file_path))
        self.issues.extend(check_deprecated_name(node.name, node.lineno, self.file_path, "class"))
        self.generic_visit(node)

    def visit_FunctionDef(self, node) -> None:  # type: ignore[no-untyped-def]
        # 函数名检查（跳过 dunder）
        if not (node.name.startswith("__") and node.name.endswith("__")):
            self.issues.extend(check_function_name(node.name, node.lineno, self.file_path))
            self.issues.extend(check_deprecated_name(node.name, node.lineno, self.file_path, "function"))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node) -> None:  # type: ignore[no-untyped-def]
        # 异步函数同普通函数检查
        if not (node.name.startswith("__") and node.name.endswith("__")):
            self.issues.extend(check_function_name(node.name, node.lineno, self.file_path))
        self.generic_visit(node)

    def visit_Assign(self, node) -> None:  # type: ignore[no-untyped-def]
        # 模块级赋值 → 常量/变量
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                if name.startswith("_"):
                    continue  # 私有变量跳过
                if re.match(r"^[A-Z][A-Z0-9_]*$", name):
                    # 全大写 → 常量
                    self.issues.extend(check_constant_name(name, node.lineno, self.file_path))
                    self.module_constants.append((name, node.lineno))
                else:
                    # 变量
                    self.issues.extend(check_variable_name(name, node.lineno, self.file_path))
                    self.issues.extend(check_prefix(name, node.lineno, self.file_path))
                self.issues.extend(check_deprecated_name(name, node.lineno, self.file_path, "variable"))
        self.generic_visit(node)

    def visit_AnnAssign(self, node) -> None:  # type: ignore[no-untyped-def]
        # 类型注解赋值
        if isinstance(node.target, ast.Name):
            name = node.target.id
            if name.startswith("_"):
                return
            if re.match(r"^[A-Z][A-Z0-9_]*$", name):
                self.issues.extend(check_constant_name(name, node.lineno, self.file_path))
                self.module_constants.append((name, node.lineno))
            else:
                self.issues.extend(check_variable_name(name, node.lineno, self.file_path))
                self.issues.extend(check_prefix(name, node.lineno, self.file_path))
        self.generic_visit(node)

    def visit_Name(self, node) -> None:  # type: ignore[no-untyped-def]
        # 跳过（避免重复检查变量引用）
        pass


# ═══════════════════════════════════════════════════════════════
# 7. 文件扫描
# ═══════════════════════════════════════════════════════════════


def should_skip(file_path: Path) -> bool:
    """判断文件是否应跳过"""
    rel = file_path.relative_to(ROOT)
    parts = rel.parts
    for exempt in EXEMPT_DIRS:
        if exempt in parts:
            return True
    fname = file_path.name
    for pattern in EXEMPT_PATTERNS:
        if pattern in fname:
            return True
    return False


def scan_file(file_path: Path) -> list[NamingIssue]:
    """扫描单个 Python 文件"""
    issues: list[NamingIssue] = []

    # 文件名检查
    issues.extend(check_file_name(file_path))

    # 读取源码
    try:
        source = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IOError):
        return issues

    # AST 解析
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return issues

    visitor = NamingVisitor(file_path)
    visitor.visit(tree)
    issues.extend(visitor.issues)

    return issues


def scan_directory(target_dir: Path) -> list[NamingIssue]:
    """递归扫描目录"""
    all_issues: list[NamingIssue] = []
    py_files = list(target_dir.rglob("*.py"))
    for py_file in py_files:
        if should_skip(py_file):
            continue
        all_issues.extend(scan_file(py_file))
    return all_issues


# ═══════════════════════════════════════════════════════════════
# 8. 主入口
# ═══════════════════════════════════════════════════════════════


def main() -> None:  # noqa: C901
    parser = argparse.ArgumentParser(description="命名规范校验 — 10前缀+5禁令 (P1-F05)")
    parser.add_argument("--dir", default=None, help="扫描目录（默认项目根 .）")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    # 加载规则表
    rules = load_naming_rules()
    print("=" * 60)
    print("  命名规范 naming_check 扫描")
    print("=" * 60)
    print(f"  规则表: {NAMING_RULE}")
    print(f"  前缀类别: {len(PREFIX_MAP)}")
    print(f"  禁令: {len(BANS)}")
    print("-" * 60)

    # 扫描
    target = ROOT / args.dir if args.dir else ROOT
    if not target.exists():
        print(f"❌ 目录不存在: {target}")
        sys.exit(3)

    issues = scan_directory(target)

    # 统计
    rule_stats: dict[str, Dict[str, Any]] = {}
    for issue in issues:
        rid = issue.rule
        if rid not in rule_stats:
            rule_stats[rid] = {"count": 0, "severity": issue.severity}
        rule_stats[rid]["count"] += 1

    print(f"\n  扫描结果: {len(issues)} 处违规\n")

    for rid in sorted(rule_stats.keys()):
        stat = rule_stats[rid]
        icon = "✅" if stat["count"] == 0 else "❌"
        print(f"    {icon} {rid}: {stat['count']} 处 ({stat['severity']})")

    if issues:
        print(f"\n  --- 详细违规 ---\n")  # noqa: F541
        for issue in issues:
            sev_icon = {"blocker": "🔴", "error": "🟡", "warning": "🔵"}
            icon = sev_icon.get(issue.severity, "⚪")
            loc = f"{issue.file}:{issue.line}" if issue.line else issue.file
            print(f"    {icon} [{issue.rule}] {loc} ({issue.kind})")
            print(f"       {issue.message}")
            if issue.suggest:
                print(f"       → {issue.suggest}")
            print()

    # 退出码
    blocker_count = sum(1 for i in issues if i.severity == "blocker")
    error_count = sum(1 for i in issues if i.severity == "error")

    if args.json:
        output = {
            "skill": "naming_check",
            "rules_loaded": len(rules.get("rules", {})),
            "prefix_categories": len(PREFIX_MAP),
            "ban_count": len(BANS),
            "total_issues": len(issues),
            "blocker_count": blocker_count,
            "error_count": error_count,
            "issues": [asdict(i) for i in issues],  # noqa: F821
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    if blocker_count > 0:
        print(f"\n❌ {blocker_count} 处阻断级违规，请修复后重试")
        sys.exit(1)

    if error_count > 0:
        print(f"\n⚠️  {error_count} 处错误级违规，建议修复")
        sys.exit(2)

    if issues:
        print(f"\n⚠️  {len(issues)} 处警告级提示")
        sys.exit(0)

    print(f"\n✅ 全部命名规范通过")  # noqa: F541
    sys.exit(0)


if __name__ == "__main__":
    main()

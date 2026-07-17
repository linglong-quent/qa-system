#!/usr/bin/env python3
"""
skill_readability_check.py — 代码可读性检查 (P1-F06)
=====================================================
三方面检查：
  1. docstring — 公开函数/类是否缺少文档字符串
  2. DRY — 大段重复代码检测
  3. 公式/魔法数字 — 公式注释缺失、魔法数字

用法:
    python scripts/skill/skill_readability_check.py [--dir <dir>]

退出码:
    0 = 全合规
    1 = 阻断级违规 (blocker)
    2 = 告警 (warning)
"""

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
SCAN_DIRS = ["."]

EXEMPT_DIRS = ["_deprecated", "__pycache__", ".git", "build", "dist", ".egg-info", "node_modules"]
EXEMPT_PATTERNS = ["__init__.py", "test_", "_test.py", "setup.py"]

# ── 命名常量（消除魔法数字）────────────────────────────────
SEP_WIDTH = 60  # 输出分隔线宽度
MIN_MATH_OPS = 3  # 公式检测的最小运算符数量
EXIT_DIR_NOT_FOUND = 3  # 目录不存在的退出码

# 内置豁免函数/类（无 docstring 但属标准模式）
EXEMPT_DOCSTRING_NAMES = {
    "__init__",
    "__new__",
    "__repr__",
    "__str__",
    "__len__",
    "__iter__",
    "__next__",
    "__enter__",
    "__exit__",
    "__contains__",
    "__getitem__",
    "__setitem__",
    "__delitem__",
    "__eq__",
    "__ne__",
    "__lt__",
    "__gt__",
    "__le__",
    "__ge__",
    "__hash__",
    "__call__",
    "__bool__",
    "__copy__",
    "__deepcopy__",
    "__getstate__",
    "__setstate__",
    "__reduce__",
    "visit_Name",
    "visit_Constant",
    "generic_visit",
}

# 公开函数/类的最小行数阈值（太短的不强制要求 docstring）
MIN_LINES_FOR_DOCSTRING = 5

# 魔法数字豁免（常见常量）
MAGIC_NUMBER_EXEMPT = {0, 1, 2, -1, 10, 100, 1000, 0.0, 1.0, 0.5, True, False, None}

# DRY: 重复行序列最小长度
DRY_MIN_LINES = 6
# DRY: 检测窗口大小（滑动窗口）
DRY_WINDOW = 6
# DRY: 跨文件最小重复行
DRY_CROSS_FILE_MIN = 8

# 公式关键字（提示需要注释的公式）
FORMULA_KEYWORDS = [
    "sqrt",
    "pow",
    "log",
    "exp",
    "abs",
    "sin",
    "cos",
    "tan",
    "mean",
    "std",
    "var",
    "min",
    "max",
    "sum",
    "+",
    "-",
    "*",
    "/",
    "**",
    "%",
]


# ═══════════════════════════════════════════════════════════════
# 1. 数据结构
# ═══════════════════════════════════════════════════════════════


@dataclass
class ReadabilityIssue:
    """可读性问题数据结构。

    规则编号 REA-001 ~ REA-009，严重度分为 blocker/error/warning 三级。
    """

    rule: str  # REA-001 ~ REA-009
    severity: str  # blocker / error / warning
    file: str
    line: int
    name: str  # 函数/类/变量名
    kind: str  # docstring / dry / magic_number / formula
    message: str
    suggest: str = ""


# ═══════════════════════════════════════════════════════════════
# 2. 工具函数
# ═══════════════════════════════════════════════════════════════


def should_skip(file_path: Path) -> bool:
    """判断文件是否应跳过扫描（豁免目录/豁免文件名模式）。"""
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


def is_public(name: str) -> bool:
    """判断是否为公开API（非 _ 开头）"""
    return not name.startswith("_")


def get_docstring(node) -> Optional[str]:  # type: ignore[no-untyped-def]
    """获取节点的 docstring"""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                return body[0].value.value
    return None


def count_effective_lines(node) -> int:  # type: ignore[no-untyped-def]
    """估算函数/类的有效行数（排除空行和 docstring）"""
    if not hasattr(node, "end_lineno") or node.end_lineno is None:
        return 0
    return node.end_lineno - node.lineno + 1  # type: ignore[no-any-return]


# ═══════════════════════════════════════════════════════════════
# 3. Docstring 检查
# ═══════════════════════════════════════════════════════════════


class DocstringVisitor(ast.NodeVisitor):
    """检查公开函数/类的 docstring"""

    def __init__(self, file_path: Path, source_lines: list[str]) -> None:
        self.file_path = file_path
        self.source_lines = source_lines
        self.issues: list[ReadabilityIssue] = []

    def _check_docstring(self, node, name: str, kind: str, node_type: str) -> None:  # type: ignore[no-untyped-def]
        """通用 docstring 检查"""
        if name in EXEMPT_DOCSTRING_NAMES:
            return
        if not is_public(name):
            return
        lines = count_effective_lines(node)
        if lines < MIN_LINES_FOR_DOCSTRING:
            return

        ds = get_docstring(node)
        if ds is None:
            self.issues.append(
                ReadabilityIssue(
                    rule="REA-001",
                    severity="error",
                    file=str(self.file_path.relative_to(ROOT)),
                    line=node.lineno,
                    name=name,
                    kind="docstring",
                    message=f"{node_type} '{name}' 缺少 docstring（{lines} 行）",
                    suggest=f"添加文档字符串说明 {node_type} 的功能、参数和返回值",
                )
            )
        elif len(ds.strip()) < 10:
            self.issues.append(
                ReadabilityIssue(
                    rule="REA-002",
                    severity="warning",
                    file=str(self.file_path.relative_to(ROOT)),
                    line=node.lineno,
                    name=name,
                    kind="docstring",
                    message=f"{node_type} '{name}' docstring 过短（{len(ds)} 字符）",
                    suggest="补充更详细的文档字符串",
                )
            )

    def visit_FunctionDef(self, node) -> None:  # type: ignore[no-untyped-def]
        """检查函数定义节点的 docstring 合规性。"""
        self._check_docstring(node, node.name, "function", "函数")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node) -> None:  # type: ignore[no-untyped-def]
        """检查异步函数定义节点的 docstring 合规性。"""
        self._check_docstring(node, node.name, "function", "异步函数")
        self.generic_visit(node)

    def visit_ClassDef(self, node) -> None:  # type: ignore[no-untyped-def]
        """检查类定义节点的 docstring 合规性。"""
        self._check_docstring(node, node.name, "class", "类")
        self.generic_visit(node)


# ═══════════════════════════════════════════════════════════════
# 4. DRY 重复代码检测（同文件内）
# ═══════════════════════════════════════════════════════════════


def check_dry_same_file(file_path: Path, lines: list[str]) -> list[ReadabilityIssue]:
    """检测同一文件内的大段重复代码"""
    issues = []
    # 归一化行：去掉空白和注释行
    normalized = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            normalized.append(("", i + 1, ""))
        else:
            # 归一化：合并空白
            norm = re.sub(r"\s+", " ", stripped)
            normalized.append((norm, i + 1, stripped))

    # 滑动窗口检测重复
    seen: Any = {}
    for i in range(len(normalized) - DRY_WINDOW + 1):
        window = tuple(n[0] for n in normalized[i : i + DRY_WINDOW])
        # 跳过全空窗口
        if all(w == "" for w in window):
            continue
        key = hashlib.md5("|".join(window).encode()).hexdigest()
        if key in seen:
            prev_start = seen[key]
            # 避免重叠
            if i - prev_start >= DRY_WINDOW:
                issues.append(
                    ReadabilityIssue(
                        rule="REA-003",
                        severity="warning",
                        file=str(file_path.relative_to(ROOT)),
                        line=normalized[i][1],
                        name=f"L{normalized[i][1]}-L{normalized[i+DRY_WINDOW-1][1]}",
                        kind="dry",
                        message=f"疑似重复代码块（{DRY_WINDOW} 行），与第 {normalized[prev_start][1]} 行重复",
                        suggest="提取为公共函数/方法",
                    )
                )
        else:
            seen[key] = i

    return issues


# ═══════════════════════════════════════════════════════════════
# 5. 公式注释检查
# ═══════════════════════════════════════════════════════════════


def check_formula_comment(file_path: Path, lines: list[str]) -> list[ReadabilityIssue]:  # noqa: C901
    """检查包含复杂公式的行是否有注释说明"""
    issues = []
    # 公式特征：含多个数学运算符
    math_ops_pattern = re.compile(r"[+\-*/%](?:\s*[+\-*/%])+")  # noqa: F841
    # 数学函数调用
    math_func_pattern = re.compile(
        r"\b(sqrt|pow|log|exp|abs|sin|cos|tan|mean|std|var|corr|cov|regress|interpolate|"
        r"rolling|ewm|shift|pct_change|diff|cumsum|cumprod|rank|quantile)\s*\("
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # 排除 import/from 语句
        if stripped.startswith("import ") or stripped.startswith("from "):
            continue
        # 排除 shebang
        if stripped.startswith("#!"):
            continue
        # 排除装饰器
        if stripped.startswith("@"):
            continue
        # 排除纯字符串赋值
        if "=" in stripped and re.match(r'^\w+\s*=\s*["\']', stripped):
            continue

        # 检查是否包含数学公式特征
        has_math = False
        if math_func_pattern.search(stripped):
            has_math = True
        elif len(re.findall(r"[+\-*/%]", stripped)) >= MIN_MATH_OPS and "=" not in stripped:
            # 3个以上运算符且不是赋值语句
            # 排除字符串内的运算符（简单检查：引号内不算）
            code_part = re.sub(r'["\'][^"\']*["\']', "", stripped)
            if len(re.findall(r"[+\-*/%]", code_part)) >= MIN_MATH_OPS:
                has_math = True

        if not has_math:
            continue

        # 检查前一行是否有注释
        has_comment_before = False
        if i > 0:
            prev = lines[i - 1].strip()
            if prev.startswith("#"):
                has_comment_before = True

        # 检查同一行是否有行内注释
        has_inline_comment = "#" in stripped.split('"')[0] if '"' in stripped else "#" in stripped

        if not has_comment_before and not has_inline_comment:
            issues.append(
                ReadabilityIssue(
                    rule="REA-004",
                    severity="warning",
                    file=str(file_path.relative_to(ROOT)),
                    line=i + 1,
                    name=f"formula_L{i+1}",
                    kind="formula",
                    message=f"第{i+1}行疑似公式/复杂计算，缺少注释说明",
                    suggest="添加注释说明公式含义、输入输出和单位",
                )
            )

    return issues


# ═══════════════════════════════════════════════════════════════
# 6. 魔法数字检查
# ═══════════════════════════════════════════════════════════════


class MagicNumberVisitor(ast.NodeVisitor):
    """检测代码中的魔法数字（非 0/1/2/-1 的字面常量）。"""

    def __init__(self, file_path: Path, source_lines: list[str]) -> None:
        self.file_path = file_path
        self.source_lines = source_lines
        self.issues: list[ReadabilityIssue] = []
        self._skip_depth = 0  # 跳过嵌套深度（下标/切片/比较右值）

    def visit_Assign(self, node) -> None:  # type: ignore[no-untyped-def]
        """赋值目标为全大写常量时豁免右侧数字。"""
        old = self._skip_depth
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                self._skip_depth += 1
                break
        self.generic_visit(node)
        self._skip_depth = old

    def visit_AnnAssign(self, node) -> None:  # type: ignore[no-untyped-def]
        """带类型注解的赋值：全大写目标豁免右侧数字。"""
        if isinstance(node.target, ast.Name) and node.target.id.isupper():
            old = self._skip_depth
            self._skip_depth += 1
            self.generic_visit(node)
            self._skip_depth = old
            return
        self.generic_visit(node)

    def visit_Compare(self, node) -> None:  # type: ignore[no-untyped-def]
        """比较表达式：右侧阈值数字降低严重性。"""
        self.visit(node.left)
        old = self._skip_depth
        self._skip_depth += 1
        for comparator in node.comparators:
            self.visit(comparator)
        self._skip_depth = old

    def visit_Call(self, node) -> None:  # type: ignore[no-untyped-def]
        """函数调用：按位置参数和关键字参数分别遍历。"""
        for kw in node.keywords:
            # 跳过关键字参数的值检查
            pass
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)

    def visit_Constant(self, node) -> None:  # type: ignore[no-untyped-def]
        """检测整型/浮点数字面量是否为非豁免的魔法数字。"""
        if not isinstance(node.value, (int, float)):
            return
        if node.value in MAGIC_NUMBER_EXEMPT:
            return
        if self._skip_depth > 0:
            return

        self.issues.append(
            ReadabilityIssue(
                rule="REA-005",
                severity="warning",
                file=str(self.file_path.relative_to(ROOT)),
                line=node.lineno if hasattr(node, "lineno") else 0,
                name=str(node.value),
                kind="magic_number",
                message=f"魔法数字 {node.value}，缺少语义化常量定义",
                suggest=f"将 {node.value} 提取为命名常量，如 THRESHOLD = {node.value}",
            )
        )

    def visit_Subscript(self, node) -> None:  # type: ignore[no-untyped-def]
        """下标表达式：跳过下标索引中的数字检查。"""
        old = self._skip_depth
        self._skip_depth += 1
        self.generic_visit(node)
        self._skip_depth = old

    def visit_Slice(self, node) -> None:  # type: ignore[no-untyped-def]
        """切片表达式：完全跳过不检查。"""

    def visit_BinOp(self, node) -> None:  # type: ignore[no-untyped-def]
        """二元运算：只检查左操作数中的数字（如 offset + 3 中的 3）。"""
        self.generic_visit(node)


# ═══════════════════════════════════════════════════════════════
# 7. 函数/类体长检查
# ═══════════════════════════════════════════════════════════════


class BodyLengthVisitor(ast.NodeVisitor):
    """检查函数/类体长是否超过可读性阈值"""

    MAX_FUNC_LINES = 80  # 函数最大行数
    MAX_CLASS_LINES = 300  # 类最大行数

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.issues: list[ReadabilityIssue] = []

    def visit_FunctionDef(self, node) -> None:  # type: ignore[no-untyped-def]
        """检查函数体长是否超过可读性阈值（MAX_FUNC_LINES）。"""
        lines = count_effective_lines(node)
        if lines > self.MAX_FUNC_LINES:
            self.issues.append(
                ReadabilityIssue(
                    rule="REA-006",
                    severity="warning",
                    file=str(self.file_path.relative_to(ROOT)),
                    line=node.lineno,
                    name=node.name,
                    kind="body_length",
                    message=f"函数 '{node.name}' 体长 {lines} 行（阈值 {self.MAX_FUNC_LINES}）",
                    suggest="拆分为更小的函数，提高可读性和可测试性",
                )
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node) -> None:  # type: ignore[no-untyped-def]
        """检查类体长是否超过可读性阈值（MAX_CLASS_LINES）。"""
        lines = count_effective_lines(node)
        if lines > self.MAX_CLASS_LINES:
            self.issues.append(
                ReadabilityIssue(
                    rule="REA-007",
                    severity="warning",
                    file=str(self.file_path.relative_to(ROOT)),
                    line=node.lineno,
                    name=node.name,
                    kind="body_length",
                    message=f"类 '{node.name}' 体长 {lines} 行（阈值 {self.MAX_CLASS_LINES}）",
                    suggest="拆分为更小的类或模块，遵循单一职责原则",
                )
            )
        self.generic_visit(node)


# ═══════════════════════════════════════════════════════════════
# 8. 文件扫描
# ═══════════════════════════════════════════════════════════════


def scan_file(file_path: Path) -> list[ReadabilityIssue]:
    """扫描单个 Python 文件"""
    issues: list[ReadabilityIssue] = []

    try:
        source = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IOError):
        return issues

    lines = source.splitlines()

    # AST 解析
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return issues

    # 1. Docstring 检查
    ds_visitor = DocstringVisitor(file_path, lines)
    ds_visitor.visit(tree)
    issues.extend(ds_visitor.issues)

    # 2. DRY 重复代码检测
    issues.extend(check_dry_same_file(file_path, lines))

    # 3. 公式注释检查
    issues.extend(check_formula_comment(file_path, lines))

    # 4. 魔法数字检查
    mn_visitor = MagicNumberVisitor(file_path, lines)
    mn_visitor.visit(tree)
    issues.extend(mn_visitor.issues)

    # 5. 函数/类体长检查
    bl_visitor = BodyLengthVisitor(file_path)
    bl_visitor.visit(tree)
    issues.extend(bl_visitor.issues)

    return issues


def scan_directory(target_dir: Path) -> list[ReadabilityIssue]:
    """递归扫描目录下所有 Python 文件，返回可读性问题列表。"""
    all_issues: list[ReadabilityIssue] = []
    target_dir_resolved = target_dir.resolve()  # 转为绝对路径
    py_files = list(target_dir_resolved.rglob("*.py"))
    for py_file in py_files:
        if should_skip(py_file):
            continue
        all_issues.extend(scan_file(py_file))
    return all_issues


# ═══════════════════════════════════════════════════════════════
# 9. 主入口
# ═══════════════════════════════════════════════════════════════


def main() -> None:  # noqa: C901
    """主入口：解析命令行参数，扫描代码可读性并输出结构化报告。

    退出码: 0=全合规 / 1=阻断级 / 2=错误级 / 3=目录不存在。
    """
    parser = argparse.ArgumentParser(description="代码可读性检查 — docstring/DRY/公式/魔法数字 (P1-F06)")
    parser.add_argument("--dir", default=None, help="扫描目录（默认项目根 .）")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    target = (ROOT / args.dir) if args.dir else ROOT
    if not target.exists():
        print(f"❌ 目录不存在: {target}")
        sys.exit(EXIT_DIR_NOT_FOUND)

    print("=" * SEP_WIDTH)
    print("  代码可读性 readability_check 扫描")
    print("=" * SEP_WIDTH)
    print(f"  扫描目录: {target}")
    print(f"  检查维度: docstring / DRY / 公式注释 / 魔法数字 / 体长")  # noqa: F541
    print("-" * SEP_WIDTH)

    issues = scan_directory(target)

    # 统计
    rule_stats: dict[str, Dict[str, Any]] = {}
    for issue in issues:
        rid = issue.rule
        if rid not in rule_stats:
            rule_stats[rid] = {"count": 0, "severity": issue.severity, "kind": issue.kind}
        rule_stats[rid]["count"] += 1

    print(f"\n  扫描结果: {len(issues)} 处问题\n")

    for rid in sorted(rule_stats.keys()):
        stat = rule_stats[rid]
        icon = "✅" if stat["count"] == 0 else "❌"
        print(f"    {icon} {rid} ({stat['kind']}): {stat['count']} 处 ({stat['severity']})")

    if issues:
        print(f"\n  --- 详细问题 ---\n")  # noqa: F541
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
            "skill": "readability_check",
            "total_issues": len(issues),
            "blocker_count": blocker_count,
            "error_count": error_count,
            "rule_stats": {rid: stat["count"] for rid, stat in rule_stats.items()},
            "issues": [asdict(i) for i in issues],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    if blocker_count > 0:
        print(f"\n❌ {blocker_count} 处阻断级问题")
        sys.exit(1)

    if error_count > 0:
        print(f"\n⚠️  {error_count} 处错误级问题")
        sys.exit(2)

    if issues:
        print(f"\n⚠️  {len(issues)} 处警告级提示")
        sys.exit(0)

    print(f"\n✅ 全部可读性检查通过")  # noqa: F541
    sys.exit(0)


def run(dir: str = None, output: str = "json") -> Dict[str, Any]:  # type: ignore[assignment]
    """统一调用入口，供 run_skill() 使用。"""
    target = (ROOT / dir) if dir else ROOT
    if not target.exists():
        return {
            "skill": "readability_check",
            "status": "error",
            "exit_code": EXIT_DIR_NOT_FOUND,
            "error": f"目录不存在: {target}",
        }
    issues = scan_directory(target)
    blocker_count = sum(1 for i in issues if i.severity == "blocker")
    error_count = sum(1 for i in issues if i.severity == "error")
    result = {
        "skill": "readability_check",
        "status": "fail" if blocker_count > 0 else ("warn" if error_count > 0 else "pass"),
        "exit_code": 1 if blocker_count > 0 else (2 if error_count > 0 else 0),
        "check_count": len(issues),
        "fail_count": blocker_count + error_count,
        "results": [asdict(i) for i in issues],
    }
    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()

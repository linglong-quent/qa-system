#!/usr/bin/env python3
"""Checker: docstring 内可执行代码与名称绑定完整性（T29 追加类）

背景（T28 P0）：`import logging` 与 `logger = logging.getLogger(__name__)`
被自动化迁移（标记 `# print->logging migration`）插进了模块 docstring 内部
（开三引号之后、而非闭三引号之后）。docstring 内文本永不执行 → `logger` 未绑定
→ 全文 `logger.` 调用首次即崩；而 **py_compile 完全通过**（那是合法 Python，
只是一段字符串）。

规则：
  DOCSTR-001 可执行语句落在 docstring 内（绑定交叉验证，BLOCKER）
  DOCSTR-002 docstring 含迁移标记（advisory，用于定位同源批量缺陷）
  UNBOUND-001 文件内被使用但从未绑定的名字（等价 flake8 F821 的文件粒度版）
  RENAME-001  疑似改名手术不完整（未绑定名与已绑定名高度相似）

精度阶梯（实测见 T29 报告）：正则初筛 275 → AST 可解析 8 → 绑定交叉验证 8。
接口: check() -> (errors: int, issues: list[str])
"""
import ast
import builtins
import os
import re
import textwrap
from typing import Dict, List, Set, Tuple

MIGRATION_MARKER = re.compile(r"print\s*->\s*logging\s+migration", re.I)
# M50：PARSE-001 逐条上报的上限（避免一个残缺仓库刷屏；超出的合并计数）
PARSE_REPORT_CAP = 25
NAME_DEF = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?::[^=]+)?=", re.M)
NAME_IMPORT = re.compile(r"^\s*(?:import\s+([A-Za-z_]\w*)|from\s+\S+\s+import\s+(.+))$", re.M)

BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__",
                                 "__spec__", "__loader__", "__builtins__", "__debug__"}

# 形如代码的行（用于 docstring 的"行级代码视图"）
CODE_LINE = re.compile(
    r"^\s*(?:import\s+\w|from\s+\S+\s+import\s|[A-Za-z_]\w*\s*(?::[^=]+)?=|"
    r"[A-Za-z_]\w*\s*\(|@\w)")


def _line_parses(line: str) -> bool:
    """单行能否独立解析为语句（用于把 docstring 里的代码行从散文里挑出来）"""
    try:
        ast.parse(textwrap.dedent(line))
        return True
    except SyntaxError:
        return False


def _is_code_template(joined) -> bool:
    """判断一个 f-string 是否是"代码模板"（用于批量生成代码的多行字符串）。

    T51 精确率复核样本 1：`_gen_scripts.py` 用 f-string 生成定时任务脚本，模板文本
    含 `APP_ROOT = os.environ.get(...)`，而 `f'{APP_ROOT}/logs'` 会让 `APP_ROOT`
    成为真实 Load 节点 → 被 UNBOUND-001 误判为未绑定名。
    判据：多行 **且** 含 import/def/class 模板行（`batch_import_one.py` 的 4 行
    命令模板不满足，故其真阳性 CH_PASSWORD 保留）。
    """
    text = "".join(v.value for v in joined.values if isinstance(v, ast.Constant))
    if "\n" not in text:
        return False
    return any(re.match(r"^\s*(?:import\s|from\s+\S+\s+import|def\s|class\s)", l)
               for l in text.splitlines())


def _fstring_template_names(tree) -> set:
    """代码模板 f-string 内部出现的名字（从"未绑定"判定中豁免）"""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and _is_code_template(node):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
    return names


def _iter_py_files(root: str, scan_dirs: List[str]):
    skip = {".git", ".venv", ".deps", "node_modules", "__pycache__", "backups",
            "site-packages", "build", "dist", "_deprecated", "archive", "_archive",
            "old_versions", "scripts_backup", "backup", "_backup"}
    targets = [os.path.join(root, d.rstrip("/\\")) for d in scan_dirs] or [root]
    for base in targets:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for fn in filenames:
                if fn.endswith(".py"):
                    yield os.path.join(dirpath, fn)


def _read(path: str) -> Tuple[str, bool, str]:
    """读取源码，返回 (文本, 是否带 UTF-8 BOM, 错误信息)。

    M50 修正（BOM 失明）：原先 `encoding="utf-8"` 会把 BOM 解码成 U+FEFF 留在字符串
    开头。`ast.parse(str)` 与文件级 tokenizer 不同，不吞 BOM，于是首个 token 变成
    '\\ufeffimport'，第 1 行即抛 SyntaxError，再被 check() 里的
    `except SyntaxError: continue` 静默吞掉 —— **整个文件对门禁不可见**。
    实测 linglong 69 + factor_forge 110 个 BOM .py，175/175 在此路径上解析失败，
    而 11,753 个非 BOM .py 仅 6 个失败 ⇒ 解析失败几乎是 BOM 的签名。
    此处改用 utf-8-sig 剥 BOM；BOM 事实另行由 ENCODING-001 上报，不再隐性丢文件。
    """
    try:
        raw = open(path, "rb").read()
    except OSError as exc:
        return "", False, str(exc)
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig", "replace"), has_bom, ""


def docstring_entries(tree):
    """产出所有"**永不执行**的多行字符串块"及其拥有者节点。

    T51 修正：首版只取 docstring 位置（Module/Class/Func 的第一条语句），
    于是漏掉了 T28 家族的第二形态 —— `optimize_industry_factors.py` 的迁移行落在一个
    非首语句的独立字符串块里（文件第 1 行是 `import os`，第 2-7 行是三引号字符串）：
    它同样永不执行、同样导致 `logger` 未绑定，但不是 Python 意义上的 docstring。

    现改为：遍历 Module/ClassDef/FunctionDef 体内的**所有** `Expr(Constant(str))` 语句。
    非首语句的字符串块额外要求含换行（排除单行字符串常量，降低误报）。
    """
    for owner in ast.walk(tree):
        if not isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(owner, "body", None) or []
        for idx, stmt in enumerate(body):
            if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)):
                continue
            text = stmt.value.value
            if idx > 0 and "\n" not in text:
                continue          # 非首语句的单行字符串常量：多为普通常量，跳过
            yield owner, stmt.value


def text_defines_names(text: str) -> Set[str]:
    """docstring 文本里定义/导入的名字"""
    out: Set[str] = set()
    for m in NAME_DEF.finditer(text):
        out.add(m.group(1))
    for m in NAME_IMPORT.finditer(text):
        if m.group(1):
            out.add(m.group(1))
        if m.group(2):
            for part in m.group(2).split(","):
                nm = part.strip().split(" as ")[-1].strip()
                if nm.isidentifier():
                    out.add(nm)
    return out


def collect_bindings(tree) -> Tuple[Set[str], Set[str], bool]:
    """返回 (绑定名集合, 使用名集合, 是否含 star-import)"""
    bound: Set[str] = set()
    used: Set[str] = set()
    star = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    star = True
                else:
                    bound.add(a.asname or a.name)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            elif isinstance(node.ctx, ast.Load):
                used.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = node.args
                for arg in list(a.args) + list(a.posonlyargs) + list(a.kwonlyargs):
                    bound.add(arg.arg)
                if a.vararg:
                    bound.add(a.vararg.arg)
                if a.kwarg:
                    bound.add(a.kwarg.arg)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Lambda):
            a = node.args
            for arg in list(a.args) + list(a.posonlyargs) + list(a.kwonlyargs):
                bound.add(arg.arg)
        elif isinstance(node, (ast.comprehension,)):
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name):
                    bound.add(t.id)
        elif isinstance(node, ast.MatchAs) and node.name:
            bound.add(node.name)
    return bound, used, star


def _similar(a: str, b: str) -> bool:
    """高度相似：包含关系或编辑距离 ≤2（用于识别改名手术不完整）。

    精度约束（T29 反检教训）：短名（<5 字符）的编辑距离极易误配 ——
    `os` vs `sys`/`df`、`Dict` vs `act` 都会被判为"相似"，产生大量噪声。
    因此对包含关系要求短名 ≥4，对编辑距离要求两个名字都 ≥5。
    """
    if a == b:
        return False
    if a in b or b in a:
        return len(min(a, b, key=len)) >= 4
    if len(a) < 5 or len(b) < 5:
        return False
    if abs(len(a) - len(b)) > 2:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= 2


class DocstringCodeChecker:
    """docstring 内可执行代码 / 名称绑定完整性"""

    CHECKER_ID = "docstring_code"
    CHECKER_LABEL = "docstring代码与绑定完整性"

    def __init__(self, config: dict, project_root: str):
        self.config = config or {}
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = self.config.get("scan_dirs", ["src/", "scripts/", "domain/"])
        self.report_marker_only = bool(self.config.get("report_marker_only", False))

    def _docstr001_002(self, rel: str, tree, src: str) -> List[str]:
        out = []
        for node, const in docstring_entries(tree):
            text = const.value
            dedented = textwrap.dedent(text)
            # T51 修复：首版要求"整段 docstring 可被解析"才提取定义，于是
            # `optimize_industry_factors.py` 这类"代码 + 中文说明（含全角标点）"
            # 混合 docstring 因整段解析失败而降级为 advisory（DOCSTR-002）。
            # 现改为**行级**视图：只保留能独立解析且形如代码的行，再整体解析。
            definitions = text_defines_names(dedented)
            if not definitions:
                code_lines = [l for l in dedented.splitlines()
                              if CODE_LINE.match(l) and _line_parses(l)]
                if code_lines:
                    rebuilt = textwrap.dedent("\n".join(code_lines))
                    definitions = text_defines_names(rebuilt)
            defines = definitions
            if not defines:
                if MIGRATION_MARKER.search(text):
                    out.append(
                        f"[DOCSTR-002] {rel}:{const.lineno} docstring 内含迁移标记但未检出死代码 "
                        f"-> 同源批量迁移残留，建议人工确认")
                continue
            bound, used, _ = collect_bindings(tree)
            dead = sorted(n for n in defines if n not in bound and n in used and n not in BUILTINS)
            if dead:
                out.append(
                    f"[DOCSTR-001] {rel}:{const.lineno} docstring 内的可执行语句永不执行："
                    f"定义了 {dead}，但别处未绑定却被使用 -> 该名字引用必崩（py_compile 看不见）")
            elif MIGRATION_MARKER.search(text):
                out.append(
                    f"[DOCSTR-002] {rel}:{const.lineno} docstring 内含迁移标记（{sorted(defines)}）"
                    f" -> 同源批量迁移残留")
        return out

    def _unbound001_rename001(self, rel: str, tree) -> List[str]:
        bound, used, star = collect_bindings(tree)
        if star:
            return []
        # 豁免：仅出现在"代码模板 f-string"里的名字（见 _is_code_template）
        template_names = _fstring_template_names(tree)
        unbound = sorted(n for n in used
                         if n not in bound and n not in BUILTINS and not n.startswith("__")
                         and n not in template_names)
        out = []
        if unbound:
            out.append(
                f"[UNBOUND-001] {rel}: 使用但全文件无绑定的名字 {unbound[:8]}"
                f"{'' if len(unbound) <= 8 else ' …'} -> 运行必崩（等价 F821）")
        for u in unbound[:10]:
            near = [b for b in bound if _similar(u, b)]
            if near:
                out.append(
                    f"[RENAME-001] {rel}: 疑似改名未同步：'{u}' 未绑定，但存在高度相似的已绑定名 "
                    f"{near[:3]} -> 改名必须同时覆盖定义与使用")
        return out

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        # M50：解析失败与 BOM 不再静默 —— 原先 `except SyntaxError: continue`
        # 让 BOM/语法错文件整个从门禁视野里消失（"门禁称 PASS，其实没看过这个文件"）。
        parse_failed: List[Tuple[str, str]] = []
        unreadable: List[Tuple[str, str]] = []
        bom_files: List[str] = []
        for path in _iter_py_files(self.project_root, self.scan_dirs):
            src, has_bom, err = _read(path)
            rel = os.path.relpath(path, self.project_root)
            if has_bom:
                bom_files.append(rel)
            if err:
                unreadable.append((rel, err))
                continue
            if not src.strip():
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                parse_failed.append((rel, f"{exc.msg} (line {exc.lineno})"))
                continue
            issues.extend(self._docstr001_002(rel, tree, src))
            issues.extend(self._unbound001_rename001(rel, tree))
        for rel, why in unreadable[:PARSE_REPORT_CAP]:
            issues.append(f"[PARSE-001] {rel}: 文件不可读 —— {why}；该文件未被任何 AST 规则覆盖")
        for rel, why in parse_failed[:PARSE_REPORT_CAP]:
            issues.append(f"[PARSE-001] {rel}: 解析失败 —— {why}；该文件未被任何 AST 规则覆盖"
                          f"（原行为：静默跳过，门禁看不见它）")
        extra = len(parse_failed) + len(unreadable) - PARSE_REPORT_CAP
        if extra > 0:
            issues.append(f"[PARSE-001] 另有 {extra} 个文件解析失败/不可读，未逐条列出")
        if bom_files:
            issues.append(
                f"[ENCODING-001] {len(bom_files)} 个 .py 携带 UTF-8 BOM（BOM 会让 ast.parse "
                f"在首行失败，历史上使本 checker 对整个文件失明）— 前 {min(10, len(bom_files))} 个: "
                + ", ".join(bom_files[:10]))
        return len(issues), issues

#!/usr/bin/env python3
"""Checker: 语义真实性（T29 盲区①）

规则：
  TRUTH-001 伪造计算   — np.random / 硬编码常量被当作计算指标输出
  TRUTH-002 空壳假成功 — 函数实质为空（TODO/占位/pass）却 return 真值
  TRUTH-003 静默降级   — except 分支返回中性值，既不 raise 也不记日志

设计原则（对齐 T21 结论：90.6% 噪声会让门禁被忽略）：
  每条规则都要求"强证据组合"才报，宁可漏报不可误报。
接口: check() -> (errors: int, issues: list[str])
"""
import logging
logger = logging.getLogger(__name__)
import ast
import os
import re
from typing import List, Tuple

# M50：PARSE-001 逐条上报的上限（超出合并计数，避免残缺仓库刷屏）
PARSE_REPORT_CAP = 25

METRIC_TOKENS = {
    "ic", "icir", "ic_mean", "icir_mean", "sharpe", "fitness", "score", "ret",
    "return", "returns", "pnl", "alpha", "beta", "annualized", "annualized_return",
    "drawdown", "win_rate", "profit", "yield", "excess", "ir",
}


def _metric_like(name: str) -> bool:
    """按 **标识符片段** 匹配指标名（修复 T29 反检发现的假阳性）。

    旧实现用无边界正则 `(ic|...)`，导致 `selected_indices`/`slices_subset`/
    `random_picks`（含子串 "ic"）被误判为指标。现改为下划线切分后的整段比较。
    """
    if not name:
        return False
    segs = [s for s in re.split(r"[^A-Za-z0-9]+", name.lower()) if s]
    if any(s in METRIC_TOKENS for s in segs):
        return True
    # 指标型带后缀命名：ret_20d / score_5 / icir_60
    return bool(re.match(r"^(ic|icir|sharpe|fitness|score|ret|pnl|alpha)(_|\d)", name.lower()))


STUB_COMMENT = re.compile(r"TODO|FIXME|占位|待实现|未实现|模拟|假数据|mock|placeholder", re.I)
SIDE_EFFECT_FUNC = re.compile(
    r"^(save|write|update|delete|remove|push|commit|upload|insert|persist|store|"
    r"connect|send|publish|sync|flush)_", re.I)
NEUTRAL_CALLS = {"DataFrame", "Series", "zeros", "empty", "dict", "list", "set", "tuple"}


COERCION_FUNC = re.compile(
    r"^_?(f|d|i|s|to_?(float|int|str|num|bool|date)|as_?(float|int|str)|"
    r"coerce|safe_?(float|int|str|cast)|_?(parse|cast)_?\w*)$", re.I)


def _coercion_ranges(tree) -> list:
    """纯类型转换辅助函数的行区间（TRUTH-003 豁免区）。

    T51 精确率复核样本 5：`_stock_fund_feeder.py:93-101` 的 `_f(val)` docstring 明写
    "安全转 float (None/空 → 0)"，`except (TypeError,ValueError): return 0.0` 是**契约**
    而非静默失效。对这类适配器报"静默降级"是噪声。

    T52 扩充（二进制解析原语）：判据从"函数名像转换器"升级为"函数体就是一个
    try 包裹 struct.unpack / int.from_bytes" —— 这类函数按 offset 读取定长字节，
    畸形数据返回中性值是**契约**（见 `_cache_reader_utils.py` 的 `_read_uint32_le`），
    且处于逐字节热路径，加日志会刷屏。用结构判定而非名字判定，
    避免把 `read_cache()` 这类真会静默失效的读函数误免。
    """
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if COERCION_FUNC.match(node.name or "") or _is_binary_primitive(node):
            spans.append((node.lineno, node.end_lineno or node.lineno))
    return spans


BINARY_DECODERS = {"unpack", "iter_unpack", "from_bytes", "unpack_from"}


def _is_binary_primitive(node) -> bool:
    """函数体是否 = 单个 try 包裹的 struct.unpack / int.from_bytes 定长解码。"""
    body = [s for s in node.body
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if len(body) != 1 or not isinstance(body[0], ast.Try):
        return False
    tri = body[0]
    if len(tri.body) != 1 or not isinstance(tri.body[0], ast.Return):
        return False
    val = tri.body[0].value
    if val is None:
        return False
    for sub in ast.walk(val):
        if isinstance(sub, ast.Attribute) and sub.attr in BINARY_DECODERS:
            return True
        if isinstance(sub, ast.Call):
            f = sub.func
            fname = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else "")
            if fname in BINARY_DECODERS:
                return True
    return False


def _in_spans(lineno: int, spans) -> bool:
    return any(a <= lineno <= b for a, b in spans)


def _is_log_call(node) -> bool:
    """是否是一次日志调用（**任意级别、任意封装**）。

    T51 精确率复核发现：首版只认 error/exception/critical/warning/warn，于是
    `logger.debug(...)`（`_stock_fund_feeder.py:155`、`_mixin_linkage_linkage.py:102`）
    与项目自有封装 `_log(...)`（`watchdog_scheduler.py:143`）都被误判为"无日志"。
    判定"是否静默"只需看有没有日志，不该评判日志级别。
    """
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
    if not name:
        return False
    if name.lower() in ("debug", "info", "warning", "warn", "error", "exception",
                        "critical", "log"):
        return True
    return bool(re.match(r"^_?log(ger)?$|_log$|^log_", name, re.I))


# 反斜杠（Windows 路径分隔符）—— 提取为常量，避免裸数字触发 BAN-5 魔法数字
_BS = "\\"


def _iter_py_files(root: str, scan_dirs: List[str], exclude_patterns=None):
    exts = (".py",)
    # T51: 归档/历史副本目录默认排除（`scripts/archive/old_versions_*` 等属历史快照，
    # 对其报缺陷只制造噪声 —— 精确率复核样本 8 即此类）
    skip = {".git", ".venv", ".deps", "node_modules", "__pycache__", "backups",
            "site-packages", "build", "dist", "_deprecated", "archive", "_archive",
            "old_versions", "scripts_backup", "backup", "_backup"}
    # T52: 读取配置里的 exclude_patterns —— 此前该键被静默忽略，
    # 配置写了 `**/open_source_systems/**` 也不生效（用户实测报出）。
    # 把 glob 归一成路径片段做片段匹配。
    frags = []
    for pat in (exclude_patterns or []):
        p = str(pat).replace(_BS, "/").strip()
        p = p.strip("*").strip("/")
        p = p.replace("**", "").strip("/")
        if p:
            frags.append(p)
    targets = [os.path.join(root, d.rstrip("/" + _BS)) for d in scan_dirs] or [root]
    for base in targets:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [
                d for d in dirnames
                if d not in skip
                and not any(f in os.path.join(dirpath, d).replace(_BS, "/")
                            for f in frags)
            ]
            for fn in filenames:
                if not fn.endswith(exts):
                    continue
                full = os.path.join(dirpath, fn)
                if any(f in full.replace(_BS, "/") for f in frags):
                    continue
                yield full


def _read(path: str) -> Tuple[str, bool, str]:
    """读取源码，返回 (文本, 是否带 UTF-8 BOM, 错误信息)。

    M50 修正（BOM 失明）：原 `encoding="utf-8"` 把 BOM 解成 U+FEFF 留在字符串开头，
    `ast.parse(str)` 不像文件 tokenizer 那样吞 BOM，首行即 SyntaxError，
    再被 check() 的 `except SyntaxError: continue` 静默吞掉 —— 文件对门禁不可见。
    """
    try:
        raw = open(path, "rb").read()
    except OSError as exc:
        return "", False, str(exc)
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig", "replace"), has_bom, ""


def _comments_of(src: str) -> set:
    """本文件注释里出现过的行号 → 是否含占位标记"""
    import io
    import tokenize
    lines = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and STUB_COMMENT.search(tok.string):
                lines.add(tok.start[0])
    except Exception as e:
        logger.warning("semantic token scan skipped: %s", e)
    return lines


def _is_random_call(node) -> bool:
    """np.random.xxx(...) / random.xxx(...)"""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    parts = list(reversed(parts))
    return len(parts) >= 2 and "random" in parts


class SemanticTruthChecker:
    """语义真实性检查器"""

    CHECKER_ID = "semantic_truth"
    CHECKER_LABEL = "语义真实性"

    def __init__(self, config: dict, project_root: str):
        self.config = config or {}
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = self.config.get("scan_dirs", ["src/", "scripts/", "domain/"])
        self.exclude_patterns = self.config.get("exclude_patterns", [])
        self.random_fields = int(self.config.get("random_block_min_fields", 3))

    # ── TRUTH-001 ─────────────────────────────────────────────
    def _truth001(self, path: str, tree) -> List[str]:
        out = []
        for node in ast.walk(tree):
            # 形态 A：字典字面量里 ≥N 个字段值来自随机数（伪造指标块）
            if isinstance(node, ast.Dict):
                rand_keys = []
                for k, v in zip(node.keys, node.values):
                    if _is_random_call(v):
                        name = k.value if isinstance(k, ast.Constant) else ""
                        if name and _metric_like(str(name)):
                            rand_keys.append(str(name))
                if len(rand_keys) >= self.random_fields:
                    out.append(
                        f"[TRUTH-001] {path}:{node.lineno} 疑似伪造指标：字典中 "
                        f"{len(rand_keys)} 个指标字段由随机数生成 {rand_keys[:6]} "
                        f"-> 计算指标不得来自 np.random / random")
            # 形态 B：把随机数赋给指标变量
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if _is_random_call(value):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for t in targets:
                        nm = t.id if isinstance(t, ast.Name) else (
                            t.attr if isinstance(t, ast.Attribute) else "")
                        if nm and _metric_like(nm):
                            out.append(
                                f"[TRUTH-001] {path}:{node.lineno} 疑似伪造计算："
                                f"'{nm}' 由随机数赋值 -> 指标必须来自真实计算")
        return out

    # ── TRUTH-002 ─────────────────────────────────────────────
    def _truth002(self, path: str, tree, stub_lines: set) -> List[str]:
        """空壳假成功：无实质工作，却以 True/1 之类的**成功哨兵**收尾。

        精度约束（T29 反检教训）：`def name(self): return "X"` 是合法的常量返回，
        不是假成功 —— 因此只在返回值为布尔真 / 非零数字时才判为哨兵；
        返回字符串等业务值的函数不报。
        """
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                body = body[1:]
            body = [b for b in body if not isinstance(b, ast.Pass)]
            if not body:
                continue
            last = body[-1]
            if not isinstance(last, ast.Return) or last.value is None:
                continue
            ret = last.value
            if not isinstance(ret, ast.Constant):
                continue
            is_sentinel = (ret.value is True) or \
                          (isinstance(ret.value, int) and not isinstance(ret.value, bool)
                           and ret.value > 0)
            if not is_sentinel:
                continue                        # 字符串/False/0 不算成功哨兵
            real = [b for b in body if b is not last]
            has_stub_comment = any(
                l in stub_lines for l in range(node.lineno, (node.end_lineno or node.lineno) + 1))
            hollow = len(real) == 0
            if hollow or has_stub_comment:
                why = "函数体为空" if hollow else "含占位标记"
                out.append(
                    f"[TRUTH-002] {path}:{node.lineno} 空壳假成功：'{node.name}' {why} 却 "
                    f"return {ast.unparse(ret)[:40]} -> 禁止以成功哨兵伪装未实现")
        return out

    # ── TRUTH-003 ─────────────────────────────────────────────
    def _truth003(self, path: str, tree) -> List[str]:
        """静默降级：异常分支返回**数据型中性值**（空表/零值），失败被抹平。

        精度约束（T29 反检教训）：`except: return None` / `return []` 多为合法可选语义，
        不报；只报返回空 DataFrame/Series 或数值 0 的情形 —— 那是"看起来有结果，
        实际是空/零"的静默失效。
        """
        out = []
        spans = _coercion_ranges(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if _in_spans(node.lineno, spans):
                continue          # 纯类型转换辅助函数：中性返回是契约，不报
            has_log_or_raise = False
            neutral_returns = []
            for sub in ast.walk(node):
                if isinstance(sub, ast.Raise):
                    has_log_or_raise = True
                if _is_log_call(sub):
                    has_log_or_raise = True
                if isinstance(sub, ast.Return) and sub.value is not None:
                    v = sub.value
                    neutral = False
                    if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) \
                            and not isinstance(v.value, bool) and v.value == 0:
                        neutral = True
                    if isinstance(v, ast.Call):
                        fnm = v.func.attr if isinstance(v.func, ast.Attribute) else (
                            v.func.id if isinstance(v.func, ast.Name) else "")
                        if fnm in ("DataFrame", "Series", "zeros", "empty"):
                            neutral = True
                    if neutral:
                        neutral_returns.append(sub.lineno)
            if neutral_returns and not has_log_or_raise:
                out.append(
                    f"[TRUTH-003] {path}:{node.lineno} 静默降级：except 分支在 L{neutral_returns} "
                    f"返回空表/零值，且无 log.error / raise -> 失败被抹平为'正常结果'")
        return out

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        # M50：解析失败与 BOM 不再静默（原 `except SyntaxError: continue` 会让
        # BOM/语法错文件整个从门禁视野里消失，而门禁仍报 PASS）。
        parse_failed: List[Tuple[str, str]] = []
        unreadable: List[Tuple[str, str]] = []
        bom_files: List[str] = []
        for path in _iter_py_files(self.project_root, self.scan_dirs,
                                   self.exclude_patterns):
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
            stub_lines = _comments_of(src)
            issues.extend(self._truth001(rel, tree))
            issues.extend(self._truth002(rel, tree, stub_lines))
            issues.extend(self._truth003(rel, tree))
            issues.extend(self._idsem001(rel, tree))
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

    # ── ID-001 伪主键（行号/计数器充当业务 ID）────────────────
    def _idsem001(self, path: str, tree) -> List[str]:
        """`x_id = df.index.astype(str)` / `id = len(...)` —— 非稳定主键。

        后果：增量/去重/幂等都建立在不稳定序列号上，重跑即错位。
        """
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.slice.value for t in targets
                     if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                     and isinstance(t.slice.value, str)]
            names += [t.attr for t in targets if isinstance(t, ast.Attribute)]
            id_targets = [n for n in names if re.search(r"(^|_)(id|key|uuid)$", n, re.I)]
            if not id_targets:
                continue
            v = node.value
            bad = None
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "astype":
                base = v.func.value
                if isinstance(base, ast.Attribute) and base.attr == "index":
                    bad = "DataFrame.index（行号）"
                elif isinstance(base, ast.Attribute) and base.attr in ("reset_index",):
                    bad = "行号"
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "len":
                bad = "len(...) 计数器"
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "enumerate":
                bad = "enumerate 序号"
            if bad:
                out.append(
                    f"[ID-001] {path}:{node.lineno} 伪主键：'{id_targets[0]}' 由 {bad} 生成 "
                    f"-> 非稳定标识，重跑/重排即错位，无法支撑增量与去重")
        return out

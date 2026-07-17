#!/usr/bin/env python3
"""Checker: detect lookahead bias in backtest / strategy code.

Rationale:
    Using shift(-N) without shift(1) or referencing future data in backtests
    introduces lookahead bias — the strategy appears profitable because it
    "sees" future data. All feature calculations must use shift(1) to align
    with the available information at prediction time.

References:
    - López de Prado, M. (2018). Advances in Financial ML, Chapter 14
    - KUN BAN-11 / G5A-009
"""

import ast
import os
import re
from typing import List, Tuple


class LookaheadChecker:
    """Detect lookahead / future-data references in backtest code."""

    def __init__(self, config: dict, project_root: str):
        self.project_root = project_root
        self.scan_dirs = config.get("scan_dirs", ["src/", "strategies/", "backtest/"])
        self.backtest_keywords = config.get("backtest_keywords", ["backtest", "回测", "strategy", "signal"])
        # Patterns that indicate lookahead
        self.patterns = [
            (re.compile(r"shift\(\s*-\d+\s*\)"), "shift(-N) 引用未来数据"),
            (re.compile(r"\.iloc\[\s*:\s*-\d+\s*\]"), "iloc[:, -N] 引用未来行"),
            (re.compile(r"\.shift\(\d+\)\s*[^)]*$\s*\n"), "shift(+N) 需要确认用途"),
            (re.compile(r"rolling\(\d+\)\.mean\(\)\.shift\(\s*-\d+\s*\)"), "rolling+shift(-N) 组合泄漏"),
        ]

    def _collect_py_files(self) -> List[str]:
        files = []
        for d in self.scan_dirs:
            full = os.path.join(self.project_root, d)
            if os.path.isdir(full):
                for root, _dirs, fnames in os.walk(full):
                    for fn in fnames:
                        if fn.endswith(".py"):
                            files.append(os.path.join(root, fn))
        return files

    def _is_backtest_file(self, relpath: str) -> bool:
        lower = relpath.lower()
        return any(kw.lower() in lower for kw in self.backtest_keywords)

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        for fpath in self._collect_py_files():
            rel = os.path.relpath(fpath, self.project_root)
            if not self._is_backtest_file(rel):
                continue

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                issues.append(f"[LOOKAHEAD-READ-ERR] {rel}: {e}")
                continue

            for pattern, desc in self.patterns:
                for m in re.finditer(pattern, content):
                    line_num = content[: m.start()].count("\n") + 1
                    issues.append(
                        f"[LOOKAHEAD-001] {rel}:{line_num} 疑似前视偏差: "
                        f"'{m.group()}' — {desc}. "
                        f"特征计算必须使用 shift(1) 对齐时间戳"
                    )

            # AST-level check: look for shift(-N) in function calls
            try:
                tree = ast.parse(content, filename=fpath)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "shift":
                        if node.args:
                            arg = node.args[0]
                            if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                                issues.append(
                                    f"[LOOKAHEAD-002] {rel}:{node.lineno} AST 检测 shift(-N) "
                                    f"-> 前视偏差，应使用 shift(1) 对齐"
                                )

        return len(issues), issues

#!/usr/bin/env python3
"""Checker: detect inplace=True in pandas calls — a known antipattern.

Rationale:
    pandas inplace=True is error-prone because it does not always operate
    in-place as the name suggests, and its behavior varies across methods.
    The recommended practice is explicit assignment.

References:
    - Pandas docs: "The inplace parameter is deprecated" (since 2.x)
    - KUN G5A-012: No inplace=True
"""

import ast
import os
from typing import List, Tuple


class InplaceChecker:
    """Detect pandas inplace=True in Python source files."""

    def __init__(self, config: dict, project_root: str):
        self.project_root = project_root
        self.scan_dirs = config.get("scan_dirs", ["src/", "scripts/"])

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

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        for fpath in self._collect_py_files():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=fpath)
            except (SyntaxError, UnicodeDecodeError) as e:
                rel = os.path.relpath(fpath, self.project_root)
                issues.append(f"[INPLACE-PARSE-ERR] {rel}: {e}")
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for kw in node.keywords:
                    if kw.arg == "inplace" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        rel = os.path.relpath(fpath, self.project_root)
                        issues.append(
                            f"[INPLACE-001] {rel}:{node.lineno} 使用 inplace=True (反模式) -> "
                            f"请使用显式赋值替代: df = df.dropna() 而非 df.dropna(inplace=True)"
                        )

        return len(issues), issues

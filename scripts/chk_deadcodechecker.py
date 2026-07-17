#!/usr/bin/env python3
"""Checker: detect orphan (unreferenced) public symbols — dead code.

Rationale:
    Dead code (functions, classes, and constants that are never imported)
    increases maintenance burden, confuses readers, and can hide bugs
    (CWE-561). Every public symbol should be used by at least one import
    in the project.

References:
    - CWE-561: Dead Code
    - KUN BAN-14 / G5A-010
    - Vulture (Python dead code detector) methodology
"""

import ast
import os
from typing import List, Set, Tuple


class DeadCodeChecker:
    """Detect orphan public functions, classes, and constants."""

    def __init__(self, config: dict, project_root: str):
        self.project_root = project_root
        self.scan_dirs = config.get("scan_dirs", ["src/", "scripts/", "tests/"])
        # Symbols whose names match these patterns are exempt
        self.exempt_names = config.get("exempt_names", [
            "main", "__init__", "__main__", "__version__", "__all__",
            "app", "application", "router", "run",
        ])
        self.entry_points = config.get("entry_points", ["main.py", "app.py", "cli.py"])

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

    def _extract_public_symbols(self, tree: ast.AST) -> List[str]:
        symbols = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith("_"):
                    symbols.append(node.name)
            elif isinstance(node, ast.AsyncFunctionDef):
                if not node.name.startswith("_"):
                    symbols.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    symbols.append(node.name)
            elif isinstance(node, ast.Assign):
                # Capture module-level public constants
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        symbols.append(target.id)
        return symbols

    def _extract_all_imports(self, py_files: List[str]) -> Set[str]:
        """Extract every name imported across all files."""
        imported = set()
        for fpath in py_files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=fpath)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.asname:
                            imported.add(alias.asname)
                        else:
                            imported.add(alias.name)
        return imported

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        py_files = self._collect_py_files()

        # Build the set of everything imported anywhere
        all_imported = self._extract_all_imports(py_files)

        # Track global-used names from entry points
        entry_point_imports: Set[str] = set()
        for ep in self.entry_points:
            ep_path = os.path.join(self.project_root, ep)
            if os.path.isfile(ep_path):
                try:
                    with open(ep_path, "r", encoding="utf-8") as f:
                        ep_tree = ast.parse(f.read(), filename=ep_path)
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for node in ast.walk(ep_tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            entry_point_imports.add(alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            entry_point_imports.add(alias.asname or alias.name)

        all_imported |= entry_point_imports

        # Check each file for orphan public symbols
        for fpath in py_files:
            rel = os.path.relpath(fpath, self.project_root)
            # Skip entry points themselves
            if os.path.basename(fpath) in self.entry_points:
                continue
            # Skip __init__.py — they are implicit entry points
            if os.path.basename(fpath) == "__init__.py":
                continue

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=fpath)
            except (SyntaxError, UnicodeDecodeError):
                continue

            symbols = self._extract_public_symbols(tree)
            for sym in symbols:
                if sym in self.exempt_names:
                    continue
                # Check if this symbol is imported anywhere in the project
                # (excluding the file that defines it)
                if sym not in all_imported:
                    issues.append(
                        f"[DEADCODE-001] {rel} 公共符号 '{sym}' 未被项目引用 "
                        f"-> 孤儿代码增加维护成本，确认无用后应删除或归档"
                    )

        return len(issues), issues

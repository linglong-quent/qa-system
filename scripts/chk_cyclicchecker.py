#!/usr/bin/env python3
"""Checker: detect circular imports in Python modules.

Rationale:
    Circular imports cause ImportError at runtime or create subtle
    initialization order bugs. Python semi-tolerates them, but they
    indicate poor module structure (violation of acyclic dependency
    principle).

References:
    - Martin, R. C. (2003). Clean Code: Acyclic Dependencies Principle
    - Python anti-pattern: cyclic imports
"""

import ast
import os
from collections import deque
from typing import Dict, List, Set, Tuple


class CyclicImportChecker:
    """Detect circular imports by analyzing AST import statements."""

    def __init__(self, config: dict, project_root: str):
        self.project_root = project_root
        self.scan_dirs = config.get("scan_dirs", ["src/", "scripts/"])
        self.skip_prefixes = config.get("skip_prefixes", ["test_", "tests."])

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

    def _module_name(self, fpath: str) -> str:
        """Convert file path to dotted module name."""
        rel = os.path.relpath(fpath, self.project_root)
        name = rel.replace(os.sep, ".").replace(".py", "").replace(".__init__", "")
        return name

    def _extract_imports(self, fpath: str) -> Set[str]:
        """Extract direct import targets from a Python file."""
        imports: Set[str] = set()
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fpath)
        except (SyntaxError, UnicodeDecodeError):
            return imports

        # Get package prefix from file path for relative imports
        rel_base = self._module_name(fpath)
        pkg_parts = rel_base.split(".")[:-1]  # parent package

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # Relative import
                    from_parts = pkg_parts[:]
                    # node.level counts dots: . = 1, .. = 2, etc.
                    if node.level <= len(pkg_parts):
                        from_parts = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                    else:
                        continue  # Go beyond root, skip
                    if node.module:
                        from_parts = from_parts + node.module.split(".")
                    from_module = ".".join(from_parts)
                else:
                    from_module = node.module or ""

                if from_module:
                    imports.add(from_module)

        return imports

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        py_files = self._collect_py_files()

        # Build module name -> file path mapping
        file_map: Dict[str, str] = {}
        for fpath in py_files:
            mod_name = self._module_name(fpath)
            file_map[mod_name] = fpath

        # Build import graph: module -> set of imported modules
        graph: Dict[str, Set[str]] = {}
        for fpath in py_files:
            mod_name = self._module_name(fpath)
            graph[mod_name] = self._extract_imports(fpath)

        # Detect cycles using DFS with recursion tracking
        def _find_cycles(
            node: str, path: List[str], visited: Set[str], stack: Set[str]
        ) -> List[List[str]]:
            cycles: List[List[str]] = []
            if node in stack:
                # Found a cycle — return the cycle path
                idx = path.index(node)
                cycles.append(path[idx:] + [node])
                return cycles
            if node in visited:
                return cycles

            visited.add(node)
            stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, set()):
                if neighbor in file_map:
                    cycles.extend(_find_cycles(neighbor, path, visited, stack))

            path.pop()
            stack.remove(node)
            return cycles

        visited_all: Set[str] = set()
        cycles_found: Set[str] = set()  # Dedup by canonical representation

        for mod in graph:
            if mod not in visited_all:
                cycles = _find_cycles(mod, [], set(), set())
                for cycle in cycles:
                    canon = " -> ".join(cycle)
                    if canon not in cycles_found:
                        cycles_found.add(canon)
                        file_refs = "; ".join(
                            f"{m} ({os.path.relpath(file_map.get(m, '?'), self.project_root)})"
                            for m in cycle
                        )
                        issues.append(
                            f"[CYCLIC-001] 检测到循环依赖: {' -> '.join(cycle)}\n"
                            f"   涉及文件: {file_refs}\n"
                            f"   -> 应遵循无环依赖原则重构模块结构"
                        )

        return len(issues), issues

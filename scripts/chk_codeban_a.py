#!/usr/bin/env python3
"""Extracted: CodeBanChecker — base class"""
import ast, os, re
from typing import List, Tuple


class CodeBanBase:
    SQL_KEYWORDS = {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "EXEC",
        "EXECUTE",
        "MERGE",
        "UNION",
        "INTO",
        "VALUES",
        "FROM",
        "WHERE",
    }

    def __init__(self, config: dict, project_root: str):
        self.config = config
        self.project_root = project_root
        # 默认配置（可由子类覆写）
        self.layers = config.get("layers", {})
        self.core_dirs = config.get("core_dirs", [])
        self.path_prefixes = config.get("path_prefixes", [])
        self.magic_whitelist = set(config.get("magic_whitelist", [1, 2, 3, 60, 100, 3600, 86400, 0, -1]))
        self.magic_keyword_whitelist = config.get("magic_keyword_whitelist", ["_PORT", "_TIMEOUT", "_MAX", "_MIN", "_THRESHOLD", "_SIZE", "_LIMIT", "_COUNT"])
        self.SQL_KEYWORDS = config.get("sql_keywords", CodeBanBase.SQL_KEYWORDS)

    def _collect_py_files(self) -> List[str]:
        py_files = []
        scan_dirs = self.config.get("scan_dirs", [])
        if scan_dirs:
            # 仅扫描配置指定的目录
            for d in scan_dirs:
                full = os.path.join(self.project_root, d)
                if not os.path.isdir(full):
                    continue
                for root, dirs, files in os.walk(full):
                    dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d not in ("__pycache__",)]
                    for f in files:
                        if f.endswith(".py"):
                            py_files.append(os.path.join(root, f))
        else:
            # 未指定 scan_dirs 时扫描整个项目
            for root, dirs, files in os.walk(self.project_root):
                dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d not in ("__pycache__",)]
                for f in files:
                    if f.endswith(".py"):
                        py_files.append(os.path.join(root, f))
        return py_files

    def _parse_ast(self, file_path: str):
        with open(file_path, encoding="utf-8") as f:
            return compile(f.read(), file_path, "exec", ast.PyCF_ONLY_AST)

    def _is_in_main_block(self, node) -> bool:
        for parent in ast.walk(node):
            if isinstance(parent, ast.If) and hasattr(parent, "test"):
                if isinstance(parent.test, ast.Compare) and hasattr(parent.test, "left"):
                    if isinstance(parent.test.left, ast.Name) and parent.test.left.id == "__name__":
                        return True
        return False

    def _annotate_parents(self, tree):
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                child.parent = node

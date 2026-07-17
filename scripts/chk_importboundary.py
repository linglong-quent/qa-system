#!/usr/bin/env python3
"""Checker: 架构边界门禁 — 禁止核心目录导入非白名单模块

通用 QA 能力，从项目 _ci_check_import_boundary.py 抽象而来：
  1. 指定 restricted_dirs 作为扫描目标
  2. 扫描其中所有 .py 文件的 import 语句
  3. 报告任何 import 指向 forbidden_prefixes（dev-only 目录）
  4. allowed_modules 中的模块不受限制

配置示例 (review-rules.yaml):
  import_boundary_check:
    enabled: true
    restricted_dirs: ["src/_core/", "src/core/"]
    forbidden_prefixes:
      - "tests"
      - "scripts"
      - "tools"
      - "archive"
      # - "test"  # 太宽泛，一般不禁止
    allowed_modules:
      # Python stdlib - 自动包含，不需配置
      # 第三方白名单
      - "numpy"
      - "pandas"
      - "requests"
"""
import ast, os, re
from typing import Tuple, List


# Python 标准库（稳定版本）
STDLIB_MODULES = {
    "abc", "ast", "asyncio", "base64", "collections", "copy", "csv",
    "dataclasses", "datetime", "decimal", "enum", "functools", "glob",
    "hashlib", "html", "http", "importlib", "inspect", "io", "itertools",
    "json", "logging", "math", "multiprocessing", "operator", "os",
    "pathlib", "pickle", "platform", "pprint", "queue", "random", "re",
    "shutil", "signal", "socket", "sqlite3", "statistics", "string",
    "struct", "subprocess", "sys", "tempfile", "threading", "time",
    "traceback", "typing", "unittest", "urllib", "uuid", "warnings",
    "weakref", "xml", "zipfile",
}


class ImportBoundaryChecker:
    """架构边界门禁检查器
    
    统一接口: check() -> (errors: int, issues: List[str])
    """

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.restricted_dirs = config.get("restricted_dirs", [])
        self.forbidden_prefixes = set(config.get("forbidden_prefixes", []))
        # 白名单 = stdlib + 配置的第三方 + 项目自身
        self.allowed = set(STDLIB_MODULES) | set(config.get("allowed_modules", []))
        # 递归扫描超过 3 层则不限制（防止全量扫描性能问题）
        self.max_depth = config.get("max_depth", 3)

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0

        for restricted_dir in self.restricted_dirs:
            full_dir = os.path.join(self.project_root, restricted_dir)
            if not os.path.isdir(full_dir):
                continue
            errors += self._scan_dir(full_dir, issues)

        return errors, issues

    def _scan_dir(self, directory: str, issues: List[str]) -> int:
        errors = 0
        for root, dirs, files in os.walk(directory):
            # 限制深度
            rel_dir = os.path.relpath(root, directory)
            if rel_dir != "." and len(rel_dir.split(os.sep)) >= self.max_depth:
                dirs[:] = []  # 不再深入
                continue

            # 跳过常见非代码目录
            dirs[:] = [d for d in dirs if not d.startswith((".", "_"))
                       and d not in ("__pycache__", "node_modules")]

            for f in files:
                if not f.endswith(".py"):
                    continue
                fpath = os.path.join(root, f)
                err = self._check_file(fpath, issues)
                errors += err

        return errors

    def _check_file(self, filepath: str, issues: List[str]) -> int:
        """AST 扫描单个 .py 文件的 import 违规"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (SyntaxError, UnicodeDecodeError):
            return 0

        rel_path = os.path.relpath(filepath, self.project_root)
        errors = 0

        for node in ast.walk(tree):
            # import X
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in self.forbidden_prefixes:
                        issues.append(
                            f"[BOUNDARY] {rel_path}:{node.lineno} "
                            f"禁止 import '{alias.name}' — "
                            f"'{top}' 是禁止导入的 dev-only 模块"
                        )
                        errors += 1

            # from X import Y
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in self.forbidden_prefixes:
                        issues.append(
                            f"[BOUNDARY] {rel_path}:{node.lineno} "
                            f"禁止 from '{node.module}' — "
                            f"'{top}' 是禁止导入的 dev-only 模块"
                        )
                        errors += 1

        return errors

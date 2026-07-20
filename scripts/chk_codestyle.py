#!/usr/bin/env python3
"""Checker: 代码风格检查（可读性 + 命名 + 文件名 + 常量 + 日志结构）

从量化项目 skill_readability_check/naming_check/filename_scan/
  constant_check/log_structure_check 提取通用模式，按 QA check() 接口重写。
"""
import os, re, ast
from typing import List, Tuple


class CodeStyleChecker:
    CHECKER_ID = "codestyle_check"
    CHECKER_LABEL = "代码风格"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/"])

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0

        for d in self.scan_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d not in ("__pycache__", "node_modules")]
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(fpath, self.project_root)
                    errs = self._check_file(fpath, rel)
                    errors += len(errs)
                    issues.extend(errs)

        return errors, issues

    def _check_file(self, fpath: str, rel: str) -> List[str]:
        issues = []
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
        except Exception:
            return []

        # 文件名检查（小写+下划线）
        basename = os.path.basename(fpath)
        if basename.endswith(".py") and basename != "__init__.py":
            if re.search(r"[A-Z\s-]", basename[:-3]):
                issues.append(f"[STYLE-01] {rel}: 文件名 '{basename}' 应使用小写+下划线")

        # 行长度检查
        for i, line in enumerate(lines, 1):
            if len(line) > 200 and not line.strip().startswith("#"):
                issues.append(f"[STYLE-02] {rel}:{i} 行过长 ({len(line)} 字符 > 200)")
                break  # 每文件只报一次

        # 文件总行数限制（不超过 500 行，保持代码聚焦）
        if len(lines) > 500:
            issues.append(f"[STYLE-05] {rel}: 文件 {len(lines)} 行 > 500，建议拆分为多个模块")

        # 函数/类命名检查
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not re.match(r'^_?[a-z][a-z0-9_]*$', node.name):
                        if node.name != node.name.upper():  # 允许全大写常量函数
                            issues.append(f"[STYLE-03] {rel}:{node.lineno} 函数名 '{node.name}' 应使用 snake_case")
                elif isinstance(node, ast.ClassDef):
                    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', node.name):
                        issues.append(f"[STYLE-03] {rel}:{node.lineno} 类名 '{node.name}' 应使用 PascalCase")
        except SyntaxError:
            pass

        # 日志结构检查
        if "import logging" in content:
            log_calls = re.findall(r'logging\.(info|debug|warning|error|critical)\(', content)
            fmt_logs = re.findall(r'f"[^"]*\{[^}]+\}[^"]*"', content)
            for match in re.finditer(r'logging\.(info|debug|warning|error|critical)\(f"', content):
                issues.append(f"[STYLE-04] {rel}:{content[:match.start()].count(chr(10))+1} "
                             f"日志应使用 %% 格式化而非 f-string")

        return issues

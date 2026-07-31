#!/usr/bin/env python3
"""Checker: 代码风格检查（可读性 + 命名 + 文件名 + 常量 + 日志结构 + 行数标准）

行业标准对齐：
  - NASA Power of 10: 函数 ≤ 60 行（配置可调）
  - Clean Code / ISO 25010: 类/文件 ≤ 500 行（配置可调）
  - PEP 8: 行长度 ≤ 120 字符
"""
import os, re, ast, logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class CodeStyleChecker:
    CHECKER_ID = "codestyle_check"
    CHECKER_LABEL = "代码风格"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/"])
        self.exclude_subdirs = set(config.get("exclude_subdirs", [
            "qa_tools", "_deprecated", "archive", "__pycache__", "node_modules",
        ]))

        # 从规则表读取行业标准阈值（Fallback: NASA 60 / Clean Code 500）
        nfr = config.get("nfr_baseline", {})
        self.max_function_lines = nfr.get("max_function_length_lines", 60)
        self.max_class_lines = nfr.get("max_class_length_lines", 500)

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0

        for d in self.scan_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d not in self.exclude_subdirs]
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(fpath, self.project_root)
                    errs = self._check_file(fpath, rel)
                    errors += len(errs)
                    issues.extend(errs)

        return errors, issues

    def _check_file(self, fpath: str, rel: str) -> List[str]:  # noqa: STYLE-06
        issues = []
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
        except Exception:
            return []

        # ── STYLE-01: 文件名小写+下划线 ──
        basename = os.path.basename(fpath)
        if basename.endswith(".py") and basename != "__init__.py":
            if re.search(r"[A-Z\s-]", basename[:-3]):
                issues.append(f"[STYLE-01] {rel}: 文件名 '{basename}' 应使用小写+下划线")

        # ── STYLE-02: 行长度 ≤ 120（PEP 8）──
        # 文件级豁免：首行含 # noqa: STYLE-02 时跳过
        style02_exempt = lines and "noqa" in lines[0].lower() and "STYLE-02" in lines[0]
        if not style02_exempt:
            for i, line in enumerate(lines, 1):
                if len(line) > 120 and not line.strip().startswith("#"):
                    issues.append(f"[STYLE-02] {rel}:{i} 行过长 ({len(line)} 字符 > 120)")
                    break

        # ── STYLE-05: 文件/类总行数 ≤ N（默认 500，ISO 25010）──
        if len(lines) > self.max_class_lines:
            if not (lines and "noqa" in lines[0].lower() and "STYLE-05" in lines[0]):
                issues.append(
                    f"[STYLE-05] {rel}: 文件 {len(lines)} 行 > {self.max_class_lines}"
                    f"，建议拆分为多个模块")

        # ── STYLE-03: 函数/类命名 ──
        # ── STYLE-06: 函数长度 ≤ N（NASA Power of 10）──
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # 命名检查（豁免 dunder 方法 __xxx__ 和名称修饰 __xxx）
                    is_dunder = node.name.startswith('__') and node.name.endswith('__')
                    is_name_mangled = node.name.startswith('__') and not node.name.endswith('_')
                    if not is_dunder and not is_name_mangled:
                        if not re.match(r'^_?[a-z][a-z0-9_]*$', node.name):
                            if node.name != node.name.upper():
                                issues.append(
                                    f"[STYLE-03] {rel}:{node.lineno} 函数名 '{node.name}' 应使用 snake_case")
                    # 函数行数检查：通过 AST 节点的 end_lineno 计算
                    if hasattr(node, 'end_lineno') and node.end_lineno:
                        func_lines = node.end_lineno - node.lineno + 1
                        if func_lines > self.max_function_lines:
                            # 尊重 # noqa: STYLE-06 豁免（def 行）
                            def_line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
                            if "noqa" in def_line.lower():
                                continue
                            issues.append(
                                f"[STYLE-06] {rel}:{node.lineno} 函数 '{node.name}' "
                                f"{func_lines} 行 > {self.max_function_lines}"
                                f"（NASA Power of 10）")
                elif isinstance(node, ast.ClassDef):
                    # 类命名检查（允许前导下划线的内部类 _ClassName）
                    class_name_to_check = node.name.lstrip('_')
                    if class_name_to_check and not re.match(r'^[A-Z][a-zA-Z0-9]*$', class_name_to_check):
                        # 全大写常量风格类名豁免（如 MEMORY_BASIC_INFORMATION 是 ctypes 结构体）
                        if node.name != node.name.upper():
                            issues.append(
                                f"[STYLE-03] {rel}:{node.lineno} 类名 '{node.name}' 应使用 PascalCase")
        except SyntaxError:
            logger.debug("AST 解析语法错误: %s", rel, exc_info=True)

        # ── STYLE-04: 日志格式 ──
        if "import logging" in content:
            for match in re.finditer(r'logging\.(info|debug|warning|error|critical)\(f"', content):
                issues.append(f"[STYLE-04] {rel}:{content[:match.start()].count(chr(10))+1} "
                             f"日志应使用 %% 格式化而非 f-string")

        return issues

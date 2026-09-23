#!/usr/bin/env python3
"""Checker: 安全增强（SQL 注入 + SQL 语法）

从量化项目 skill_sql_injection/ci_sqlfluff_gate 提取通用模式。
使用 AST 分析区分真注入风险与安全的动态 SQL（表名/占位符拼接）。
"""
import ast
import os
import re
import logging
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)


class SecurityPlusChecker:
    CHECKER_ID = "securityplus_check"
    CHECKER_LABEL = "安全增强"

    SQL_EXEC_METHODS = {
        "execute", "executemany", "executescript",
        "query", "raw", "run",
    }

    SAFE_WHITELIST_SUFFIXES = {
        "_table", "_tablename", "table_name", "tbl",
        "_column", "_col", "column_name",
        "placeholder", "placeholders", "ph",
        "where_clause", "where", "condition",
        "order_by", "order_clause",
        "group_by", "group_clause",
        "_value", "_val",
    }

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/"])

    def _collect_files(self) -> List[str]:
        files = []
        for d in self.scan_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, fnames in os.walk(full):
                dirs[:] = [d for d in dirs if not d.startswith((".", "_"))
                           and d not in ("__pycache__", "node_modules")]
                for fn in fnames:
                    if fn.endswith(".py"):
                        files.append(os.path.join(root, fn))
        return files

    def _is_safe_sql_variable(self, var_name: str) -> bool:
        """判断变量名是否属于安全的动态 SQL 片段（表名/占位符/条件等）"""
        name_lower = var_name.lower()
        for suffix in self.SAFE_WHITELIST_SUFFIXES:
            if name_lower.endswith(suffix):
                return True
        return False

    def _get_fstring_var_names(self, node: ast.JoinedStr) -> Set[str]:
        """提取 f-string 中所有变量名"""
        names = set()
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                if isinstance(value.value, ast.Name):
                    names.add(value.value.id)
                elif isinstance(value.value, ast.Call):
                    if isinstance(value.value.func, ast.Name):
                        names.add(value.value.func.id)
        return names

    def _is_from_dict_whitelist(self, var_name: str, func_node: ast.AST) -> bool:
        """检查变量是否来自字典白名单查找（如 tables.get(block_type)）"""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == var_name:
                        if isinstance(node.value, ast.Call):
                            if isinstance(node.value.func, ast.Attribute):
                                if node.value.func.attr in ("get", "pop"):
                                    return True
        return False

    def _find_sqli_in_tree(self, tree: ast.AST, rel_path: str) -> List[Tuple[int, str]]:
        """通过 AST 分析查找真正的 SQL 注入风险"""
        issues = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in self.SQL_EXEC_METHODS:
                continue
            if not node.args:
                continue

            first_arg = node.args[0]

            if isinstance(first_arg, ast.JoinedStr):
                var_names = self._get_fstring_var_names(first_arg)

                if not var_names:
                    continue

                all_safe = True
                for var_name in var_names:
                    if not self._is_safe_sql_variable(var_name):
                        all_safe = False
                        break

                if all_safe and var_names:
                    continue

                issues.append(
                    (node.lineno,
                     f"f-string SQL 注入风险 — 变量 {var_names} 未通过安全白名单验证。"
                     f"如为表名/占位符，请重命名为 *_table / placeholders 等白名单后缀")
                )

            elif isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Add):
                issues.append(
                    (node.lineno,
                     "字符串拼接 SQL — 存在 SQL 注入风险，请使用参数化查询")
                )

            elif isinstance(first_arg, ast.Mod):
                issues.append(
                    (node.lineno,
                     "% 格式化 SQL — 存在 SQL 注入风险，请使用参数化查询")
                )

        return issues

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        errors = 0

        for fpath in self._collect_files():
            rel = os.path.relpath(fpath, self.project_root)
            try:
                with open(fpath, "r", encoding="utf-8-sig", errors="replace") as fh:
                    content = fh.read()
            except Exception:
                logger.warning("读取安全扫描文件失败: %s", fpath, exc_info=True)
                issues.append(f"[PARSE-001] {rel}: 文件不可读；该文件未被安全扫描覆盖"
                              f"（原行为：仅 warning 后静默跳过）")
                continue

            try:
                tree = ast.parse(content, filename=fpath)
            except SyntaxError as exc:
                # M50：原为静默 `continue`（BOM 文件首行必抛 U+FEFF → 整个文件跳过
                # 安全扫描）。改为上报，读取用 utf-8-sig 剥 BOM。
                issues.append(f"[PARSE-001] {rel}: 解析失败 —— {exc.msg} (line {exc.lineno})；"
                              f"该文件未被安全扫描覆盖（原行为：静默跳过）")
                continue

            for lineno, desc in self._find_sqli_in_tree(tree, rel):
                issues.append(f"[SECP-01] {rel}:{lineno} {desc}")
                errors += 1

        return errors, issues

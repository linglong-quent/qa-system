#!/usr/bin/env python3
"""Checker: 安全增强（SQL 注入 + SQL 语法）

从量化项目 skill_sql_injection/ci_sqlfluff_gate 提取通用模式。
"""
import os, re
from typing import List, Tuple


class SecurityPlusChecker:
    CHECKER_ID = "securityplus_check"
    CHECKER_LABEL = "安全增强"

    SQLI_PATTERNS = [
        (re.compile(r'(?i)execute\(["\'].*\+.*["\']'), "字符串拼接 SQL"),
        (re.compile(r'(?i)execute\(f["\']'), "f-string SQL"),
        (re.compile(r'(?i)raw_input.*cursor\.execute'), "用户输入直传 SQL"),
        (re.compile(r'cursor\.execute\(["\'].*\%.*["\']'), "%% 格式化 SQL"),
    ]

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
                    if not f.endswith((".py", ".sql")):
                        continue
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(fpath, self.project_root)
                    try:
                        with open(fpath, "r", encoding="utf-8") as fh:
                            content = fh.read()
                    except Exception:
                        continue

                    # SQL 注入检测
                    for pattern, desc in self.SQLI_PATTERNS:
                        for match in pattern.finditer(content):
                            linenum = content[:match.start()].count("\n") + 1
                            issues.append(f"[SECP-01] {rel}:{linenum} {desc}")
                            errors += 1

        return errors, issues

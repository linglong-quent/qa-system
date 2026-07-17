#!/usr/bin/env python3
"""Checker: 零打印 — 禁止生产模块使用 print()

通用 QA 能力，从量化 skill_g5_scan 提取。
"""
import os, re
from typing import List, Tuple


class ZeroPrintChecker:
    CHECKER_ID = "zeroprint_check"
    CHECKER_LABEL = "零打印"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/", "linglong/"])
        self.banned_modules = config.get("banned_modules", ["core", "engine", "api"])

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
                    # 检查是否在禁用模块列表内
                    if not any(f"/{m}/" in f"/{rel}/" for m in self.banned_modules):
                        continue
                    try:
                        with open(fpath, "r", encoding="utf-8") as fh:
                            for lineno, line in enumerate(fh, 1):
                                stripped = line.strip()
                                if re.match(r'^print\s*\(', stripped) and "logger.setLevel" not in stripped:
                                    issues.append(f"[NOPRINT] {rel}:{lineno} 禁止 print()，使用 logging 替代")
                                    errors += 1
                    except Exception:
                        continue
        return errors, issues

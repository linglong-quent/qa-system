#!/usr/bin/env python3
"""Checker: 自定义规则引擎 — 可配置的 N 条业务规则

通用 QA 能力，从量化 skill_g5a_scan 提取。
"""
import os, re
from typing import List, Tuple


class CustomRulesChecker:
    CHECKER_ID = "customrules_check"
    CHECKER_LABEL = "自定义规则"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/"])
        self.rules = config.get("rules", [
            {"name": "禁止裸 except", "pattern": r"^\s*except\s*:", "severity": "BLOCKER"},
            {"name": "禁止 magic number", "pattern": r"^\s+return\s+[0-2]?[0-9]?[0-9]$", "severity": "WARN"},
            {"name": "日志必须带异常", "pattern": r"logging\.exception\(", "mode": "require"},
        ])

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
                    try:
                        content = open(fpath, "r", encoding="utf-8").read()
                    except Exception:
                        continue
                    for rule in self.rules:
                        pattern = rule.get("pattern", "")
                        name = rule.get("name", "?")
                        mode = rule.get("mode", "ban")
                        if mode == "require":
                            if not re.search(pattern, content, re.IGNORECASE):
                                issues.append(f"[CUSTOM-{name}] {rel}: 缺少 {rule.get('description', name)}")
                                errors += 1
                        else:
                            for match in re.finditer(pattern, content, re.MULTILINE):
                                linenum = content[:match.start()].count("\n") + 1
                                issues.append(f"[CUSTOM-{name}] {rel}:{linenum} {name}")
                                errors += 1
        return errors, issues

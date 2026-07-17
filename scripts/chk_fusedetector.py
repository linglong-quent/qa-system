#!/usr/bin/env python3
"""Checker: 熔断检测 — 检查外部调用是否有熔断/重试保护

通用 QA 能力，从量化 skill_fuse_detector 提取。
"""
import os, re
from typing import List, Tuple


class FuseDetectorChecker:
    CHECKER_ID = "fusedetect_check"
    CHECKER_LABEL = "熔断检测"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/"])
        self.trigger_patterns = config.get("triggers", [
            "requests", "urllib", "http", "socket", "grpc", 
            "cursor\\.execute", "conn\\.", "client\\.",
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
                        with open(fpath, "r", encoding="utf-8") as fh:
                            content = fh.read()
                    except Exception:
                        continue
                    if "retry" in content.lower() or "backoff" in content.lower():
                        continue  # 已有熔断保护
                    lines = content.split("\n")
                    for pattern_text in self.trigger_patterns:
                        for i, line in enumerate(lines):
                            if re.search(pattern_text, line, re.IGNORECASE):
                                issues.append(f"[FUSE] {rel}:{i+1} '{pattern_text}' 调用无 retry/backoff 保护")
                                errors += 1
        return errors, issues

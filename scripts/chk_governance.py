#!/usr/bin/env python3
"""Checker: 项目治理（目录结构 + 未使用资产 + 注册表一致性）

从量化项目 skill_dir_governance/skill_asset_scan/skill_registry_guard 提取。
"""
import os
from typing import List, Tuple


class GovernanceChecker:
    CHECKER_ID = "governance_check"
    CHECKER_LABEL = "项目治理"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.expected_structure = config.get("expected_dirs", ["src/", "tests/", "docs/", "scripts/"])

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0

        # 1. 目录结构检查
        for ed in self.expected_structure:
            full = os.path.join(self.project_root, ed)
            if not os.path.isdir(full):
                issues.append(f"[GOV-01] 期望目录 '{ed}' 不存在")
                errors += 1

        # 2. 顶层文件检查（不应过多）
        top_dir = self.project_root
        top_items = [f for f in os.listdir(top_dir)
                     if os.path.isfile(os.path.join(top_dir, f))
                     and not f.startswith((".", "_"))
                     and f not in ("README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml",
                                  "setup.py", "requirements.txt")]
        if len(top_items) > 15:
            issues.append(f"[GOV-02] 顶层目录文件过多 ({len(top_items)} 个)，建议移入子目录")
            errors += 1

        # 3. 未使用资产检查（__pycache__ 残留）
        pycache_count = 0
        for root, dirs, files in os.walk(self.project_root):
            pycache_count += dirs.count("__pycache__")
        if pycache_count > 5:
            issues.append(f"[GOV-03] 发现 {pycache_count} 个 __pycache__ 目录，建议清理并加入 .gitignore")
            errors += 1

        # 4. README.md 存在
        if not os.path.exists(os.path.join(self.project_root, "README.md")):
            issues.append("[GOV-04] 缺少 README.md")
            errors += 1

        return errors, issues

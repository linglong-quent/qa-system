#!/usr/bin/env python3
"""Extracted: NamingRuleChecker"""
import os, re
from typing import List
from chk_load_yaml import load_yaml


class NamingRuleChecker:
    """命名规则检测器 — 从 naming-rule.yaml 读取正则，验证文件名合规性"""

    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        naming_path = os.path.join(self.project_root, ".ai", "config", "naming-rule.yaml")
        self.rules = load_yaml(naming_path) if os.path.exists(naming_path) else {}
        self.issues: List[str] = []

    def check(self) -> List[str]:
        """检查文件命名是否符合 naming-rule.yaml 中定义的规则"""
        self.issues = []
        if not self.rules:
            return self.issues

        skip_dirs = {".git", "__pycache__", "_deprecated", "build", "dist", ".venv", "node_modules", ".workbuddy"}

        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                fpath = os.path.relpath(os.path.join(root, f), self.project_root)
                if f.endswith(".py") and f != "__init__.py":
                    self._check_python_file(f, fpath)
                if f.endswith(".yaml") and ".ai/config/" in fpath:
                    self._check_yaml_file(f, fpath)
                if f.endswith(".yml") and ".github/workflows/" in fpath:
                    self._check_ci_file(f, fpath)
        return self.issues

    def _check_python_file(self, filename: str, fpath: str):
        import re

        code_rules = self.rules.get("code", {})
        if "tests/" in fpath:
            test_pattern = code_rules.get("test", {}).get("file", {}).get("pattern", "")
            if test_pattern and not re.match(test_pattern, filename):
                self.issues.append(f"[NamingRule] 测试文件命名不合规: {fpath} (期望 {test_pattern})")
        else:
            file_pattern = code_rules.get("file", {}).get("pattern", "")
            if file_pattern and not re.match(file_pattern, filename):
                self.issues.append(f"[NamingRule] Python 文件命名不合规: {fpath} (期望 {file_pattern})")

    def _check_yaml_file(self, filename: str, fpath: str):
        import re

        rule_pattern = self.rules.get("config", {}).get("rule", {}).get("pattern", "")
        if rule_pattern and not re.match(rule_pattern, filename):
            self.issues.append(f"[NamingRule] 配置文件命名不合规: {fpath} (期望 {rule_pattern})")

    def _check_ci_file(self, filename: str, fpath: str):
        import re

        workflow_pattern = self.rules.get("ci", {}).get("workflow", {}).get("pattern", "")
        if workflow_pattern and not re.match(workflow_pattern, filename):
            self.issues.append(f"[NamingRule] CI workflow 命名不合规: {fpath} (期望 {workflow_pattern})")

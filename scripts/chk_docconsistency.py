#!/usr/bin/env python3
"""Checker: 文档一致性 — 代码中的公共符号是否有文档覆盖

通用 QA 能力，从量化 skill_doc_consistency 提取。
"""
import os, re, ast
from typing import List, Tuple


class DocConsistencyChecker:
    CHECKER_ID = "docconsistency_check"
    CHECKER_LABEL = "文档一致性"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.code_dirs = config.get("code_dirs", ["src/"])
        self.doc_dirs = config.get("doc_dirs", ["docs/"])

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0

        # 收集代码中的公共符号
        public_symbols = set()
        for d in self.code_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, files in os.walk(full):
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    fpath = os.path.join(root, f)
                    try:
                        tree = ast.parse(open(fpath, "r", encoding="utf-8").read())
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                                if not node.name.startswith("_"):
                                    public_symbols.add(node.name)
                    except Exception:
                        continue

        if not public_symbols:
            return 0, []

        # 收集文档中出现的符号引用
        doc_symbols = set()
        for d in self.doc_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, files in os.walk(full):
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    fpath = os.path.join(root, f)
                    try:
                        content = open(fpath, "r", encoding="utf-8").read()
                        # 文档中反引号引用的符号名和普通出现的函数/类名
                        refs = re.findall(r'`([a-z_]\w+(?:\(\))?)`', content, re.IGNORECASE)
                        refs += re.findall(r'`([A-Z]\w+)`', content)
                        doc_symbols.update(r.replace("()", "") for r in refs)
                    except Exception:
                        continue

        # 公共符号在文档中无引用
        undocumented = public_symbols - doc_symbols
        if undocumented:
            sample = list(sorted(undocumented))[:10]
            issues.append(f"[DOCCONSISTENCY] {len(undocumented)} 个公共符号文档中未引用: {', '.join(sample)}")
            errors += 1

        return errors, issues

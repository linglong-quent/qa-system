#!/usr/bin/env python3
"""Checker: 文档质量（文档结构 + Schema 验证 + 归档合规）

从量化项目 ai-doc-build/ai-doc-generate/ai-doc-scan 提取通用模式。
"""
import os, json
from typing import List, Tuple


class DocumentationChecker:
    CHECKER_ID = "documentation_check"
    CHECKER_LABEL = "文档质量"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.docs_dir = config.get("docs_dir", "docs/")
        self.require_schema = config.get("require_schema", False)

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0
        docs_path = os.path.join(self.project_root, self.docs_dir)

        if not os.path.isdir(docs_path):
            issues.append("[DOC-01] docs/ 目录不存在")
            return 1, issues

        md_files = []
        for root, dirs, files in os.walk(docs_path):
            for f in files:
                if f.endswith(".md"):
                    md_files.append(os.path.join(root, f))

        if not md_files:
            issues.append("[DOC-02] docs/ 中无 .md 文档")
            errors += 1

        # 文档必须包含标题
        for fpath in md_files:
            rel = os.path.relpath(fpath, self.project_root)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                if not first_line.startswith("#"):
                    issues.append(f"[DOC-03] {rel}: 文档缺少标题 (# Title)")
                    errors += 1
            except Exception:
                continue

        # WORM 归档合规（docs/ 内必须纯 md，无二进制）
        non_md = []
        for root, dirs, files in os.walk(docs_path):
            for f in files:
                if f.startswith("."):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext not in (".md", ".txt", ".json", ".yaml", ".yml", ".svg", ".png", ".jpg"):
                    non_md.append(os.path.relpath(os.path.join(root, f), self.project_root))
        if non_md:
            issues.append(f"[DOC-04] WORM 归档: 非标准文档格式共 {len(non_md)} 个")
            errors += 1

        # README.md 存在
        if not os.path.exists(os.path.join(self.project_root, "README.md")):
            issues.append("[DOC-05] 缺少 README.md")
            errors += 1

        return errors, issues

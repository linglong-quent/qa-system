#!/usr/bin/env python3
"""Extracted: GlossaryChecker"""
import os, re
from typing import List, Tuple
from chk_load_yaml import load_yaml


class GlossaryChecker:
    """扫描文档是否使用了 glossary.yaml 中 forbidden 的非标词"""

    def __init__(self, config: dict, project_root: str):
        """
        初始化术语检测器

        Args:
            config: review-rules.yaml 中 glossary_check 配置段
            project_root: 项目根目录
        """
        self.glossary_file = os.path.join(project_root, config.get("glossary_file", ".ai/config/glossary.yaml"))
        self.case_sensitive = config.get("case_sensitive", False)
        self.code_block_exempt = config.get("code_block_exempt", True)
        self.project_root = project_root
        self._forbidden_words = None

    @property
    def forbidden_words(self) -> List[str]:
        """加载术语表中的禁止词汇"""
        if self._forbidden_words is not None:
            return self._forbidden_words

        glossary = load_yaml(self.glossary_file)
        words = []

        for term_key, term_data in glossary.get("terms", {}).items():
            forbidden = term_data.get("forbidden", [])
            words.extend(forbidden)

        self._forbidden_words = words
        return words

    def check(self, md_file: str) -> Tuple[int, List[str]]:
        """
        检测单个 Markdown 文件的术语合规

        Args:
            md_file: Markdown 文件路径

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0
        max_deduction = 10
        per_issue = 2

        if not os.path.exists(md_file):
            return 0, [f"文件不存在: {md_file}"]

        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 移除代码块内容
        if self.code_block_exempt:
            content = re.sub(r"```[\s\S]*?```", "", content)

        # 检测每个禁止词
        for word in self.forbidden_words:
            if not word:
                continue

            search_word = word if self.case_sensitive else word.lower()
            search_content = content if self.case_sensitive else content.lower()

            count = search_content.count(search_word)
            if count > 0:
                issues.append(f"非标术语: '{word}' 出现 {count} 次")
                deduction = min(deduction + per_issue * count, max_deduction)

        return deduction, issues

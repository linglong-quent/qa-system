#!/usr/bin/env python3
"""Extracted: ReadabilityChecker"""
import os, re
from typing import List, Tuple, Optional


class ReadabilityChecker:
    """检查文档结构质量"""

    def __init__(self, config: dict, project_root: str):
        """
        初始化可读性检测器

        Args:
            config: review-rules.yaml 中 readability_check 配置段
            project_root: 项目根目录
        """
        self.max_heading_depth = config.get("max_heading_depth", 4)
        self.max_paragraph_chars = config.get("max_paragraph_chars", 500)
        self.code_block_ratio_min = config.get("code_block_ratio_min", 0.10)
        self.code_block_ratio_max = config.get("code_block_ratio_max", 0.60)
        self.project_root = project_root

    def check(self, md_file: str) -> Tuple[int, List[str]]:
        """
        检测单个文件的可读性

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0
        max_deduction = 5
        per_issue = 1

        if not os.path.exists(md_file):
            return 0, [f"文件不存在: {md_file}"]

        rel_path = os.path.relpath(md_file, self.project_root)

        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查标题层级
        max_depth = self._get_max_heading_depth(content)
        if max_depth > self.max_heading_depth:
            issues.append(f"标题层级过深: H{max_depth} > H{self.max_heading_depth} in {rel_path}")
            deduction = min(deduction + per_issue, max_deduction)

        # 检查段落长度
        long_paragraphs = self._check_paragraph_length(content)
        for para_len, line_num in long_paragraphs:
            issues.append(f"段落过长: {para_len} 字 > {self.max_paragraph_chars} in {rel_path}:{line_num}")
            deduction = min(deduction + per_issue, max_deduction)

        # 检查代码块占比
        code_ratio = self._get_code_block_ratio(content)
        if code_ratio is not None:
            if code_ratio < self.code_block_ratio_min:
                issues.append(f"代码块占比过低: {code_ratio:.0%} < {self.code_block_ratio_min:.0%} in {rel_path}")
                deduction = min(deduction + per_issue, max_deduction)
            elif code_ratio > self.code_block_ratio_max:
                issues.append(f"代码块占比过高: {code_ratio:.0%} > {self.code_block_ratio_max:.0%} in {rel_path}")
                deduction = min(deduction + per_issue, max_deduction)

        return deduction, issues

    def _get_max_heading_depth(self, content: str) -> int:
        """获取最大标题层级"""
        max_depth = 0
        for match in re.finditer(r"^(#+)\s+", content, re.MULTILINE):
            depth = len(match.group(1))
            if depth > max_depth:
                max_depth = depth
        return max_depth

    def _check_paragraph_length(self, content: str) -> List[Tuple[int, int]]:
        """检查段落长度，返回超长段落列表"""
        long_paragraphs = []
        lines = content.split("\n")
        current_para = []
        current_start = 0

        for i, line in enumerate(lines):
            if line.strip() == "" or line.startswith("#") or line.startswith("```"):
                if current_para:
                    para_text = " ".join(current_para)
                    if len(para_text) > self.max_paragraph_chars:
                        long_paragraphs.append((len(para_text), current_start + 1))
                    current_para = []
                    current_start = i + 1
            else:
                if not current_para:
                    current_start = i
                current_para.append(line.strip())

        if current_para:
            para_text = " ".join(current_para)
            if len(para_text) > self.max_paragraph_chars:
                long_paragraphs.append((len(para_text), current_start + 1))

        return long_paragraphs

    def _get_code_block_ratio(self, content: str) -> Optional[float]:
        """计算代码块占比"""
        total_chars = len(content)
        if total_chars == 0:
            return None

        code_chars = 0
        in_code = False
        for match in re.finditer(r"```[\s\S]*?```", content):
            code_chars += len(match.group(0))

        return code_chars / total_chars if total_chars > 0 else 0

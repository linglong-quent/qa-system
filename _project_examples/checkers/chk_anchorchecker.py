#!/usr/bin/env python3
"""Extracted: AnchorChecker"""
import os, re
from typing import List, Dict, Tuple


class AnchorChecker:
    """扫描代码 [DOC-REF] 标记，检查文档中是否有对应锚点"""

    def __init__(self, config: dict, project_root: str):
        """
        初始化锚点检测器

        Args:
            config: review-rules.yaml 中 anchor_check 配置段
            project_root: 项目根目录
        """
        self.doc_ref_pattern = re.compile(config.get("pattern", r"#\s*\[DOC-REF:\s*([^\]]+)\]"))
        self.anchor_pattern = re.compile(config.get("anchor_pattern", r"\{#([^}]+)\}"))
        self.check_orphan = config.get("check_orphan", True)
        self.project_root = project_root

    def check(self, docs_dir: str) -> Tuple[int, List[str]]:
        """
        检测锚点完整性

        Args:
            docs_dir: docs 目录路径

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0
        max_deduction = 20  # V2.0: anchor_complete 满分 20
        per_issue = 5

        # Step 1: 扫描 src/ 中的所有 [DOC-REF] 标记
        doc_refs = self._scan_doc_refs(os.path.join(self.project_root, "src"))

        # Step 2: 扫描 docs/ 中的所有锚点 ID
        doc_anchors = self._scan_doc_anchors(docs_dir)

        # Step 3: 检查每个 [DOC-REF] 是否有对应文档和锚点
        for ref in doc_refs:
            doc_path, anchor_id = ref
            full_doc_path = os.path.join(docs_dir, doc_path + ".md")

            # 检查文档文件是否存在
            if not os.path.exists(full_doc_path):
                issues.append(f"文档缺失: [DOC-REF: {doc_path}] → {full_doc_path} 不存在")
                deduction = min(deduction + per_issue, max_deduction)
                continue

            # 检查锚点是否存在（如果指定了锚点）
            if anchor_id:
                if anchor_id not in doc_anchors.get(full_doc_path, set()):
                    issues.append(f"锚点缺失: [DOC-REF: {doc_path}#{anchor_id}] → 文档中无此锚点")
                    deduction = min(deduction + per_issue, max_deduction)

        return deduction, issues

    def _scan_doc_refs(self, src_dir: str) -> List[Tuple[str, str]]:
        """
        扫描 src/ 中的所有 [DOC-REF] 标记

        Returns:
            [(文档路径, 锚点ID), ...]
        """
        refs = []

        if not os.path.exists(src_dir):
            return refs

        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                if not fname.endswith(".py"):
                    continue

                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        for match in self.doc_ref_pattern.finditer(line):
                            ref_str = match.group(1).strip()
                            # 解析: path/to/doc#anchor
                            if "#" in ref_str:
                                doc_path, anchor_id = ref_str.rsplit("#", 1)
                            else:
                                doc_path, anchor_id = ref_str, ""
                            refs.append((doc_path.strip(), anchor_id.strip()))

        return refs

    def _scan_doc_anchors(self, docs_dir: str) -> Dict[str, set]:
        """
        扫描 docs/ 中所有 Markdown 文件的锚点 ID

        Returns:
            {文件路径: {锚点ID, ...}, ...}
        """
        anchors = {}

        if not os.path.exists(docs_dir):
            return anchors

        for root, dirs, files in os.walk(docs_dir):
            for fname in files:
                if not fname.endswith(".md"):
                    continue

                fpath = os.path.join(root, fname)
                anchor_set = set()

                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()

                for match in self.anchor_pattern.finditer(content):
                    anchor_set.add(match.group(1).strip())

                anchors[fpath] = anchor_set

        return anchors

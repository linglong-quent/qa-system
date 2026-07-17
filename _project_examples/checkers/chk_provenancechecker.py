#!/usr/bin/env python3
"""Extracted: ProvenanceChecker"""
import os, json, re
from typing import List, Tuple


class ProvenanceChecker:
    """检查 AI 生成文档的 provenance 记录完整性"""

    def __init__(self, config: dict, project_root: str):
        """
        初始化 Provenance 检测器

        Args:
            config: review-rules.yaml 中 provenance_check 配置段
            project_root: 项目根目录
        """
        self.prov_suffix = config.get("prov_suffix", ".prov.json")
        self.required_fields = config.get(
            "required_fields",
            [
                "doc_path",
                "generated_by",
                "model.name",
                "prompt.hash",
                "sources",
                "generated_at",
                "confidence",
                "review_status",
                "schema_version",
                # V2.0-A++ 新增: Git 变更追溯字段（ISO 27001 A.12.4 / SLSA Level 2）
                "git.commit_hash",
                "git.branch",
                "ci.triggered_by",
                "ci.environment",
            ],
        )
        self.blocking_statuses = config.get("blocking_statuses", ["pending", "rejected", "needs_revision"])
        self.low_confidence_threshold = config.get("low_confidence_threshold", 0.7)
        self.project_root = project_root

    def check(self, docs_dir: str) -> Tuple[int, List[str]]:
        """
        检测所有 AI 生成文档的 provenance 完整性

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0
        max_deduction = 15
        per_issue = 5

        if not os.path.exists(docs_dir):
            return 0, []

        for root, dirs, files in os.walk(docs_dir):
            dirs[:] = [d for d in dirs if d not in (".build", "archive")]
            for fname in files:
                if not fname.endswith(".md"):
                    continue

                md_path = os.path.join(root, fname)
                prov_path = md_path + self.prov_suffix

                # 检查文档是否包含 [PROV:] 标记
                with open(md_path, "r", encoding="utf-8") as f:
                    content = f.read()

                has_prov_marker = "[PROV:" in content or "[prov:" in content

                if has_prov_marker:
                    # 检查 .prov.json 是否存在
                    if not os.path.exists(prov_path):
                        issues.append(
                            f"Provenance 缺失: {os.path.relpath(md_path, self.project_root)} 标注了 [PROV:] 但缺少 .prov.json"
                        )
                        deduction = min(deduction + per_issue, max_deduction)
                        continue

                    # 检查 .prov.json 字段完整性
                    prov_issues = self._check_prov_fields(prov_path, md_path)
                    issues.extend(prov_issues)
                    deduction = min(deduction + per_issue * len(prov_issues), max_deduction)

        return deduction, issues

    def _check_prov_fields(self, prov_path: str, md_path: str) -> List[str]:
        """检查 provenance 记录的字段完整性"""
        issues = []

        try:
            with open(prov_path, "r", encoding="utf-8") as f:
                prov = json.load(f)
        except Exception as e:
            return [f"Provenance 解析失败: {os.path.relpath(md_path, self.project_root)} - {e}"]

        # 检查必填字段
        for field in self.required_fields:
            if "." in field:
                # 嵌套字段（如 model.name）
                parts = field.split(".")
                value = prov
                for part in parts:
                    if not isinstance(value, dict) or part not in value:
                        issues.append(f"Provenance 字段缺失: {field} in {os.path.relpath(md_path, self.project_root)}")
                        break
                    value = value[part]
            else:
                if field not in prov:
                    issues.append(f"Provenance 字段缺失: {field} in {os.path.relpath(md_path, self.project_root)}")

        # 检查 review_status
        review_status = prov.get("review_status", "")
        if review_status in self.blocking_statuses:
            issues.append(
                f"Provenance 阻断: review_status={review_status} in {os.path.relpath(md_path, self.project_root)}"
            )

        # 检查置信度
        confidence = prov.get("confidence", 0)
        if confidence < self.low_confidence_threshold:
            issues.append(
                f"Provenance 低置信度: confidence={confidence} < {self.low_confidence_threshold} in {os.path.relpath(md_path, self.project_root)}"
            )

        return issues

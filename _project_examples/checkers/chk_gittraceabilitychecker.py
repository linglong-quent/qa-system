#!/usr/bin/env python3
"""Extracted: GitTraceabilityChecker"""
import os, json, re
from typing import List, Tuple


class GitTraceabilityChecker:
    """
    检测 .prov.json 中的 Git 变更追溯完整性

    审计链路: 代码变更(Git commit) → CI 触发 → AI 生成 → .prov.json(含 commit_hash)
    → 评分验证 → WORM 归档

    检测项:
    1. 每个有 [PROV:] 标记的文档对应的 .prov.json 包含 git.commit_hash
    2. commit_hash 格式正确（至少 7 位 hex，完整 40 位推荐）
    3. 同一 CI run 生成的所有 .prov.json 的 commit_hash 一致
    4. artifact_hash 存在且格式正确（SLSA Level 3）

    对应标准: ISO 27001 A.12.4 / CMMI CM SP 1.3 / SOC 2 CC7.2 / SLSA Level 2-3
    """

    def __init__(self, config: dict, project_root: str):
        """
        初始化 Git 追溯检测器

        Args:
            config: review-rules.yaml 中 git_traceability_check 配置段
            project_root: 项目根目录
        """
        self.max_deduction = config.get("max_deduction", 5)
        self.deduction_per_issue = config.get("deduction_per_issue", 2)
        self.require_artifact_hash = config.get("require_artifact_hash", True)
        self.min_hash_length = config.get("min_hash_length", 7)
        self.full_hash_length = config.get("full_hash_length", 40)
        self.check_consistency = config.get("check_consistency", True)
        self.project_root = project_root

    def check(self, docs_dir: str) -> Tuple[int, List[str]]:
        """
        检测所有 .prov.json 的 Git 追溯完整性

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0
        all_hashes = {}  # commit_hash -> [file_list]

        if not os.path.exists(docs_dir):
            return 0, []

        for root, dirs, files in os.walk(docs_dir):
            dirs[:] = [d for d in dirs if d not in (".build", "archive")]
            for fname in files:
                if not fname.endswith(".prov.json"):
                    continue

                prov_path = os.path.join(root, fname)
                rel_path = os.path.relpath(prov_path, self.project_root)

                try:
                    with open(prov_path, "r", encoding="utf-8") as f:
                        prov = json.load(f)
                except Exception as e:
                    issues.append(f"Git追溯: .prov.json 解析失败: {rel_path} - {e}")
                    deduction = min(deduction + self.deduction_per_issue, self.max_deduction)
                    continue

                # 检测1: git.commit_hash 存在
                git_info = prov.get("git", {})
                commit_hash = git_info.get("commit_hash", "")

                if not commit_hash:
                    issues.append(f"Git追溯: commit_hash 缺失 in {rel_path}")
                    deduction = min(deduction + self.deduction_per_issue, self.max_deduction)
                elif not self._is_valid_hash(commit_hash):
                    issues.append(f"Git追溯: commit_hash 格式无效 '{commit_hash[:20]}' in {rel_path}")
                    deduction = min(deduction + self.deduction_per_issue, self.max_deduction)
                else:
                    # 收集 hash 用于一致性检测
                    if commit_hash not in all_hashes:
                        all_hashes[commit_hash] = []
                    all_hashes[commit_hash].append(rel_path)

                # 检测2: git.branch 存在
                branch = git_info.get("branch", "")
                if not branch:
                    issues.append(f"Git追溯: branch 缺失 in {rel_path}")
                    deduction = min(deduction + self.deduction_per_issue, self.max_deduction)

                # 检测3: artifact_hash 存在且格式正确（SLSA Level 3）
                if self.require_artifact_hash:
                    artifact_hash = prov.get("artifact_hash", "")
                    if not artifact_hash:
                        issues.append(f"Git追溯: artifact_hash 缺失 in {rel_path}")
                        deduction = min(deduction + self.deduction_per_issue, self.max_deduction)
                    elif not artifact_hash.startswith("sha256:") or len(artifact_hash) != 71:
                        issues.append(f"Git追溯: artifact_hash 格式无效 in {rel_path}")
                        deduction = min(deduction + self.deduction_per_issue, self.max_deduction)

                # 检测4: ci.environment 存在
                ci_info = prov.get("ci", {})
                environment = ci_info.get("environment", "")
                if not environment:
                    issues.append(f"Git追溯: ci.environment 缺失 in {rel_path}")
                    deduction = min(deduction + self.deduction_per_issue, self.max_deduction)

        # 检测5: 同一 CI run 的 commit_hash 一致性
        if self.check_consistency and len(all_hashes) > 1:
            hash_summary = "; ".join(f"{h[:8]}({len(files)}个文件)" for h, files in all_hashes.items())
            issues.append(
                f"Git追溯: commit_hash 不一致（{len(all_hashes)}种）— {hash_summary}。"
                f"同一 CI run 生成的文档应共享同一 commit_hash"
            )
            deduction = min(deduction + self.deduction_per_issue, self.max_deduction)

        return deduction, issues

    def _is_valid_hash(self, hash_str: str) -> bool:
        """
        验证 Git commit hash 格式

        Args:
            hash_str: 待验证的 hash 字符串

        Returns:
            True 如果格式正确（7-40 位 hex 字符）
        """
        # 移除可能的 "unknown" 占位值
        if hash_str in ("unknown", "", "HEAD"):
            return False
        # 验证 hex 格式（7-40 位）
        try:
            int(hash_str, 16)
            return self.min_hash_length <= len(hash_str) <= self.full_hash_length
        except ValueError:
            return False

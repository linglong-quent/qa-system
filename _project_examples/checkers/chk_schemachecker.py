#!/usr/bin/env python3
"""Extracted: SchemaChecker"""
import os, re
from typing import List, Tuple, Optional
from chk_load_yaml import load_yaml


class SchemaChecker:
    """检查文档内容是否符合 JSON Schema 定义"""

    def __init__(self, config: dict, project_root: str):
        """
        初始化 Schema 检测器

        Args:
            config: review-rules.yaml 中 schema_check 配置段
            project_root: 项目根目录
        """
        self.check_required_sections = config.get("check_required_sections", True)
        self.project_root = project_root
        # 加载内容类型配置
        self.content_types = load_yaml(os.path.join(project_root, ".ai/config/content-types.yaml"))

    def check(self, md_file: str) -> Tuple[int, List[str]]:
        """
        检测单个文件的 Schema 合规

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0
        max_deduction = 10
        per_issue = 3

        if not os.path.exists(md_file):
            return 0, [f"文件不存在: {md_file}"]

        rel_path = os.path.relpath(md_file, self.project_root)

        # 确定内容类型
        content_type = self._get_content_type(rel_path)
        if not content_type:
            # 无映射的文件，跳过 schema 检测
            return 0, []

        # 获取该类型的 schema 要求
        type_config = self.content_types.get("types", {}).get(content_type, {})
        schema_config = type_config.get("schema", {})
        required_sections = schema_config.get("required_sections", [])

        if not required_sections:
            return 0, []

        # 读取文档内容
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取标题
        headings = re.findall(r"^#+\s+(.+)$", content, re.MULTILINE)

        # 检查必填章节
        for section in required_sections:
            # 简单匹配：检查标题中是否包含章节关键词
            found = any(section.lower() in h.lower() for h in headings)
            if not found:
                issues.append(f"Schema 缺失必填章节: '{section}' in {rel_path}")
                deduction = min(deduction + per_issue, max_deduction)

        return deduction, issues

    def _get_content_type(self, rel_path: str) -> Optional[str]:
        """从路径映射确定内容类型"""
        # 规范化路径分隔符（Windows 兼容）
        rel_path = rel_path.replace("\\", "/")
        path_mapping = self.content_types.get("path_mapping", [])
        for entry in path_mapping:
            pattern = entry.get("path", "")
            if self._match_pattern(rel_path, pattern):
                return entry.get("type")
        return None

    def _match_pattern(self, path: str, pattern: str) -> bool:
        """简单通配符匹配（** → .*, * → [^/]*）"""
        regex = pattern.replace("**", "\x00").replace("*", "[^/]*").replace("\x00", ".*")
        return bool(re.match(regex, path))

#!/usr/bin/env python3
"""Extracted: ParamChecker"""
import os, re
from typing import List, Dict, Tuple
from chk_load_yaml import load_yaml


class ParamChecker:
    """对比文档参数表与 YAML 源文件的实际值"""

    def __init__(self, config: dict, project_root: str):
        """
        初始化参数检测器

        Args:
            config: review-rules.yaml 中 param_check 配置段
            project_root: 项目根目录
        """
        self.yaml_sources = config.get("yaml_sources", [])
        self.type_coerce = config.get("type_coerce", True)
        self.nest_separator = config.get("nest_separator", ".")
        self.row_exempt_keywords = config.get("row_exempt_keywords", ["示例值", "参考值"])
        self.table_pattern = re.compile(config.get("table_pattern", r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"))
        self.project_root = project_root
        # V2.0-A++ 盲区2修复：自动发现 config YAML
        self.auto_discover = config.get("auto_discover", True)
        self.auto_discover_dirs = config.get("auto_discover_dirs", [".ai/config/", "config/"])
        self.auto_discover_docs_dir = config.get("auto_discover_docs_dir", "docs/config/")

    def check(self) -> Tuple[int, List[str]]:
        """
        检测所有参数表镜像的一致性

        V2.0-A++ 盲区2修复：自动发现 config/ 下所有 YAML 文件

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0
        max_deduction = 25  # V2.0: param_consistency 满分 25
        per_issue = 10

        # 显式配置的 YAML 源
        for source in self.yaml_sources:
            yaml_path = os.path.join(self.project_root, source["source"])
            docs_path = os.path.join(self.project_root, source["docs"])

            if not os.path.exists(yaml_path):
                issues.append(f"YAML 源文件不存在: {source['source']}")
                deduction = min(deduction + per_issue, max_deduction)
                continue

            if not os.path.exists(docs_path):
                issues.append(f"参数文档不存在: {source['docs']}")
                deduction = min(deduction + per_issue, max_deduction)
                continue

            # 加载 YAML 参数
            yaml_params = self._load_yaml_params(yaml_path)
            if not yaml_params:
                continue

            # 加载文档中的参数表
            doc_params = self._load_doc_params(docs_path)

            # 对比参数
            mismatches = self._compare_params(yaml_params, doc_params, source["source"])
            for mismatch in mismatches:
                issues.append(mismatch)
                deduction = min(deduction + per_issue, max_deduction)

        # V2.0-A++ 盲区2修复：自动发现额外的 config YAML
        if self.auto_discover:
            auto_issues = self._auto_discover_yaml_sources()
            for issue in auto_issues:
                issues.append(issue)
                deduction = min(deduction + per_issue, max_deduction)

        return deduction, issues

    def _auto_discover_yaml_sources(self) -> List[str]:
        """自动发现 config 目录下的 YAML 文件并检查文档覆盖

        对每个未在 yaml_sources 中显式声明的 YAML 文件:
        - 尝试在 docs/config/ 下找对应的 .md 文件
        - 如果找到 → 交叉验证参数一致性
        - 如果未找到 → 报告"配置 YAML 无文档镜像"

        Returns:
            问题列表
        """
        issues = []

        # 已显式声明的 YAML 文件集合（相对路径）
        declared_yamls = set()
        for source in self.yaml_sources:
            declared_yamls.add(source["source"].replace("\\", "/"))

        for search_dir in self.auto_discover_dirs:
            dir_path = os.path.join(self.project_root, search_dir)
            if not os.path.isdir(dir_path):
                continue

            for root, dirs, files in os.walk(dir_path):
                for fname in files:
                    if not (fname.endswith(".yaml") or fname.endswith(".yml")):
                        continue

                    yaml_abs = os.path.join(root, fname)
                    yaml_rel = os.path.relpath(yaml_abs, self.project_root).replace("\\", "/")

                    # 跳过已显式声明的
                    if yaml_rel in declared_yamls:
                        continue

                    # 尝试找对应的文档文件
                    # .ai/config/glossary.yaml → docs/config/glossary.md
                    base_name = fname.rsplit(".", 1)[0]
                    doc_path = os.path.join(self.project_root, self.auto_discover_docs_dir, base_name + ".md")

                    if not os.path.exists(doc_path):
                        # 文档不存在 — 跳过（不是所有 config YAML 都需要文档镜像）
                        continue

                    # 文档存在，交叉验证
                    yaml_params = self._load_yaml_params(yaml_abs)
                    if not yaml_params:
                        continue

                    doc_params = self._load_doc_params(doc_path)
                    mismatches = self._compare_params(yaml_params, doc_params, yaml_rel)
                    issues.extend(mismatches)

        return issues

    def _load_yaml_params(self, yaml_path: str) -> Dict[str, str]:
        """加载 YAML 参数并展平为 {key: str_value}"""
        data = load_yaml(yaml_path)
        flattened = {}

        def _flatten(obj, prefix=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key = f"{prefix}{self.nest_separator}{k}" if prefix else k
                    _flatten(v, key)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    key = f"{prefix}[{i}]"
                    _flatten(v, key)
            else:
                # 类型转换
                if self.type_coerce:
                    flattened[prefix] = str(obj).strip()
                else:
                    flattened[prefix] = obj

        _flatten(data)
        return flattened

    def _load_doc_params(self, docs_path: str) -> Dict[str, str]:
        """从 Markdown 表格中提取参数"""
        params = {}

        if not os.path.exists(docs_path):
            return params

        with open(docs_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取表格行
        for match in self.table_pattern.finditer(content):
            key = match.group(1).strip()
            value = match.group(2).strip()

            # 跳过表头
            if key in ("参数名", "参数", "Parameter", "名称", "---"):
                continue

            # 跳过分隔行
            if re.match(r"^[-:]+$", key):
                continue

            # 跳过豁免行
            if any(kw in value for kw in self.row_exempt_keywords):
                continue

            params[key] = value

        return params

    def _compare_params(self, yaml_params: Dict, doc_params: Dict, source_name: str) -> List[str]:
        """对比 YAML 参数与文档参数"""
        mismatches = []

        for key, yaml_value in yaml_params.items():
            if key in doc_params:
                doc_value = doc_params[key]
                # 类型转换后比较
                if str(yaml_value).strip() != str(doc_value).strip():
                    mismatches.append(f"参数不一致 [{source_name}]: {key} → YAML={yaml_value}, 文档={doc_value}")

        return mismatches

#!/usr/bin/env python3
"""Extracted: DocCoverageChecker"""
import os, re
from typing import List, Tuple
from chk_load_yaml import load_yaml


class DocCoverageChecker:
    """统计 public class/function 的文档覆盖率

    解决盲区：无 public API 文档覆盖率检测 — 不检查每个 public
    class/function 是否有对应文档。
    """

    def __init__(self, config: dict, project_root: str):
        """
        初始化文档覆盖率检测器

        Args:
            config: review-rules.yaml 中 doc_coverage_check 配置段
            project_root: 项目根目录
        """
        self.project_root = project_root
        self.max_deduction = config.get("max_deduction", 5)
        self.per_issue = config.get("deduction_per_issue", 2)
        self.min_coverage = config.get("min_coverage", 0.60)
        # 加载 doc-owned.yaml 映射
        self.doc_owned = load_yaml(os.path.join(project_root, ".ai/config/doc-owned.yaml"))
        # 加载 nodoc 列表
        self.nodoc_patterns = self.doc_owned.get("nodoc", [])

    def check(self) -> Tuple[int, List[str]]:
        """
        检测所有 1:1 和 N:1 映射的文档覆盖率

        Returns:
            (扣分数, 问题列表)
        """
        import ast

        issues = []
        deduction = 0

        mappings = self.doc_owned.get("mappings", [])
        for mapping in mappings:
            mode = mapping.get("mode", "")
            if mode not in ("1:1", "N:1"):
                continue

            source = mapping.get("source", "")
            docs = mapping.get("docs", "")
            mid = mapping.get("id", "")

            source_path = os.path.join(self.project_root, source)
            docs_path = os.path.join(self.project_root, docs)

            if not os.path.exists(source_path):
                continue

            # 提取 public API
            public_apis = self._extract_public_apis(source_path)
            if not public_apis:
                continue

            # 检查文档是否存在
            if not os.path.exists(docs_path):
                issues.append(f"文档覆盖率 [{mid}]: 文档路径不存在 {docs}，" f"{len(public_apis)} 个 public API 无文档")
                deduction = min(deduction + self.per_issue, self.max_deduction)
                continue

            # 检查每个 public API 是否在文档中被提及
            doc_content = self._read_doc_content(docs_path)
            undocumented = []
            for api_name in public_apis:
                # 兼容 ClassName.method_name 和纯 method_name
                # 如果是 ClassName.method_name，也检查 method_name 部分
                search_names = [api_name]
                if "." in api_name:
                    short_name = api_name.split(".", 1)[1]
                    search_names.append(short_name)

                found = any(name in doc_content for name in search_names)
                if not found:
                    undocumented.append(api_name)

            if undocumented:
                coverage = 1 - len(undocumented) / len(public_apis)
                if coverage < self.min_coverage:
                    issues.append(
                        f"文档覆盖率 [{mid}]: {len(undocumented)}/{len(public_apis)} "
                        f"API 未文档化 (覆盖率 {coverage:.0%} < {self.min_coverage:.0%}): "
                        f"{', '.join(undocumented[:5])}"
                    )
                    deduction = min(deduction + self.per_issue, self.max_deduction)

        return deduction, issues

    def _extract_public_apis(self, source_path: str) -> List[str]:
        """提取 public class/function 名称"""
        import ast

        apis = []

        py_files = []
        if os.path.isfile(source_path) and source_path.endswith(".py"):
            py_files = [source_path]
        elif os.path.isdir(source_path):
            for root, dirs, files in os.walk(source_path):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fname in files:
                    if fname.endswith(".py"):
                        py_files.append(os.path.join(root, fname))

        for py_file in py_files:
            # 跳过 nodoc 文件
            rel_path = os.path.relpath(py_file, self.project_root).replace("\\", "/")
            if self._is_nodoc(rel_path):
                continue

            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=py_file)
            except (SyntaxError, UnicodeDecodeError):
                continue

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        apis.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    if not node.name.startswith("_"):
                        apis.append(node.name)
                        # 也提取 class 内的 public 方法
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if not item.name.startswith("_"):
                                    apis.append(f"{node.name}.{item.name}")

        return apis

    def _read_doc_content(self, docs_path: str) -> str:
        """读取文档目录下所有 Markdown 内容"""
        content = ""

        md_files = []
        if os.path.isfile(docs_path) and docs_path.endswith(".md"):
            md_files = [docs_path]
        elif os.path.isdir(docs_path):
            for root, dirs, files in os.walk(docs_path):
                for fname in files:
                    if fname.endswith(".md"):
                        md_files.append(os.path.join(root, fname))

        for md_file in md_files:
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content += f.read() + "\n"
            except (IOError, UnicodeDecodeError):
                continue

        return content

    def _is_nodoc(self, rel_path: str) -> bool:
        """检查路径是否在 nodoc 列表中"""
        for pattern in self.nodoc_patterns:
            regex = pattern.replace("**", "\x00").replace("*", "[^/]*").replace("\x00", ".*")
            if re.match(regex, rel_path):
                return True
        return False

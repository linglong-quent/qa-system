#!/usr/bin/env python3
"""Extracted: DocRefEnforcer"""
import os, re
from typing import List, Dict, Tuple
from chk_load_yaml import load_yaml


class DocRefEnforcer:
    """强制每个 public function/class 必须有 [DOC-REF] 标记

    解决盲区：[DOC-REF] 是自愿的 — 无强制要求每个 public
    function 必须有标记指向其文档位置。

    工作原理:
      1. AST 提取 src/ 下所有 public class/function
      2. 检查每个定义所在的源文件是否有 [DOC-REF] 注释
      3. 缺失 [DOC-REF] 的 public API → 扣分（归属 anchor_complete 维度）
    """

    # [DOC-REF: path/to/doc#anchor] 注释模式
    DOC_REF_PATTERN = re.compile(r"#\s*\[DOC-REF:\s*([^\]]+)\]")

    def __init__(self, config: dict, project_root: str):
        """
        初始化 [DOC-REF] 强制检测器

        Args:
            config: review-rules.yaml 中 doc_ref_enforce 配置段
            project_root: 项目根目录
        """
        self.project_root = project_root
        self.max_deduction = config.get("max_deduction", 5)
        self.per_issue = config.get("deduction_per_issue", 1)
        # 加载 doc-owned.yaml 获取 src 目录范围
        self.doc_owned = load_yaml(os.path.join(project_root, ".ai/config/doc-owned.yaml"))
        # nodoc 列表
        self.nodoc_patterns = self.doc_owned.get("nodoc", [])

    def check(self) -> Tuple[int, List[str]]:
        """
        检测所有映射的 public API 是否有 [DOC-REF] 标记

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
            mid = mapping.get("id", "")

            source_path = os.path.join(self.project_root, source)
            if not os.path.exists(source_path):
                continue

            # 提取 public API 和其所在文件
            public_apis = self._extract_public_apis_with_files(source_path)
            if not public_apis:
                continue

            # 检查每个文件是否有 [DOC-REF] 标记
            for py_file, apis_in_file in public_apis.items():
                rel_py = os.path.relpath(py_file, self.project_root).replace("\\", "/")

                # 跳过 nodoc
                if self._is_nodoc(rel_py):
                    continue

                # 读取文件内容检查 [DOC-REF]
                try:
                    with open(py_file, "r", encoding="utf-8") as f:
                        content = f.read()
                except (IOError, UnicodeDecodeError):
                    continue

                has_doc_ref = bool(self.DOC_REF_PATTERN.search(content))

                if not has_doc_ref:
                    # 文件中无任何 [DOC-REF] 标记
                    api_names = [a for a in apis_in_file][:3]  # 只展示前3个
                    issues.append(
                        f"[DOC-REF] 缺失 [{mid}]: {rel_py} "
                        f"含 {len(apis_in_file)} 个 public API "
                        f"({', '.join(api_names)}...) 但无 [DOC-REF] 标记"
                    )
                    deduction = min(deduction + self.per_issue, self.max_deduction)

        return deduction, issues

    def _extract_public_apis_with_files(self, source_path: str) -> Dict[str, List[str]]:
        """提取 public API 及其所在文件

        Returns:
            {文件路径: [api_name, ...]}
        """
        import ast

        result = {}

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
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=py_file)
            except (SyntaxError, UnicodeDecodeError):
                continue

            apis = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        apis.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    if not node.name.startswith("_"):
                        apis.append(node.name)
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if not item.name.startswith("_"):
                                    apis.append(f"{node.name}.{item.name}")

            if apis:
                result[py_file] = apis

        return result

    def _is_nodoc(self, rel_path: str) -> bool:
        """检查路径是否在 nodoc 列表中"""
        for pattern in self.nodoc_patterns:
            regex = pattern.replace("**", "\x00").replace("*", "[^/]*").replace("\x00", ".*")
            if re.match(regex, rel_path):
                return True
        return False

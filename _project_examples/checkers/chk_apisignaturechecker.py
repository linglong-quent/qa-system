#!/usr/bin/env python3
"""Extracted: APISignatureChecker"""
import os, re
from typing import List, Dict, Tuple
from chk_load_yaml import load_yaml


class APISignatureChecker:
    """AST 提取函数签名，与文档参数表对比

    解决盲区：无 API 签名漂移检测 — 函数参数变更但文档未更新。
    """

    # Markdown 中函数签名模式: ### `function_name(param1, param2)`
    FUNC_PATTERN = re.compile(r"#+\s*`?(\w+)\s*\(([^)]*)\)`?")

    def __init__(self, config: dict, project_root: str):
        """
        初始化 API 签名检测器

        Args:
            config: review-rules.yaml 中 api_signature_check 配置段
            project_root: 项目根目录
        """
        self.project_root = project_root
        self.max_deduction = config.get("max_deduction", 5)
        self.per_issue = config.get("deduction_per_issue", 2)
        # 加载 doc-owned.yaml 映射
        self.doc_owned = load_yaml(os.path.join(project_root, ".ai/config/doc-owned.yaml"))

    def check(self) -> Tuple[int, List[str]]:
        """
        检测所有 1:1 映射的 API 签名一致性

        Returns:
            (扣分数, 问题列表)
        """
        import ast

        issues = []
        deduction = 0

        mappings = self.doc_owned.get("mappings", [])
        for mapping in mappings:
            # 仅检测 1:1 模式（强绑定的 API 文档）
            mode = mapping.get("mode", "")
            if mode != "1:1":
                continue

            source = mapping.get("source", "")
            docs = mapping.get("docs", "")
            mid = mapping.get("id", "")

            source_path = os.path.join(self.project_root, source)
            docs_path = os.path.join(self.project_root, docs)

            if not os.path.exists(source_path):
                continue

            # 提取源代码中的函数签名
            code_signatures = self._extract_signatures(source_path)
            if not code_signatures:
                continue

            # 提取文档中的函数参数表
            doc_params = self._extract_doc_params(docs_path)

            # 对比签名
            for func_name, sig in code_signatures.items():
                doc_param_names = doc_params.get(func_name)
                if doc_param_names is None:
                    continue  # 文档中无此函数的参数表，跳过（由 DocCoverageChecker 检测）

                # 对比参数名
                code_args = sig["args"]
                if code_args != doc_param_names:
                    issues.append(
                        f"API 签名漂移 [{mid}]: 函数 {func_name}() "
                        f"代码参数={code_args}, 文档参数={doc_param_names} "
                        f"(源: {sig['file']}:{sig['line']})"
                    )
                    deduction = min(deduction + self.per_issue, self.max_deduction)

        return deduction, issues

    def _extract_signatures(self, source_path: str) -> Dict[str, dict]:
        """使用 AST 提取 Python 源码中的 public 函数签名"""
        import ast

        signatures = {}

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

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # 跳过 private 函数
                    if node.name.startswith("_"):
                        continue

                    # 提取参数名列表
                    args = []
                    for arg in node.args.args:
                        args.append(arg.arg)

                    # 剥离 self / cls（方法首参数，文档不记录）
                    if args and args[0] in ("self", "cls"):
                        args = args[1:]

                    # 添加 *args 和 **kwargs
                    if node.args.vararg:
                        args.append(f"*{node.args.vararg.arg}")
                    if node.args.kwarg:
                        args.append(f"**{node.args.kwarg.arg}")

                    # 默认值数量（用于判断哪些参数可选）
                    n_defaults = len(node.args.defaults)

                    signatures[node.name] = {
                        "args": args,
                        "n_defaults": n_defaults,
                        "file": os.path.relpath(py_file, self.project_root),
                        "line": node.lineno,
                    }

        return signatures

    def _extract_doc_params(self, docs_path: str) -> Dict[str, List[str]]:
        """
        从文档目录中提取函数参数表

        返回: {函数名: [参数1, 参数2, ...]}
        """
        result = {}

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
                    content = f.read()
            except (IOError, UnicodeDecodeError):
                continue

            for match in self.FUNC_PATTERN.finditer(content):
                func_name = match.group(1)
                params_str = match.group(2).strip()

                if not params_str:
                    result[func_name] = []
                    continue

                # 解析参数列表
                params = []
                for p in params_str.split(","):
                    p = p.strip()
                    # 去掉类型注解: param: int → param
                    if ":" in p:
                        p = p.split(":")[0].strip()
                    # 去掉默认值: param=default → param
                    if "=" in p:
                        p = p.split("=")[0].strip()
                    if p:
                        params.append(p)

                result[func_name] = params

        return result

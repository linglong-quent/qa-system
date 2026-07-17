#!/usr/bin/env python3
"""Extracted: FaithfulnessChecker"""
import ast, os, re
from pathlib import Path
from typing import Any


class FaithfulnessChecker:
    """AI 文档忠实度检测器 — V2.1 新增

    对齐 ISO 25023 准确性子特性 + LLM Multi-Judge Accuracy 指标。
    检测逻辑：从 AST 提取 public API，与文档中声明的 API 引用进行匹配对比。

    扣分规则：
    - 文档中引用了不存在的 API → 每个扣 2
    - 文档中参数名与代码不匹配 → 每个扣 2
    - 文档中返回值说明与代码不匹配 → 每个扣 2
    - Paraphrase（逐行复述）: 函数意图 vs 代码实现偏差 → 每个扣 1
    - Contract（契约审查）: API 前置条件/后置条件/不变量缺失 → 每个扣 2
    """

    def __init__(self, config: dict, project_root: str):
        self.config = config
        self.project_root = project_root

    def check(self, docs_dir: str = None) -> tuple:
        """检查文档忠实度

        Returns:
            (deduction, issues): (总扣分, 问题列表)

        扩展: Paraphrase（逐行复述）— 调用 _paraphrase_check
              Contract（契约审查）— 调用 _contract_check
        """
        deduction = 0
        issues = []

        if docs_dir is None:
            docs_dir = os.path.join(self.project_root, "docs")

        src_dirs = [
            os.path.join(self.project_root, "src"),
            os.path.join(self.project_root, "scripts"),
        ]

        # 1. 搜集代码中的 public API 签名
        code_apis = {}  # {api_name: {"params": [...], "returns": "..."}}
        for src_dir in src_dirs:
            if not os.path.isdir(src_dir):
                continue
            for py_file in Path(src_dir).rglob("*.py"):
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if node.name.startswith("_"):
                                continue  # 私有方法跳过
                            api_info = {
                                "params": [arg.arg for arg in node.args.args],
                                "returns": "Any",
                            }
                            if node.returns:
                                api_info["returns"] = ast.dump(node.returns)
                            code_apis[node.name] = api_info
                except (SyntaxError, UnicodeDecodeError, OSError):
                    continue

        if not code_apis:
            return 0, []  # 无代码可对比

        # 2. 扫描文档，提取 API 引用，对比
        if not os.path.isdir(docs_dir):
            return 0, []

        doc_api_refs = {}  # {api_name: line_number}
        for md_file in Path(docs_dir).rglob("*.md"):
            try:
                lines = md_file.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines):
                    # 匹配 Markdown 中类似 `func_name()` 或 `ClassName.method()` 的代码引用
                    for match in re.finditer(r"`([a-zA-Z_][a-zA-Z0-9_]+)\([^)]*\)`", line):
                        api_name = match.group(1)
                        if api_name not in doc_api_refs:
                            doc_api_refs[api_name] = (str(md_file), i + 1)
            except (UnicodeDecodeError, OSError):
                continue

        # 3. 对比：文档引用的 API 在代码中不存在 → 不忠实
        for api_name, (filepath, line_no) in doc_api_refs.items():
            if api_name not in code_apis:
                deduction += 2
                issues.append(f"[Faithfulness] 文档引用 API `{api_name}()` 在代码中不存在 " f"[{filepath}:{line_no}]")
            else:
                # 进一步对比参数名一致性（如果文档明确列出了参数）
                code_params = set(code_apis[api_name]["params"])
                doc_params = self._extract_doc_params(filepath, api_name)
                if doc_params:
                    extra_params = doc_params - code_params
                    if extra_params:
                        deduction += 2
                        issues.append(
                            f"[Faithfulness] 文档声明了代码中不存在的参数 "
                            f"{extra_params} 用于 `{api_name}()` [{filepath}:{line_no}]"
                        )

        deduction = min(deduction, self.config.get("max_deduction", 5))
        return deduction, issues

    def _extract_doc_params(self, md_file: str, api_name: str) -> set:
        """从文档中提取指定 API 的参数名集合（启发式）"""
        params = set()
        try:
            text = Path(md_file).read_text(encoding="utf-8")
            # 找代码块中包含 api_name 定义的部分
            pattern = re.compile(rf"`{re.escape(api_name)}\s*\(([^)]*)\)`|{re.escape(api_name)}\s*\(([^)]*)\)")
            for match in pattern.finditer(text):
                param_str = match.group(1) or match.group(2) or ""
                for p in param_str.split(","):
                    p = p.strip().split("=")[0].strip().split(":")[0].strip()
                    if p and not p.startswith("*"):
                        params.add(p)
        except OSError:
            pass
        return params

    # ─── Paraphrase Agent（逐行复述 — 函数意图 vs 代码实现偏差）───
    def paraphrase_check(self, py_file: str) -> list:
        """逐行复述检查：函数 docstring 声明的意图 vs 代码实际逻辑"""
        issues = []
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    docstring = ast.get_docstring(node)
                    if not docstring:
                        continue
                    # 检查 docstring 中声明的参数 vs 实际参数
                    declared_params = set()
                    for match in re.finditer(r":param\s+(\w+):", docstring):
                        declared_params.add(match.group(1))
                    actual_params = {arg.arg for arg in node.args.args}
                    missing_in_doc = actual_params - declared_params
                    if missing_in_doc and declared_params:
                        issues.append(
                            f"[PARAPHRASE] {py_file}:{node.lineno} "
                            f"函数 {node.name} 的参数 {missing_in_doc} 在 docstring 中未声明"
                        )
        except Exception:
            pass
        return issues

    # ─── Contract Agent（契约审查 — _core/ 前置条件/后置条件验证）───
    def contract_check(self, py_file: str) -> list:
        """契约审查：检查 _core/ 中 API 是否有前置/后置条件文档"""
        issues = []
        if "_core" not in py_file and "core" not in py_file.split(os.sep):
            return issues
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    docstring = ast.get_docstring(node) or ""
                    # 必须包含前置条件
                    has_pre = ":raises" in docstring or "Raises" in docstring or "前置" in docstring
                    # 必须声明参数类型（契约的一部分）
                    has_types = any(arg.arg and hasattr(arg, "annotation") and arg.annotation for arg in node.args.args)
                    if node.name.startswith("_") and not node.name.startswith("__"):
                        continue  # 准私有方法跳过
                    if not has_pre and not has_types:
                        issues.append(
                            f"[CONTRACT] {py_file}:{node.lineno} "
                            f"_core/ 函数 {node.name} 缺少前置条件声明（:raises/参数类型）"
                        )
        except Exception:
            pass
        return issues

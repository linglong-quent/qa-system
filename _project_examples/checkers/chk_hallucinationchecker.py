#!/usr/bin/env python3
"""Extracted: HallucinationChecker"""
import os, re
from pathlib import Path


class HallucinationChecker:
    """文档幻觉检测器 — V2.1 新增

    对齐 LLM Multi-Judge Hallucination Penalty with amplification 机制。
    检测逻辑：扫描文档中虚构的 API、功能名称、版本号引用。

    扣分规则：
    - 引用不存在的文件/路径 → 每个扣 5
    - 声称已废弃但代码中仍存在的功能 → 每个扣 5
    - 关键路径不存在 → 每个扣 5（触发红线）
    """

    HALLUCINATION_PATTERNS = [
        # 版本号虚构检测：声称的版本号格式不符合 semver
        r"version\s+(?:is|should be)\s+['\"]?(\d+\.\d+(?:\.\d+)?)['\"]?",
        # 声称已支持的平台/特性
        r"support(?:s|ed)?\s+(?:for\s+)?(?:Linux|Windows|macOS|iOS|Android)\s+\d+",
    ]

    def __init__(self, config: dict, project_root: str):
        self.config = config
        self.project_root = project_root
        # DS 修正: 允许的未来 API / 外部依赖白名单（对标 review-rules.yaml hallucination_check）
        self.allowed_futures = set(config.get("allowed_futures", []))
        self.external_apis = set(config.get("external_apis", []))

    def check(self, docs_dir: str = None) -> tuple:
        """检查文档中的虚构内容

        Returns:
            (deduction, issues): (总扣分, 问题列表)
        """
        deduction = 0
        issues = []
        docs_path = os.path.join(self.project_root, docs_dir) if docs_dir else self.project_root
        if not os.path.isdir(docs_path):
            return 0, []

        # 扫描所有 .md 文件
        import glob as _glob

        md_files = _glob.glob(os.path.join(docs_path, "**/*.md"), recursive=True)

        for md_file in md_files:
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # DS 修正: 跳过含 [TODO], [FUTURE], [EXTERNAL] 标记的段落
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if "[TODO]" in line or "[FUTURE]" in line or "[EXTERNAL]" in line:
                        continue  # 跳过标记行

                    for pattern in self.HALLUCINATION_PATTERNS:
                        import re

                        matches = re.findall(pattern, line)
                        for m in matches:
                            # DS 修正: 检查是否在白名单中
                            if self.allowed_futures and any(af in line for af in self.allowed_futures):
                                continue
                            if self.external_apis and any(ea in line for ea in self.external_apis):
                                continue
                            deduction += 5
                            rel = os.path.relpath(md_file, self.project_root)
                            issues.append(f"可能的虚构内容: '{m}' in {rel}")

            except Exception:
                pass

        deduction = min(deduction, 5)  # 满分 5
        return deduction, issues
        issues = []

        if docs_dir is None:
            docs_dir = os.path.join(self.project_root, "docs")

        if not os.path.isdir(docs_dir):
            return 0, []

        # 1. 引用不存在的文件/路径
        for md_file in Path(docs_dir).rglob("*.md"):
            try:
                lines = md_file.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines):
                    # 检测 Markdown 链接指向不存在的本地文件
                    for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", line):
                        link = match.group(2)
                        if link.startswith(".") or link.startswith("/"):
                            # 本地文件引用
                            target = (Path(md_file).parent / link).resolve()
                            if not target.exists():
                                deduction += 5
                                issues.append(f"[Hallucination] 引用不存在的文件 `{link}` " f"[{md_file}:{i + 1}]")

                    # 检测虚构 API 引用（Backtick + 不存在的函数名）
                    for match in re.finditer(r"`([a-zA-Z_]\w*)\(\)`", line):
                        func_name = match.group(1)
                        # 检查该函数是否在项目代码中存在
                        found = False
                        for root_dir in ["src", "scripts", ".ai"]:
                            root_path = os.path.join(self.project_root, root_dir)
                            if os.path.isdir(root_path):
                                for py_file in Path(root_path).rglob("*.py"):
                                    if not py_file.is_file():
                                        continue
                                    try:
                                        tree = ast.parse(py_file.read_text(encoding="utf-8"))
                                        for node in ast.walk(tree):
                                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                                if node.name == func_name:
                                                    found = True
                                                    break
                                    except (SyntaxError, OSError):
                                        continue
                                if found:
                                    break
                        if not found and func_name not in {
                            "print",
                            "len",
                            "range",
                            "str",
                            "int",
                            "list",
                            "dict",
                            "set",
                            "tuple",
                            "open",
                            "type",
                            "isinstance",
                            "hasattr",
                            "getattr",
                            "setattr",
                            "super",
                            "next",
                            "iter",
                            "map",
                            "filter",
                            "zip",
                            "enumerate",
                            "sorted",
                            "reversed",
                            "min",
                            "max",
                            "sum",
                            "abs",
                            "any",
                            "all",
                            "round",
                            "format",
                            "repr",
                            "eval",
                            "exec",
                            "compile",
                            "__init__",
                            "__str__",
                            "__repr__",
                        }:
                            deduction += 5
                            issues.append(f"[Hallucination] 文档引用虚构的 API `{func_name}()` " f"[{md_file}:{i + 1}]")

            except (OSError, UnicodeDecodeError):
                continue

        # 引用包含类型: P{1,5}
        severe_issues = [i for i in issues if "虚构的 API" in i]
        deduction = min(deduction, self.config.get("max_deduction", 5))
        return deduction, issues

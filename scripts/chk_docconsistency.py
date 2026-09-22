#!/usr/bin/env python3
"""Checker: 文档一致性 — 代码中的公共符号是否有文档覆盖

通用 QA 能力，从量化 skill_doc_consistency 提取。
"""
import os, re, ast, logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class DocConsistencyChecker:
    CHECKER_ID = "docconsistency_check"
    CHECKER_LABEL = "文档一致性"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.code_dirs = config.get("code_dirs", ["src/"])
        self.doc_dirs = config.get("doc_dirs", ["docs/"])

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0
        # M50：原先 `ast.parse(open(..., encoding="utf-8").read())` 被 `except Exception: continue`
        # 包住 —— 带 BOM 的文件在 ast.parse(str) 下首行必抛 U+FEFF，于是该文件的公共符号
        # 整体不进 public_symbols ⇒ 它的未文档化符号永远不会被发现（假阴性，实测 0 vs 1 条）。
        parse_failed = []

        # 收集代码中的公共符号
        public_symbols = set()
        for d in self.code_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, files in os.walk(full):
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    fpath = os.path.join(root, f)
                    try:
                        src = open(fpath, "r", encoding="utf-8-sig", errors="replace").read()
                    except Exception:
                        logger.warning("读取源文件失败: %s", fpath, exc_info=True)
                        parse_failed.append((os.path.relpath(fpath, self.project_root), "读取失败"))
                        continue
                    try:
                        tree = ast.parse(src)
                    except SyntaxError as exc:
                        parse_failed.append(
                            (os.path.relpath(fpath, self.project_root),
                             f"{exc.msg} (line {exc.lineno})"))
                        continue
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            if not node.name.startswith("_"):
                                public_symbols.add(node.name)

        if not public_symbols:
            return 0, []

        # 收集文档中出现的符号引用
        doc_symbols = set()
        for d in self.doc_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, files in os.walk(full):
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    fpath = os.path.join(root, f)
                    try:
                        content = open(fpath, "r", encoding="utf-8").read()
                        # 文档中反引号引用的符号名和普通出现的函数/类名
                        refs = re.findall(r'`([a-z_]\w+(?:\(\))?)`', content, re.IGNORECASE)
                        refs += re.findall(r'`([A-Z]\w+)`', content)
                        doc_symbols.update(r.replace("()", "") for r in refs)
                    except Exception:
                        logger.warning("读取文档文件失败: %s", fpath, exc_info=True)
                        continue

        # 公共符号在文档中无引用
        undocumented = public_symbols - doc_symbols
        if undocumented:
            sample = list(sorted(undocumented))[:10]
            issues.append(f"[DOCCONSISTENCY] {len(undocumented)} 个公共符号文档中未引用: {', '.join(sample)}")
            errors += 1

        # M50：解析失败不再静默（这些文件的公共符号根本没进入比对集合）
        for rel, why in parse_failed[:25]:
            issues.append(f"[PARSE-001] {rel}: 解析失败 —— {why}；其公共符号未参与文档一致性比对"
                          f"（原行为：静默跳过，造成假阴性）")
            errors += 1
        if len(parse_failed) > 25:
            issues.append(f"[PARSE-001] 另有 {len(parse_failed) - 25} 个文件解析失败，未逐条列出")

        return errors, issues

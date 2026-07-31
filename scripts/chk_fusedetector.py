#!/usr/bin/env python3
"""Checker: 熔断检测 — 检查外部网络调用是否有熔断/重试保护

Rationale:
    外部调用（HTTP 请求、数据库连接、第三方 API）必须有重试/熔断机制，
    否则网络抖动会直接导致系统故障。这是量化系统可靠性的基础要求。

References:
    - ISO 25010 可靠性
    - Nygard, M. (2007). Release It!: Stability Patterns
    - Netflix Hystrix / Resilience4j 设计思想
"""
import ast
import os
import re
import logging
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)


class FuseDetectorChecker:
    CHECKER_ID = "fusedetect_check"
    CHECKER_LABEL = "熔断检测"

    EXTERNAL_CALL_PATTERNS = [
        ("requests", ["get", "post", "put", "delete", "patch", "head", "options", "request"]),
        ("urllib.request", ["urlopen", "Request"]),
        ("http.client", ["HTTPConnection", "HTTPSConnection"]),
        ("socket", ["socket", "create_connection", "connect"]),
        ("websocket", ["create_connection", "WebSocket"]),
        ("websockets", ["connect", "serve"]),
        ("pymongo", ["MongoClient"]),
        ("redis", ["Redis", "StrictRedis"]),
    ]

    PROTECTION_KEYWORDS = [
        "retry", "backoff", "tenacity", "circuit", "breaker",
    ]

    BASIC_ERROR_HANDLING_KEYWORDS = [
        "try:", "except", "timeout",
    ]

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/"])
        self.custom_triggers = config.get("triggers", [])

    def _collect_py_files(self) -> List[str]:
        files = []
        for d in self.scan_dirs:
            full = os.path.join(self.project_root, d)
            if os.path.isdir(full):
                for root, dirs, fnames in os.walk(full):
                    dirs[:] = [d for d in dirs if not d.startswith((".", "_"))
                               and d not in ("__pycache__", "node_modules")]
                    for fn in fnames:
                        if fn.endswith(".py"):
                            files.append(os.path.join(root, fn))
        return files

    def _has_fuse_protection(self, content: str, func_lineno: int) -> bool:
        lines = content.split("\n")
        start = max(0, func_lineno - 30)
        end = min(len(lines), func_lineno + 30)
        surrounding = "\n".join(lines[start:end])
        return any(kw in surrounding.lower() for kw in self.PROTECTION_KEYWORDS)

    def _has_basic_error_handling(self, content: str, func_lineno: int) -> bool:
        lines = content.split("\n")
        start = max(0, func_lineno - 20)
        end = min(len(lines), func_lineno + 20)
        surrounding = "\n".join(lines[start:end])
        return any(kw in surrounding.lower() for kw in self.BASIC_ERROR_HANDLING_KEYWORDS)

    def _find_functions_with_external_calls(self, tree: ast.AST, content: str) -> Set[int]:
        """通过 AST 分析找到包含外部调用的函数起始行号"""
        external_module_names = set()
        for mod, _funcs in self.EXTERNAL_CALL_PATTERNS:
            external_module_names.add(mod.split(".")[0])

        imported_external = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_name = alias.name.split(".")[0]
                    if top_name in external_module_names:
                        imported_external.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_name = node.module.split(".")[0]
                    if top_name in external_module_names:
                        for alias in node.names:
                            imported_external.add(alias.asname or alias.name)

        if not imported_external:
            return set()

        call_lines = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id in imported_external:
                            call_lines.add(node.lineno)
                    elif isinstance(node.func.value, ast.Attribute):
                        full = ast.unparse(node.func.value) if hasattr(ast, "unparse") else ""
                        if any(full == mod or full.startswith(mod + ".") for mod, _ in self.EXTERNAL_CALL_PATTERNS):
                            call_lines.add(node.lineno)
                elif isinstance(node.func, ast.Name):
                    if node.func.id in imported_external:
                        call_lines.add(node.lineno)

        return call_lines

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        errors = 0

        for fpath in self._collect_py_files():
            rel = os.path.relpath(fpath, self.project_root)
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except Exception:
                logger.warning("读取文件失败: %s", fpath, exc_info=True)
                continue

            try:
                tree = ast.parse(content, filename=fpath)
            except SyntaxError:
                continue

            call_lines = self._find_functions_with_external_calls(tree, content)

            for lineno in sorted(call_lines):
                line_text = content.split("\n")[lineno - 1].strip()
                # 支持 # no-fuse: 行内豁免（服务器监听/初始化等无需熔断的场景）
                if "no-fuse" in line_text.lower() or "no-fuse" in content.split("\n")[lineno - 1].lower():
                    continue
                if not self._has_fuse_protection(content, lineno):
                    if self._has_basic_error_handling(content, lineno):
                        issues.append(
                            f"[FUSE-002] {rel}:{lineno} 外部调用缺少重试/熔断机制 "
                            f"(仅有 try/except) — '{line_text[:60]}'. "
                            f"建议添加 retry/backoff 或集成 CircuitBreaker"
                        )
                    else:
                        issues.append(
                            f"[FUSE-001] {rel}:{lineno} 外部调用无任何错误处理 — "
                            f"'{line_text[:60]}'. "
                            f"必须添加 try/except + timeout + retry"
                        )
                        errors += 1

            if self.custom_triggers:
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    for pattern_text in self.custom_triggers:
                        if re.search(pattern_text, line):
                            if not self._has_fuse_protection(content, i):
                                if not self._has_basic_error_handling(content, i):
                                    issues.append(
                                        f"[FUSE-001] {rel}:{i} '{pattern_text}' 调用无任何错误处理"
                                    )
                                    errors += 1

        return errors, issues

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/skill/skill_log_abuse_scan.py — 日志分级滥用扫描 (B2-10)
=================================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B2-10)

职责:
  1. 正则扫描 ERROR/FATAL 用于正常流程
  2. 检测 logger.exception() 在非 except 块中使用
  3. 检测 print() 直接输出（应使用 logger）

引用: p1_spec.md §六 LOG 日志标准化 日志分级滥用扫描

用法:
    python scripts/skill/skill_log_abuse_scan.py
    python scripts/skill/skill_log_abuse_scan.py --path linglong/_core/
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


@dataclass
class AbuseFinding:
    """滥用发现"""

    file: str
    line: int
    level: str  # ERROR/FATAL/EXCEPTION/PRINT
    pattern: str  # 匹配到的模式
    snippet: str
    severity: str  # error/warning


class LogAbuseScanner:
    """日志分级滥用扫描器

    检测项:
      1. ERROR/FATAL 用于正常流程 — 非 except 块中的 logger.error/fatal
      2. logger.exception() 在非 except 块使用
      3. print() 直接输出 — 应使用 logger
    """

    # 日志级别关键词
    LOG_ERROR_PATTERNS = [
        (re.compile(r"logger\.error\s*\("), "logger.error"),
        (re.compile(r"logger\.fatal\s*\("), "logger.fatal"),
        (re.compile(r"logger\.critical\s*\("), "logger.critical"),
    ]

    # logger.exception 模式
    EXCEPTION_PATTERN = re.compile(r"logger\.exception\s*\(")

    # print 模式
    PRINT_PATTERN = re.compile(r"\bprint\s*\(")

    # 豁免文件
    EXEMPT_FILES: Set[str] = {
        "__init__.py",
        "setup.py",
        "conftest.py",
        "skill_scanner_selfcheck.py",
    }

    def __init__(self, target_path: Optional[str] = None) -> None:
        self._target = Path(target_path) if target_path else _PROJECT_ROOT
        if not self._target.is_absolute() and target_path:
            self._target = (_PROJECT_ROOT / self._target).resolve()
        self._findings: List[AbuseFinding] = []

    def scan(self) -> List[AbuseFinding]:
        """执行扫描"""
        self._findings = []

        for py_file in self._target.rglob("*.py"):
            if py_file.name in self.EXEMPT_FILES:
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                lines = content.split("\n")

                # 1. 检测 print()
                self._check_print(py_file, lines)

                # 2. AST 深度检测
                self._check_ast(py_file, content, lines)

            except Exception:
                pass

        return self._findings

    def _check_print(self, filepath: Path, lines: List[str]) -> None:
        """检测 print() 使用"""
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 跳过注释
            if stripped.startswith("#"):
                continue
            # 跳过 docstring 中的 print
            if '"""' in stripped or "'''" in stripped:
                continue

            if self.PRINT_PATTERN.search(stripped):
                self._findings.append(
                    AbuseFinding(
                        file=str(filepath.relative_to(_PROJECT_ROOT)),
                        line=i,
                        level="PRINT",
                        pattern="print()",
                        snippet=stripped[:120],
                        severity="warning",
                    )
                )

    def _check_ast(self, filepath: Path, content: str, lines: List[str]) -> None:
        """AST 深度检测"""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        visitor = _LogAbuseVisitor(filepath, lines, self._findings, _PROJECT_ROOT)
        visitor.visit(tree)


class _LogAbuseVisitor(ast.NodeVisitor):
    """AST 遍历器"""

    def __init__(self, filepath: Path, lines: List[str], findings: List[AbuseFinding], root: Path) -> None:
        self.filepath = filepath
        self.lines = lines
        self.findings = findings
        self.root = root
        self._in_except = False

    def visit_ExceptHandler(self, node) -> None:  # type: ignore[no-untyped-def]
        """进入 except 块"""
        old = self._in_except
        self._in_except = True
        self.generic_visit(node)
        self._in_except = old

    def visit_Call(self, node) -> None:  # type: ignore[no-untyped-def]
        """检查函数调用"""
        # 检查 logger.error/fatal/critical
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id == "logger":
                    method = node.func.attr
                    if method in ("error", "fatal", "critical"):
                        if not self._in_except:
                            # 非 except 块中使用 error/fatal → 可能滥用
                            lineno = node.lineno
                            self.findings.append(
                                AbuseFinding(
                                    file=str(self.filepath.relative_to(self.root)),
                                    line=lineno,
                                    level=method.upper(),
                                    pattern=f"logger.{method}() outside except",
                                    snippet=self.lines[lineno - 1].strip()[:120] if lineno <= len(self.lines) else "",
                                    severity="warning",
                                )
                            )

                    if method == "exception":
                        if not self._in_except:
                            lineno = node.lineno
                            self.findings.append(
                                AbuseFinding(
                                    file=str(self.filepath.relative_to(self.root)),
                                    line=lineno,
                                    level="EXCEPTION",
                                    pattern="logger.exception() outside except",
                                    snippet=self.lines[lineno - 1].strip()[:120] if lineno <= len(self.lines) else "",
                                    severity="error",
                                )
                            )

        self.generic_visit(node)


def format_findings(findings: List[AbuseFinding]) -> str:
    """格式化输出"""
    if not findings:
        return "✅ 无日志滥用违规"

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    lines = [
        f"日志分级滥用扫描: {len(findings)} 项",
        f"  ERROR: {len(errors)}  |  WARNING: {len(warnings)}",
        "",
    ]

    if errors:
        lines.append("── ERROR 级别 ──")
        for f in errors:
            lines.append(f"  {f.file}:{f.line} [{f.level}] {f.pattern}")
            lines.append(f"    → {f.snippet}")

    if warnings:
        lines.append("── WARNING 级别 ──")
        for f in warnings[:20]:  # 限制输出
            lines.append(f"  {f.file}:{f.line} [{f.level}] {f.pattern}")

    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="日志分级滥用扫描")
    parser.add_argument("--path", type=str, help="扫描路径")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    scanner = LogAbuseScanner(args.path)
    findings = scanner.scan()

    if args.json:
        import json

        print(
            json.dumps(
                [
                    {
                        "file": f.file,
                        "line": f.line,
                        "level": f.level,
                        "pattern": f.pattern,
                        "severity": f.severity,
                    }
                    for f in findings
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(format_findings(findings))

    # exit 0=无违规, 1=有error, 2=仅有warning
    errors = sum(1 for f in findings if f.severity == "error")
    if errors > 0:
        sys.exit(1)
    elif findings:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

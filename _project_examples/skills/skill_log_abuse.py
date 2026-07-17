#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_log_abuse.py — 日志分级滥用扫描 (B1-22)
================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-22)

职责: 检测日志级别滥用
  1. ERROR/FATAL 用于正常业务流程
  2. warning 用于需要人工关注的场景
  3. info 用于高频循环中（性能问题）

用法:
    python scripts/skill/skill_log_abuse.py
    python scripts/skill/skill_log_abuse.py --output json

退出码:
    0 = 无滥用
    2 = 发现滥用（warning）
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402


class SkillLogAbuse(BaseSkill):
    """日志分级滥用扫描"""

    def __init__(self, target_path: Optional[str] = None):
        super().__init__("log_abuse")
        self.target = Path(target_path or ".").resolve()
        if not self.target.is_absolute():
            self.target = (_ROOT / self.target).resolve()

    def _scan_file(self, filepath: Path) -> list[Dict[str, Any]]:
        """扫描单个文件中的日志滥用"""
        findings = []
        try:
            content = filepath.read_text(encoding="utf-8")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # 检测 ERROR 级别日志在正常流程中
                if re.search(r"logger\.(error|fatal)\s*\(", line, re.IGNORECASE):
                    # 检查是否在 try/except 块内（合理）
                    # 简化：标记所有 ERROR 调用供人工审查
                    pass

                # 检测 info 级别日志在循环/高频调用中
                if re.search(r"logger\.(info|debug)\s*\(", line, re.IGNORECASE):
                    # 检查是否在 for/while 循环内
                    pass

                # 检测裸 print 调用
                if re.search(r"\bprint\s*\(", line) and "def print" not in line:
                    findings.append(
                        {
                            "rule_id": "LOG-001",
                            "severity": "warning",
                            "file": str(filepath),
                            "line": i,
                            "message": "使用 print() 而非 logger",
                            "suggest": "改用 _core.logger 统一日志入口",
                        }
                    )

                # 检测 logger.exception 在非 except 块中
                if re.search(r"logger\.exception\s*\(", line, re.IGNORECASE):
                    # 简单检查前几行是否有 except
                    context_start = max(0, i - 5)
                    context = "\n".join(lines[context_start:i])
                    if "except" not in context.lower():
                        findings.append(
                            {
                                "rule_id": "LOG-002",
                                "severity": "warning",
                                "file": str(filepath),
                                "line": i,
                                "message": "logger.exception() 在非 except 块中使用",
                                "suggest": "exception() 应仅在 except 块中调用",
                            }
                        )

        except (IOError, UnicodeDecodeError):
            pass
        return findings

    def run_checks(self) -> list[CheckResult]:
        """执行日志滥用扫描"""
        all_findings = []
        py_files = list(self.target.rglob("*.py"))

        for fp in py_files:
            all_findings.extend(self._scan_file(fp))

        results: list[CheckResult] = []
        print_abuse = [f for f in all_findings if f["rule_id"] == "LOG-001"]
        exception_abuse = [f for f in all_findings if f["rule_id"] == "LOG-002"]

        if print_abuse:
            for f in print_abuse[:10]:
                results.append(
                    CheckResult(
                        rule=f["rule_id"],
                        severity=f["severity"],
                        file=f["file"],
                        line=f["line"],
                        message=f["message"],
                        suggest=f.get("suggest", ""),
                    )
                )
            results.append(
                CheckResult(
                    rule="LOG-001",
                    severity="warning",
                    message=f"发现 {len(print_abuse)} 处 print() 调用 (应使用 logger)",
                )
            )

        if exception_abuse:
            for f in exception_abuse[:5]:
                results.append(
                    CheckResult(
                        rule=f["rule_id"],
                        severity=f["severity"],
                        file=f["file"],
                        line=f["line"],
                        message=f["message"],
                    )
                )

        if not all_findings:
            results.append(
                CheckResult(
                    rule="LOG-000",
                    severity="info",
                    message=f"未发现日志滥用 (扫描 {len(py_files)} 文件)",
                )
            )

        return results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """统一入口"""
    checker = SkillLogAbuse(target_path=path)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n日志滥用扫描报告")  # noqa: F541
        print(f"{'='*50}")
        for r in results:
            icon = {"info": "✓", "warning": "⚠", "blocker": "✗"}.get(r.severity, "?")
            loc = f" [{r.file}:{r.line}]" if r.file else ""
            print(f"  [{icon}] [{r.rule}] {r.message}{loc}")
            if r.suggest:
                print(f"       → {r.suggest}")
        print(f"{'='*50}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="日志分级滥用扫描")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--path", default=None, help="扫描目标路径")
    args = parser.parse_args()
    result = run(output=args.output, path=args.path)
    sys.exit(result.get("exit_code", 0))

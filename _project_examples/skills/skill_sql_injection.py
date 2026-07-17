#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_sql_injection.py — 入参防注入 AST 扫描中间件 (B1-16)
============================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-16)

职责: 检测 SQL 入参裸拼接，防止注入攻击
  引用: p1_spec.md §十一「入参防注入中间件」

检测模式:
  1. f-string 拼接到 SQL: f"SELECT * FROM {table}"
  2. str.format 拼接到 SQL: "SELECT * FROM {}".format(table)
  3. + 拼接 SQL 字符串: "SELECT * FROM " + table
  4. % 格式化 SQL: "SELECT * FROM %s" % table

用法:
    python scripts/skill/skill_sql_injection.py
    python scripts/skill/skill_sql_injection.py --output json

退出码:
    0 = 无 SQL 注入风险
    1 = 发现 SQL 注入风险
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

# ═══════════════════════════════════════════════════════════════
# SQL 注入检测模式
# ═══════════════════════════════════════════════════════════════

SQL_KEYWORDS = [
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "REPLACE",
    "MERGE",
    "EXEC",
    "EXECUTE",
]

# f-string SQL 拼接
FSTRING_SQL_PATTERN = re.compile(
    r'f["\']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\s',
    re.IGNORECASE,
)

# .format() SQL 拼接
FORMAT_SQL_PATTERN = re.compile(
    r'["\']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s.*\.format\s*\(',
    re.IGNORECASE,
)

# + 号 SQL 拼接
PLUS_SQL_PATTERN = re.compile(
    r'["\']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s.*["\']\s*\+',
    re.IGNORECASE,
)

# % SQL 格式化
PERCENT_SQL_PATTERN = re.compile(
    r'["\']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s.*["\']\s*%\s*\(',
    re.IGNORECASE,
)

# 豁免文件
EXEMPT_FILES = [
    "skill_sql_injection.py",
    "test_",
    "db_config.py",
    "db_pool.py",
    "orm",
]


class SkillSQLInjection(BaseSkill):
    """入参防注入 AST 扫描"""

    def __init__(self, target_path: Optional[str] = None):
        super().__init__("sql_injection")
        self.target = Path(target_path or ".").resolve()
        if not self.target.is_absolute():
            self.target = (_ROOT / self.target).resolve()

    def _is_exempt(self, filepath: Path) -> bool:
        """豁免文件：自身/测试/ORM + 废弃目录/构建产物"""
        path_str = str(filepath).replace("\\", "/")
        # 排除废弃目录和构建产物
        if any(d in path_str for d in ("_deprecated/", "/build/", "/dist/", "/.venv/", "/.egg-info/")):
            return True
        name = filepath.name.lower()
        for pattern in EXEMPT_FILES:
            if pattern in name:
                return True
        return False

    def _scan_file(self, filepath: Path) -> list[Dict[str, Any]]:
        findings: Any = []
        if self._is_exempt(filepath):
            return findings  # type: ignore[no-any-return]

        try:
            content = filepath.read_text(encoding="utf-8")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue

                # f-string 拼接
                if FSTRING_SQL_PATTERN.search(line):
                    findings.append(
                        {
                            "rule_id": "SQL-001",
                            "severity": "blocker",
                            "file": str(filepath),
                            "line": i,
                            "message": "f-string SQL 拼接存在注入风险",
                            "suggest": "使用参数化查询: cursor.execute('SELECT * FROM t WHERE id=?', (id,))",
                        }
                    )

                # .format 拼接 — 检测上下文是否有安全校验
                if FORMAT_SQL_PATTERN.search(line):
                    guarded = self._has_ident_guard(lines, i)
                    findings.append(
                        {
                            "rule_id": "SQL-002",
                            "severity": "info" if guarded else "warning",
                            "file": str(filepath),
                            "line": i,
                            "message": ".format() SQL 拼接" + (" (已有标识符校验防护)" if guarded else " 存在注入风险"),
                            "suggest": None if guarded else "确认标识符已校验后可使用, 否则改为参数化查询",
                        }
                    )

                # + 拼接
                if PLUS_SQL_PATTERN.search(line):
                    findings.append(
                        {
                            "rule_id": "SQL-003",
                            "severity": "warning",
                            "file": str(filepath),
                            "line": i,
                            "message": "+ 运算符 SQL 拼接存在注入风险",
                            "suggest": "使用参数化查询",
                        }
                    )

                # % 格式化
                if PERCENT_SQL_PATTERN.search(line):
                    findings.append(
                        {
                            "rule_id": "SQL-004",
                            "severity": "blocker",
                            "file": str(filepath),
                            "line": i,
                            "message": "% SQL 格式化存在注入风险",
                            "suggest": "使用参数化查询: cursor.execute('SELECT * FROM t WHERE id=?', (id,))",
                        }
                    )

        except (IOError, UnicodeDecodeError):
            pass
        return findings  # type: ignore[no-any-return]

    @staticmethod
    def _has_ident_guard(lines: list[str], line_idx: int, window: int = 5) -> bool:
        """检测 .format() 行前面 window 行内是否有标识符安全校验调用"""
        start = max(0, line_idx - window)
        for j in range(start, line_idx):
            candidate = lines[j]
            if any(guard in candidate for guard in ("_safe_ident(", "_validate_identifier(", "_quote_ident(")):
                return True
        return False

    def run_checks(self) -> list[CheckResult]:
        all_findings = []
        py_files = list(self.target.rglob("*.py"))

        for fp in py_files:
            all_findings.extend(self._scan_file(fp))

        results: list[CheckResult] = []

        for f in all_findings:
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

        if not all_findings:
            results.append(
                CheckResult(
                    rule="SQL-000",
                    severity="info",
                    message=f"未发现 SQL 注入风险 (扫描 {len(py_files)} 文件)",
                )
            )

        return results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    checker = SkillSQLInjection(target_path=path)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\nSQL 注入风险扫描报告")  # noqa: F541
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

    parser = argparse.ArgumentParser(description="SQL 注入风险扫描")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--path", default=None, help="扫描目标路径")
    args = parser.parse_args()
    result = run(output=args.output, path=args.path)
    sys.exit(result.get("exit_code", 0))

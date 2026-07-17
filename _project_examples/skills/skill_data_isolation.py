#!/usr/bin/env python3
"""测试数据隔离检查 Skill (B3-05)

检查测试代码是否使用了隔离的测试数据源，防止测试污染生产数据。
检测规则：测试文件中使用生产数据库路径/表名/连接串。

审计: CB P1-B3 Batch3 数据与验证 (2026-07-08)
"""

from __future__ import annotations

import ast
import datetime
import sys
from pathlib import Path
from typing import Any, Dict

# ─── 配置 ────────────────────────────────────────────
PRODUCTION_PATTERNS = [
    # 生产数据库路径
    r"linglong\.db",
    r"production\.db",
    r"live\.db",
    r"实盘",
    # 生产表名
    "trade_log",
    "order_book",
    "position_live",
    "risk_events",
    "pnl_daily",
    # 生产连接
    "prod_host",
    "production_host",
    "live_data_source",
]

TEST_DIRS = ["tests", "test", "testing", "__tests__"]

WHITELIST_FILES = {
    "test_data_isolation.py",
    "conftest.py",
    "__init__.py",
}


class DataIsolationVisitor(ast.NodeVisitor):
    """AST 访问器：检测生产数据引用"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.violations: list[Dict[str, Any]] = []

    def _check_value(self, node: ast.AST, value: str, context: str) -> None:
        """检查字符串值是否包含生产模式"""
        for pattern in PRODUCTION_PATTERNS:
            if pattern in value:
                self.violations.append(
                    {
                        "file": self.filepath,
                        "line": getattr(node, "lineno", 0),
                        "pattern": pattern,
                        "value": value[:120],
                        "context": context,
                        "severity": "warning",
                    }
                )

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self._check_value(node, node.value, "string_literal")
        self.generic_visit(node)

    def visit_Str(self, node: ast.Constant) -> None:
        # 兼容旧版 Python
        if isinstance(node.value, str):
            self._check_value(node, node.value, "string_literal")
        self.generic_visit(node)


def is_test_file(filepath: Path) -> bool:
    """判断是否为测试文件"""
    parts = filepath.parts
    for td in TEST_DIRS:
        if td in parts:
            return True
    return filepath.stem.startswith("test_") or filepath.stem.endswith("_test")


def scan_data_isolation(
    base_dir: str | None = None,
) -> Dict[str, Any]:
    """扫描测试数据隔离违规"""
    if base_dir is None:
        base_dir = str(Path(__file__).parent.parent.parent)

    base = Path(base_dir)
    violations = []
    files_scanned = 0
    test_files = 0

    for py_file in base.rglob("*.py"):
        if py_file.name in WHITELIST_FILES:
            continue
        if not is_test_file(py_file):
            continue

        test_files += 1
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        visitor = DataIsolationVisitor(str(py_file))
        visitor.visit(tree)
        if visitor.violations:
            violations.extend(visitor.violations)
        files_scanned += 1

    passed = len(violations) == 0
    report = {
        "run_at": datetime.datetime.now().isoformat(),
        "passed": passed,
        "files_scanned": files_scanned,
        "test_files": test_files,
        "violation_count": len(violations),
        "violations": violations,
    }

    return report


def main() -> int:
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="测试数据隔离检查")
    parser.add_argument(
        "--dir",
        default=None,
        help="扫描目录（默认项目根目录）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 格式输出",
    )
    args = parser.parse_args()

    report = scan_data_isolation(args.dir)

    if args.json:
        import json

        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"测试数据隔离检查: {'PASS' if report['passed'] else 'FAIL'}")
        print(f"  扫描测试文件: {report['files_scanned']}")
        print(f"  违规数: {report['violation_count']}")
        for v in report["violations"]:
            print(f"  [{v['severity']}] {v['file']}:{v['line']} " f"— {v['pattern']} ({v['context']})")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

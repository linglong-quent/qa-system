#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/skill/skill_scanner_selfcheck.py — 扫描工具自校验 (B2-9)
=================================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B2-9)

职责:
  1. 已知用例集校验 — CI 命中率100%
  2. 漏报率检测 — 目标 ≤5%
  3. 误报率检测 — 目标 ≤3%

引用: p1_spec.md §七 GATE 质量门 §52

用法:
    python scripts/skill/skill_scanner_selfcheck.py
    python scripts/skill/skill_scanner_selfcheck.py --verbose
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile

# 确保项目根在 path
from dataclasses import dataclass
from pathlib import Path
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# ── 已知违规用例（应检测到）────────────────


@dataclass
class TestCase:
    """测试用例"""

    id: str
    scanner: str  # 对应扫描器
    rule: str  # 违规规则
    code: str  # 违规代码
    description: str
    should_detect: bool = True  # True=应检测到, False=不应误报


# 应检出的违规用例
POSITIVE_CASES = [
    TestCase("P001", "ban_check", "print", 'print("hello world")', "print() 使用"),
    TestCase("P002", "ban_check", "eval", 'result = eval("1+1")', "eval() 使用"),
    TestCase("P003", "ban_check", "hardcoded_path", 'data = open("C:/Users/data.csv").read()', "硬编码路径"),
    TestCase("P004", "naming_check", "class_naming", "class myclass:\n    pass", "类名非 PascalCase"),
    TestCase("P005", "naming_check", "function_naming", "def MyFunction():\n    pass", "函数名非 snake_case"),
    TestCase("P006", "g5_scan", "print", 'print("debug info")', "G5 零 print"),
    TestCase("P007", "g5a_scan", "hardcoded_ip", 'host = "192.168.1.1"', "G5A 硬编码 IP"),
    TestCase("P008", "g5a_scan", "hardcoded_password", 'password = "admin123"', "G5A 硬编码密码"),
    TestCase("P009", "readability_check", "no_docstring", "def foo():\n    return 42", "无 docstring"),
    TestCase("P010", "layer_check", "cross_layer", "from _core.logger import get_logger", "跨层导入（需确认违规）"),
]

# 不应误报的用例（合法代码）
NEGATIVE_CASES = [
    TestCase(
        "N001", "ban_check", "logging", 'import logging\nlogging.info("ok")', "合法 logging 使用", should_detect=False
    ),
    TestCase(
        "N002",
        "naming_check",
        "valid_class",
        "class MyProcessor:\n    pass",
        "合法 PascalCase 类名",
        should_detect=False,
    ),
    TestCase(
        "N003",
        "naming_check",
        "valid_function",
        "def my_function():\n    pass",
        "合法 snake_case 函数",
        should_detect=False,
    ),
    TestCase(
        "N004",
        "g5a_scan",
        "config_ip",
        'host = os.environ.get("DB_HOST", "localhost")',
        "环境变量 IP（非硬编码）",
        should_detect=False,
    ),
    TestCase(
        "N005",
        "readability_check",
        "with_docstring",
        'def foo():\n    """Return 42."""\n    return 42',
        "有 docstring 的函数",
        should_detect=False,
    ),
]

ALL_CASES = POSITIVE_CASES + NEGATIVE_CASES


@dataclass
class SelfCheckResult:
    """自校验结果"""

    case_id: str
    expected: bool  # 期望检测到
    actual: bool  # 实际检测到
    passed: bool
    details: str = ""


@dataclass
class SelfCheckReport:
    """自校验报告"""

    total: int
    passed: int
    failed: int
    true_positives: int  # 检出违规
    false_negatives: int  # 漏报
    true_negatives: int  # 正确放过
    false_positives: int  # 误报
    miss_rate: float  # 漏报率
    false_alarm_rate: float  # 误报率
    results: List  # type: ignore[type-arg]
    checked_at: str


def run_selfcheck(verbose: bool = False) -> SelfCheckReport:
    """运行扫描工具自校验

    为每个测试用例创建临时 Python 文件，运行对应扫描器，检查是否检测到违规。
    """
    results: List[SelfCheckResult] = []
    tmpdir = Path(tempfile.mkdtemp(prefix="scanner_selfcheck_"))

    try:
        for case in ALL_CASES:
            # 创建临时文件
            tmp_file = tmpdir / f"{case.id}.py"
            tmp_file.write_text(case.code, encoding="utf-8")

            # 运行对应扫描器
            detected = _run_scanner_on_file(case.scanner, str(tmp_file))

            passed = detected == case.should_detect
            detail = ""
            if not passed:
                if case.should_detect and not detected:
                    detail = f"FALSE NEGATIVE: expected detection for '{case.rule}'"
                elif not case.should_detect and detected:
                    detail = f"FALSE POSITIVE: unexpected detection for '{case.rule}'"

            results.append(
                SelfCheckResult(
                    case_id=case.id,
                    expected=case.should_detect,
                    actual=detected,
                    passed=passed,
                    details=detail,
                )
            )

            if verbose:
                status = "PASS" if passed else "FAIL"
                print(f"  [{status}] {case.id} ({case.rule}): {case.description}")

    finally:
        # 清理临时文件
        for f in tmpdir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            tmpdir.rmdir()
        except OSError:
            pass

    total = len(results)
    passed = sum(1 for r in results if r.passed)  # type: ignore[assignment,misc]
    failed = total - passed
    tp = sum(1 for r in results if r.expected and r.actual)
    fn = sum(1 for r in results if r.expected and not r.actual)
    tn = sum(1 for r in results if not r.expected and not r.actual)
    fp = sum(1 for r in results if not r.expected and r.actual)

    # 漏报率 = FN / (TP+FN)
    total_positive = tp + fn
    miss_rate = fn / total_positive if total_positive > 0 else 0.0

    # 误报率 = FP / (FP+TN)
    total_negative = fp + tn
    false_alarm_rate = fp / total_negative if total_negative > 0 else 0.0

    return SelfCheckReport(
        total=total,
        passed=passed,
        failed=failed,
        true_positives=tp,
        false_negatives=fn,
        true_negatives=tn,
        false_positives=fp,
        miss_rate=round(miss_rate, 4),
        false_alarm_rate=round(false_alarm_rate, 4),
        results=results,
        checked_at=datetime.datetime.now().isoformat(),
    )


def _run_scanner_on_file(scanner: str, filepath: str) -> bool:
    """在单文件上运行扫描器，返回是否检测到违规"""
    try:
        skill_dir = _PROJECT_ROOT / "scripts" / "skill"
        scanner_map = {
            "ban_check": skill_dir / "skill_ban_check.py",
            "naming_check": skill_dir / "skill_naming_check.py",
            "g5_scan": skill_dir / "skill_g5_scan.py",
            "g5a_scan": skill_dir / "skill_g5a_scan.py",
            "readability_check": skill_dir / "skill_readability_check.py",
            "layer_check": skill_dir / "skill_layer_check.py",
        }

        scanner_path = scanner_map.get(scanner)
        if scanner_path is None or not scanner_path.exists():
            return False

        # 执行扫描器
        import subprocess

        result = subprocess.run(
            [sys.executable, str(scanner_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, "SCAN_FILE": filepath},
        )
        # exit 非 0 表示检测到违规
        return result.returncode != 0
    except Exception:
        return False


def format_report(report: SelfCheckReport) -> str:
    """格式化报告"""
    lines = [
        "=" * 60,
        "  扫描工具自校验报告",
        "=" * 60,
        f"检查时间: {report.checked_at}",
        f"总用例数: {report.total}",
        f"通过: {report.passed}  |  失败: {report.failed}",
        "",
        "── 分类统计 ──",
        f"  TP (正确检出): {report.true_positives}",
        f"  FN (漏报):     {report.false_negatives}",
        f"  TN (正确放过): {report.true_negatives}",
        f"  FP (误报):     {report.false_positives}",
        "",
        "── 关键指标 ──",
        f"  漏报率: {report.miss_rate*100:.1f}%  (目标 ≤5%)  {'✅' if report.miss_rate <= 0.05 else '❌'}",
        f"  误报率: {report.false_alarm_rate*100:.1f}%  (目标 ≤3%)  {'✅' if report.false_alarm_rate <= 0.03 else '❌'}",
        "",
    ]

    if report.failed > 0:
        lines.append("── 失败用例 ──")
        for r in report.results:
            if not r.passed:
                lines.append(f"  [{r.case_id}] {r.details}")

    # 通过判定
    passed_overall = report.miss_rate <= 0.05 and report.false_alarm_rate <= 0.03
    lines.append("")
    lines.append(f"整体判定: {'✅ PASS' if passed_overall else '❌ FAIL'}")

    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="扫描工具自校验")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    report = run_selfcheck(args.verbose)

    if args.json:
        print(
            json.dumps(
                {
                    "total": report.total,
                    "passed": report.passed,
                    "failed": report.failed,
                    "tp": report.true_positives,
                    "fn": report.false_negatives,
                    "tn": report.true_negatives,
                    "fp": report.false_positives,
                    "miss_rate": report.miss_rate,
                    "false_alarm_rate": report.false_alarm_rate,
                    "checked_at": report.checked_at,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(format_report(report))

    # exit code: 0=全部通过, 1=有失败
    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()

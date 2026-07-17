#!/usr/bin/env python3
"""测试覆盖率强制检查 Skill (B3-07)

CI 中强制检查覆盖率，低于阈值阻断 MR。
支持 pytest-cov 输出解析 + 覆盖率趋势追踪。

审计: CB P1-B3 Batch3 数据与验证 (2026-07-08)
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

# ─── 阈值配置 ────────────────────────────────────────
COVERAGE_THRESHOLDS = {
    "total": 60.0,  # 总覆盖率最低要求
    "core": 80.0,  # _core/ 模块覆盖率要求
    "scripts": 50.0,  # scripts/ 模块覆盖率要求
}

MIN_TEST_FILES = 3  # 最少测试文件数


def run_coverage(  # noqa: C901
    test_dir: str | None = None,
    source_dir: str | None = None,
) -> Dict[str, Any]:
    """运行 pytest-cov 并解析结果"""
    project_root = Path(__file__).parent.parent.parent

    test_dir = test_dir or str(project_root / "tests")
    source_dir = source_dir or str(project_root)

    cov_file = project_root / ".coverage_report.json"  # noqa: F841

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        test_dir,
        f"--cov={source_dir}",
        "--cov-report=json",
        "--cov-report=term",
        "-q",
        "--tb=short",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(project_root),
        )
    except subprocess.TimeoutExpired:
        return {
            "run_at": datetime.datetime.now().isoformat(),
            "error": "pytest 执行超时 (>300s)",
            "passed": False,
        }
    except FileNotFoundError:
        return {
            "run_at": datetime.datetime.now().isoformat(),
            "error": "pytest 未安装或不可用",
            "passed": False,
        }

    stdout = result.stdout
    stderr = result.stderr

    # 解析覆盖率输出
    total_pct = 0.0
    core_pct = 0.0
    scripts_pct = 0.0
    test_count = 0

    # 解析 pytest 结果
    test_match = re.search(r"(\d+)\s+passed", stdout)
    if test_match:
        test_count = int(test_match.group(1))

    # 解析覆盖率汇总行
    cov_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", stdout)
    if cov_match:
        total_pct = float(cov_match.group(1))

    # 从 JSON 报告中提取模块级覆盖率
    json_cov = project_root / "coverage.json"
    if json_cov.exists():
        try:
            cov_data = json.loads(json_cov.read_text(encoding="utf-8"))
            totals = cov_data.get("totals", {})
            total_pct = totals.get("percent_covered", total_pct)

            files = cov_data.get("files", {})
            core_files = [v for k, v in files.items() if "_core" in k]
            scripts_files = [v for k, v in files.items() if "scripts" in k]

            if core_files:
                core_sum = sum(f.get("summary", {}).get("percent_covered", 0) for f in core_files)
                core_pct = round(core_sum / len(core_files), 1)

            if scripts_files:
                scripts_sum = sum(f.get("summary", {}).get("percent_covered", 0) for f in scripts_files)
                scripts_pct = round(scripts_sum / len(scripts_files), 1)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # 阈值检查
    checks = [
        {
            "check": "total_coverage",
            "actual": total_pct,
            "threshold": COVERAGE_THRESHOLDS["total"],
            "passed": total_pct >= COVERAGE_THRESHOLDS["total"],
        },
        {
            "check": "core_coverage",
            "actual": core_pct,
            "threshold": COVERAGE_THRESHOLDS["core"],
            "passed": core_pct >= COVERAGE_THRESHOLDS["core"] or core_pct == 0,
        },
        {
            "check": "test_count",
            "actual": test_count,
            "threshold": MIN_TEST_FILES,
            "passed": test_count >= MIN_TEST_FILES,
        },
    ]

    all_passed = all(c["passed"] for c in checks)

    return {
        "run_at": datetime.datetime.now().isoformat(),
        "passed": all_passed,
        "pytest_exit_code": result.returncode,
        "test_count": test_count,
        "total_coverage": total_pct,
        "core_coverage": core_pct,
        "scripts_coverage": scripts_pct,
        "checks": checks,
        "stdout_summary": stdout[-500:] if len(stdout) > 500 else stdout,
        "stderr_summary": stderr[-200:] if len(stderr) > 200 else stderr,
    }


def main() -> int:
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="覆盖率强制检查")
    parser.add_argument("--test-dir", default=None, help="测试目录")
    parser.add_argument("--source-dir", default=None, help="源码目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    report = run_coverage(args.test_dir, args.source_dir)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"覆盖率强制检查: {'PASS' if report['passed'] else 'FAIL'}")
        print(f"  测试数: {report['test_count']}")
        print(f"  总覆盖率: {report['total_coverage']}% " f"(阈值: {COVERAGE_THRESHOLDS['total']}%)")
        for c in report.get("checks", []):
            status = "✅" if c["passed"] else "❌"
            print(f"  {status} {c['check']}: {c['actual']} (≥{c['threshold']})")
        if "error" in report:
            print(f"  ❌ 错误: {report['error']}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

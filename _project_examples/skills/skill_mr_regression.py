#!/usr/bin/env python3
"""MR 全量回归测试自动化 (B4-03)
规范引用: p1_spec §五 HOOK "MR 全量回归测试"
功能: pytest 全量回归+覆盖率强制门禁(total≥60%+_core≥80%)
退出码: 0=通过, 1=测试失败, 2=覆盖率不足
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

COVERAGE_THRESHOLDS = {
    "total": 60.0,  # 总体覆盖率 ≥ 60%
    "_core": 80.0,  # _core 模块覆盖率 ≥ 80%
}


def run_tests(root: Path) -> Tuple[bool, Optional[Dict]]:  # type: ignore[type-arg]
    """运行 pytest 全量测试并返回覆盖率数据"""
    print("[B4-03] MR 全量回归测试 + 覆盖率门禁")
    print("=" * 60)

    # 步骤1: 检查 tests/ 目录
    test_dir = root / "tests"
    if not test_dir.exists():
        print("⚠️  tests/ 目录不存在，自动创建")
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "__init__.py").write_text("# 回归测试套件\n", encoding="utf-8")

    # 步骤2: 运行 pytest --cov
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_dir),
        f"--cov={root}",
        "--cov-report=term",
        "--cov-report=json",
        "--cov-report=html:reports/coverage",
        "-v",
        "--tb=short",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        print("❌ 测试超时 (600s)")
        return False, None
    except FileNotFoundError:
        print("❌ pytest 未安装，请运行: pip install pytest pytest-cov")
        return False, None

    print(result.stdout[-2000:])  # 打印最后2000字符
    if result.stderr:
        print(f"[stderr] {result.stderr[-500:]}")

    # 步骤3: 解析覆盖率 JSON
    cov_data = None
    cov_json = root / "coverage.json"
    if cov_json.exists():
        cov_data = json.loads(cov_json.read_text(encoding="utf-8"))

    return result.returncode == 0, cov_data


def check_coverage(cov_data: Optional[Dict]) -> Tuple[bool, List[Any]]:  # type: ignore
    """检查覆盖率是否达标"""
    issues = []
    if not cov_data:
        issues.append("⚠️  无法获取覆盖率数据 (pytest-cov 未生成 coverage.json)")
        return False, issues

    totals = cov_data.get("totals", {})
    total_pct = totals.get("percent_covered", 0)
    if total_pct < COVERAGE_THRESHOLDS["total"]:
        issues.append(f"❌ 总体覆盖率 {total_pct:.1f}% < {COVERAGE_THRESHOLDS['total']}%")
    else:
        issues.append(f"✅ 总体覆盖率 {total_pct:.1f}% ≥ {COVERAGE_THRESHOLDS['total']}%")

    # 检查 _core 覆盖率
    core_pct = 0.0
    core_count = 0
    files = cov_data.get("files", {})
    for fpath, fdata in files.items():
        if "/_core/" in fpath or "\\_core\\" in fpath:
            core_pct += fdata.get("summary", {}).get("percent_covered", 0)
            core_count += 1
    if core_count > 0:
        core_avg = core_pct / core_count
        if core_avg < COVERAGE_THRESHOLDS["_core"]:
            issues.append(f"❌ _core 覆盖率 {core_avg:.1f}% < {COVERAGE_THRESHOLDS['_core']}%")
        else:
            issues.append(f"✅ _core 覆盖率 {core_avg:.1f}% ≥ {COVERAGE_THRESHOLDS['_core']}%")
    else:
        issues.append("⚠️  未检测到 _core 模块覆盖率数据")

    all_pass = all(not i.startswith("❌") for i in issues)
    return all_pass, issues


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    # 运行测试
    test_ok, cov_data = run_tests(root)

    # 检查覆盖率
    cov_ok, issues = check_coverage(cov_data)

    print(f"\n📋 覆盖率检查结果:")  # noqa: F541
    for issue in issues:
        print(f"   {issue}")

    print("=" * 60)

    if not test_ok:
        print("❌ 测试失败 (退出码=1)")
        return 1
    if not cov_ok:
        print("❌ 覆盖率不达标 (退出码=2)")
        return 2
    print("✅ MR 全量回归测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

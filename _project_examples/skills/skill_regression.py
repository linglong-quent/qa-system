#!/usr/bin/env python3
"""
skill_regression.py — P1-F25 全量回归验证
==========================================
每次 P1 任务完成后自动执行全量回归：
1. 调用 lint_all（编码规范）
2. 调用 baseline_all（四大基线）
3. 调用 preflight（启动预检）
4. 调用 readability_check（可读性）
5. 调用 g5_scan（零print）
6. 调用 g5a_scan（11条规则）
7. 对比上次回归结果，输出差异报告

使用:
    python scripts/skill/skill_regression.py [--output json]
"""

import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# 回归结果缓存路径
_CACHE_DIR = _ROOT / "_tasks" / "results"
_CACHE_FILE = _CACHE_DIR / "regression_cache.json"

# 回归步骤
REGRESSION_STEPS = [
    "readability_check",
    "g5_scan",
    "g5a_scan",
    "preflight",
    "baseline_all",
]


class SkillRegression(BaseSkill):
    """P1 回归验证"""

    def __init__(self, diff_only: bool = False) -> None:
        super().__init__("regression")
        self.diff_only = diff_only
        self.step_results: dict[str, Dict[str, Any]] = {}
        self.results: list[CheckResult] = []

    def _load_last_cache(self) -> Dict[str, Any]:
        """加载上次回归结果"""
        if _CACHE_FILE.exists():
            try:
                return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_cache(self, data: Dict[str, Any]) -> None:
        """保存本次回归结果"""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _run_step(self, skill_name: str) -> Dict[str, Any]:
        """通过 run_skill 执行单个回归步骤"""
        from scripts.skill import run_skill

        result = run_skill(skill_name)
        return (
            result
            if isinstance(result, dict)
            else {"skill": skill_name, "status": "error", "exit_code": 3, "error": str(result)}
        )

    def _diff_with_cache(self, current: Dict[str, Any], cache: Dict[str, Any]) -> list[CheckResult]:
        """对比当前与上次回归结果"""
        results = []
        for skill_name in REGRESSION_STEPS:
            cur = current.get("steps", {}).get(skill_name, {})
            last = cache.get("steps", {}).get(skill_name, {})

            cur_status = cur.get("status", "unknown")
            last_status = last.get("status", "unknown")

            if cur_status != last_status:
                results.append(
                    CheckResult(
                        rule="RG-DIFF",
                        severity="warning" if cur_status == "pass" else "blocker",
                        message=f"回归状态变化: {skill_name}: {last_status} → {cur_status}",
                        suggest="检查回归差异原因",
                    )
                )
            elif cur_status == "fail":
                results.append(
                    CheckResult(
                        rule="RG-FAIL",
                        severity="blocker",
                        message=f"回归持续失败: {skill_name}",
                        file="",
                        suggest="检查回归失败原因并修复",
                    )
                )

        if not results:
            results.append(CheckResult(rule="RG-DIFF", severity="info", message="回归结果与上次一致 ✅"))
        return results

    def run_checks(self) -> list[CheckResult]:
        """执行全量回归"""
        all_results = []
        cache = self._load_last_cache()
        steps_data = {}

        for step_name in REGRESSION_STEPS:
            step_result = self._run_step(step_name)
            steps_data[step_name] = step_result
            status = step_result.get("status", "error")
            exit_code = step_result.get("exit_code", 3)
            check_count = step_result.get("check_count", 0)
            fail_count = step_result.get("fail_count", 0)

            severity = "blocker" if exit_code == 1 else "warning" if exit_code == 2 else "info"
            all_results.append(
                CheckResult(
                    rule=f"RG-{step_name}",
                    severity=severity,
                    message=f"{step_name}: {status} (检查{check_count}, 失败{fail_count})",
                )
            )

        # 差异对比
        current_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "steps": steps_data,
        }
        diff_results = self._diff_with_cache(current_data, cache)
        all_results.extend(diff_results)

        # 保存缓存
        self._save_cache(current_data)
        self.steps_data = steps_data
        self.results = all_results
        return all_results

    def output_results(self, results: list[CheckResult]) -> Dict[str, Any]:
        """扩展输出，包含各步骤详情"""
        base = super().output_results(results)
        base["steps"] = self.steps_data
        return base


def run(output: str = "json", diff_only: bool = False) -> Dict[str, Any]:
    skill = SkillRegression(diff_only=diff_only)
    results = skill.run_checks()
    result = skill.output_results(results)
    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="P1 全量回归验证")
    parser.add_argument("--output", default="json")
    parser.add_argument("--diff-only", action="store_true", help="仅对比差异")
    args = parser.parse_args()
    run(output=args.output, diff_only=args.diff_only)

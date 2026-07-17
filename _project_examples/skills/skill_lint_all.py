#!/usr/bin/env python3
"""
skill_lint_all.py — 编码全扫描一站式入口 (P1-F26)
===================================================
聚合调用 F04(禁令7条) / F05(命名规范) / F06(可读性) / F13(G5零print) / F14(G5A十一项规则)
的扫描器，汇总输出统一报告。

复用已有扫描器，不重复造轮：
  F04 → skill_ban_check.py  (via import)
  F05 → skill_naming_check.py (via import → main() 改造为模块调用)
  F06 → skill_readability_check.py  (via run_skill)
  F13 → skill_g5_scan.py           (via run_skill)
  F14 → skill_g5a_scan.py          (via run_skill)

使用:
    python scripts/skill/skill_lint_all.py [--output json] [--path DIR]

退出码:
    0 = 全部通过
    1 = 阻断级违规 (blocker)
    2 = 仅有警告 (warning)
    3 = 执行错误
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# 聚合的扫描步骤
LINT_STEPS = [
    "ban_check",  # F04: 量化禁令7条
    "naming_check",  # F05: 命名规范
    "readability_check",  # F06: 代码可读性
    "g5_scan",  # F13: 零print扫描
    "g5a_scan",  # F14: G5A十一项规则
]

STEP_LABELS = {
    "ban_check": "F04 量化禁令7条",
    "naming_check": "F05 命名规范",
    "readability_check": "F06 代码可读性",
    "g5_scan": "F13 零print扫描",
    "g5a_scan": "F14 G5A十一项规则",
}


class SkillLintAll(BaseSkill):
    """编码全扫描聚合器"""

    def __init__(self, target_dir: Optional[str] = None):
        super().__init__("lint_all")
        self.target_dir = Path(target_dir or ".").resolve()
        if not self.target_dir.is_absolute():
            self.target_dir = (_ROOT / self.target_dir).resolve()
        self.step_results: dict[str, Dict[str, Any]] = {}
        self.results: list[CheckResult] = []

    def _run_ban_check(self) -> Dict[str, Any]:
        """F04: 量化禁令7条 — 直接 import 扫描模块"""
        try:
            from scripts.skill.skill_naming_check import scan_directory

            issues = scan_directory(self.target_dir)

            blocker_count = sum(1 for i in issues if i.severity == "blocker")
            error_count = sum(1 for i in issues if i.severity == "error")
            warning_count = sum(1 for i in issues if i.severity == "warning")

            if blocker_count > 0:
                status, exit_code = "fail", 1
            elif error_count > 0 or warning_count > 0:
                status, exit_code = "warning", 2
            else:
                status, exit_code = "pass", 0

            return {
                "skill": "ban_check",
                "status": status,
                "exit_code": exit_code,
                "check_count": len(issues),
                "fail_count": blocker_count,
                "blocker_count": blocker_count,
                "error_count": error_count,
                "warning_count": warning_count,
                "results": issues,
            }
        except Exception as e:
            return {
                "skill": "ban_check",
                "status": "error",
                "exit_code": 3,
                "error": str(e),
            }

    def _run_naming_check(self) -> Dict[str, Any]:
        """F05: 命名规范 — 直接 import 扫描模块"""
        try:
            from scripts.skill.skill_naming_check import load_naming_rules
            from scripts.skill.skill_naming_check import scan_directory as naming_scan

            rules = load_naming_rules()  # noqa: F841
            issues = naming_scan(self.target_dir)

            # NamingIssue 是普通类（非 dict），用属性访问
            blocker_count = sum(1 for i in issues if getattr(i, "severity", "") == "blocker")
            error_count = sum(1 for i in issues if getattr(i, "severity", "") == "error")
            warning_count = sum(1 for i in issues if getattr(i, "severity", "") == "warning")

            if blocker_count > 0:
                status, exit_code = "fail", 1
            elif error_count > 0 or warning_count > 0:
                status, exit_code = "warning", 2
            else:
                status, exit_code = "pass", 0

            # 将 NamingIssue 对象转为可序列化 dict
            serializable = []
            for i in issues:
                d = {
                    "rule": getattr(i, "rule", ""),
                    "severity": getattr(i, "severity", ""),
                    "file": getattr(i, "file", ""),
                    "line": getattr(i, "line", 0),
                    "message": getattr(i, "message", ""),
                    "suggest": getattr(i, "suggest", ""),
                }
                serializable.append(d)

            return {
                "skill": "naming_check",
                "status": status,
                "exit_code": exit_code,
                "check_count": len(issues),
                "fail_count": blocker_count,
                "blocker_count": blocker_count,
                "error_count": error_count,
                "warning_count": warning_count,
                "results": serializable,
            }
        except Exception as e:
            return {
                "skill": "naming_check",
                "status": "error",
                "exit_code": 3,
                "error": str(e),
            }

    def _run_via_registry(self, skill_name: str) -> Dict[str, Any]:
        """通过 __init__.py run_skill 执行 registry 中的 Skill"""
        try:
            from scripts.skill import run_skill

            result = run_skill(skill_name, {"output": "json"})
            return (
                result
                if isinstance(result, dict)
                else {
                    "skill": skill_name,
                    "status": "error",
                    "exit_code": 3,
                    "error": str(result),
                }
            )
        except Exception as e:
            return {
                "skill": skill_name,
                "status": "error",
                "exit_code": 3,
                "error": str(e),
            }

    def run_checks(self) -> list[CheckResult]:  # noqa: C901
        """顺序执行全部扫描步骤"""
        all_results: list[CheckResult] = []
        steps_data: dict[str, Dict[str, Any]] = {}

        start = time.time()

        for step_name in LINT_STEPS:
            step_start = time.time()

            if step_name == "ban_check":
                result = self._run_ban_check()
            elif step_name == "naming_check":
                result = self._run_naming_check()
            elif step_name == "readability_check":
                result = self._run_via_registry("readability_check")
            elif step_name == "g5_scan":
                result = self._run_via_registry("g5_scan")
            elif step_name == "g5a_scan":
                result = self._run_via_registry("g5a_scan")
            else:
                result = {
                    "skill": step_name,
                    "status": "error",
                    "exit_code": 3,
                    "error": f"未知步骤: {step_name}",
                }

            result["duration_ms"] = round((time.time() - step_start) * 1000, 2)
            steps_data[step_name] = result

            status = result.get("status", "error")
            exit_code = result.get("exit_code", 3)
            fail_count = result.get("fail_count", 0)
            check_count = result.get("check_count", 0)

            label = STEP_LABELS.get(step_name, step_name)

            if exit_code == 0:
                sev = "info"
            elif exit_code == 1:
                sev = "blocker"
            elif exit_code == 2:
                sev = "warning"
            else:
                sev = "error"

            # 构建汇总消息
            msg_parts = [f"{label}: {status}"]
            if check_count > 0:
                msg_parts.append(f"检查{check_count}项")
            if fail_count > 0:
                msg_parts.append(f"失败{fail_count}项")
            if result.get("error"):
                msg_parts.append(f"错误: {result['error']}")

            all_results.append(
                CheckResult(
                    rule=f"LINT-{step_name}",
                    severity=sev,
                    message=", ".join(msg_parts),
                )
            )

        self.steps_data = steps_data
        self.total_duration_ms = round((time.time() - start) * 1000, 2)
        self.results = all_results
        return all_results

    def output_results(self, results: list[CheckResult]) -> Dict[str, Any]:
        """扩展输出"""
        base = super().output_results(results)
        base["steps"] = self.steps_data
        base["duration_ms"] = self.total_duration_ms

        # 汇总统计
        total_checks = sum(s.get("check_count", 0) for s in self.steps_data.values())
        total_blockers = sum(s.get("blocker_count", 0) or s.get("fail_count", 0) for s in self.steps_data.values())
        base["total_checks"] = total_checks
        base["total_blockers"] = total_blockers

        # ─── 串联结果校验 ──────────────────────────────────
        # 任何步骤 exit_code != 0 则 lint_all 为 fail
        exit_codes = [s.get("exit_code", 3) for s in self.steps_data.values()]
        if any(c == 1 for c in exit_codes):
            base["status"] = "fail"
            base["exit_code"] = 1
        elif any(c == 2 for c in exit_codes):
            base["status"] = "warning"
            base["exit_code"] = 2
        elif any(c == 3 for c in exit_codes):
            base["status"] = "error"
            base["exit_code"] = 3
        # else: stay "pass" with exit_code 0

        return base


def run(output: str = "json", path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """
    统一入口函数，兼容 run_skill 调用。

    Args:
        output: 输出格式 (json)
        path: 扫描目标目录（默认 linglong/）

    Returns:
        结构化结果 dict
    """
    target = path or "."
    skill = SkillLintAll(target_dir=target)
    results = skill.run_checks()
    result = skill.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="编码全扫描一站式 (F26)")
    parser.add_argument("--output", default="json")
    parser.add_argument("--path", default=None, help="扫描目标目录")
    args = parser.parse_args()
    run(output=args.output, path=args.path)

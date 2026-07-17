#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_mr_full.py — MR 全流程一站式校验 (B1-05)
=================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-05)

职责: MR 合并前全量校验一站式入口
  1. lint_all — 编码规范全扫描
  2. baseline_all — 四大基线
  3. preflight — 启动预检
  4. asset_scan — 资产复用巡检
  5. doc_consistency — 文档一致性

用法:
    python scripts/skill/skill_mr_full.py
    python scripts/skill/skill_mr_full.py --skip asset_scan
    python scripts/skill/skill_mr_full.py --output json

退出码:
    0 = 全部通过
    1 = 阻断 (blocker)
    2 = 告警 (warning)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# ═══════════════════════════════════════════════════════════════
# MR 校验步骤定义
# ═══════════════════════════════════════════════════════════════

MR_STEPS = [
    {
        "name": "lint_all",
        "label": "编码规范全扫描 (F26)",
        "module": "scripts.skill.skill_lint_all",
        "func": "run",
        "priority": "P0",
        "blocking": True,
    },
    {
        "name": "baseline_all",
        "label": "四大基线校验 (F21)",
        "module": "scripts.skill.skill_baseline_all",
        "func": "run",
        "priority": "P0",
        "blocking": True,
    },
    {
        "name": "preflight",
        "label": "环境启动预检 (F19)",
        "module": "scripts.skill.skill_preflight",
        "func": "run",
        "priority": "P0",
        "blocking": True,
    },
    {
        "name": "asset_scan",
        "label": "资产复用巡检",
        "module": "scripts.skill.skill_asset_scan",
        "func": "run",
        "priority": "P1",
        "blocking": False,
    },
    {
        "name": "doc_consistency",
        "label": "文档一致性 (R01)",
        "module": "scripts.skill.skill_doc_consistency",
        "func": "run",
        "priority": "P1",
        "blocking": False,
    },
    {
        "name": "registry_guard",
        "label": "注册表门禁 (F28)",
        "module": "scripts.skill.skill_registry_guard",
        "func": "run",
        "priority": "P0",
        "blocking": True,
    },
]


class SkillMRFull(BaseSkill):
    """MR 全流程一站式校验"""

    def __init__(self, skip: Optional[list[str]] = None):
        super().__init__("mr_full")
        self.skip = set(skip or [])
        self.step_results: dict[str, Dict[str, Any]] = {}

    def _run_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个校验步骤"""
        name = step["name"]
        if name in self.skip:
            return {
                "step": name,
                "label": step["label"],
                "status": "skipped",
                "exit_code": 0,
                "duration_ms": 0,
            }

        start = time.time()
        try:
            import importlib

            module = importlib.import_module(step["module"])
            func = getattr(module, step["func"], None)
            if func is None:
                return {
                    "step": name,
                    "label": step["label"],
                    "status": "error",
                    "exit_code": 3,
                    "error": f"函数 {step['func']} 不存在",
                    "duration_ms": round((time.time() - start) * 1000, 2),
                }
            result = func()
            duration = round((time.time() - start) * 1000, 2)

            if isinstance(result, dict):
                return {
                    "step": name,
                    "label": step["label"],
                    "status": result.get("status", "unknown"),
                    "exit_code": result.get("exit_code", 3),
                    "check_count": result.get("check_count", 0),
                    "fail_count": result.get("fail_count", 0),
                    "duration_ms": duration,
                }
            return {
                "step": name,
                "label": step["label"],
                "status": "pass",
                "exit_code": 0,
                "duration_ms": duration,
            }
        except ImportError:
            return {
                "step": name,
                "label": step["label"],
                "status": "skipped",
                "exit_code": 0,
                "error": "模块不可导入",
                "duration_ms": round((time.time() - start) * 1000, 2),
            }
        except Exception as e:
            return {
                "step": name,
                "label": step["label"],
                "status": "error",
                "exit_code": 3,
                "error": str(e),
                "duration_ms": round((time.time() - start) * 1000, 2),
            }

    def run_checks(self) -> list[CheckResult]:
        """执行全量 MR 校验"""
        results: list[CheckResult] = []
        start = time.time()

        for step in MR_STEPS:
            step_result = self._run_step(step)
            self.step_results[step["name"]] = step_result  # type: ignore[index]

            exit_code = step_result.get("exit_code", 3)
            status = step_result.get("status", "error")
            label = step_result.get("label", step["name"])

            if status == "skipped":
                sev = "info"
                msg = f"[SKIP] {label}"
            elif exit_code == 0:
                sev = "info"
                msg = f"[PASS] {label} ({step_result.get('duration_ms', 0):.0f}ms)"
            elif exit_code == 1:
                sev = "blocker" if step.get("blocking") else "warning"
                msg = f"[FAIL] {label}: exit={exit_code}"
            elif exit_code == 2:
                sev = "warning"
                msg = f"[WARN] {label}: exit={exit_code}"
            else:
                sev = "error"
                msg = f"[ERROR] {label}: {step_result.get('error', 'unknown')}"

            results.append(
                CheckResult(
                    rule=f"MR-{step['name']}",
                    severity=sev,
                    message=msg,
                )
            )

        self._total_duration_ms = round((time.time() - start) * 1000, 2)
        return results

    def output_results(self, results: list[CheckResult]) -> Dict[str, Any]:
        """扩展输出"""
        base = super().output_results(results)
        base["steps"] = self.step_results
        base["duration_ms"] = self._total_duration_ms

        # 聚合退出码
        exit_codes = [s.get("exit_code", 3) for s in self.step_results.values()]
        if any(c == 1 for c in exit_codes):
            base["status"], base["exit_code"] = "fail", 1
        elif any(c == 2 for c in exit_codes):
            base["status"], base["exit_code"] = "warning", 2
        elif any(c == 3 for c in exit_codes):
            base["status"], base["exit_code"] = "error", 3

        return base


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", skip: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """统一入口"""
    skip_list = [s.strip() for s in skip.split(",")] if skip else []
    checker = SkillMRFull(skip=skip_list)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  MR 全流程校验报告")  # noqa: F541
        print(f"{'='*60}")
        for step_name, sr in checker.step_results.items():
            icon = {"pass": "✓", "fail": "✗", "warning": "⚠", "skipped": "○", "error": "✗"}.get(
                sr.get("status", ""), "?"
            )
            print(
                f"  [{icon}] {sr['label']}: {sr.get('status')} "
                f"(exit={sr.get('exit_code')}, {sr.get('duration_ms', 0):.0f}ms)"
            )
            if sr.get("error"):
                print(f"       错误: {sr['error']}")
        print(f"{'='*60}")
        print(f"  总耗时: {checker._total_duration_ms:.0f}ms")
        print(f"  状态: {result['status']}  exit={result['exit_code']}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MR 全流程一站式校验")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--skip", default=None, help="跳过的步骤(逗号分隔)")
    args = parser.parse_args()
    result = run(output=args.output, skip=args.skip)
    sys.exit(result.get("exit_code", 0))

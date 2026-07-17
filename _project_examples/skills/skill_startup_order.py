#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_startup_order.py — 启动加载顺序强制校验 (B1-15)
========================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-15)

职责: 程序启动时强制校验加载顺序
  引用: p1_spec.md §十一「启动加载顺序校验」

强制顺序:
  1. 配置加载 (config → yaml → env)
  2. 日志初始化 (logger)
  3. 数据库连接 (DB pool)
  4. 风控侧车连接 (sidecar)
  5. 策略加载 (strategies)

用法:
    python scripts/skill/skill_startup_order.py
    python scripts/skill/skill_startup_order.py --check
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# ═══════════════════════════════════════════════════════════════
# 安全的导入检查（替代 exec）
# ═══════════════════════════════════════════════════════════════


def _try_import_check(check_str: str) -> None:
    """安全解析并执行导入检查语句。

    支持的格式：
      - "import module_name"
      - "from module_name import name"
    """
    stripped = check_str.strip()
    if stripped.startswith("from "):
        # from X import Y
        parts = stripped[5:].split(" import ")
        if len(parts) == 2:
            module_name = parts[0].strip()
            name = parts[1].strip()
            __import__(module_name, fromlist=[name])
        else:
            raise ValueError(f"无法解析 from-import 语句: {check_str}")
    elif stripped.startswith("import "):
        module_name = stripped[7:].strip()
        __import__(module_name)
    else:
        raise ValueError(f"不支持的检查语句: {check_str}")


# ═══════════════════════════════════════════════════════════════
# 启动顺序定义
# ═══════════════════════════════════════════════════════════════

STARTUP_STEPS = [
    {
        "order": 1,
        "name": "config",
        "label": "配置加载",
        "check": "import _core.config_loader",
        "required": True,
        "timeout_ms": 5000,
    },
    {
        "order": 2,
        "name": "logger",
        "label": "日志初始化",
        "check": "import _core.logger",
        "required": True,
        "timeout_ms": 3000,
    },
    {
        "order": 3,
        "name": "db",
        "label": "数据库连接",
        "check": "from data.db_pool import get_connection",
        "required": True,
        "timeout_ms": 10000,
    },
    {
        "order": 4,
        "name": "sidecar",
        "label": "风控侧车",
        "check": "from sidecar.risk_sidecar import RiskSidecar",
        "required": True,
        "timeout_ms": 15000,
    },
    {
        "order": 5,
        "name": "strategies",
        "label": "策略加载",
        "check": "import strategies",
        "required": False,
        "timeout_ms": 30000,
    },
]


class SkillStartupOrder(BaseSkill):
    """启动加载顺序强制校验"""

    def __init__(self) -> None:
        super().__init__("startup_order")

    def _check_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """检查单个启动步骤"""
        start = time.time()
        result = {
            "step": step["name"],
            "label": step["label"],
            "order": step["order"],
            "required": step["required"],
        }

        try:
            _try_import_check(step["check"])
            result["status"] = "pass"
            result["exit_code"] = 0
        except ImportError as e:
            if step["required"]:
                result["status"] = "fail"
                result["exit_code"] = 1
                result["error"] = f"必需模块不可导入: {e}"
            else:
                result["status"] = "warning"
                result["exit_code"] = 2
                result["error"] = f"可选模块不可导入: {e}"
        except Exception as e:
            result["status"] = "error"
            result["exit_code"] = 3
            result["error"] = str(e)

        result["duration_ms"] = round((time.time() - start) * 1000, 2)
        return result

    def run_checks(self) -> list[CheckResult]:
        """执行启动顺序校验"""
        results: list[CheckResult] = []

        for step in STARTUP_STEPS:
            sr = self._check_step(step)
            icon = {"pass": "✓", "fail": "✗", "warning": "⚠", "error": "✗"}.get(sr["status"], "?")  # noqa: F841

            if sr["status"] == "pass":
                sev = "info"
            elif sr["status"] == "fail":
                sev = "blocker"
            else:
                sev = "warning"

            msg = f"#{sr['order']} {sr['label']}: {sr['status']} ({sr.get('duration_ms', 0):.0f}ms)"
            if sr.get("error"):
                msg += f" — {sr['error']}"

            results.append(
                CheckResult(
                    rule=f"STARTUP-{step['order']:02d}",
                    severity=sev,
                    message=msg,
                )
            )

        return results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text") -> Dict[str, Any]:
    checker = SkillStartupOrder()
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n启动加载顺序校验报告")  # noqa: F541
        print(f"{'='*50}")
        for r in results:
            icon = {"info": "✓", "warning": "⚠", "blocker": "✗"}.get(r.severity, "?")
            print(f"  [{icon}] {r.message}")
        print(f"{'='*50}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="启动加载顺序校验")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--check", action="store_true", help="执行检查")
    args = parser.parse_args()
    result = run(output=args.output)
    sys.exit(result.get("exit_code", 0))

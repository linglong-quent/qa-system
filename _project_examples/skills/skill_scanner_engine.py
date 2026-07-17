#!/usr/bin/env python3
"""
skill_scanner_engine.py — 统一扫描引擎 (P1-E01)
================================================
查表驱动，统一调度 F04(禁令)/F05(命名)/F06(可读性)/F13(G5零print)/F14(G5A)/layer_check
与 lint_all 的区别：scanner_engine 从 registry.yaml 查表决定扫描组合，
按 quality_gate 动态解析，不硬编码步骤列表。

架构:
    skill_registry.yaml (quality_gates 字段)
         │
         ▼
    scanner_engine.py (查表 → 解析 gate → 调度对应 Skill)
         │
         ├── skill_ban_check.py       (F04)
         ├── skill_naming_check.py    (F05)
         ├── skill_readability_check  (F06)
         ├── skill_g5_scan.py         (F13)
         ├── skill_g5a_scan.py        (F14)
         └── skill_layer_check.py     (layer)

用法:
    python scripts/skill/skill_scanner_engine.py --gate G5
    python scripts/skill/skill_scanner_engine.py --all
    python scripts/skill/skill_scanner_engine.py --scan ban_check,naming_check

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

import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# ─── 注册表路径 ──────────────────────────────────────────
_REGISTRY_PATH = Path(__file__).resolve().parent / "skill_registry.yaml"

# ─── 扫描器到 Skill 名的映射 (用于直接 --scan) ───────────
SCANNER_MAP = {
    "ban_check": "ban_check",
    "naming_check": "naming_check",
    "readability_check": "readability_check",
    "g5_scan": "g5_scan",
    "g5a_scan": "g5a_scan",
    "layer_check": "layer_check",
}

SCANNER_LABELS = {
    "ban_check": "F04 量化禁令7条",
    "naming_check": "F05 命名规范",
    "readability_check": "F06 代码可读性",
    "g5_scan": "F13 零print扫描",
    "g5a_scan": "F14 G5A十一项规则",
    "layer_check": "分层架构校验",
}


class ScannerEngine(BaseSkill):
    """统一扫描引擎 — 查表驱动调度"""

    def __init__(
        self,
        gate: Optional[str] = None,
        scanners: Optional[list[str]] = None,
        target_dir: Optional[str] = None,
        run_all: bool = False,
    ):
        super().__init__("scanner_engine")
        self.gate = gate
        self.scanners = scanners or []
        self.run_all = run_all
        self.target_dir = Path(target_dir or ".").resolve()
        if not self.target_dir.is_absolute():
            self.target_dir = (_ROOT / self.target_dir).resolve()
        self.step_results: dict[str, Dict[str, Any]] = {}
        self.results: list[CheckResult] = []
        self._registry: Optional[Dict[str, Any]] = None

    # ─── 注册表加载 ──────────────────────────────────────

    def _load_registry(self) -> Dict[str, Any]:
        """加载 skill_registry.yaml"""
        if self._registry is None:
            if _REGISTRY_PATH.is_file():
                with open(_REGISTRY_PATH, encoding="utf-8") as f:
                    self._registry = yaml.safe_load(f)
            else:
                self._registry = {}
        return self._registry or {}

    def _resolve_scanners(self) -> list[str]:
        """查表解析：根据 gate / scanners / all 决定执行哪些扫描器"""
        if self.scanners:
            # 直接指定扫描器列表
            valid = [s for s in self.scanners if s in SCANNER_MAP]
            return valid

        registry = self._load_registry()
        skills = registry.get("skills", {})

        if self.gate:
            # 查表：找所有 quality_gates 包含指定 gate 且 enabled=true 的 Skill
            gate_upper = self.gate.upper()
            resolved = []
            for name, entry in skills.items():
                if not entry.get("enabled", True):
                    continue
                gates = entry.get("quality_gates", [])
                if gate_upper in gates and name in SCANNER_MAP:
                    resolved.append(name)
            return resolved

        if self.run_all:
            # 全部启用的扫描器
            return [s for s in SCANNER_MAP if skills.get(s, {}).get("enabled", True)]

        return []

    # ─── 扫描执行 ────────────────────────────────────────

    def _run_ban_check(self) -> Dict[str, Any]:
        """F04: 量化禁令7条"""
        try:
            from scripts.skill.skill_ban_check import scan_directory

            issues = scan_directory(self.target_dir)
            blocker_count = sum(1 for i in issues if i.get("severity") == "blocker")
            error_count = sum(1 for i in issues if i.get("severity") == "error")
            warning_count = sum(1 for i in issues if i.get("severity") == "warning")

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
            return {"skill": "ban_check", "status": "error", "exit_code": 3, "error": str(e)}

    def _run_naming_check(self) -> Dict[str, Any]:
        """F05: 命名规范"""
        try:
            from scripts.skill.skill_naming_check import scan_directory as naming_scan

            issues = naming_scan(self.target_dir)
            blocker_count = sum(1 for i in issues if getattr(i, "severity", "") == "blocker")
            error_count = sum(1 for i in issues if getattr(i, "severity", "") == "error")
            warning_count = sum(1 for i in issues if getattr(i, "severity", "") == "warning")

            if blocker_count > 0:
                status, exit_code = "fail", 1
            elif error_count > 0 or warning_count > 0:
                status, exit_code = "warning", 2
            else:
                status, exit_code = "pass", 0

            serializable = []
            for i in issues:
                serializable.append(
                    {
                        "rule": getattr(i, "rule", ""),
                        "severity": getattr(i, "severity", ""),
                        "file": getattr(i, "file", ""),
                        "line": getattr(i, "line", 0),
                        "message": getattr(i, "message", ""),
                        "suggest": getattr(i, "suggest", ""),
                    }
                )

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
            return {"skill": "naming_check", "status": "error", "exit_code": 3, "error": str(e)}

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
            return {"skill": skill_name, "status": "error", "exit_code": 3, "error": str(e)}

    # ─── 统一调度 ────────────────────────────────────────

    def run_checks(self) -> list[CheckResult]:  # noqa: C901
        """查表驱动：解析扫描列表 → 逐个执行 → 汇总"""
        scanner_names = self._resolve_scanners()

        if not scanner_names:
            return [
                CheckResult(
                    rule="SCAN-000",
                    severity="error",
                    message=f"未解析到任何扫描器 (gate={self.gate}, scanners={self.scanners}, all={self.run_all})",
                    suggest="请检查 skill_registry.yaml 的 quality_gates 配置",
                )
            ]

        all_results: list[CheckResult] = []
        steps_data: dict[str, Dict[str, Any]] = {}
        start = time.time()

        for scan_name in scanner_names:
            step_start = time.time()

            if scan_name == "ban_check":
                result = self._run_ban_check()
            elif scan_name == "naming_check":
                result = self._run_naming_check()
            elif scan_name == "readability_check":
                result = self._run_via_registry("readability_check")
            elif scan_name == "g5_scan":
                result = self._run_via_registry("g5_scan")
            elif scan_name == "g5a_scan":
                result = self._run_via_registry("g5a_scan")
            elif scan_name == "layer_check":
                result = self._run_via_registry("layer_check")
            else:
                result = {
                    "skill": scan_name,
                    "status": "error",
                    "exit_code": 3,
                    "error": f"未知扫描器: {scan_name}",
                }

            result["duration_ms"] = round((time.time() - step_start) * 1000, 2)
            steps_data[scan_name] = result

            status = result.get("status", "error")
            exit_code = result.get("exit_code", 3)
            fail_count = result.get("fail_count", 0)
            check_count = result.get("check_count", 0)
            label = SCANNER_LABELS.get(scan_name, scan_name)

            if exit_code == 0:
                sev = "info"
            elif exit_code == 1:
                sev = "blocker"
            elif exit_code == 2:
                sev = "warning"
            else:
                sev = "error"

            msg_parts = [f"{label}: {status}"]
            if check_count > 0:
                msg_parts.append(f"检查{check_count}项")
            if fail_count > 0:
                msg_parts.append(f"失败{fail_count}项")
            if result.get("error"):
                msg_parts.append(f"错误: {result['error']}")

            all_results.append(
                CheckResult(
                    rule=f"SCAN-{scan_name}",
                    severity=sev,
                    message=", ".join(msg_parts),
                )
            )

        self.steps_data = steps_data
        self.total_duration_ms = round((time.time() - start) * 1000, 2)
        self.results = all_results
        return all_results

    def output_results(self, results: list[CheckResult]) -> Dict[str, Any]:
        """扩展输出：包含 steps 详情 + 汇总统计"""
        base = super().output_results(results)
        base["steps"] = self.steps_data
        base["duration_ms"] = self.total_duration_ms

        total_checks = sum(s.get("check_count", 0) for s in self.steps_data.values())
        total_blockers = sum(s.get("blocker_count", 0) or s.get("fail_count", 0) for s in self.steps_data.values())
        base["total_checks"] = total_checks
        base["total_blockers"] = total_blockers
        base["engine"] = "scanner_engine"
        base["gate"] = self.gate

        # 串联结果校验
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

        return base


# ─── CLI / run 入口 ──────────────────────────────────────


def run(output: str = "json", gate: str = None, scan: str = None, path: str = None, all: bool = False) -> Dict[str, Any]:  # type: ignore[assignment]  # noqa: E501
    """
    统一入口函数，兼容 run_skill 调用。

    Args:
        output: 输出格式 (json)
        gate: 按质量关执行 (G5/G5A/G6/...)
        scan: 逗号分隔的扫描器列表 (ban_check,naming_check)
        path: 扫描目标目录
        all: 执行全部扫描器
    """
    scanners = None
    if scan:
        scanners = [s.strip() for s in scan.split(",")]

    target = path or "."
    engine = ScannerEngine(gate=gate, scanners=scanners, target_dir=target, run_all=all)
    results = engine.run_checks()
    result = engine.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="统一扫描引擎 (P1-E01)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--gate", default=None, help="按质量关执行 (G5/G5A/G6/...)")
    group.add_argument("--scan", default=None, help="逗号分隔扫描器 (ban_check,naming_check,...)")
    group.add_argument("--all", action="store_true", help="执行全部扫描器")
    parser.add_argument("--output", default="json")
    parser.add_argument("--path", default=None, help="扫描目标目录")
    args = parser.parse_args()
    run(output=args.output, gate=args.gate, scan=args.scan, path=args.path, all=args.all)

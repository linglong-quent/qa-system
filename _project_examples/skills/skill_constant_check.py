#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_constant_check.py — 时间常量池 G5A 裸写检测 (B1-09)
===========================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-09)

职责: 检测硬编码时间常量、重复字符串、磁盘/内存阈值裸写
  引用: p1_spec.md §六「时间常量池」+ §六「磁盘/内存阈值全局管控」

检测规则:
  1. 时间常量裸写: "09:30", "14:57", "T+1" 等不在 constants.py 中引用
  2. 重复硬编码字符串: 板块/行业/标签名硬编码
  3. 磁盘/内存阈值硬编码: 如 disk_threshold=90 未从配置读取

用法:
    python scripts/skill/skill_constant_check.py
    python scripts/skill/skill_constant_check.py --output json

退出码:
    0 = 全部合规
    1 = 发现硬编码常量
    2 = 告警
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
# 检测规则
# ═══════════════════════════════════════════════════════════════

# 时间常量模式（裸写检测）
TIME_LITERAL_PATTERNS = [
    (r'"09:?30"', "开盘时间 09:30 应使用 constants.MARKET_OPEN_TIME"),
    (r"'09:?30'", "开盘时间 09:30 应使用 constants.MARKET_OPEN_TIME"),
    (r'"14:?57"', "收盘前 14:57 应使用 constants.LAST_CALL_TIME"),
    (r"'14:?57'", "收盘前 14:57 应使用 constants.LAST_CALL_TIME"),
    (r'"15:?00"', "收盘时间 15:00 应使用 constants.MARKET_CLOSE_TIME"),
    (r"'15:?00'", "收盘时间 15:00 应使用 constants.MARKET_CLOSE_TIME"),
    (r'"T\+1"', "T+1 应使用 constants.SETTLEMENT_T1"),
    (r"'T\+1'", "T+1 应使用 constants.SETTLEMENT_T1"),
]

# 磁盘/内存阈值硬编码模式
THRESHOLD_LITERAL_PATTERNS = [
    (r"disk.*?threshold.*?=.*?\d+", "磁盘阈值应使用 threshold.yaml 配置"),
    (r"memory.*?threshold.*?=.*?\d+", "内存阈值应使用 threshold.yaml 配置"),
    (r"memory.*?limit.*?=.*?\d+", "内存限制应使用 threshold.yaml 配置"),
    (r"disk.*?limit.*?=.*?\d+", "磁盘限制应使用 threshold.yaml 配置"),
    (r"ram.*?threshold.*?=.*?\d+", "内存阈值应使用 threshold.yaml 配置"),
]

# 重复硬编码字符串
REPEATED_LITERAL_PATTERNS = [
    (r'"上证指数"', "板块名称应纳入常量池"),
    (r'"深证成指"', "板块名称应纳入常量池"),
    (r'"沪深300"', "板块名称应纳入常量池"),
    (r'"中证500"', "板块名称应纳入常量池"),
    (r'"涨停"', "行业标签应纳入常量池"),
    (r'"跌停"', "行业标签应纳入常量池"),
    (r'"open"', "字段名应使用常量，如 COL_OPEN"),
    (r'"close"', "字段名应使用常量，如 COL_CLOSE"),
    (r'"high"', "字段名应使用常量，如 COL_HIGH"),
    (r'"low"', "字段名应使用常量，如 COL_LOW"),
    (r'"volume"', "字段名应使用常量，如 COL_VOLUME"),
]

# 豁免文件
EXEMPT_FILES = [
    "constants.py",
    "config.py",
    "config_loader.py",
    "skill_constant_check.py",
    "test_",
]


class SkillConstantCheck(BaseSkill):
    """时间常量池 + 阈值裸写检测"""

    def __init__(self, target_path: Optional[str] = None):
        super().__init__("constant_check")
        self.target = Path(target_path or ".").resolve()
        if not self.target.is_absolute():
            self.target = (_ROOT / self.target).resolve()

    def _is_exempt(self, filepath: Path) -> bool:
        """检查文件是否豁免"""
        name = filepath.name.lower()
        for pattern in EXEMPT_FILES:
            if pattern in name:
                return True
        return False

    def _scan_file(self, filepath: Path) -> list[Dict[str, Any]]:  # noqa: C901
        """扫描单个文件"""
        findings: Any = []
        if self._is_exempt(filepath):
            return findings  # type: ignore[no-any-return]

        try:
            content = filepath.read_text(encoding="utf-8")
            lines = content.split("\n")

            # 时间常量检测
            for pattern, msg in TIME_LITERAL_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        # 跳过注释行
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith('"""'):
                            continue
                        findings.append(
                            {
                                "rule_id": "CONST-001",
                                "severity": "warning",
                                "file": str(filepath),
                                "line": i,
                                "message": msg,
                                "suggest": "请在 constants.py 中定义时间常量并引用",
                            }
                        )
                        break  # 每种模式每个文件只报告一次

            # 阈值裸写检测
            for pattern, msg in THRESHOLD_LITERAL_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(
                            {
                                "rule_id": "CONST-002",
                                "severity": "warning",
                                "file": str(filepath),
                                "line": i,
                                "message": msg,
                                "suggest": "请在 config/rule/threshold.yaml 中配置阈值",
                            }
                        )
                        break

            # 重复字符串检测
            for pattern, msg in REPEATED_LITERAL_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith('"""'):
                            continue
                        findings.append(
                            {
                                "rule_id": "CONST-003",
                                "severity": "warning",
                                "file": str(filepath),
                                "line": i,
                                "message": msg,
                            }
                        )
                        break

        except (IOError, UnicodeDecodeError):
            pass
        return findings  # type: ignore[no-any-return]

    def run_checks(self) -> list[CheckResult]:
        """执行常量检测"""
        all_findings = []
        py_files = list(self.target.rglob("*.py"))

        for fp in py_files:
            all_findings.extend(self._scan_file(fp))

        results: list[CheckResult] = []
        time_findings = [f for f in all_findings if f["rule_id"] == "CONST-001"]  # noqa: F841
        threshold_findings = [f for f in all_findings if f["rule_id"] == "CONST-002"]  # noqa: F841
        repeated_findings = [f for f in all_findings if f["rule_id"] == "CONST-003"]  # noqa: F841

        for f in all_findings[:20]:
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
                    rule="CONST-000",
                    severity="info",
                    message=f"未发现常量硬编码 (扫描 {len(py_files)} 文件)",
                )
            )

        return results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    checker = SkillConstantCheck(target_path=path)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n常量池检测报告")  # noqa: F541
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

    parser = argparse.ArgumentParser(description="时间常量池+阈值裸写检测")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--path", default=None, help="扫描目标路径")
    args = parser.parse_args()
    result = run(output=args.output, path=args.path)
    sys.exit(result.get("exit_code", 0))

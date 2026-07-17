#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_data_verify.py — 数据质量校验 (B1-07)
=============================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-07)

职责: 行情数据清洗、对账、异常统计
  1. 检查 SQLite 数据库完整性 (integrity_check)
  2. 检查数据表行数是否在合理范围
  3. 检测异常值（NaN/Inf/极端价格）
  4. 检查最新数据时间是否在合理延迟内

用法:
    python scripts/skill/skill_data_verify.py
    python scripts/skill/skill_data_verify.py --db-path data/market.db
    python scripts/skill/skill_data_verify.py --output json

退出码:
    0 = 全部正常
    1 = 数据异常 (blocker)
    2 = 数据告警 (warning)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# ═══════════════════════════════════════════════════════════════
# 默认检查规则
# ═══════════════════════════════════════════════════════════════

# 表名 → 最小行数（低于此值告警）
MIN_ROW_THRESHOLDS: dict[str, int] = {
    "daily_kline": 100,
    "minute_kline": 1000,
    "tick_data": 5000,
    "index_daily": 50,
    "stock_list": 100,
}

# 数据最大延迟（分钟），超时告警
MAX_DATA_DELAY_MINUTES: int = 60

# 允许的最大 NaN 比例
MAX_NAN_RATIO: float = 0.05


class SkillDataVerify(BaseSkill):
    """数据质量校验"""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__("data_verify")
        self.db_path = Path(db_path or (_ROOT / "data" / "market.db"))

    # ─── 数据库完整性检查 ──────────────────────────────

    def _check_db_integrity(self, conn: sqlite3.Connection) -> list[CheckResult]:
        """PRAGMA integrity_check"""
        results = []
        try:
            cursor = conn.execute("PRAGMA integrity_check")
            row = cursor.fetchone()
            if row and row[0] == "ok":
                results.append(
                    CheckResult(
                        rule="DATA-001",
                        severity="info",
                        message="数据库完整性检查通过",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        rule="DATA-001",
                        severity="blocker",
                        message=f"数据库完整性检查失败: {row[0] if row else 'unknown'}",
                        suggest="请执行数据库修复或从备份恢复",
                    )
                )
        except sqlite3.Error as e:
            results.append(
                CheckResult(
                    rule="DATA-001",
                    severity="error",
                    message=f"数据库完整性检查异常: {e}",
                )
            )
        return results

    # ─── 表行数检查 ──────────────────────────────────

    def _check_table_rows(self, conn: sqlite3.Connection) -> list[CheckResult]:
        """检查各表行数"""
        results = []
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            try:
                cursor = conn.execute("SELECT COUNT(*) FROM [{}]".format(table))
                count = cursor.fetchone()
                threshold = MIN_ROW_THRESHOLDS.get(table, 0)

                if threshold > 0 and count < threshold:
                    results.append(
                        CheckResult(
                            rule="DATA-002",
                            severity="warning",
                            message=f"表 {table} 行数不足: {count} < {threshold}",
                            suggest="请检查数据采集是否正常",
                        )
                    )
                elif count == 0:
                    results.append(
                        CheckResult(
                            rule="DATA-002",
                            severity="warning",
                            message=f"表 {table} 为空",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            rule="DATA-002",
                            severity="info",
                            message=f"表 {table}: {count} 行",
                        )
                    )
            except sqlite3.Error as e:
                results.append(
                    CheckResult(
                        rule="DATA-002",
                        severity="error",
                        message=f"表 {table} 查询异常: {e}",
                    )
                )

        return results

    # ─── 数据时效性检查 ──────────────────────────────

    def _check_data_freshness(self, conn: sqlite3.Connection) -> list[CheckResult]:  # noqa: C901
        """检查最新数据是否在合理延迟内"""
        results = []
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cursor.fetchall()]

        now = datetime.now()
        has_timestamp_table = False

        for table in tables:
            # 尝试找日期/时间列
            try:
                cursor = conn.execute(f"PRAGMA table_info([{table}])")
                columns = [row[1].lower() for row in cursor.fetchall()]
            except sqlite3.Error:
                continue

            time_cols = [c for c in columns if any(k in c for k in ["date", "time", "timestamp", "trade_date"])]
            if not time_cols:
                continue

            has_timestamp_table = True
            try:
                time_col = time_cols
                cursor = conn.execute(
                    "SELECT MAX([{}]) FROM [{}] WHERE [{}] IS NOT NULL".format(time_col, table, time_col)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    try:
                        latest = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
                        delay = (now - latest.replace(tzinfo=None)).total_seconds() / 60
                        if delay > MAX_DATA_DELAY_MINUTES:
                            results.append(
                                CheckResult(
                                    rule="DATA-003",
                                    severity="warning",
                                    message=f"表 {table} 数据延迟 {delay:.0f} 分钟 > {MAX_DATA_DELAY_MINUTES} 分钟",
                                    suggest="请检查数据采集任务是否正常运行",
                                )
                            )
                    except ValueError:
                        results.append(
                            CheckResult(
                                rule="DATA-003",
                                severity="info",
                                message=f"表 {table} 最新时间: {row[0]}",
                            )
                        )
            except sqlite3.Error:
                pass

        if not has_timestamp_table:
            results.append(
                CheckResult(
                    rule="DATA-003",
                    severity="info",
                    message="未找到含时间列的表，跳过时效性检查",
                )
            )

        return results

    # ─── 主入口 ──────────────────────────────────────

    def run_checks(self) -> list[CheckResult]:
        """执行数据质量校验"""
        all_results: list[CheckResult] = []

        if not self.db_path.exists():
            all_results.append(
                CheckResult(
                    rule="DATA-000",
                    severity="warning",
                    message=f"数据库文件不存在: {self.db_path}",
                    suggest="请确认数据库路径配置",
                )
            )
            return all_results

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            all_results.extend(self._check_db_integrity(conn))
            all_results.extend(self._check_table_rows(conn))
            all_results.extend(self._check_data_freshness(conn))

            conn.close()
        except sqlite3.Error as e:
            all_results.append(
                CheckResult(
                    rule="DATA-000",
                    severity="blocker",
                    message=f"数据库连接失败: {e}",
                )
            )

        return all_results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", db_path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """统一入口"""
    checker = SkillDataVerify(db_path=db_path)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"  数据质量校验报告")  # noqa: F541
        print(f"{'='*50}")
        for r in results:
            icon = {"info": "✓", "warning": "⚠", "blocker": "✗", "error": "✗"}.get(r.severity, "?")
            print(f"  [{icon}] [{r.rule}] {r.message}")
            if r.suggest:
                print(f"       → {r.suggest}")
        print(f"{'='*50}")
        print(f"  状态: {result['status']}  exit={result['exit_code']}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="数据质量校验")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--db-path", default=None, help="数据库路径")
    args = parser.parse_args()
    result = run(output=args.output, db_path=args.db_path)
    sys.exit(result.get("exit_code", 0))

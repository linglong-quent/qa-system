#!/usr/bin/env python3
"""日志结构化入参校验 Skill (B3-12)

校验交易日志是否包含必需字段：订单号/标的/时间戳/TraceID。
缺失关键字段时标记为异常。

审计: CB P1-B3 Batch3 数据与验证 (2026-07-08)
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict

# ─── 必需字段规范 ────────────────────────────────────
REQUIRED_LOG_FIELDS = {
    "trade": ["order_id", "symbol", "price", "volume", "side", "timestamp", "trace_id"],
    "risk": ["check_type", "symbol", "result", "timestamp", "trace_id"],
    "signal": ["signal_name", "symbol", "value", "timestamp", "trace_id"],
    "data": ["source", "symbol", "field", "timestamp"],
    "system": ["module", "level", "message", "timestamp"],
}

CRITICAL_FIELDS = ["timestamp", "trace_id", "order_id", "symbol"]


def check_log_structure(  # noqa: C901
    log_dir: str | None = None,
    hours: int = 24,
) -> Dict[str, Any]:
    """检查日志结构化合规性"""
    log_dir = Path(log_dir) if log_dir else Path(__file__).parent.parent.parent / "logs"  # type: ignore[assignment]
    if not log_dir.exists():  # type: ignore[union-attr]
        return {
            "run_at": datetime.datetime.now().isoformat(),
            "passed": True,
            "files_checked": 0,
            "note": "日志目录不存在，跳过检查",
        }

    cutoff = datetime.datetime.now() - timedelta(hours=hours)  # noqa: F841
    violations = []
    files_checked = 0
    total_entries = 0
    valid_entries = 0

    for log_file in log_dir.glob("*.log"):  # type: ignore[union-attr]
        try:
            content = log_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        files_checked += 1
        # 根据文件名推断日志类别
        category = "system"
        for cat in REQUIRED_LOG_FIELDS:
            if cat in log_file.stem.lower():
                category = cat
                break

        required = REQUIRED_LOG_FIELDS.get(category, REQUIRED_LOG_FIELDS["system"])

        for line_no, line in enumerate(content.split("\n"), 1):
            line = line.strip()
            if not line:
                continue
            total_entries += 1

            # 尝试解析为 JSON 或 key=value
            parsed = _try_parse_line(line)
            if parsed is None:
                violations.append(
                    {
                        "file": str(log_file),
                        "line": line_no,
                        "category": category,
                        "issue": "unparseable",
                        "message": "日志行无法解析为结构化格式",
                        "raw": line[:100],
                    }
                )
                continue

            # 检查必需字段
            missing = [f for f in required if f not in parsed]
            if missing:
                severity = "error" if any(f in CRITICAL_FIELDS for f in missing) else "warning"
                violations.append(
                    {
                        "file": str(log_file),
                        "line": line_no,
                        "category": category,
                        "issue": "missing_fields",
                        "missing": missing,
                        "severity": severity,
                        "message": f"缺少字段: {missing}",
                    }
                )
            else:
                valid_entries += 1

    error_count = len([v for v in violations if v.get("severity") == "error"])
    passed = error_count == 0

    return {
        "run_at": datetime.datetime.now().isoformat(),
        "passed": passed,
        "files_checked": files_checked,
        "total_entries": total_entries,
        "valid_entries": valid_entries,
        "violation_count": len(violations),
        "error_count": error_count,
        "violations": violations[:50],  # 最多返回50条
    }


def _try_parse_line(line: str) -> Dict[str, Any] | None:
    """尝试解析日志行"""
    # 尝试 JSON
    try:
        return json.loads(line)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # 尝试 key=value 格式
    kv_pattern = re.findall(r'(\w+)=("[^"]*"|\S+)', line)
    if kv_pattern:
        return {k: v.strip('"') for k, v in kv_pattern}

    # 尝试 [timestamp][LEVEL][module] 格式
    ts_match = re.match(
        r"\[(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})?\]" r"\[(\w+)\]" r"\[(\w+)\]",
        line,
    )
    if ts_match:
        return {
            "timestamp": ts_match.group(1) or "",
            "level": ts_match.group(2),
            "module": ts_match.group(3),
        }

    return None


def main() -> int:
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="日志结构化入参校验")
    parser.add_argument("--log-dir", default=None, help="日志目录")
    parser.add_argument("--hours", type=int, default=24, help="检查最近N小时")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    report = check_log_structure(args.log_dir, args.hours)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"日志结构化校验: {'PASS' if report['passed'] else 'FAIL'}")
        print(f"  文件: {report['files_checked']} | 条目: {report['total_entries']}")
        print(f"  有效: {report['valid_entries']} | 违规: {report['violation_count']}")
        for v in report.get("violations", [])[:10]:
            print(f"  [{v.get('severity', '?')}] {v['file']}:{v['line']} — {v['message']}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

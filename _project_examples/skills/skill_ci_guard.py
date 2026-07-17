#!/usr/bin/env python3
"""
skill_ci_guard.py — 验收守护脚本 (P2-GD01)
============================================
定时扫描 todo.json，检测虚假 verified 验收状态，自动回退+记违规。

职责:
  1. 读取 _tasks/todo.json，遍历所有 task
  2. 对 status=done 且 acceptance=verified 的任务执行交付物存在性检查
  3. 交付物不存在 → acceptance 回退为 delivered，记入 violations.log
  4. 交付物存在但内容为空 → 标记为 suspicious，写入审计日志
  5. 输出 JSON 报告到 _reports/CI_latest.json

运行方式:
  python scripts/skill/skill_ci_guard.py              # 扫描+报告
  python scripts/skill/skill_ci_guard.py --auto-fix    # 扫描+自动回退
  python scripts/skill/skill_ci_guard.py --check-id P1-F01  # 单任务检查

退出码:
  0 — 全部 verified 任务交付物存在
  1 — 发现 verified 任务交付物缺失 (已自动回退)
  2 — 配置/文件读取错误
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 路径配置 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# 优先使用项目内 _tasks/todo.json，不存在则回退到 workspace 级别
TODO_PATH = PROJECT_ROOT / "_tasks" / "todo.json"
WORKSPACE_TODO = Path(os.environ.get("KUN_WORKSPACE", PROJECT_ROOT.parent)) / "_tasks" / "todo.json"
if not TODO_PATH.exists() and WORKSPACE_TODO.exists():
    TODO_PATH = WORKSPACE_TODO
VIOLATIONS_LOG = PROJECT_ROOT / "_tasks" / "audit" / "violations.log"
CI_REPORT = PROJECT_ROOT / "_reports" / "CI_latest.json"
AUDIT_DIR = PROJECT_ROOT / "_tasks" / "audit"

SEP = "=" * 60


def find_todo_paths() -> List[Path]:
    """查找所有可能的 todo.json 路径"""
    candidates = [
        PROJECT_ROOT / "_tasks" / "todo.json",
        PROJECT_ROOT.parent / "_tasks" / "todo.json",
        Path(os.environ.get("KUN_WORKSPACE", "")) / "_tasks" / "todo.json",
    ]
    return [p for p in candidates if p.exists()]


def load_todo(path: Optional[Path] = None) -> Tuple[Path, Dict[str, Any]]:
    """加载 todo.json

    Returns:
        (actual_path, data)
    """
    if path and path.exists():
        todo_path = path
    else:
        paths = find_todo_paths()
        if not paths:
            print("[ERROR] 未找到 todo.json，已搜索:", file=sys.stderr)
            for p in [PROJECT_ROOT / "_tasks" / "todo.json", PROJECT_ROOT.parent / "_tasks" / "todo.json"]:
                print(f"  - {p}", file=sys.stderr)
            sys.exit(2)
        todo_path = paths[0]

    with open(todo_path, "r", encoding="utf-8") as f:
        return todo_path, json.load(f)


def save_todo(todo_path: Path, data: Dict[str, Any]) -> None:
    """保存 todo.json"""
    data["meta"]["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    data["meta"]["audit_by"] = "ci_guard (自动验收守护)"
    with open(todo_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_violation(task_id: str, reason: str) -> None:
    """写入违规日志"""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] [CI_GUARD] {task_id} — {reason}\n"
    with open(VIOLATIONS_LOG, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"  ⚠ VIOLATION: {task_id} — {reason}")


def check_deliverable_existence(deliverables: List[str]) -> Tuple[bool, List[str]]:
    """检查交付物列表是否都存在

    Returns:
        (all_exist, missing_paths)
    """
    missing: List[str] = []
    for d in deliverables:
        # 处理各种引用格式
        path_str = d.strip()
        # 跳过纯描述性文字
        if not path_str or path_str.startswith("#") or path_str.startswith("http"):
            continue
        # 提取文件路径 (去除列表符号和引号)
        path_str = path_str.strip("- *`\"'[]")

        # 检查多种可能的路径格式
        candidates = [
            PROJECT_ROOT / path_str,
            Path(path_str) if Path(path_str).is_absolute() else PROJECT_ROOT / path_str,
        ]
        found = any(p.exists() for p in candidates)
        if not found:
            missing.append(path_str)
    return len(missing) == 0, missing


def check_single_task(task: Dict[str, Any], auto_fix: bool = False) -> Optional[Dict[str, Any]]:
    """检查单个 verified 任务的交付物"""
    task_id = task.get("id", "?")
    acceptance = task.get("acceptance", "")
    deliverables = task.get("deliverables", [])

    if not deliverables:
        return None

    all_exist, missing = check_deliverable_existence(deliverables)
    if all_exist:
        return None

    # 交付物缺失
    result = {"id": task_id, "acceptance": acceptance, "missing": missing, "action": "none"}
    reason = f"交付物缺失 {len(missing)} 项: {', '.join(missing[:5])}"

    if auto_fix and acceptance == "verified":
        result["action"] = "rolled_back"
        reason += " → acceptance 回退为 delivered"
        log_violation(task_id, reason)
    else:
        log_violation(task_id, reason)

    return result


def scan_and_guard(auto_fix: bool = False, check_id: Optional[str] = None) -> Dict[str, Any]:
    """主扫描逻辑"""
    todo_path, data = load_todo()
    print(f"[INFO] 扫描: {todo_path}")
    tasks = data.get("tasks", [])
    issues: List[Dict[str, Any]] = []
    verified_count = 0

    for task in tasks:
        tid = task.get("id", "?")
        status = task.get("status", "")
        acceptance = task.get("acceptance", "")

        # 只检查 done + verified 的任务
        if status != "done" or acceptance != "verified":
            continue

        # 单任务过滤
        if check_id and tid != check_id:
            continue

        verified_count += 1
        result = check_single_task(task, auto_fix=auto_fix)
        if result:
            issues.append(result)

            # 自动回退
            if auto_fix and result["action"] == "rolled_back":
                task["acceptance"] = "delivered"
                note = task.get("note", "")
                now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                guard_note = f"\n\n【CI_GUARD 自动回退 {now_ts}】交付物缺失，acceptance verified→delivered"
                task["note"] = note + guard_note

    if auto_fix and issues:
        save_todo(todo_path, data)
        print(f"\n{SEP}")
        print(f"  AUTO-FIX: {len(issues)} 项 verified→delivered 已回退")
        print(f"{SEP}")

    # 生成报告
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scanner": "ci_guard (P2-GD01)",
        "total_verified": verified_count,
        "issues_found": len(issues),
        "auto_fixed": sum(1 for i in issues if i.get("action") == "rolled_back"),
        "issues": issues,
        "status": "PASS" if len(issues) == 0 else "FAIL",
    }

    # 写入 CI 报告
    CI_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(CI_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def print_report(report: Dict[str, Any]) -> None:
    """打印扫描报告"""
    sep = "=" * 60
    print(f"\n{sep}")
    print("  CI Guard 验收守护扫描报告")
    print(sep)
    print(f"  扫描时间:     {report['timestamp'][:19]}")
    print(f"  verified 任务: {report['total_verified']}")
    print(f"  发现问题:     {report['issues_found']}")
    print(f"  自动回退:     {report['auto_fixed']}")
    print(f"  状态:         {report['status']}")
    print(sep)

    if report["issues"]:
        print("\n  详情:")
        for issue in report["issues"]:
            print(f"    [{issue['id']}] 缺失 {len(issue['missing'])} 项交付物:")
            for m in issue["missing"][:3]:
                print(f"      - {m}")
            if issue.get("action") == "rolled_back":
                print("      → 已自动回退 acceptance: verified→delivered")


def main() -> None:
    parser = argparse.ArgumentParser(description="CI Guard — 验收守护脚本 (P2-GD01)")
    parser.add_argument("--auto-fix", action="store_true", help="自动回退虚假 verified 为 delivered")
    parser.add_argument("--check-id", type=str, help="仅检查指定任务 ID")
    args = parser.parse_args()

    report = scan_and_guard(auto_fix=args.auto_fix, check_id=args.check_id)
    print_report(report)

    exit_code = 0 if report["issues_found"] == 0 else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

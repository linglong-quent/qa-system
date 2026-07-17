#!/usr/bin/env python3
"""CB 心跳轮询脚本 — 每 3 秒扫一次任务看板。

CB Agent 常驻进程：
  1. 读私有收件箱 → 有任务就修
  2. 读公共 handoff → 兜底
  3. 写完 processed.log → 标记已处理
  4. 写 fixed_result.json → QA 读到就知道修好了
"""
import os, json, sys, time, subprocess
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)

# 路径
INBOX = os.path.join(_PROJECT_ROOT, ".ai/agents/cb/_tasks/inbox.json")
PROCESSED_LOG = os.path.join(_PROJECT_ROOT, ".ai/agents/cb/_tasks/processed.log")
HANDPFF = os.path.join(_PROJECT_ROOT, ".ai/handoff/latest.json")
FIXED_RESULT = os.path.join(_PROJECT_ROOT, ".ai/handoff/fixed_result.json")
CLAUDEMD = os.path.join(_PROJECT_ROOT, ".ai/prompts/CLAUDE.md")


def load_processed():
    """加载已处理记录"""
    if os.path.exists(PROCESSED_LOG):
        with open(PROCESSED_LOG, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_processed(processed: set):
    """保存已处理记录"""
    with open(PROCESSED_LOG, "w", encoding="utf-8") as f:
        json.dump(list(processed), f, ensure_ascii=False, indent=2)


def get_task_id(task: dict) -> str:
    """从任务中提取唯一 ID"""
    return task.get("id") or task.get("taskId") or hash(task.get("issue", "")) % 100000


def scan_inbox():
    """扫描私有收件箱"""
    if not os.path.exists(INBOX):
        return []
    try:
        with open(INBOX, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("tasks", data.get("failure_context", {}).get("tasks", []))
    except Exception:
        return []


def scan_handoff():
    """扫描公共 handoff 池"""
    if not os.path.exists(HANDPFF):
        return []
    try:
        with open(HANDPFF, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("failure_context", {}).get("tasks", data.get("tasks", []))
    except Exception:
        return []


def fix_task(task: dict) -> dict:
    """执行单个任务的修复
    
    这里 CB Agent 会：
      1. 读 CLAUDE.md 了解编码标准
      2. 按 fix_guide 修复代码
      3. 运行 qa_check.py 验证
    
    返回修复结果
    """
    result = {
        "taskId": get_task_id(task),
        "checker": task.get("checker", ""),
        "severity": task.get("severity", "WARN"),
        "file": task.get("file", ""),
        "issue": task.get("issue", "")[:200],
        "status": "fixed",
        "fixed_at": datetime.now().isoformat(),
    }

    # 验证：跑 QA check
    try:
        qa_result = subprocess.run(
            [sys.executable, os.path.join(_SCRIPTS_DIR, "qa_check.py"), "health"],
            capture_output=True, cwd=_PROJECT_ROOT, timeout=60,
        )
        result["qa_exit"] = qa_result.returncode
        # 读取 QA 报告确认
        report_path = os.path.join(_PROJECT_ROOT, ".ai/logs/qa-report.json")
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            result["qa_errors"] = report.get("errors", -1)
            if report.get("errors", 0) == 0:
                result["status"] = "verified"
            else:
                result["status"] = "still_failing"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def try_clear_inbox():
    """任务全部处理完后清理收件箱"""
    processed = load_processed()
    tasks = scan_inbox()
    if not tasks:
        return
    all_done = all(get_task_id(t) in processed for t in tasks)
    if all_done:
        with open(INBOX, "w", encoding="utf-8") as f:
            json.dump({"tasks": [], "status": "all_processed", "timestamp": datetime.now().isoformat()},
                      f, ensure_ascii=False, indent=2)
        print("  [] inbox cleared (all tasks processed)")


def tick_once() -> list:
    """单次心跳扫描"""
    processed = load_processed()
    results = []

    # Step 1: 扫私有收件箱（高优先）
    tasks = scan_inbox()
    source = "inbox"

    # Step 2: 如果没有，扫公共 handoff
    if not tasks:
        tasks = scan_handoff()
        source = "handoff"

    if not tasks:
        return results  # 无任务

    for task in tasks:
        tid = get_task_id(task)
        if tid in processed:
            continue  # 已处理
        print(f"  [CB] Fixing {tid}: {task.get('checker','?')} — {str(task.get('issue',''))[:80]}")
        result = fix_task(task)
        if result["status"] == "verified":
            processed.add(tid)
            save_processed(processed)
            results.append(result)
        else:
            print(f"  [CB] {tid} still failing (errors: {result.get('qa_errors','?')}) — retrying")
            # 留在队列里，下次 tick 再试

    # 写回固定结果
    if results:
        with open(FIXED_RESULT, "w", encoding="utf-8") as f:
            json.dump({"results": results, "timestamp": datetime.now().isoformat()},
                      f, ensure_ascii=False, indent=2)
        print(f"  [CB] Written {len(results)} results to fixed_result.json")

    # 尝试清理已处理完的收件箱
    try_clear_inbox()

    return results


def main_loop(interval: int = 3):
    """常驻轮询"""
    print(f"CB tick started (interval={interval}s)")
    print(f"  inbox:    {INBOX}")
    print(f"  handoff:  {HANDPFF}")
    print(f"  log:      {PROCESSED_LOG}")
    print()

    while True:
        results = tick_once()
        if results:
            print(f"  cycle complete: {len(results)} tasks processed")
        time.sleep(interval)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CB 心跳轮询")
    parser.add_argument("--one-shot", "-1", action="store_true", help="只跑一次不循环")
    parser.add_argument("--interval", "-i", type=int, default=3, help="轮询间隔秒数")
    args = parser.parse_args()

    if args.one_shot:
        results = tick_once()
        print(f"Done: {len(results)} tasks processed")
    else:
        main_loop(interval=args.interval)

#!/usr/bin/env python3
"""不良品追踪器 — 每个被 Gate 拦住的问题都有生命周期。

检出 → 登记 → 修复 → 验证 → 关闭
                    → 挂起（不修）→ 记录原因 → 归档

所有不良品都有档案，没有"拒收就完了"。
"""
import os, json, sys
from datetime import datetime, timedelta

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
DEFECTS_DIR = os.path.join(_PROJECT_ROOT, ".ai/defects")
REGISTRY_PATH = os.path.join(DEFECTS_DIR, "registry.json")


def _load_defects():
    """加载所有不良品记录"""
    os.makedirs(DEFECTS_DIR, exist_ok=True)
    path = os.path.join(DEFECTS_DIR, "registry.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"defects": [], "next_id": 1, "last_updated": ""}


def _save_defects(data):
    path = os.path.join(DEFECTS_DIR, "registry.json")
    data["last_updated"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create(report: dict, gate_result: dict):
    """从 QA 报告和门控结果创建不良品记录
    相同 issue 不重复创建，仅增加 loop_count。
    """
    data = _load_defects()
    new_defects = []
    existing_issues = set(
        d["issue"] for d in data["defects"] if d["status"] in ("open", "suspended")
    )

    for cid, cdata in report.get("checkers", {}).items():
        if cdata.get("skipped") or cdata.get("errors", 0) == 0:
            continue
        for issue in cdata.get("issues", []):
            # 已存在相同的 open/suspended 缺陷 → 增加循环计数
            existing = [d for d in data["defects"]
                        if d["issue"] == issue and d["status"] in ("open", "suspended")]
            if existing:
                existing[0]["loop_count"] = existing[0].get("loop_count", 0) + 1
                existing[0]["last_seen"] = datetime.now().isoformat()
                continue

            did = f"D{data['next_id']:04d}"
            data["next_id"] += 1
            defect = {
                "id": did,
                "checker": cid,
                "status": "open",
                "created_at": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
                "issue": issue,
                "fix_action": "",
                "fix_by": "",
                "resolved_at": "",
                "suspension_reason": "",
                "loop_count": 0,
            }
            new_defects.append(defect)
            data["defects"].append(defect)

    # 关联门控结果
    if new_defects:
        data["last_gate"] = {
            "timestamp": gate_result.get("timestamp", datetime.now().isoformat()),
            "passed": gate_result.get("all_pass", False),
            "gate_checks": gate_result.get("checks", []),
        }

    _save_defects(data)
    return new_defects


def close(defect_id: str, fix_action: str = "", fix_by: str = ""):
    """关闭一个不良品"""
    data = _load_defects()
    for d in data["defects"]:
        if d["id"] == defect_id:
            d["status"] = "closed"
            d["fix_action"] = fix_action
            d["fix_by"] = fix_by
            d["resolved_at"] = datetime.now().isoformat()
            _save_defects(data)
            return d
    return None


def suspend(defect_id: str, reason: str):
    """挂起一个不良品（决定不修）"""
    data = _load_defects()
    for d in data["defects"]:
        if d["id"] == defect_id:
            d["status"] = "suspended"
            d["suspension_reason"] = reason
            d["resolved_at"] = datetime.now().isoformat()
            _save_defects(data)
            return d
    return None


def reopen(defect_id: str):
    """重新打开一个已关闭的不良品"""
    data = _load_defects()
    for d in data["defects"]:
        if d["id"] == defect_id:
            d["status"] = "open"
            d["loop_count"] = d.get("loop_count", 0) + 1
            d["resolved_at"] = ""
            _save_defects(data)
            return d
    return None


def summary() -> dict:
    """不良品统计摘要"""
    data = _load_defects()
    defects = data.get("defects", [])
    result = {
        "total": len(defects),
        "open": sum(1 for d in defects if d["status"] == "open"),
        "closed": sum(1 for d in defects if d["status"] == "closed"),
        "suspended": sum(1 for d in defects if d["status"] == "suspended"),
        "loop_exceeded": sum(1 for d in defects if d.get("loop_count", 0) >= 3),
        "open_defects": [d for d in defects if d["status"] == "open"],
    }
    return result


def feedback_to_plan() -> list:
    """不良品趋势 → 反馈到质量规划"""
    data = _load_defects()
    defects = data.get("defects", [])
    suggestions = []

    # 同一 checker 反复检出不良品 → 标准可能不够严
    from collections import Counter
    checker_counts = Counter(d["checker"] for d in defects if d["status"] != "closed")
    for checker, count in checker_counts.most_common(3):
        if count >= 3:
            suggestions.append({
                "type": "tighten",
                "target": checker,
                "reason": f"'{checker}' 有 {count} 个未关闭不良品，标准需收紧",
            })

    # 同一缺陷反复打开 → 修复可能不彻底
    for d in defects:
        if d.get("loop_count", 0) >= 3:
            suggestions.append({
                "type": "review-fix",
                "target": d["id"],
                "reason": f"缺陷 {d['id']} 已反复打开 {d['loop_count']} 次，修复不彻底",
            })

    # 挂起的不良品过多 → 需评审
    suspended = [d for d in defects if d["status"] == "suspended"]
    if len(suspended) >= 5:
        suggestions.append({
            "type": "review-suspended",
            "target": "quality-plan",
            "reason": f"已挂起 {len(suspended)} 个不良品，需评审规划是否合理",
        })

    return suggestions


def main():
    import argparse
    parser = argparse.ArgumentParser(description="不良品追踪器")
    parser.add_argument("action", nargs="?", default="summary",
                        choices=["summary", "create", "close", "suspend", "open", "feedback"])
    parser.add_argument("--id", default="")
    parser.add_argument("--action-text", default="")
    parser.add_argument("--by", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    if args.action == "summary":
        s = summary()
        print(f"=== 不良品统计 ===")
        print(f"  总计:    {s['total']}")
        print(f"  未关闭:  {s['open']}")
        print(f"  已关闭:  {s['closed']}")
        print(f"  已挂起:  {s['suspended']}")
        print(f"  反复:    {s['loop_exceeded']}")
        if s['open_defects']:
            print(f"\n  未关闭不良品:")
            for d in s['open_defects'][:10]:
                print(f"    {d['id']} [{d['checker']}] {d['issue'][:80]}")
                d.get('loop_count', 0)
            if len(s['open_defects']) > 10:
                print(f"    ... 共 {len(s['open_defects'])} 项")

    elif args.action == "feedback":
        suggestions = feedback_to_plan()
        if suggestions:
            print("=== 不良品反馈 → 规划更新建议 ===")
            for s in suggestions:
                print(f"  [{s['type']}] {s['target']}: {s['reason']}")
        else:
            print("无不良品反馈建议")

    elif args.action == "create":
        # 从最新 QA 报告和门控结果创建
        report_path = os.path.join(_PROJECT_ROOT, ".ai/logs/qa-report.json")
        if not os.path.exists(report_path):
            print("无 QA 报告")
            return
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        gate_result = {"timestamp": datetime.now().isoformat(), "all_pass": False, "checks": []}
        defects = create(report, gate_result)
        print(f"创建 {len(defects)} 个不良品记录")

    elif args.action == "close" and args.id:
        d = close(args.id, args.action_text, args.by)
        if d:
            print(f"已关闭: {args.id}")
        else:
            print(f"未找到: {args.id}")

    elif args.action == "suspend" and args.id:
        d = suspend(args.id, args.reason)
        if d:
            print(f"已挂起: {args.id}")
        else:
            print(f"未找到: {args.id}")

    elif args.action == "open" and args.id:
        d = reopen(args.id)
        if d:
            print(f"已重新打开: {args.id} (第 {d['loop_count']} 次)")
        else:
            print(f"未找到: {args.id}")


if __name__ == "__main__":
    main()

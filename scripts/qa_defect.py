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


def _as_int(v, default: int = 0) -> int:
    """容错取整：历史 registry 里 loop_count 存在字符串 '0'（T03-R4）"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _index_by_issue(defects: list) -> dict:
    """{issue: defect} 仅索引 open/suspended，供 O(1) 去重（64k 规模必需）"""
    idx = {}
    for d in defects:
        if d.get("status") in ("open", "suspended"):
            idx.setdefault(d.get("issue", ""), d)
    return idx


def create(report: dict, gate_result: dict):
    """从 QA 报告和门控结果创建不良品记录

    相同 issue 不重复创建，仅增加 loop_count。
    v1.1: 用 issue 索引替代 O(n) 线性扫描，并统一 loop_count 为 int。
    """
    data = _load_defects()
    idx = _index_by_issue(data["defects"])
    new_defects = []

    for cid, cdata in report.get("checkers", {}).items():
        if cdata.get("skipped") or cdata.get("errors", 0) == 0:
            continue
        for issue in cdata.get("issues", []):
            existing = idx.get(issue)
            if existing is not None:
                existing["loop_count"] = _as_int(existing.get("loop_count")) + 1
                existing["last_seen"] = datetime.now().isoformat()
                existing["absent_rounds"] = 0
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
                "absent_rounds": 0,
            }
            new_defects.append(defect)
            data["defects"].append(defect)
            idx[issue] = defect

    # 关联门控结果
    if new_defects:
        data["last_gate"] = {
            "timestamp": gate_result.get("timestamp", datetime.now().isoformat()),
            "passed": gate_result.get("all_pass", False),
            "gate_checks": gate_result.get("checks", []),
        }

    _save_defects(data)
    return new_defects


def reconcile(report: dict, close_after: int = 2) -> dict:
    """对账：把"本轮未复现"的 open 缺陷累计 absent_rounds，连续 N 轮未复现则自动关闭。

    这是让 64k 条"全 open"缺陷收敛的唯一机制（T03-R4）。
    close_after<=0 表示只计数不自动关闭。
    """
    data = _load_defects()
    present = set()
    for cid, cdata in (report or {}).get("checkers", {}).items():
        if cdata.get("skipped"):
            continue
        for issue in cdata.get("issues", []):
            present.add(issue)

    auto_closed, seen, still_open = 0, 0, 0
    now = datetime.now().isoformat()
    for d in data["defects"]:
        if d.get("status") != "open":
            continue
        if d.get("issue", "") in present:
            d["absent_rounds"] = 0
            d["loop_count"] = _as_int(d.get("loop_count"))
            seen += 1
            continue
        d["absent_rounds"] = _as_int(d.get("absent_rounds")) + 1
        if close_after > 0 and d["absent_rounds"] >= close_after:
            d["status"] = "closed"
            d["resolved_at"] = now
            d["fix_by"] = "qa-auto-close"
            d["fix_action"] = f"连续 {d['absent_rounds']} 轮未复现（自动关闭）"
            auto_closed += 1
        else:
            still_open += 1

    _save_defects(data)
    return {"seen": seen, "still_open": still_open, "auto_closed": auto_closed,
            "total": len(data["defects"])}


def compact(archive_path: str = "", keep_recent: int = 0) -> dict:
    """归档压缩：把 closed 缺陷移出 registry.json，写入 JSONL 归档，并去重。

    返回统计；registry.json 只保留 open/suspended（活跃视图）。
    """
    data = _load_defects()
    archive_path = archive_path or os.path.join(DEFECTS_DIR, "registry.archive.jsonl")
    active, archived = [], []
    seen_issues = set()
    deduped = 0
    for d in data["defects"]:
        if d.get("status") == "closed":
            archived.append(d)
            continue
        key = d.get("issue", "")
        if key in seen_issues:
            deduped += 1
            archived.append(dict(d, status="closed",
                                 fix_action="压缩时判定为重复项",
                                 fix_by="qa-compact"))
            continue
        seen_issues.add(key)
        active.append(d)

    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
    with open(archive_path, "a", encoding="utf-8") as f:
        for d in archived:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    data["defects"] = active
    data["archived_count"] = _as_int(data.get("archived_count")) + len(archived)
    _save_defects(data)
    return {"active": len(active), "archived": len(archived), "deduped": deduped,
            "archive_path": archive_path,
            "registry_bytes": os.path.getsize(os.path.join(DEFECTS_DIR, "registry.json"))}


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
            d["loop_count"] = _as_int(d.get("loop_count")) + 1
            d["absent_rounds"] = 0
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
        "loop_exceeded": sum(1 for d in defects if _as_int(d.get("loop_count")) >= 3),
        "archived_count": _as_int(data.get("archived_count")),
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
        if _as_int(d.get("loop_count")) >= 3:
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


def main():  # noqa: STYLE-06
    import argparse
    parser = argparse.ArgumentParser(description="不良品追踪器")
    parser.add_argument("action", nargs="?", default="summary",
                        choices=["summary", "create", "close", "suspend", "open", "feedback",
                                 "reconcile", "compact"])
    parser.add_argument("--id", default="")
    parser.add_argument("--action-text", default="")
    parser.add_argument("--by", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--report", default="", help="QA 报告路径（默认自动定位）")
    parser.add_argument("--close-after", type=int, default=2,
                        help="连续 N 轮未复现则自动关闭（0=只计数不关闭）")
    parser.add_argument("--archive", default="", help="compact 的 JSONL 归档路径")
    parser.add_argument("--json", dest="json_out", default="", help="把统计结果写成 JSON")
    args = parser.parse_args()

    def _resolve_report_path() -> str:
        if args.report:
            return os.path.abspath(args.report)
        staged = os.environ.get("QA_RUN_REPORT_PATH", "")
        if staged and os.path.exists(staged):
            return staged
        root = os.environ.get("QA_SYSTEM_ROOT", "")
        name = os.environ.get("QA_PROJECT_NAME", "")
        cands = []
        if root and name:
            cands.append(os.path.join(root, ".ai", "logs", name, "qa-report.json"))
        cands.append(os.path.join(_PROJECT_ROOT, ".ai/logs/qa-report.json"))
        for c in cands:
            if os.path.exists(c):
                return c
        return ""

    if args.action == "summary":
        s = summary()
        print(f"=== 不良品统计 ===")
        print(f"  总计:    {s['total']}")
        print(f"  未关闭:  {s['open']}")
        print(f"  已关闭:  {s['closed']}")
        print(f"  已挂起:  {s['suspended']}")
        print(f"  反复:    {s['loop_exceeded']}")
        print(f"  已归档:  {s['archived_count']}")
        if s['open_defects']:
            print(f"\n  未关闭不良品:")
            for d in s['open_defects'][:10]:
                print(f"    {d['id']} [{d['checker']}] {d['issue'][:80]}")
            if len(s['open_defects']) > 10:
                print(f"    ... 共 {len(s['open_defects'])} 项")
        if args.json_out:
            payload = {k: v for k, v in s.items() if k != "open_defects"}
            payload["open_sample"] = [d["id"] for d in s["open_defects"][:20]]
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"\n  JSON: {args.json_out}")

    elif args.action == "reconcile":
        rp = _resolve_report_path()
        if not rp:
            print("无 QA 报告，无法对账")
            return
        with open(rp, "r", encoding="utf-8") as f:
            report = json.load(f)
        print(f"对账报告: {rp}")
        r = reconcile(report, close_after=args.close_after)
        print(f"  复现: {r['seen']} · 仍未复现: {r['still_open']} · 自动关闭: {r['auto_closed']}")
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=2)

    elif args.action == "compact":
        r = compact(args.archive)
        print(f"  活跃: {r['active']} · 归档: {r['archived']} · 去重: {r['deduped']}")
        print(f"  归档文件: {r['archive_path']}")
        print(f"  registry.json 大小: {r['registry_bytes']} bytes")

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
        report_path = _resolve_report_path()
        if not report_path:
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

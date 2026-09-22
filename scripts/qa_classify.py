#!/usr/bin/env python3
"""QA 问题分类器 — 将 QA 报告中的问题分类为智能体可执行的修复任务。

不是修代码的。是告诉智能体该修什么、怎么修。
智能体（AI/人）读取输出后自己修代码。

输出：
  .ai/fixes/pending.json   → 智能体读这个文件，按指导修代码
  .ai/fixes/metrics.json   → 问题分布统计（给质量工程看）

架构：
  chk_*（查）→ qa-report.json → qa_issue_classifier（分类）→ pending.json
                                                                  ↓
                                                       智能体读 → 修 → 重新检查
  
  QA 不碰代码。QA 只发现问题、分类问题、跟踪问题。
"""
import os, json, re
from datetime import datetime
from collections import Counter

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)


# 分类规则：匹配 issue 文本 → 输出结构化修复任务
CLASSIFIER_RULES = [
    # ── BLOCKER 级（必须修） ──
    {"pattern": "SECRET|API Key", "category": "security", "severity": "BLOCKER",
     "action": "替换为环境变量", "effort": "5min"},
    {"pattern": "BOUNDARY|禁止 import", "category": "architecture", "severity": "BLOCKER",
     "action": "提取公共接口", "effort": "30min"},
    {"pattern": "前视偏差|shift\\(-", "category": "backtest", "severity": "BLOCKER",
     "action": "数据对齐修正", "effort": "15min"},
    {"pattern": "循环导入", "category": "architecture", "severity": "BLOCKER",
     "action": "提取公共模块", "effort": "15min"},

    # ── WARN 级（建议修） ──
    {"pattern": "inplace=True", "category": "code-style", "severity": "WARN",
     "action": "改为链式调用", "effort": "2min"},
    {"pattern": "DEADCODE|孤儿", "category": "code-quality", "severity": "WARN",
     "action": "确认后删除或豁免", "effort": "5min"},
    {"pattern": "魔法数字", "category": "code-quality", "severity": "WARN",
     "action": "提取为命名常量", "effort": "5min"},
    {"pattern": "BOM|FEFF|non-printable", "category": "encoding", "severity": "WARN",
     "action": "以 UTF-8 without BOM 重新保存文件", "effort": "1min"},
    {"pattern": "YAML解析失败", "category": "config", "severity": "WARN",
     "action": "修复 YAML 语法错误", "effort": "10min"},
    {"pattern": "except.*pass", "category": "error-handling", "severity": "WARN",
     "action": "记录日志或 re-raise", "effort": "5min"},
    {"pattern": "未注册的配置", "category": "config", "severity": "INFO",
     "action": "确认使用状态，删除或注册", "effort": "5min"},
]


def classify(report: dict) -> dict:
    """将 QA 报告分类为智能体可执行的修复任务"""
    tasks = []
    categories = Counter()

    for cid, cdata in report.get("checkers", {}).items():
        if cdata.get("skipped") or cdata.get("errors", 0) == 0:
            continue
        for issue_text in cdata.get("issues", []):
            matched = False
            for rule in CLASSIFIER_RULES:
                if re.search(rule["pattern"], issue_text, re.IGNORECASE):
                    file_path, line_no = _extract_location(issue_text)
                    tasks.append({
                        "checker": cid,
                        "file": file_path,
                        "line": line_no,
                        "message": issue_text[:150],
                        "category": rule["category"],
                        "severity": rule["severity"],
                        "action": rule["action"],
                        "effort": rule["effort"],
                    })
                    categories[rule["category"]] += 1
                    matched = True
                    break
            if not matched:
                tasks.append({
                    "checker": cid,
                    "file": _extract_location(issue_text)[0] or "未知",
                    "line": 0,
                    "message": issue_text[:150],
                    "category": "uncategorized",
                    "severity": "INFO",
                    "action": "需人工确认",
                    "effort": "未知",
                })

    return {
        "timestamp": datetime.now().isoformat(),
        "total_issues": report.get("total_issues", 0),
        "total_errors": report.get("errors", 0),
        "classified_tasks": tasks,
        "category_summary": dict(categories),
    }


def _extract_location(text: str):
    m = re.search(r"""([\w\\/.-]+\.py)""", text)
    if not m:
        return "", 0
    line_m = re.search(r""":(\d+)""", text)
    line = int(line_m.group(1)) if line_m else 0
    return m.group(1), line


def _resolve_report_path(project_root: str, explicit: str = "", run_dir: str = "") -> str:
    """报告定位（v1.1 修复 T03-B6：不再写死 QA-System 自身路径）

    顺序：显式 --report > 本 run 的采集产物 > QA_RUN_REPORT_PATH > 0-污染项目日志 > 项目本地
    """
    if explicit:
        return os.path.abspath(explicit)
    cands = []
    if run_dir:
        cands.append(os.path.join(run_dir, "qa-report.json"))
    staged = os.environ.get("QA_RUN_REPORT_PATH", "")
    if staged:
        cands.append(staged)
    root = os.environ.get("QA_SYSTEM_ROOT", "")
    name = os.environ.get("QA_PROJECT_NAME", "")
    if root and name:
        cands.append(os.path.join(root, ".ai", "logs", name, "qa-report.json"))
    cands.append(os.path.join(project_root, ".ai/logs/qa-report.json"))
    for c in cands:
        if os.path.exists(c):
            return c
    return ""


def _task_id(cid: str, message: str, file_path: str, line) -> str:
    """稳定任务 ID（跨 run 幂等，T03-B4）"""
    import hashlib
    raw = f"{cid}|{file_path}|{line}|{message}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QA 问题分类器")
    parser.add_argument("--project", "-p", default=_PROJECT_ROOT, help="目标项目根目录")
    parser.add_argument("--report", default="", help="QA 报告路径（默认自动定位）")
    parser.add_argument("--run-id", default="", help="run 标识：pending.json 写入 run 目录")
    parser.add_argument("--runs-dir", default="", help="run 基准目录")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project)
    run_dir = ""
    if args.run_id:
        from qa_run import resolve_run_dir
        run_dir = resolve_run_dir(args.run_id, project_root, runs_dir=args.runs_dir)
    report_path = _resolve_report_path(project_root, args.report, run_dir)
    if not report_path:
        print("无 QA 报告。请先运行 python scripts/qa_check.py health")
        return
    print(f"报告: {report_path}")

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    result = classify(report)
    result["run_id"] = args.run_id
    result["source_report"] = report_path
    for t in result["classified_tasks"]:
        t["task_id"] = _task_id(t["checker"], t["message"], t.get("file", ""), t.get("line", 0))
        t["idempotency_key"] = t["task_id"]

    # 输出摘要
    print("=== QA 问题分类 ===")
    print(f"  总问题: {result['total_issues']}")
    print(f"  已分类: {len(result['classified_tasks'])}")
    print()

    # 按严重级别分组
    by_severity = {"BLOCKER": [], "WARN": [], "INFO": [], "uncategorized": []}
    for task in result["classified_tasks"]:
        sev = task.get("severity", "INFO")
        if sev not in by_severity:
            sev = "uncategorized"
        by_severity[sev].append(task)

    for severity in ["BLOCKER", "WARN", "INFO"]:
        items = by_severity.get(severity, [])
        if not items:
            continue
        print(f"  [{severity}] {len(items)} 项")
        for item in items[:5]:
            print(f"    {item['checker']:20s} {item['file']}:{item['line']}")
            print(f"    {'':24s} → {item['action']} (预计{item['effort']})")
        if len(items) > 5:
            print(f"    ... 共 {len(items)} 项")
        print()

    # 类别分布
    if result["category_summary"]:
        print("  类别分布:")
        for cat, count in sorted(result["category_summary"].items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")

    # 保存到 .ai/fixes/pending.json（智能体读取）
    # run-id 指定时产物隔离到 run 目录，避免并行 DAG 分支互相覆盖
    if run_dir:
        fix_dir = run_dir
    else:
        fix_dir = os.path.join(project_root, ".ai/fixes")
    os.makedirs(fix_dir, exist_ok=True)
    pending_path = os.path.join(fix_dir, "pending.json")
    with open(pending_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 分类统计单独保存
    with open(os.path.join(fix_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": result["timestamp"],
            "total": result["total_issues"],
            "by_category": result["category_summary"],
        }, f, ensure_ascii=False, indent=2)

    if args.run_id:
        from qa_run import write_run_meta
        write_run_meta(fix_dir, run_id=args.run_id, command="qa_classify",
                       project_root=project_root,
                       tasks_total=len(result["classified_tasks"]),
                       artifacts={"pending": pending_path})

    print(f"\n  分类结果已保存到 {pending_path}")
    print(f"  智能体读取此文件后按指导修复")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""QA 质量规划器 — 开工前定义质量标准 + 反馈闭环。

品质不是检出来的，是规划出来的。
在写任何代码之前，定义：
  1. 质量目标（什么算"好"）
  2. 红线标准（什么不能过）
  3. 检查策略（哪个 checker 守哪条线）
  4. 风险分配（不同模块不同标准）

反馈闭环（直线变闭环的关键）：
  Plan → Do → Check → Act (feedback) → Plan (updated) → ...
                        ↑ 每次检查结果回到规划层，更新规划
"""

import os, json, sys
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)

DEFAULT_PLAN = {
    "plan_version": "1.0",
    "last_updated": datetime.now().strftime("%Y-%m-%d"),
    "project_type": "generic",
    "quality_objectives": [
        {"id": "Q1", "name": "零硬编码密钥", "standard": "OWASP Top 10 A2",
         "enforced_by": "secret_check", "severity": "BLOCKER",
         "target": "任何提交中零硬编码密钥"},
        {"id": "Q2", "name": "架构边界合规", "standard": "NASA Power of 10 #3",
         "enforced_by": "import_boundary", "severity": "BLOCKER",
         "target": "_core/ 不导入 dev-only 模块"},
        {"id": "Q3", "name": "没有前视偏差", "standard": "量化交易最佳实践",
         "enforced_by": "lookahead_check", "severity": "BLOCKER",
         "target": "回测代码中无 shift(-N) 穿越"},
        {"id": "Q4", "name": "代码可维护", "standard": "ISO 25010 Maintainability",
         "enforced_by": "deadcode_check", "severity": "WARN",
         "target": "无多余公共符号"},
        {"id": "Q5", "name": "配置自洽", "standard": "IEEE 730",
         "enforced_by": "config_audit", "severity": "WARN",
         "target": "所有配置可解析、无废弃文件"},
        {"id": "Q6", "name": "AI 编码有约束", "standard": "ISO 25010",
         "enforced_by": "claude_validation", "severity": "WARN",
         "target": "CLAUDE.md 存在且规则完整"},
    ],
    "risk_zones": [
        {"zone": "core", "path_pattern": "src/_core/|_core/",
         "risk_level": "critical", "require_gates": ["Q1","Q2","Q3","Q4"]},
        {"zone": "strategy", "path_pattern": "strategy/|strategies/",
         "risk_level": "high", "require_gates": ["Q1","Q3","Q4"]},
        {"zone": "data", "path_pattern": "data/|feeder/",
         "risk_level": "medium", "require_gates": ["Q1","Q4"]},
        {"zone": "tools", "path_pattern": "tools/|scripts/",
         "risk_level": "low", "require_gates": ["Q4"]},
    ],
    "gate_threshold": {
        "BLOCKER": "零容忍，有则阻断",
        "WARN": "建议修复，不阻断",
    },
}


def feedback(report: dict, plan: dict) -> list:
    """反馈：检查结果 → 规划更新建议"""
    suggestions = []
    for obj in plan.get("quality_objectives", []):
        cid = obj.get("enforced_by", "")
        data = report.get("checkers", {}).get(cid, {})
        if data.get("skipped"):
            continue
        errors = data.get("errors", 0)
        sev = obj.get("severity", "WARN")
        name = obj.get("name", cid)

        if errors == 0 and sev == "WARN":
            suggestions.append({"type": "tighten", "target": obj["id"],
                                "msg": f"'{name}' 持续通过，可升级为 BLOCKER"})
        if errors >= 5 and sev == "BLOCKER":
            suggestions.append({"type": "review", "target": obj["id"],
                                "msg": f"'{name}' 持续不过({errors})，标准是否过严"})

    for zone in plan.get("risk_zones", []):
        for p in zone.get("path_pattern", "").split("|"):
            if not os.path.exists(os.path.join(_PROJECT_ROOT, p.strip())):
                suggestions.append({"type": "update-path", "target": zone["zone"],
                                    "msg": f"路径 '{p}' 已不存在"})
    return suggestions


def main():
    import argparse, yaml
    parser = argparse.ArgumentParser(description="QA 质量规划器")
    parser.add_argument("action", nargs="?", default="feedback",
                        choices=["init", "check", "validate", "feedback"])
    parser.add_argument("--plan", "-p", default="")
    args = parser.parse_args()

    plan_path = args.plan or os.path.join(_PROJECT_ROOT, ".ai/config/quality-plan.yaml")

    if args.action == "init":
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        with open(plan_path, "w", encoding="utf-8") as f:
            yaml.dump(DEFAULT_PLAN, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"Plan generated: {plan_path}")
        print(f"  Objectives: {len(DEFAULT_PLAN['quality_objectives'])}")
        print(f"  Risk zones: {len(DEFAULT_PLAN['risk_zones'])}")

    elif args.action == "check":
        if not os.path.exists(plan_path):
            print("No quality plan. Run: python scripts/qa_plan.py init")
            return
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = yaml.safe_load(f)
        print(f"Plan: {plan.get('plan_version','?')} type={plan.get('project_type','?')}")
        for obj in plan.get("quality_objectives", []):
            print(f"  [{obj['severity']:8s}] Q{obj['id']} {obj['name']} -> {obj['enforced_by']}")
        for zone in plan.get("risk_zones", []):
            exists = any(os.path.exists(os.path.join(_PROJECT_ROOT, p.strip()))
                        for p in zone["path_pattern"].split("|"))
            print(f"  {'OK' if exists else 'MISS'} zone={zone['zone']} risk={zone['risk_level']}")

    elif args.action == "feedback":
        if not os.path.exists(plan_path):
            print("No quality plan. Run: python scripts/qa_plan.py init")
            return
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = yaml.safe_load(f)
        report_path = os.path.join(_PROJECT_ROOT, ".ai/logs/qa-report.json")
        if not os.path.exists(report_path):
            print("No QA report. Run qa_check.py first")
            return
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        suggestions = feedback(report, plan)
        if suggestions:
            print("=== Feedback: plan update suggestions ===")
            for s in suggestions:
                print(f"  {s['type']:15s} {s.get('target','')} | {s['msg']}")
        else:
            print("Plan is adequate. No updates needed.")


if __name__ == "__main__":
    main()

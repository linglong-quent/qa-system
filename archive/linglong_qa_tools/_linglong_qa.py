"""玲珑量化 QA 全流程入口
一键运行：qa_check + qa_gate（处理报告路径问题）

用法:
    python _linglong_qa.py          # 全流程
    python _linglong_qa.py check    # 仅检查
    python _linglong_qa.py gate     # 仅门禁
    python _linglong_qa.py health   # 健康汇总
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import sys
import shutil

LINGLONG_ROOT = str(PROJECT_ROOT)
QA_SYSTEM_ROOT = r"E:\WB\qa-system"
PROJECT_NAME = "linglong_local"

os.environ["QA_SYSTEM_ROOT"] = QA_SYSTEM_ROOT
os.environ["QA_PROJECT_NAME"] = PROJECT_NAME

sys.path.insert(0, os.path.join(QA_SYSTEM_ROOT, "scripts"))


def sync_report():
    """0-污染模式下，报告在 qa-system/.ai/logs/<project>/ 下
    复制到项目 .ai/logs/ 供 qa_gate 读取
    """
    src = os.path.join(QA_SYSTEM_ROOT, f".ai/logs/{PROJECT_NAME}/qa-report.json")
    dst_dir = os.path.join(LINGLONG_ROOT, ".ai/logs")
    dst = os.path.join(dst_dir, "qa-report.json")

    if os.path.exists(src):
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"[sync] 报告已同步: {src} → {dst}")
        return True
    else:
        print(f"[sync] 警告: 源报告不存在: {src}")
        return False


def run_check():
    """运行 qa_check"""
    print("=" * 60)
    print("  QA Check — 全量检查")
    print("=" * 60)
    from chk_healthscorer import HealthScorer
    scorer = HealthScorer(
        LINGLONG_ROOT,
        qa_system_root=QA_SYSTEM_ROOT,
        project_name=PROJECT_NAME,
    )
    report = scorer.run_all()
    scorer.save_report(report)

    errors = report.get("errors", 0)
    print(f"\n结果: {errors} 个错误, {report.get('total_issues', 0)} 个问题")
    for cid, cdata in report["checkers"].items():
        if cdata.get("skipped"):
            print(f"  ⏭️  {cdata.get('label', cid):<30s} (skipped)")
        elif "error" in cdata:
            print(f"  ❌ {cdata.get('label', cid):<30s} ERROR: {cdata['error']}")
        else:
            err = cdata.get("errors", 0)
            icon = "✅" if err == 0 else "❌"
            print(f"  {icon} {cdata.get('label', cid):<30s} errors={err}")
    return errors == 0


def run_gate():
    """运行 qa_gate"""
    sync_report()
    print()
    print("=" * 60)
    print("  QA Gate — Gate0-Gate9 十层门禁")
    print("=" * 60)

    from qa_gate import GateKeeper
    gate = GateKeeper(LINGLONG_ROOT)
    gate.run()

    passed = sum(1 for r in gate.results if r["passed"])
    total = len(gate.results)
    print(f"\n结果: {passed}/{total} 门禁通过")
    return all(r["passed"] for r in gate.results)


def main():
    """主入口。"""
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "check":
        ok = run_check()
        sys.exit(0 if ok else 1)
    elif mode == "gate":
        ok = run_gate()
        sys.exit(0 if ok else 1)
    elif mode == "health":
        # 简化版：只跑核心checker
        print("health 模式 — 快速健康检查")
        ok = run_check()
        sys.exit(0 if ok else 1)
    else:
        # all: check + gate
        check_ok = run_check()
        gate_ok = run_gate()
        print()
        print("=" * 60)
        print(f"  最终: {'✅ ALL PASS' if (check_ok and gate_ok) else '❌ HAS ISSUES'}")
        print("=" * 60)
        sys.exit(0 if (check_ok and gate_ok) else 1)


if __name__ == "__main__":
    main()

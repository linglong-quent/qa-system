#!/usr/bin/env python3
"""QA 系统统一入口 — 跨环境 (本地/CI/GitHub) 运行所有 checker。

用法:
  python scripts/qa_check.py                    # 全部运行 (同 all)
  python scripts/qa_check.py all                # 全部运行 + 保存报告
  python scripts/qa_check.py health             # 健康汇总 (无详细输出)
  python scripts/qa_check.py inplace            # 单个 checker
  python scripts/qa_check.py lookahead
  python scripts/qa_check.py secret
  python scripts/qa_check.py deadcode
  python scripts/qa_check.py cyclic
  python scripts/qa_check.py code-ban
  python scripts/qa_check.py plugins            # 仅运行项目插件
  python scripts/qa_check.py list               # 列出所有可用 checker
  python scripts/qa_check.py --bootstrap        # 不阻断，仅报告

输出:
  - stdout: 人类可读的检查结果
  - .ai/logs/qa-report.json: 完整 JSON 报告
  - exit code: 0 (通过) / 1 (有问题)
"""
import os, sys, json

# 自动将 scripts/ 加入路径（兼容 pre-commit / CI / 直接运行）
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# 项目根 = scripts/ 的父目录
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)


def run_all(project_root: str = _PROJECT_ROOT, bootstrap: bool = False):
    """运行所有 checker 并报告"""
    from chk_healthscorer import HealthScorer

    scorer = HealthScorer(project_root, bootstrap=bootstrap)
    report = scorer.run_all()

    # 保存报告
    report_path = scorer.save_report(report)

    # 输出摘要
    print(f"QA System Check — {project_root}")
    print(f"  Profile:    {report['profile']}")
    print(f"  Bootstrap:  {report['bootstrap']}")
    print(f"  Errors:     {report['errors']}")
    print(f"  Issues:     {report['total_issues']}")
    print(f"  Blocked:    {report['blocked']}")
    print()

    for cid, cdata in report["checkers"].items():
        if cdata.get("skipped"):
            print(f"  ⏭️  {cdata.get('label', cid):<40s} (skipped)")
        elif "error" in cdata:
            print(f"  ❌ {cdata.get('label', cid):<40s} ERROR: {cdata['error']}")
        else:
            err = cdata.get("errors", 0)
            icon = "✅" if err == 0 else "❌"
            print(f"  {icon} {cdata.get('label', cid):<40s} errors={err}")

    print()
    if report["all_issues"]:
        print(f"Issues ({len(report['all_issues'])} total):")
        for i, issue in enumerate(report["all_issues"][:20], 1):
            print(f"  {i:>3}. {issue}")
        if len(report["all_issues"]) > 20:
            print(f"  ... and {len(report['all_issues']) - 20} more")

    print(f"\nReport saved: {report_path}")
    return report


def run_single(checker_name: str, project_root: str = _PROJECT_ROOT):
    """运行单个 checker"""
    CHECKER_MAP = {
        "inplace":  ("chk_inplacechecker",   "InplaceChecker"),
        "lookahead":("chk_lookaheadchecker", "LookaheadChecker"),
        "secret":   ("chk_secretchecker",    "SecretChecker"),
        "deadcode": ("chk_deadcodechecker",  "DeadCodeChecker"),
        "cyclic":   ("chk_cyclicchecker",    "CyclicImportChecker"),
        "code-ban": ("chk_codebanchecker",   "CodeBanChecker"),
        "boundary": ("chk_importboundary",    "ImportBoundaryChecker"),
        "config":   ("chk_configauditchecker","ConfigAuditChecker"),
        "gates":    ("chk_qualitygates",     "QualityGateChecker"),
        "claude":   ("chk_claudevalidator",   "ClaudeValidator"),
        "prod":     ("chk_production",        "ProductionChecker"),
    }

    if checker_name not in CHECKER_MAP:
        print(f"未知 checker: {checker_name}")
        print(f"可用: {', '.join(CHECKER_MAP.keys())}")
        sys.exit(1)

    mod_name, cls_name = CHECKER_MAP[checker_name]
    mod = __import__(mod_name, fromlist=[cls_name])
    cls = getattr(mod, cls_name)

    config_path = os.path.join(project_root, ".ai/config/review-rules.yaml")
    if os.path.exists(config_path):
        from chk_load_yaml import load_yaml
        config = load_yaml(config_path)
        cfg_key = {
            "inplace": "inplace_check", "lookahead": "lookahead_check",
            "secret": "secret_check", "deadcode": "deadcode_check",
            "cyclic": "cyclic_check", "code-ban": "code_ban_check",
            "prod": "production_check",
            "boundary": "import_boundary_check",
            "config": "config_audit_check",
            "gates": "quality_gates",
            "claude": "claude_validation",
        }[checker_name]
        cfg = config.get(cfg_key, {})
    else:
        cfg = {}

    instance = cls(cfg, project_root)
    errors, issues = instance.check()

    if errors == 0:
        print(f"[{checker_name}] ✅ 通过")
    else:
        print(f"[{checker_name}] ❌ {errors} 个错误")
        for issue in issues:
            print(f"  {issue}")

    return errors > 0


def list_checkers(project_root: str = _PROJECT_ROOT):
    """列出所有可用 checker"""
    from chk_healthscorer import HealthScorer
    s = HealthScorer(project_root)
    print("Available checkers:")
    print()
    print("Layer A — Built-in:")
    for cid in ["inplace_check", "lookahead_check", "secret_check",
                 "deadcode_check", "cyclic_check", "code_ban",
                 "import_boundary", "config_audit", "quality_gates", "claude_validation"]:
        cfg = s.config.get(cid, {})
        enabled = cfg.get("enabled", True)
        scan = cfg.get("scan_dirs", ["(default)"])
        sev = cfg.get("severity", "INFO")
        print(f"  {'✅' if enabled else '⏭️'} {cid:<35s}  severity={sev}  scan={scan}")

    print()
    print("Layer B — Plugins:")
    plugin_dir = os.path.join(project_root, ".ai/plugins")
    if os.path.isdir(plugin_dir):
        for entry in sorted(os.listdir(plugin_dir)):
            if entry.endswith(".py") and entry != "__init__.py":
                print(f"  🔌 {entry}")
            elif os.path.isdir(os.path.join(plugin_dir, entry)) and not entry.startswith("_"):
                for sub in sorted(os.listdir(os.path.join(plugin_dir, entry))):
                    if sub.endswith(".py") and sub != "__init__.py":
                        print(f"  🔌 {entry}/{sub}")
    else:
        print("  (none)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QA 系统统一入口")
    parser.add_argument("command", nargs="?", default="all",
                        help="all|health|inplace|lookahead|secret|deadcode|cyclic|code-ban|plugins|list")
    parser.add_argument("--project-root", default=_PROJECT_ROOT)
    parser.add_argument("--bootstrap", action="store_true", help="不阻断，仅报告")
    args = parser.parse_args()

    cmd = args.command

    if cmd == "list":
        list_checkers(args.project_root)
        sys.exit(0)

    if cmd == "health":
        report = run_all(args.project_root, args.bootstrap)
        sys.exit(1 if report["errors"] > 0 and not args.bootstrap else 0)

    if cmd == "all":
        report = run_all(args.project_root, args.bootstrap)
        sys.exit(1 if report["errors"] > 0 and not args.bootstrap else 0)

    SINGLE = ["inplace", "lookahead", "secret", "deadcode", "cyclic", "code-ban", "boundary", "prod", "config", "gates", "claude"]
    if cmd in SINGLE:
        failed = run_single(cmd, args.project_root)
        sys.exit(1 if failed else 0)

    if cmd == "plugins":
        from chk_healthscorer import HealthScorer
        s = HealthScorer(args.project_root, bootstrap=args.bootstrap)
        r = s.run_all()
        plugin_results = {k: v for k, v in r["checkers"].items() if k.startswith("plugin_")}
        for pid, pdata in plugin_results.items():
            label = pdata.get("label", pid)
            if pdata.get("skipped"):
                print(f"  ⏭️ {label:<40s} (skipped)")
            elif "error" in pdata:
                print(f"  ❌ {label:<40s} {pdata['error']}")
            else:
                err = pdata.get("errors", 0)
                print(f"  {'✅' if err==0 else '❌'} {label:<40s} errors={err}")
        sys.exit(0)

    print(f"未知命令: {cmd}")
    sys.exit(1)


if __name__ == "__main__":
    main()

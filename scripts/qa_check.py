#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, logging
# 强制 stdout/stderr 用 UTF-8，防止 GBK 管道截断 Unicode
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')   # py3.7+
    except Exception:
        logging.exception("stdout.reconfigure failed")
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        logging.exception("stderr.reconfigure failed")
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


def run_all(project_root: str = _PROJECT_ROOT, bootstrap: bool = False, run_id: str = "",
            runs_dir: str = "", sarif_path: str = ""):
    """运行所有 checker 并报告

    run_id 非空时启用 run 隔离：报告写 {base}/.ai/runs/{run_id}/qa-report.json，
    不再触碰 .ai/logs/ 下的权威报告（T03-R2 修复）。
    """
    from chk_healthscorer import HealthScorer

    run_dir = ""
    if run_id:
        from qa_run import resolve_run_dir
        run_dir = resolve_run_dir(run_id, project_root, runs_dir=runs_dir)

    scorer = HealthScorer(project_root, bootstrap=bootstrap, run_dir=run_dir)
    report = scorer.run_all()

    # 保存报告（显式；run_dir 为空时落权威路径，保持向后兼容）
    report_path = scorer.save_report(report)

    # SARIF 2.1.0 出口（供 GitHub Code Scanning / 编排系统消费）
    if sarif_path:
        sarif_path = os.path.abspath(sarif_path)
        os.makedirs(os.path.dirname(sarif_path) or ".", exist_ok=True)
        with open(sarif_path, "w", encoding="utf-8") as f:
            json.dump(scorer.to_sarif(report), f, ensure_ascii=False, indent=2)
        print(f"SARIF saved: {sarif_path}")

    # 输出摘要
    print(f"QA System Check — {project_root}")
    print(f"  Profile:    {report['profile']}")
    print(f"  Bootstrap:  {report['bootstrap']}")
    if run_id:
        print(f"  RunId:      {run_id}")
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


def run_single(checker_name: str, project_root: str = _PROJECT_ROOT):  # noqa: STYLE-06
    """运行单个 checker（支持 0-污染模式：优先读 QA-System/.ai/projects/{name}.yaml）"""
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
        "codestyle":("chk_codestyle",        "CodeStyleChecker"),
        "naming":   ("chk_namingconflict",   "NamingConflictChecker"),
        "largefiles":("chk_largefiles",      "LargeFilesChecker"),
        "solid":    ("chk_solid",            "SolidChecker"),
    }

    if checker_name not in CHECKER_MAP:
        print(f"未知 checker: {checker_name}")
        print(f"可用: {', '.join(CHECKER_MAP.keys())}")
        sys.exit(1)

    mod_name, cls_name = CHECKER_MAP[checker_name]
    mod = __import__(mod_name, fromlist=[cls_name])  # noqa: BAN-8 (动态加载 checker 模块，可信)
    cls = getattr(mod, cls_name)

    # 0-污染模式：优先从 QA-System/.ai/projects/{project_name}_local.yaml 加载
    qa_system_root = os.environ.get("QA_SYSTEM_ROOT", "")
    project_name = os.environ.get("QA_PROJECT_NAME", "")
    config = {}
    if qa_system_root and project_name:
        candidates = [
            os.path.join(qa_system_root, ".ai", "projects", f"{project_name}_local.yaml"),
            os.path.join(qa_system_root, ".ai", "projects", f"{project_name}.yaml"),
        ]
        for cp in candidates:
            if os.path.exists(cp):
                from chk_load_yaml import load_yaml
                try:
                    config = load_yaml(cp)
                    break
                except Exception:
                    logging.warning("加载项目配置失败: %s", cp, exc_info=True)

    # 自动探测: 环境变量未设置时, 按 project_root 目录名在 QA-System 下定位项目配置
    # (避免漏加载 magic_whitelist 等规则导致全量误报)
    if not config:
        try:
            from chk_load_yaml import load_yaml
            base = qa_system_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            auto_name = os.path.basename(os.path.normpath(project_root))
            for suffix in ("_local.yaml", ".yaml"):
                cp = os.path.join(base, ".ai", "projects", f"{auto_name}{suffix}")
                if os.path.exists(cp):
                    config = load_yaml(cp)
                    logging.info("自动加载项目配置: %s", cp)
                    break
        except Exception:
            logging.warning("自动加载项目配置失败", exc_info=True)

    # 项目本地配置（补充，向后兼容）
    if not config:
        config_path = os.path.join(project_root, ".ai/config/review-rules.yaml")
        if os.path.exists(config_path):
            from chk_load_yaml import load_yaml
            try:
                config = load_yaml(config_path)
            except Exception:
                logging.warning("加载本地配置失败: %s", config_path, exc_info=True)

    cfg_key = {
        "inplace": "inplace_check", "lookahead": "lookahead_check",
        "secret": "secret_check", "deadcode": "deadcode_check",
        "cyclic": "cyclic_check", "code-ban": "code_ban_check",
        "prod": "production_check",
        "boundary": "import_boundary_check",
        "config": "config_audit_check",
        "gates": "quality_gates",
        "claude": "claude_validation",
        "codestyle": "codestyle_check",
        "largefiles": "largefiles_check",
        "naming": "naming_conflict_check",
        "solid": "solid_check",
    }[checker_name]
    cfg = config.get(cfg_key, {})

    instance = cls(cfg, project_root)
    errors, issues = instance.check()

    if errors == 0:
        if issues:
            print(f"[{checker_name}] ⚠️ 通过（{len(issues)} 个警告）")
            for issue in issues[:10]:
                print(f"  {issue}")
            if len(issues) > 10:
                print(f"  ... 共 {len(issues)} 个警告")
        else:
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
                        help="all|health|inplace|lookahead|secret|deadcode|cyclic|code-ban|boundary|prod|config|gates|claude|codestyle|largefiles|naming|solid|plugins|list")
    parser.add_argument("--project-root", default=_PROJECT_ROOT)
    parser.add_argument("--bootstrap", action="store_true", help="不阻断，仅报告")
    parser.add_argument("--run-id", default="",
                        help="运行标识：产物隔离到 {base}/.ai/runs/{run_id}/（编排契约 v1.1）")
    parser.add_argument("--runs-dir", default="", help="run 基准目录（默认 QA_SYSTEM_ROOT/.ai/runs）")
    parser.add_argument("--sarif", default="", help="同时输出 SARIF 2.1.0 报告到该路径")
    args = parser.parse_args()

    # 0-污染模式: 切换 cwd 到目标项目, 保证 checker 相对 scan_dirs 解析正确
    project_root = os.path.abspath(args.project_root)
    try:
        os.chdir(project_root)
    except OSError:
        logging.warning("无法切换 cwd 到项目根: %s", project_root)

    cmd = args.command

    if cmd == "list":
        list_checkers(project_root)
        sys.exit(0)

    if cmd == "health":
        report = run_all(project_root, args.bootstrap, args.run_id, args.runs_dir, args.sarif)
        sys.exit(1 if report["errors"] > 0 and not args.bootstrap else 0)

    if cmd == "all":
        report = run_all(project_root, args.bootstrap, args.run_id, args.runs_dir, args.sarif)
        sys.exit(1 if report["errors"] > 0 and not args.bootstrap else 0)

    SINGLE = ["inplace", "lookahead", "secret", "deadcode", "cyclic", "code-ban",
              "boundary", "prod", "config", "gates", "claude", "codestyle", "largefiles",
              "naming"]
    if cmd in SINGLE:
        failed = run_single(cmd, project_root)
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

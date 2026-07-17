#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docs-as-Code 文档健康度评分工具 V2.0-A++
入口聚合: 从拆分后的 chk_* 模块导入所有功能
"""
import os, sys
from pathlib import Path

_THIS_DIR = str(Path(__file__).parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Docs-as-Code 文档健康度评分工具 V2.0-A++")
    subparsers = parser.add_subparsers(dest="command")

    p = subparsers.add_parser("init", help="初始化项目目录结构")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("check", help="执行文档健康度评分")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("code-ban", help="代码质量禁止事项检测")
    p.add_argument("--project-root", default=".")

    for cmd in (
        "config-audit",
        "dir-audit",
        "doc-sync",
        "archive",
        "dedup",
        "fagan-inspect",
        "review-metrics",
        "dynamic-checklist",
        "defect-pareto",
        "opa-sync",
        "dep-graph",
        "config-push",
        "dashboard",
        "preflight",
        "coordinator",
        "integrity",
        "baseline",
        "cross-validate",
    ):
        p = subparsers.add_parser(cmd, help=f"{cmd} 命令")
        p.add_argument("--project-root", default=".")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "init":
        from chk_init_project import init_project

        init_project(args.project_root)
    elif args.command == "check":
        from chk_healthscorer import HealthScorer
        import json

        scorer = HealthScorer(args.project_root)
        result = {"command": "check", "status": "module_loaded"}
        print(json.dumps(result, indent=2))
    elif args.command == "code-ban":
        from chk_codebanchecker import CodeBanChecker

        checker = CodeBanChecker({"enabled": True}, args.project_root)
        errors, issues = checker.check()
        for i in issues:
            print(i)
        sys.exit(1 if errors else 0)
    # ─── 已实现的命令 ───
    elif args.command == "config-audit":
        from chk_configauditchecker import ConfigAuditChecker
        checker = ConfigAuditChecker(args.project_root)
        issues = checker.check()
        for i in issues:
            print(i)
        sys.exit(1 if issues else 0)
    elif args.command == "dir-audit":
        from chk_provenancechecker import ProvenanceChecker
        docs_dir = os.path.join(args.project_root, "_docs")
        if not os.path.isdir(docs_dir):
            docs_dir = os.path.join(args.project_root, "docs")
        checker = ProvenanceChecker({}, args.project_root)
        errors, issues = checker.check(docs_dir)
        for i in issues:
            print(i)
        sys.exit(1 if errors else 0)
    elif args.command == "doc-sync":
        from chk_codedocsyncchecker import CodeDocSyncChecker
        checker = CodeDocSyncChecker({}, args.project_root)
        errors, issues = checker.check()
        for i in issues:
            print(i)
        sys.exit(1 if errors else 0)
    elif args.command == "integrity":
        from chk_gittraceabilitychecker import GitTraceabilityChecker
        docs_dir = os.path.join(args.project_root, "_docs")
        if not os.path.isdir(docs_dir):
            docs_dir = os.path.join(args.project_root, "docs")
        checker = GitTraceabilityChecker({}, args.project_root)
        errors, issues = checker.check(docs_dir)
        for i in issues:
            print(i)
        sys.exit(1 if errors else 0)
    elif args.command == "cross-validate":
        from chk_faithfulnesschecker import FaithfulnessChecker
        docs_dir = os.path.join(args.project_root, "_docs")
        if not os.path.isdir(docs_dir):
            docs_dir = os.path.join(args.project_root, "docs")
        checker = FaithfulnessChecker({}, args.project_root)
        errors, issues = checker.check(docs_dir)
        for i in issues:
            print(i)
        sys.exit(1 if errors else 0)
    else:
        print(f"ℹ️  {args.command} 命令待实现")


if __name__ == "__main__":
    main()

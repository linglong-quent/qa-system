#!/usr/bin/env python3
"""
Self-Audit: 标准执行审计器
===========================
插件式架构: 审计规则放在 audit_rules/ 目录
增删规则 = 增删文件，不改主代码

用法:
    python scripts/self_audit.py --project-root .
"""

import argparse
import sys

from audit_rules import discover_rules, run_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-Audit: 标准执行审计器")
    parser.add_argument("--project-root", default=".", help="项目根目录")
    parser.add_argument("--list", action="store_true", help="列出可用规则")
    args = parser.parse_args()

    if args.list:
        rules = discover_rules()
        print(f"可用规则 ({len(rules)}):")
        for r in rules:
            name = getattr(r, "name", r.__name__)
            print(f"  - {name}")
        return 0

    print("=" * 54)
    print("  Self-Audit: 标准执行审计")
    print("  原则: 不逃避、不绕行、不禁用")
    print("=" * 54)

    all_issues = run_all(args.project_root)

    print(f"\n结果: {len(all_issues)} 个问题")
    for issue in all_issues:
        print(issue)

    print("\n" + "=" * 54)
    if not all_issues:
        print("  ✅ 全部通过")
    else:
        print(f"  ❌ 发现 {len(all_issues)} 个问题，修复后重试")
    print("=" * 54)

    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())

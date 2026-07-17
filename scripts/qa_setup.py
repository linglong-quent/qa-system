#!/usr/bin/env python3
"""QA 系统快速接入脚本 — 为任意项目一键安装 QA 防线

用法:
  python scripts/qa_setup.py                          # 交互模式
  python scripts/qa_setup.py --project /path/to/proj  # 指定项目
  python scripts/qa_setup.py --quick                  # 默认配置快速安装

创建:
  .ai/config/review-rules.yaml       — 核心评分配置
  .ai/plugins/__init__.py            — 插件入口
  .ai/schemas/                       — Schema 目录
  .pre-commit-config.yaml            — pre-commit 钩子
  docs/qa-adoption.md                — 集成指南

QA 系统核心文件需从本 repo 复制: scripts/chk_*.py, scripts/qa_check.py 等。
"""
import json, os, shutil, sys
from pathlib import Path


DEFAULT_RULES = """# review-rules.yaml — QA 系统配置
# 由 qa_setup.py 自动生成
version: "3.0"
last_updated: "{date}"
bootstrap_mode: false
default_profile: "full"

plugins:
  enabled: true
  default_plugin_enabled: true
  enabled_plugins: {{}}
  plugin_configs: {{}}

profiles:
  full:
    description: "全量检查"
    checkers_on:
      - inplace_check
      - lookahead_check
      - secret_check
      - deadcode_check
      - cyclic_check
      - code_ban
      - import_boundary
  dev:
    description: "开发模式"
    checkers_on:
      - inplace_check
      - lookahead_check
      - secret_check
  quick:
    description: "快速检查（仅安全）"
    checkers_on:
      - secret_check
      - lookahead_check

inplace_check:
  enabled: true
  scan_dirs: ["src/"]
  severity: WARN

lookahead_check:
  enabled: true
  scan_dirs: ["src/"]
  severity: BLOCKER

secret_check:
  enabled: true
  scan_dirs: ["src/"]
  severity: BLOCKER

deadcode_check:
  enabled: true
  scan_dirs: ["src/"]
  exempt_names: ["main", "__init__", "__main__", "__version__", "__all__"]
  entry_points: ["main.py", "app.py", "cli.py"]
  severity: WARN

cyclic_check:
  enabled: true
  scan_dirs: ["src/"]
  severity: BLOCKER

code_ban_check:
  enabled: true
  scan_dirs: ["src/"]
  severity: BLOCKER
  ban_rules:
    bare_print: true
    sql_injection: true
    except_pass: true
    hardcoded_path: true
    magic_number: true

import_boundary_check:
  enabled: true
  severity: BLOCKER
  restricted_dirs: ["src/_core/"]
  forbidden_prefixes:
    - tests
    - scripts
    - tools
    - archive
  allowed_modules:
    - numpy
    - pandas
    - requests
  max_depth: 3
"""

DEFAULT_PRE_COMMIT = """repos:
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
        name: black-format
        language_version: python3.12
        args: ["--line-length=120", "--target-version=py312"]

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        name: isort-imports
        args: ["--profile=black", "--line-length=120"]

  - repo: https://github.com/pycqa/flake8
    rev: 7.1.0
    hooks:
      - id: flake8
        name: flake8-lint
        args: ["--max-line-length=120", "--max-complexity=10"]

  - repo: local
    hooks:
      - id: qa-health
        name: qa-health (QA 统一检查)
        entry: python scripts/qa_check.py health
        language: system
        files: \\.py$
        pass_filenames: false
        always_run: false
"""

PLUGIN_INIT = '\"\"\"项目插件目录。在此目录下放 .py 文件，QA 系统自动发现。\n\n每个文件需导出:\n  check(config: dict, project_root: str) -> tuple[int, list[str]]\n  返回 (errors, issues)\n\n示例: .ai/plugins/my_rule.py\n  CHECKER_ID = \"plugin_my_rule\"\n  CHECKER_LABEL = \"我的规则\"\n  def check(config, project_root):\n      return 0, []\n\"\"\"\n'


def setup_project(project_root: str, quick: bool = False):
    root = os.path.abspath(project_root)
    ai_dir = os.path.join(root, ".ai")
    config_dir = os.path.join(ai_dir, "config")
    plugins_dir = os.path.join(ai_dir, "plugins")
    schemas_dir = os.path.join(ai_dir, "schemas")
    logs_dir = os.path.join(ai_dir, "logs")
    docs_dir = os.path.join(root, "docs")

    # 创建目录结构
    for d in [config_dir, plugins_dir, schemas_dir, logs_dir, docs_dir]:
        os.makedirs(d, exist_ok=True)

    # 生成 review-rules.yaml
    rules_path = os.path.join(config_dir, "review-rules.yaml")
    if not os.path.exists(rules_path):
        from datetime import date
        content = DEFAULT_RULES.format(date=date.today().isoformat())
        with open(rules_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✅ 生成 {os.path.relpath(rules_path, root)}")
    else:
        print(f"  ⏭️  已存在 {os.path.relpath(rules_path, root)}")

    # 生成 pre-commit
    pc_path = os.path.join(root, ".pre-commit-config.yaml")
    if not os.path.exists(pc_path):
        with open(pc_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PRE_COMMIT)
        print(f"  ✅ 生成 {os.path.relpath(pc_path, root)}")
    else:
        print(f"  ⏭️  已存在 {os.path.relpath(pc_path, root)}")

    # 生成插件入口
    init_path = os.path.join(plugins_dir, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(PLUGIN_INIT)
        print(f"  ✅ 生成 {os.path.relpath(init_path, root)}")
    else:
        print(f"  ⏭️  已存在 {os.path.relpath(init_path, root)}")

    # 生成 schema 目录标志
    schema_marker = os.path.join(schemas_dir, ".gitkeep")
    if not os.path.exists(schema_marker):
        Path(schema_marker).touch()

    if not quick:
        print()
        print("  📋 接下来需要:")
        print(f"  1. 将 QA 系统 scripts/chk_*.py 和 scripts/qa_check.py 复制到 {root}/scripts/")
        print(f"  2. 运行 pip install pyyaml (检查器运行依赖)")
        print(f"  3. 运行 pre-commit install (启用提交前检查)")
        print(f"  4. 在 .ai/plugins/ 下编写项目特有检查规则")
        print(f"  5. 修改 review-rules.yaml 中的 scan_dirs 为项目实际目录")

    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QA 系统快速接入脚本")
    parser.add_argument("--project", "-p", default=".",
                        help="目标项目根目录 (默认当前目录)")
    parser.add_argument("--quick", "-q", action="store_true",
                        help="默认配置快速安装，不显示后续指引")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project)
    if not os.path.isdir(project_root):
        print(f"❌ 目录不存在: {project_root}")
        sys.exit(1)

    print(f"QA 系统接入 — {project_root}")
    print("=" * 50)

    setup_project(project_root, quick=args.quick)

    print()
    print("=" * 50)
    print("✅ 接入完成")
    print(f"   下一步: 复制 QA 系统核心文件到 {project_root}/scripts/")


if __name__ == "__main__":
    main()

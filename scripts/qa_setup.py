#!/usr/bin/env python3
"""QA 系统 v4.0 — 快速接入脚本（本地/双模）

为一键安装 QA 防线到任意项目。支持 0-污染模式（QA 系统独立运行）和嵌入式模式。

用法:
  python scripts/qa_setup.py                                          # 交互模式
  python scripts/qa_setup.py --project /path/to/proj                  # 指定项目
  python scripts/qa_setup.py --project /path/to/proj --quick          # 快速安装
  python scripts/qa_setup.py --project /path/to/proj --with-checkers  # 含 checker 复制
  python scripts/qa_setup.py --project /path/to/proj --local-windows  # 含 Windows 启动脚本

创建:
  .ai/config/review-rules.yaml       — 核心评分配置 (v4.0)
  .ai/config/21 张 YAML 规则表        — 全量门禁配置
  .ai/plugins/__init__.py            — 插件入口
  .ai/schemas/                       — Schema 目录
  .pre-commit-config.yaml            — pre-commit 钩子
  scripts/qa_check.py                — QA 检查脚本 (可选)
  scripts/qa_gate.py                 — 十层门禁 (可选)
  scripts/chk_*.py                   — 各 checker (可选)
  run_qa.bat                         — Windows 一键启动脚本 (可选)
  docs/qa-adoption.md                — 集成指南
"""
import json, os, shutil, sys
from pathlib import Path

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_QA_ROOT = os.path.dirname(_SCRIPTS_DIR)

# ── 21 张规则表的完整清单 ────────────────────────────────────

REQUIRED_CONFIGS = [
    "review-rules.yaml",
    "quality-plan.yaml",
    "nfr-baseline.yaml",
    "deployment-gates.yaml",
    "issue-template.yaml",
    "retro-gates.yaml",
    "schema-validator.yaml",
    "framework-self-audit.yaml",
    "codeowner-rules.yaml",
    "security-baseline.yaml",
    "performance-baseline.yaml",
    "test-coverage.yaml",
    "change-management.yaml",
    "worm-policy.yaml",
    "agent-boundary.yaml",
    "compliance-mapping.yaml",
    "secrets-scan.yaml",
    "dead-code.yaml",
    "ai-pipeline.yaml",
    "ai-whitelist.yaml",
    "arch-review.yaml",
]

CHECKER_FILES = [
    "qa_check.py", "qa_gate.py", "qa_plan.py", "qa_classify.py",
    "qa_defect.py", "qa_ai.py", "qa_self_test.py", "qa_cb_tick.py",
    "qa.py",
    "chk_healthscorer.py", "chk_load_yaml.py",
    "chk_inplacechecker.py", "chk_lookaheadchecker.py",
    "chk_secretchecker.py", "chk_deadcodechecker.py",
    "chk_cyclicchecker.py", "chk_codebanchecker.py",
    "chk_codeban_a.py", "chk_codeban_b.py",
    "chk_importboundary.py", "chk_configauditchecker.py",
    "chk_qualitygates.py", "chk_claudevalidator.py",
    "chk_codestyle.py", "chk_governance.py",
    "chk_securityplus.py", "chk_documentation.py",
    "chk_production.py", "chk_zeroprint.py",
    "chk_customrules.py", "chk_fusedetector.py",
    "chk_docconsistency.py",
]

WINDOWS_BAT = """@echo off
chcp 65001 >nul
REM QA 系统 v4.0 — Windows 一键启动脚本
REM 由 qa_setup.py 自动生成

setlocal enabledelayedexpansion

set QA_ROOT=%~dp0
set QA_SYSTEM_ROOT=%QA_ROOT%
set PYTHON=python

echo ============================================================
echo   QA 系统 v4.0 — Gate0-Gate9 十层门禁
echo   项目: %CD%
echo ============================================================
echo.
echo  1. 全量检查 (qa check)
echo  2. 十层门禁 (qa gate)
echo  3. 全流程  (qa local — 检查+分类+门禁)
echo  4. 单门禁   (qa gate --gate=N)
echo  5. 系统自检 (qa self-test)
echo  6. 框架自审 (qa gate --gate=3.1)
echo  7. 退出
echo.

:menu
set /p choice="选择 (1-7): "

if "%choice%"=="1" (
    %PYTHON% "%QA_ROOT%scripts\\qa_check.py" health
    goto menu
)
if "%choice%"=="2" (
    %PYTHON% "%QA_ROOT%scripts\\qa_gate.py"
    goto menu
)
if "%choice%"=="3" (
    call :local_full
    goto menu
)
if "%choice%"=="4" (
    set /p gatenum="输入 Gate 编号 (0/1/2/3/3.1/4/5/6/7/8/9): "
    %PYTHON% "%QA_ROOT%scripts\\qa_gate.py" --gate=!gatenum!
    goto menu
)
if "%choice%"=="5" (
    %PYTHON% "%QA_ROOT%scripts\\qa_self_test.py"
    goto menu
)
if "%choice%"=="6" (
    %PYTHON% "%QA_ROOT%scripts\\qa_gate.py" --gate=3.1
    goto menu
)
if "%choice%"=="7" (
    exit /b 0
)
goto menu

:local_full
%PYTHON% "%QA_ROOT%scripts\\qa_check.py" health
%PYTHON% "%QA_ROOT%scripts\\qa_gate.py"
exit /b
"""

DEFAULT_REVIEW_RULES = """# review-rules.yaml — QA 系统 v4.0 配置
# 由 qa_setup.py 自动生成
version: "4.0"
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
    description: "全量检查（生产标准）"
    checkers_on:
      - inplace_check
      - lookahead_check
      - secret_check
      - deadcode_check
      - cyclic_check
      - code_ban
      - import_boundary
      - config_audit
      - quality_gates
      - claude_validation
      - production
      - codestyle
      - governance
      - securityplus
      - documentation
      - zeroprint
      - customrules
      - fusedetect
      - docconsistency
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
  forbidden_prefixes: ["tests", "scripts", "tools", "archive"]
  allowed_modules: ["numpy", "pandas", "requests"]
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
      - id: qa-gate
        name: qa-gate (Gate0-Gate9 十层门禁)
        entry: python scripts/qa_gate.py
        language: system
        files: \\.py$
        pass_filenames: false
        always_run: true
"""

PLUGIN_INIT = '\"\"\"QA 系统 v4.0 — 插件目录。在此目录下放 .py 文件，自动发现。\n\n每个文件需导出:\n  check(config: dict, project_root: str) -> tuple[int, list[str]]\n  返回 (errors, issues)\n\n示例: .ai/plugins/my_rule.py\n  CHECKER_ID = \"plugin_my_rule\"\n  CHECKER_LABEL = \"我的规则\"\n  def check(config, project_root):\n      return 0, []\n\"\"\"\n'


def setup_project(project_root: str, quick: bool = False,
                  with_checkers: bool = False, local_windows: bool = False):
    root = os.path.abspath(project_root)
    ai_dir = os.path.join(root, ".ai")
    config_dir = os.path.join(ai_dir, "config")
    plugins_dir = os.path.join(ai_dir, "plugins")
    schemas_dir = os.path.join(ai_dir, "schemas")
    logs_dir = os.path.join(ai_dir, "logs")
    fixes_dir = os.path.join(ai_dir, "fixes")
    defects_dir = os.path.join(ai_dir, "defects")
    agents_dir = os.path.join(ai_dir, "agents")
    docs_dir = os.path.join(root, "docs")
    scripts_dir = os.path.join(root, "scripts")

    # 创建目录结构
    for d in [config_dir, plugins_dir, schemas_dir, logs_dir,
              fixes_dir, defects_dir, agents_dir, docs_dir]:
        os.makedirs(d, exist_ok=True)
    if with_checkers:
        os.makedirs(scripts_dir, exist_ok=True)

    # ── 步骤 1: 复制 21 张规则表 ──
    print(f"  ── 规则表 ({len(REQUIRED_CONFIGS)} 张) ──")
    qa_config_dir = os.path.join(_QA_ROOT, ".ai/config")
    copied = 0
    for cf in REQUIRED_CONFIGS:
        src = os.path.join(qa_config_dir, cf)
        dst = os.path.join(config_dir, cf)
        if not os.path.exists(src):
            print(f"  ⏭️  {cf} — 源文件不存在")
            continue
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"  ✅ {cf}")
            copied += 1
        else:
            print(f"  ⏭️  {cf} (已存在)")
    print(f"  复制了 {copied}/{len(REQUIRED_CONFIGS)} 张规则表")

    # ── 步骤 2: 生成 review-rules.yaml ──
    rules_path = os.path.join(config_dir, "review-rules.yaml")
    if not os.path.exists(rules_path) and copied == 0:
        from datetime import date
        with open(rules_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_REVIEW_RULES.format(date=date.today().isoformat()))
        print(f"  ✅ 生成 {os.path.relpath(rules_path, root)}")

    # ── 步骤 3: 生成 pre-commit ──
    pc_path = os.path.join(root, ".pre-commit-config.yaml")
    if not os.path.exists(pc_path):
        with open(pc_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PRE_COMMIT)
        print(f"  ✅ 生成 {os.path.relpath(pc_path, root)}")
    else:
        print(f"  ⏭️  pre-commit 配置已存在")

    # ── 步骤 4: 生成插件入口 ──
    init_path = os.path.join(plugins_dir, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(PLUGIN_INIT)
        print(f"  ✅ 生成 {os.path.relpath(init_path, root)}")

    # ── 步骤 5: 生成 schema 目录标志 ──
    schema_marker = os.path.join(schemas_dir, ".gitkeep")
    if not os.path.exists(schema_marker):
        Path(schema_marker).touch()

    # ── 步骤 6: 复制 checker 脚本 ──
    if with_checkers:
        print(f"  ── Checker 脚本 ({len(CHECKER_FILES)} 个) ──")
        qa_scripts_dir = os.path.join(_QA_ROOT, "scripts")
        chk_copied = 0
        for cf in CHECKER_FILES:
            src = os.path.join(qa_scripts_dir, cf)
            dst = os.path.join(scripts_dir, cf)
            if not os.path.exists(src):
                continue
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                chk_copied += 1
        print(f"  复制了 {chk_copied}/{len(CHECKER_FILES)} 个脚本")

    # ── 步骤 7: 生成 Windows 启动脚本 ──
    if local_windows:
        bat_path = os.path.join(root, "run_qa.bat")
        if not os.path.exists(bat_path):
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(WINDOWS_BAT)
            print(f"  ✅ 生成 run_qa.bat (Windows 启动脚本)")

    # ── 步骤 8: 生成集成指南 ──
    adopt_path = os.path.join(docs_dir, "qa-adoption.md")
    if not os.path.exists(adopt_path):
        with open(adopt_path, "w", encoding="utf-8") as f:
            f.write(_ADOPTION_GUIDE)
        print(f"  ✅ 生成 {os.path.relpath(adopt_path, root)}")

    return True


_ADOPTION_GUIDE = """# QA 系统 v4.0 集成指南

## 开始使用

### 1. 安装依赖
```bash
pip install pyyaml
```

### 2. 运行全量检查
```bash
python scripts/qa_check.py health
```

### 3. 运行十层门禁
```bash
python scripts/qa_gate.py
```

### 4. 一键全流程
```bash
python scripts/qa.py local
```

### 5. 单门禁运行
```bash
python scripts/qa_gate.py --gate=3     # SchemaValidator
python scripts/qa_gate.py --gate=3.1   # 框架自审
python scripts/qa_gate.py --gate=5     # 评分检测
```

### 6. 指定项目运行
```bash
set QA_PROJECT=C:\\path\\to\\project
python scripts/qa.py gate
```

## 环境变量
- `QA_PROJECT=<路径>` — 目标项目
- `QA_ENV=production` — 生产模式（门禁自动通过）
- `QA_SYSTEM_ROOT=<路径>` — QA 系统根目录
- `QA_PROJECT_NAME=<名>` — 目标项目名

## 22 张规则表
`.ai/config/` 下的 YAML 文件构成 QA 系统的完整规则底座。
"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QA 系统 v4.0 快速接入脚本")
    parser.add_argument("--project", "-p", default=".",
                        help="目标项目根目录 (默认当前目录)")
    parser.add_argument("--quick", "-q", action="store_true",
                        help="默认配置快速安装")
    parser.add_argument("--with-checkers", "-c", action="store_true",
                        help="同时复制 checker 脚本到项目 scripts/")
    parser.add_argument("--local-windows", "-w", action="store_true",
                        help="生成 Windows 启动脚本 (run_qa.bat)")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project)
    if not os.path.isdir(project_root):
        print(f"❌ 目录不存在: {project_root}")
        sys.exit(1)

    print(f"QA 系统 v4.0 接入 — {project_root}")
    print("=" * 50)

    if args.quick:
        setup_project(project_root, quick=True)
    else:
        setup_project(project_root, with_checkers=args.with_checkers,
                      local_windows=args.local_windows)

    print()
    print("=" * 50)
    print("✅ QA 系统 v4.0 接入完成")
    print()
    print("  Gate0-Gate9 十层门禁")
    print("  21 张 YAML 规则表")
    print("  19 个内置 Checker")
    print("  SchemaValidator 文档↔代码参数比对")
    print("  Gate3.1 框架手册自审")
    print()
    print("  启动: python scripts/qa.py local")
    print("  或:   run_qa.bat (Windows)")
    print()
    print(f"  QA 系统根: {_QA_ROOT}")
    print(f"  目标项目:  {project_root}")


if __name__ == "__main__":
    main()

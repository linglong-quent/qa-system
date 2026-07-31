# -*- coding: utf-8 -*-
"""生成 .pre-commit-config.yaml + GitHub CI workflow (v2 严格规则版).

设计原则:
  1. 0污染三仓原则: 业务(linglong) / QA(qa-system) / 配置 分离
  2. 严格 flake8 规则: 不忽略 F401/F821/F841/E999 (关键错误必须阻断)
  3. CI 分层: 严重错误(阻断) + 风格问题(记录不阻断)
  4. QA 门禁: 通过 QA_SYSTEM_ROOT 环境变量外部引用, 不内嵌 QA 逻辑

生成产物:
  - .pre-commit-config.yaml: 本地提交钩子 (black + isort + flake8 + QA 外部引用)
  - .github/workflows/ci.yml: GitHub Actions CI (lint + test + preflight + qa-gate + architecture-check + doc-scan)

用法:
  python scripts/qa_tools/_setup_ci.py
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os

LINGLONG_ROOT = str(PROJECT_ROOT)

# ===================================================================
# 1. .pre-commit-config.yaml — 严格规则版 (不忽略关键错误)
# ===================================================================
PRECOMMIT_CONTENT = """# .pre-commit-config.yaml — 玲珑量化
# 0污染原则: 只引用外部QA系统, 不内嵌QA逻辑
# QA_SYSTEM_ROOT 环境变量必须设置, 例如: E:\\WB\\qa-system

repos:
  # ===== 代码格式化 =====
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
        args: [--line-length=120]
        files: \\.(py)$

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: [--profile=black, --line-length=120]
        files: \\.(py)$

  # ===== 代码规范 (严格规则, 不忽略关键错误) =====
  - repo: https://github.com/PyCQA/flake8
    rev: 7.1.0
    hooks:
      - id: flake8
        args:
          - --max-line-length=120
          - --max-complexity=15
          # 只忽略 black 兼容需要的规则, 不再忽略 F401/F821/F841/E999
          - --extend-ignore=E203,W503,E501
          - --count
          - --statistics
        files: \\.(py)$
        exclude: (_deprecated/|archive/|tests/|docs/|\\.venv/|build/|dist/)

  # ===== QA 系统门禁 (外部引用, 0污染) =====
  - repo: local
    hooks:
      - id: qa-health
        name: QA Health Check (19 checker)
        entry: python %QA_SYSTEM_ROOT%/scripts/qa_check.py health --project .
        language: system
        pass_filenames: false
        stages: [commit]

      - id: qa-naming-conflict
        name: QA 命名冲突检测 (STYLE-03b)
        entry: python %QA_SYSTEM_ROOT%/scripts/qa_check.py naming --project .
        language: system
        pass_filenames: false
        stages: [commit]

      - id: qa-cyclic
        name: QA 循环依赖检测 (CYCLIC-001)
        entry: python %QA_SYSTEM_ROOT%/scripts/qa_check.py cyclic --project .
        language: system
        pass_filenames: false
        stages: [commit]

      - id: qa-boundary
        name: QA Gate3 架构边界
        entry: python %QA_SYSTEM_ROOT%/scripts/qa_gate.py --gate=3 --project .
        language: system
        pass_filenames: false
        stages: [push]

      - id: qa-gate5
        name: QA Gate5 评分检测
        entry: python %QA_SYSTEM_ROOT%/scripts/qa_gate.py --gate=5 --project .
        language: system
        pass_filenames: false
        stages: [push]
"""

# ===================================================================
# 2. .github/workflows/ci.yml — 分层 CI (严格 + 渐进)
# ===================================================================
CI_CONTENT = """name: Linglong CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  # ===== 1. 代码规范 (严格规则) =====
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"

      # 严重错误检测: 语法错误、未定义名称、重定义、未使用变量 (必须通过)
      - name: Flake8 Critical (E999/F821/F811/F401/F841)
        run: |
          flake8 shared/ domain/ access/ scripts/ \\
            --count --max-line-length=120 \\
            --select=E999,F821,F811,F401,F841 \\
            --extend-ignore= \\
            --show-source \\
            --statistics

      # 风格检测: 所有规则 (记录但不阻断, 渐进修复)
      - name: Flake8 Style (full report)
        run: |
          flake8 shared/ domain/ access/ scripts/ \\
            --count --max-line-length=120 \\
            --extend-ignore=E203,W503,E501 \\
            --statistics \\
            --exit-zero

  # ===== 2. 单元测试 =====
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ -v --tb=short --ignore=tests/unit/test_factor_property.py --ignore=tests/unit/test_fuzz_wide.py --ignore=tests/unit/test_property_based.py --ignore=tests/unit/test_property_based_v2.py

  # ===== 3. 预检门禁 (核心模块导入验证) =====
  preflight-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: |
          python -c "
          from shared.resilience import CircuitBreaker
          from shared.gambit_veto import GambitVeto
          from shared.market_regime import MarketRegime
          from shared.profile_db import ProfileDB
          print('preflight: 4/4 modules OK')
          "

  # ===== 4. QA 系统门禁 (0污染: 外部引用) =====
  qa-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Clone QA System
        run: git clone --depth 1 https://github.com/linglong-quent/qa-system.git /tmp/qa-system

      - name: Set QA System Env
        run: echo "QA_SYSTEM_ROOT=/tmp/qa-system" >> $GITHUB_ENV

      - name: Gate3 架构边界
        run: python /tmp/qa-system/scripts/qa_gate.py --gate=3 --project .

      - name: Gate3.1 框架自审
        run: python /tmp/qa-system/scripts/qa_gate.py --gate=3.1 --project .
        continue-on-error: true

      - name: Gate5 评分检测
        run: python /tmp/qa-system/scripts/qa_gate.py --gate=5 --project .
        continue-on-error: true

      - name: Gate9 合规自检
        run: python /tmp/qa-system/scripts/qa_gate.py --gate=9 --project .
        continue-on-error: true

      - name: QA Full Health Report
        if: always()
        run: python /tmp/qa-system/scripts/qa_check.py health --project .
        continue-on-error: true

  # ===== 5. 命名冲突 + 循环依赖 + 架构边界检测 =====
  architecture-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"

      - name: Clone QA System
        run: git clone --depth 1 https://github.com/linglong-quent/qa-system.git /tmp/qa-system

      - name: Set QA System Env
        run: echo "QA_SYSTEM_ROOT=/tmp/qa-system" >> $GITHUB_ENV
        shell: bash

      - name: 命名冲突检测 (STYLE-03b)
        run: python /tmp/qa-system/scripts/chk_namingconflict.py --project .
        continue-on-error: true

      - name: 循环依赖检测 (CYCLIC-001)
        run: python /tmp/qa-system/scripts/chk_cyclicchecker.py --project .

      - name: 架构边界检测 (BOUNDARY)
        run: python /tmp/qa-system/scripts/chk_importboundary.py --project .
        env:
          QA_PROJECT_NAME: linglong

  # ===== 6. 文档健康扫描 =====
  doc-scan:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pyyaml

      - name: Clone QA System
        run: git clone --depth 1 https://github.com/linglong-quent/qa-system.git /tmp/qa-system

      - name: Doc Health Scan
        run: python /tmp/qa-system/scripts/qa_check.py --mode doc-health --project .
        continue-on-error: true
"""


def main() -> None:
    """生成 pre-commit 与 CI workflow 配置."""
    # 1. .pre-commit-config.yaml
    precommit_path = os.path.join(LINGLONG_ROOT, ".pre-commit-config.yaml")
    with open(precommit_path, "w", encoding="utf-8") as f:
        f.write(PRECOMMIT_CONTENT)
    print(f"  [OK] {precommit_path}")

    # 2. .github/workflows/ci.yml
    ci_dir = os.path.join(LINGLONG_ROOT, ".github", "workflows")
    os.makedirs(ci_dir, exist_ok=True)
    ci_path = os.path.join(ci_dir, "ci.yml")
    with open(ci_path, "w", encoding="utf-8") as f:
        f.write(CI_CONTENT)
    print(f"  [OK] {ci_path}")

    print()
    print("配置生成完成!")
    print(f"  pre-commit: {precommit_path}")
    print(f"  CI workflow: {ci_path}")
    print()
    print("验证命令:")
    print("  flake8 shared/ domain/ access/ scripts/ \\")
    print("    --count --max-line-length=120 \\")
    print("    --select=E999,F821,F811,F401,F841 --show-source --statistics")


if __name__ == "__main__":
    main()

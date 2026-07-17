#!/usr/bin/env python3
"""
skill_dir_governance.py — 目录治理扫描器 (Phase 1)
检查根目录是否存在违规文件（不在规划目录中的散落文件）

规划依据: _docs/inventory/系统资产台账.md  §一

白名单（允许放在根目录的文件）:
  .gitignore, .editorconfig, .pre-commit-config.yaml, .sqlfluff
  pyproject.toml, setup.py, requirements.txt, mypy.ini, pytest.ini
  version_ledger.worm, README.md, CHANGELOG.md, Dockerfile
  docker-compose.yml, alembic.ini, .dockerignore, .flake8
  _ci_check*.ps1, _ci_sign.ps1, _ci_verify.ps1
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ALLOWED_ROOT_FILES = {
    ".gitignore",
    ".editorconfig",
    ".pre-commit-config.yaml",
    ".sqlfluff",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "mypy.ini",
    "pytest.ini",
    ".flake8",
    ".dockerignore",
    "alembic.ini",
    "version_ledger.worm",
    "README.md",
    "CHANGELOG.md",
    "Dockerfile",
    "docker-compose.yml",
}

ALLOWED_ROOT_PREFIXES = ("_ci_check", "_ci_sign", "_ci_verify", "_ci_reports", ".git", ".github", ".kun")

ALLOWED_DIRECTORIES = {
    "_config",
    "_core",
    "_deprecated",
    "_dev",
    "_docs",
    "_gov",
    "_reports",
    "_tasks",
    "api",
    "archive",
    "bailian",
    "config",
    "data",
    "docs",
    "linglong",
    "logs",
    "order",
    "runtime",
    "scripts",
    "sidecar",
    "src",
    "strategies",
    "strategy",
    "tdx_bridge",
    "test",
    "tests",
    "tools",
    "恢复",
    "Knowledge",
}


def scan():
    issues = []
    for entry in ROOT.iterdir():
        name = entry.name

        # Skip hidden dirs
        if name.startswith("."):
            continue

        if entry.is_file():
            # Check if allowed in root
            if name in ALLOWED_ROOT_FILES:
                continue
            if any(name.startswith(p) for p in ALLOWED_ROOT_PREFIXES):
                continue

            # Everything else in root is a violation
            issues.append(("ROOT_POLLUTION", name, "文件不应放在根目录，请移到 scripts/ _docs/ 等对应目录"))

        elif entry.is_dir():
            if name not in ALLOWED_DIRECTORIES:
                issues.append(("UNKNOWN_DIR", name, "目录不在台账规划中，请移到 linglong/ 下或清理"))

    return issues


def main():
    issues = scan()
    if not issues:
        print("==> 目录治理: PASS (0 违规)")
        sys.exit(0)

    print(f"==> 目录治理: {len(issues)} 项违规")
    for typ, name, msg in issues:
        print(f"  [{typ}] {name}")
        print(f"         {msg}")
    sys.exit(2)


if __name__ == "__main__":
    main()

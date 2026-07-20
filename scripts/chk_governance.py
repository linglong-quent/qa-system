#!/usr/bin/env python3
"""Checker: 项目治理 — Python 工程结构 + 目录规范 + 资产健康

检查项：
  - Python 标准工程结构（pyproject.toml / src/ / tests/ 等）
  - 目录结构完整
  - 顶层文件整洁
  - __pycache__ 管理
  - 文档健康
  - 编码合规（UTF-8, 无 BOM）
"""
import os
from typing import List, Tuple


class GovernanceChecker:
    CHECKER_ID = "governance_check"
    CHECKER_LABEL = "项目治理"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.expected_structure = config.get("expected_dirs",
                                              ["src/", "tests/", "docs/", "scripts/"])
        self.strict_python = config.get("strict_python_struct", True)

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0

        # ── 1. Python 标准工程结构 ──
        has_pyproject = os.path.exists(os.path.join(self.project_root, "pyproject.toml"))
        has_setup = os.path.exists(os.path.join(self.project_root, "setup.py"))
        has_setup_cfg = os.path.exists(os.path.join(self.project_root, "setup.cfg"))
        has_requirements = os.path.exists(os.path.join(self.project_root, "requirements.txt"))
        has_gitignore = os.path.exists(os.path.join(self.project_root, ".gitignore"))
        has_license = os.path.exists(os.path.join(self.project_root, "LICENSE"))
        has_readme = os.path.exists(os.path.join(self.project_root, "README.md"))
        has_src = os.path.isdir(os.path.join(self.project_root, "src"))
        has_tests = os.path.isdir(os.path.join(self.project_root, "tests"))

        if not (has_pyproject or has_setup or has_setup_cfg):
            issues.append("[PY-01] 缺少 Python 项目定义（pyproject.toml / setup.py / setup.cfg）")
            errors += 1

        if not has_requirements:
            issues.append("[PY-02] 缺少 requirements.txt（依赖管理）")
            errors += 1

        if not has_gitignore:
            issues.append("[PY-03] 缺少 .gitignore")
            errors += 1

        if not has_license:
            issues.append("[PY-04] 缺少 LICENSE")
            errors += 1

        if not has_readme:
            issues.append("[PY-05] 缺少 README.md（项目说明）")
            errors += 1

        if self.strict_python:
            # src/ 或根级 Python 包
            has_root_pkg = any(
                os.path.isdir(os.path.join(self.project_root, d))
                and os.path.exists(os.path.join(self.project_root, d, "__init__.py"))
                for d in os.listdir(self.project_root)
                if os.path.isdir(os.path.join(self.project_root, d))
                and not d.startswith((".", "_"))
                and d not in ("tests", "docs", "scripts", "config", "data", "archive")
            )
            if not has_src and not has_root_pkg:
                issues.append("[PY-06] 缺少 src/ 目录或 Python 包（含 __init__.py）")
                errors += 1

            if not has_tests:
                issues.append("[PY-07] 缺少 tests/ 目录")
                errors += 1

        # ── 2. 目录结构检查 ──
        for ed in self.expected_structure:
            full = os.path.join(self.project_root, ed)
            if not os.path.isdir(full):
                issues.append(f"[GOV-01] 期望目录 '{ed}' 不存在")
                errors += 1

        # ── 3. 顶层文件检查（不应过多） ──
        top_allowed = {
            "README.md", "CHANGELOG.md", "LICENSE",
            "pyproject.toml", "setup.py", "setup.cfg",
            "requirements.txt", ".gitignore", ".pre-commit-config.yaml",
            "VERSION", "version.txt", "Makefile", "Dockerfile",
            "docker-compose.yml", "docker-compose.yaml",
            ".env.example", ".editorconfig", ".flake8", ".pylintrc",
            ".python-version", ".gitattributes",
            "CLAUDE.md", "SOUL.md",
        }
        top_dir = self.project_root
        top_items = [
            f for f in os.listdir(top_dir)
            if os.path.isfile(os.path.join(top_dir, f))
            and not f.startswith(".")
            and f not in top_allowed
        ]
        if len(top_items) > 20:
            issues.append(f"[GOV-02] 顶层目录文件过多 ({len(top_items)} 个)，建议移入子目录")
            errors += 1

        # ── 4. __pycache__ 清理检查 ──
        pycache_count = 0
        for root, dirs, files in os.walk(self.project_root):
            pycache_count += dirs.count("__pycache__")
        if pycache_count > 10:
            issues.append(f"[GOV-03] 发现 {pycache_count} 个 __pycache__ 目录，建议清理并加入 .gitignore")
            errors += 1

        # ── 5. 编码合规检查（UTF-8 BOM） ──
        bom_count = 0
        py_files_found = 0
        for root, dirs, files in os.walk(self.project_root):
            if "__pycache__" in root or ".git" in root:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                py_files_found += 1
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "rb") as bf:
                        header = bf.read(3)
                    # UTF-8 BOM: EF BB BF
                    if header == b"\xef\xbb\xbf":
                        bom_count += 1
                        if bom_count <= 3:
                            rel = os.path.relpath(fpath, self.project_root)
                            issues.append(f"[ENC-01] {rel} 包含 UTF-8 BOM（应使用无 BOM UTF-8）")
                            errors += 1
                except Exception:
                    pass

        if py_files_found == 0:
            issues.append("[PY-08] 项目不含任何 .py 文件")
            errors += 1

        # ── 6. __init__.py 覆盖检查 ──
        pkg_dirs_without_init = 0
        for root, dirs, files in os.walk(self.project_root):
            if "__pycache__" in root or ".git" in root:
                continue
            for d in dirs:
                dpath = os.path.join(root, d)
                is_python_pkg = any(
                    f.endswith(".py") for f in os.listdir(dpath)
                    if os.path.isfile(os.path.join(dpath, f))
                )
                if is_python_pkg and not os.path.exists(os.path.join(dpath, "__init__.py")):
                    pkg_dirs_without_init += 1

        if pkg_dirs_without_init > 0 and has_src:
            issues.append(f"[PY-09] {pkg_dirs_without_init} 个含 .py 的目录缺少 __init__.py")
            errors += 1

        return errors, issues

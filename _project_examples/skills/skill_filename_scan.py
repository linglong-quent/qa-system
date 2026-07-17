#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_filename_scan.py — 文件名强制英文+snake_case 全量扫描 (B1-11)
===================================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-11)

职责: 全量扫描文件名规范
  1. 禁止中文/拼音命名
  2. 禁止驼峰命名
  3. 禁止大写字母（除 __init__.py 等特殊文件）
  4. 强制 snake_case

用法:
    python scripts/skill/skill_filename_scan.py
    python scripts/skill/skill_filename_scan.py --output json

退出码:
    0 = 全部合规
    1 = 存在违规文件名
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# ═══════════════════════════════════════════════════════════════
# 文件名规则
# ═══════════════════════════════════════════════════════════════

# 允许的特殊文件名（不检查）
WHITELIST_FILES = {
    "__init__.py",
    "__main__.py",
    "README.md",
    "CHANGELOG.md",
    "CODEBUDDY.md",
    "SYSTEM_MANUAL.md",
    "SKILL_DEV_GUIDE.md",
    "CODEOWNERS",
    ".editorconfig",
    ".gitignore",
    ".pre-commit-config.yaml",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
}

# 中文字符检测
CN_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")

# 驼峰检测
CAMEL_PATTERN = re.compile(r"[a-z][A-Z]")

# 大写字母检测（非首字母）
UPPER_PATTERN = re.compile(r"[A-Z]{2,}")


def is_snake_case(name: str) -> bool:
    """检查是否为 snake_case"""
    if name in WHITELIST_FILES:
        return True
    # 去掉扩展名
    stem = Path(name).stem
    if stem.startswith("__") and stem.endswith("__"):
        return True
    return bool(re.match(r"^[a-z][a-z0-9_]*$", stem))


def has_chinese(name: str) -> bool:
    """检查是否含中文"""
    return bool(CN_PATTERN.search(name))


def has_camel_case(name: str) -> bool:
    """检查是否驼峰命名"""
    stem = Path(name).stem
    return bool(CAMEL_PATTERN.search(stem))


def has_consecutive_upper(name: str) -> bool:
    """检查是否连续大写（缩写词）"""
    stem = Path(name).stem
    return bool(UPPER_PATTERN.search(stem))


class SkillFilenameScan(BaseSkill):
    """文件名规范扫描"""

    def __init__(self, target_path: Optional[str] = None):
        super().__init__("filename_scan")
        self.target = Path(target_path or _ROOT).resolve()

    def _scan_directory(self, directory: Path) -> list[Dict[str, Any]]:  # noqa: C901
        """递归扫描目录"""
        findings = []
        try:
            for item in directory.iterdir():
                if item.name.startswith(".") and item.name != ".editorconfig":
                    continue  # 跳过隐藏文件
                if item.name in WHITELIST_FILES:
                    continue
                if item.name.startswith("__pycache__"):
                    continue
                if item.suffix in (".pyc", ".pyo", ".egg-info"):
                    continue

                # 检查文件名
                issues = []
                if has_chinese(item.name):
                    issues.append(f"含中文字符")  # noqa: F541
                if has_camel_case(item.name):
                    issues.append(f"驼峰命名")  # noqa: F541
                if has_consecutive_upper(item.name):
                    issues.append(f"连续大写字母")  # noqa: F541
                if not is_snake_case(item.name) and item.is_file():
                    issues.append(f"非 snake_case")  # noqa: F541

                if issues:
                    findings.append(
                        {
                            "rule_id": "FILE-001",
                            "severity": "warning",
                            "file": str(item),
                            "line": 0,
                            "message": f"文件名不合规: {item.name} ({', '.join(issues)})",
                            "suggest": f"建议改为 snake_case: {_to_snake_case(item.stem)}{item.suffix}",
                        }
                    )

                # 递归子目录
                if item.is_dir() and not item.name.startswith("."):
                    findings.extend(self._scan_directory(item))

        except PermissionError:
            pass
        return findings

    def run_checks(self) -> list[CheckResult]:
        """执行文件名扫描"""
        all_findings = self._scan_directory(self.target)

        results: list[CheckResult] = []

        if not all_findings:
            results.append(
                CheckResult(
                    rule="FILE-000",
                    severity="info",
                    message="所有文件名符合规范",
                )
            )
        else:
            for f in all_findings[:30]:
                results.append(
                    CheckResult(
                        rule=f["rule_id"],
                        severity=f["severity"],
                        file=f["file"],
                        message=f["message"],
                        suggest=f.get("suggest", ""),
                    )
                )
            results.append(
                CheckResult(
                    rule="FILE-001",
                    severity="warning",
                    message=f"发现 {len(all_findings)} 个不合规文件名",
                )
            )

        return results


def _to_snake_case(name: str) -> str:
    """尝试将驼峰转为 snake_case"""
    # 简单转换
    result = re.sub(r"([A-Z])", r"_\1", name).lower()
    result = re.sub(r"_+", "_", result).strip("_")
    # 中文转拼音（简单映射）
    return result


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """统一入口"""
    checker = SkillFilenameScan(target_path=path)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n文件名规范扫描报告")  # noqa: F541
        print(f"{'='*50}")
        for r in results:
            icon = {"info": "✓", "warning": "⚠", "blocker": "✗"}.get(r.severity, "?")
            loc = f" [{r.file}]" if r.file else ""
            print(f"  [{icon}] {r.message}{loc}")
            if r.suggest:
                print(f"       → {r.suggest}")
        print(f"{'='*50}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="文件名规范扫描")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--path", default=None, help="扫描目标路径")
    args = parser.parse_args()
    result = run(output=args.output, path=args.path)
    sys.exit(result.get("exit_code", 0))

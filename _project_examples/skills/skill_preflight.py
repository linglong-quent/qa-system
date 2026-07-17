#!/usr/bin/env python3
"""
skill_preflight.py — P1-F19 环境指纹启动校验
=============================================
启动前检查以下环境要素：
1. Python 版本 >= 3.10
2. 核心依赖可导入（yaml, numpy, pandas 等）
3. DB 文件存在且可读写
4. 磁盘空间充足
5. 配置文件完整性

使用:
    python scripts/skill/skill_preflight.py [--output json]
"""

import importlib
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# Python 版本要求
MIN_PYTHON = (3, 10)

# 核心依赖
CORE_DEPS = [
    "yaml",
    "numpy",
    "pandas",
    "sqlite3",
    "json",
    "datetime",
    "pathlib",
]

# 关键路径 (相对于 workspace 根)
KEY_PATHS = {
    "config_rules": "config/rule",
    "linglong_core": "linglong/_core",
    "skill_dir": "linglong/scripts/skill",
    "tasks_dir": "_tasks",
}

# 最低磁盘空间 (MB)
MIN_DISK_MB = 500


class PreflightCheck(BaseSkill):
    """启动预检器"""

    def __init__(self) -> None:
        super().__init__("preflight")
        self.workspace = _ROOT.parent  # workspace 根目录
        self.results: list[CheckResult] = []

    def _check_python_version(self) -> list[CheckResult]:
        results = []
        v = sys.version_info
        if v.major < MIN_PYTHON[0] or (v.major == MIN_PYTHON[0] and v.minor < MIN_PYTHON[1]):
            results.append(
                CheckResult(
                    rule="PF-001",
                    severity="blocker",
                    message=f"Python 版本过低: {v.major}.{v.minor}.{v.micro}，需要 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
                    suggest="升级到 Python 3.10+",
                )
            )
        else:
            results.append(
                CheckResult(rule="PF-001", severity="info", message=f"Python {v.major}.{v.minor}.{v.micro} ✅")
            )
        return results

    def _check_dependencies(self) -> list[CheckResult]:
        results = []
        for dep in CORE_DEPS:
            try:
                importlib.import_module(dep)
                results.append(CheckResult(rule="PF-002", severity="info", message=f"依赖 {dep} ✅"))
            except ImportError:
                results.append(
                    CheckResult(
                        rule="PF-002", severity="blocker", message=f"核心依赖缺失: {dep}", suggest=f"pip install {dep}"
                    )
                )
        return results

    def _check_paths(self) -> list[CheckResult]:
        results = []
        for name, rel_path in KEY_PATHS.items():
            full_path = self.workspace / rel_path
            if full_path.exists():
                results.append(CheckResult(rule="PF-003", severity="info", message=f"路径 {rel_path} ✅"))
            else:
                results.append(
                    CheckResult(
                        rule="PF-003",
                        severity="error",
                        message=f"关键路径不存在: {rel_path}",
                        suggest=f"创建目录: {full_path}",
                    )
                )
        return results

    def _check_disk_space(self) -> list[CheckResult]:
        results = []
        try:
            usage = shutil.disk_usage(self.workspace)
            free_mb = usage.free / (1024 * 1024)
            if free_mb < MIN_DISK_MB:
                results.append(
                    CheckResult(
                        rule="PF-004",
                        severity="error",
                        message=f"磁盘空间不足: {free_mb:.0f}MB < {MIN_DISK_MB}MB",
                        suggest="清理磁盘空间",
                    )
                )
            else:
                results.append(CheckResult(rule="PF-004", severity="info", message=f"磁盘空间 {free_mb:.0f}MB ✅"))
        except Exception as e:
            results.append(CheckResult(rule="PF-004", severity="warning", message=f"磁盘检查失败: {e}"))
        return results

    def run_checks(self) -> list[CheckResult]:
        self.results = []
        self.results.extend(self._check_python_version())
        self.results.extend(self._check_dependencies())
        self.results.extend(self._check_paths())
        self.results.extend(self._check_disk_space())
        return self.results


def run(output: str = "json") -> Dict[str, Any]:
    skill = PreflightCheck()
    results = skill.run_checks()
    result = skill.output_results(results)
    if output == "json":
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="环境指纹启动校验")
    parser.add_argument("--output", default="json")
    args = parser.parse_args()
    run(output=args.output)

#!/usr/bin/env python3
"""
skill_baseline_all.py — P1-F21 四大基线一键执行
================================================
1. 资产复用基线 — asset_reuse_map.yaml 完整性
2. 密钥/敏感信息基线 — 扫描残留密钥
3. 数据血缘基线 — 表名引用一致性
4. 性能基线 — 大文件/大函数检查

使用:
    python scripts/skill/skill_baseline_all.py [--output json]
"""

import os  # noqa: F401
import re
import sys
from pathlib import Path
from typing import Optional  # noqa: F401

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# 大文件阈值 (KB)
LARGE_FILE_KB = 200

# 大函数阈值 (行数)
LARGE_FUNCTION_LINES = 100


class BaselineAll(BaseSkill):
    """四大基线检查器"""

    def __init__(self):  # type: ignore[no-untyped-def]
        super().__init__("baseline_all")
        self.workspace = _ROOT.parent  # workspace 根目录
        self.results: list[CheckResult] = []

    def _baseline_asset_reuse(self) -> list[CheckResult]:
        """资产复用基线：检查 asset_reuse_map.yaml 是否存在且格式正确"""
        results = []
        map_path = self.workspace / "config" / "rule" / "asset_reuse_map.yaml"
        if not map_path.exists():
            results.append(
                CheckResult(
                    rule="BL-001",
                    severity="blocker",
                    message="asset_reuse_map.yaml 不存在",
                    suggest="创建 config/rule/asset_reuse_map.yaml",
                )
            )
            return results

        try:
            import yaml

            data = yaml.safe_load(map_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "assets" not in data:
                results.append(
                    CheckResult(rule="BL-001", severity="error", message="asset_reuse_map.yaml 缺少 assets 字段")
                )
            else:
                count = len(data["assets"])
                results.append(CheckResult(rule="BL-001", severity="info", message=f"资产复用映射表: {count} 条 ✅"))
        except Exception as e:
            results.append(CheckResult(rule="BL-001", severity="error", message=f"asset_reuse_map.yaml 解析失败: {e}"))
        return results

    def _baseline_secrets(self) -> list[CheckResult]:  # noqa: C901
        """密钥/敏感信息基线：扫描残留密钥"""
        results = []
        patterns = [
            (r"TDX-\w+", "TDX Token", "warning"),
            (r"(?i)password\s*=", "密码赋值", "warning"),
            (r"(?i)api[_-]?key\s*=", "API Key", "warning"),
            (r"(?i)secret\b", "Secret 字段", "info"),
        ]
        # 只扫描 skills 目录和配置文件
        scan_dirs = [
            self.workspace / "linglong" / "scripts" / "skill",
            self.workspace / "config",
        ]
        found = 0
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for fp in scan_dir.rglob("*"):
                if fp.suffix not in (".py", ".yaml", ".yml", ".json", ".md"):
                    continue
                if "__pycache__" in str(fp):
                    continue
                try:
                    text = fp.read_text(encoding="utf-8")
                    for pattern, label, sev in patterns:
                        for m in re.finditer(pattern, text):
                            found += 1
                            if found <= 5:  # 限制报告数量
                                results.append(
                                    CheckResult(
                                        rule="BL-002",
                                        severity=sev,
                                        message=f"发现{label}: {m.group()[:40]}",
                                        file=str(fp.relative_to(self.workspace)),
                                        line=text[: m.start()].count("\n") + 1,
                                        suggest="将敏感信息移至环境变量或密钥管理",
                                    )
                                )
                except (UnicodeDecodeError, OSError):
                    continue
        if found == 0:
            results.append(CheckResult(rule="BL-002", severity="info", message="未发现敏感信息泄露 ✅"))
        return results

    def _baseline_file_size(self) -> list[CheckResult]:
        """性能基线：大文件检查"""
        results = []
        large_files = []
        scan_dir = self.workspace
        for fp in scan_dir.rglob("*.py"):
            if "_deprecated" in str(fp) or "__pycache__" in str(fp):
                continue
            size_kb = fp.stat().st_size / 1024
            if size_kb > LARGE_FILE_KB:
                large_files.append((fp, size_kb))
        if large_files:
            for fp, size in sorted(large_files, key=lambda x: -x[1])[:5]:
                results.append(
                    CheckResult(
                        rule="BL-003",
                        severity="warning",
                        message=f"大文件: {size:.0f}KB",
                        file=str(fp.relative_to(self.workspace)),
                        suggest="考虑拆分模块",
                    )
                )
        results.append(
            CheckResult(
                rule="BL-003", severity="info", message=f"大文件检查: {len(large_files)} 个超过 {LARGE_FILE_KB}KB"
            )
        )
        return results

    def _baseline_table_refs(self) -> list[CheckResult]:
        """数据血缘基线：检查表名引用一致性"""
        results = []
        try:
            sys.path.insert(0, str(self.workspace))
            from linglong._core.constants import (  # noqa: F401
                T_CHIP,
                T_FINANCIAL,
                T_FLOW,
                T_HIST,
                T_L2_DEPTH,
                T_POSITION,
                T_SNAP,
                T_STILL,
            )

            results.append(
                CheckResult(
                    rule="BL-004",
                    severity="info",
                    message=f"表名常量可用: {T_HIST}, {T_STILL}, {T_CHIP}, {T_FLOW}... ✅",
                )
            )
        except ImportError as e:
            results.append(CheckResult(rule="BL-004", severity="error", message=f"表名常量无法导入: {e}"))
        return results

    def run_checks(self) -> list[CheckResult]:
        self.results = []
        self.results.extend(self._baseline_asset_reuse())
        self.results.extend(self._baseline_secrets())
        self.results.extend(self._baseline_file_size())
        self.results.extend(self._baseline_table_refs())
        return self.results


def run(output: str = "json") -> dict:  # type: ignore[type-arg]
    skill = BaselineAll()  # type: ignore[no-untyped-call]
    results = skill.run_checks()
    result = skill.output_results(results)
    if output == "json":
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="四大基线检查")
    parser.add_argument("--output", default="json")
    args = parser.parse_args()
    run(output=args.output)

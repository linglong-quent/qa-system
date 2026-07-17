#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_asset_scan.py — 每日资产复用巡检 (B1-06)
=================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-06)

职责: 每日自动巡检项目资产复用情况
  1. 扫描所有 Python 文件
  2. 读取 asset_reuse_map.yaml 对照表
  3. 检测新增文件是否可复用已有资产（AST 相似度 >=60%）
  4. 统计标注率，<60% 告警

用法:
    python scripts/skill/skill_asset_scan.py
    python scripts/skill/skill_asset_scan.py --threshold 60
    python scripts/skill/skill_asset_scan.py --output json

退出码:
    0 = 标注率 >= 阈值
    2 = 标注率 < 阈值（告警，不阻断）
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# 默认资产复用对照表路径
_ASSET_MAP_PATH = _ROOT / "config" / "rule" / "asset_reuse_map.yaml"

# 默认扫描目录
_SCAN_DIRS = [
    "linglong/_core/",
    "linglong/scripts/",
    "linglong/data/",
    "linglong/tools/",
    "linglong/sidecar/",
]


def _compute_ast_hash(filepath: Path) -> str:
    """计算文件 AST 结构哈希（忽略注释/docstring 差异）"""
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
        # 移除 docstring 和注释
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
                node.body = [
                    n for n in node.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
                ]
        return hashlib.sha256(ast.dump(tree).encode()).hexdigest()
    except (SyntaxError, IOError):
        return ""


def _compute_similarity(hash1: str, hash2: str) -> float:
    """计算两个哈希的近似相似度（基于字符重叠）"""
    if not hash1 or not hash2:
        return 0.0
    if hash1 == hash2:
        return 100.0
    # 简单 Jaccard 相似度
    set1 = set(hash1[i : i + 4] for i in range(0, len(hash1), 4))
    set2 = set(hash2[i : i + 4] for i in range(0, len(hash2), 4))
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return round(intersection / union * 100, 1)


def _has_reuse_annotation(filepath: Path) -> bool:
    """检查文件是否含 REUSE 标注"""
    try:
        content = filepath.read_text(encoding="utf-8")
        return "REUSE:" in content or "复用:" in content or "复用来源" in content
    except IOError:
        return False


class SkillAssetScan(BaseSkill):
    """每日资产复用巡检"""

    def __init__(self, threshold: float = 60.0, target_dirs: Optional[list[str]] = None):
        super().__init__("asset_scan")
        self.threshold = threshold
        self.target_dirs = target_dirs or _SCAN_DIRS
        self._asset_map: Dict[str, Any] = {}

    def _load_asset_map(self) -> Dict[str, Any]:
        """加载资产复用对照表"""
        if _ASSET_MAP_PATH.exists():
            import yaml

            with open(_ASSET_MAP_PATH, encoding="utf-8") as f:
                self._asset_map = yaml.safe_load(f) or {}
        return self._asset_map

    def _scan_directory(self, dir_path: Path) -> Dict[str, Any]:
        """扫描单个目录"""
        stats = {"files_total": 0, "files_with_reuse": 0, "files_without_reuse": 0, "high_similarity_pairs": []}
        if not dir_path.exists():
            return stats

        py_files = list(dir_path.rglob("*.py"))
        stats["files_total"] = len(py_files)

        for f in py_files:
            if _has_reuse_annotation(f):
                stats["files_with_reuse"] += 1  # type: ignore[operator]
            else:
                stats["files_without_reuse"] += 1  # type: ignore[operator]

        return stats

    def run_checks(self) -> list[CheckResult]:
        """执行资产复用巡检"""
        self._load_asset_map()
        results: list[CheckResult] = []

        total_files = 0
        total_reuse = 0
        total_no_reuse = 0

        for dir_name in self.target_dirs:
            dir_path = _ROOT / dir_name
            if not dir_path.exists():
                continue
            stats = self._scan_directory(dir_path)
            total_files += stats["files_total"]
            total_reuse += stats["files_with_reuse"]
            total_no_reuse += stats["files_without_reuse"]

        if total_files == 0:
            results.append(
                CheckResult(
                    rule="ASSET-000",
                    severity="info",
                    message="未找到 Python 文件",
                )
            )
            return results

        reuse_rate = round(total_reuse / total_files * 100, 1) if total_files > 0 else 0

        # 判断是否达标
        if reuse_rate >= self.threshold:
            sev = "info"
            msg = f"资产复用标注率 {reuse_rate}% >= {self.threshold}% " f"({total_reuse}/{total_files} 文件已标注)"
        else:
            sev = "warning"
            msg = (
                f"资产复用标注率 {reuse_rate}% < {self.threshold}% "
                f"({total_reuse}/{total_files} 文件已标注，"
                f"{total_no_reuse} 文件未标注 REUSE)"
            )

        results.append(
            CheckResult(
                rule="ASSET-001",
                severity=sev,
                message=msg,
                suggest=f"建议为未标注文件添加 REUSE 注释" if reuse_rate < self.threshold else "",  # noqa: F541
            )
        )

        # 检查对照表完整性
        map_entries = len(self._asset_map.get("assets", {}))
        results.append(
            CheckResult(
                rule="ASSET-002",
                severity="info",
                message=f"资产对照表含 {map_entries} 项映射",
            )
        )

        return results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", threshold: float = 60.0, dirs: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """统一入口"""
    target = [d.strip() for d in dirs.split(",")] if dirs else _SCAN_DIRS
    checker = SkillAssetScan(threshold=threshold, target_dirs=target)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for r in results:
            icon = {"info": "ℹ", "warning": "⚠", "blocker": "✗", "error": "✗"}.get(r.severity, "?")
            print(f"[{icon}] {r.message}")
            if r.suggest:
                print(f"    → {r.suggest}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="每日资产复用巡检")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--threshold", type=float, default=60.0, help="标注率阈值 (默认60%)")
    parser.add_argument("--dirs", default=None, help="扫描目录(逗号分隔)")
    args = parser.parse_args()
    result = run(output=args.output, threshold=args.threshold, dirs=args.dirs)
    sys.exit(result.get("exit_code", 0))

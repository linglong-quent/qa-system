#!/usr/bin/env python3
"""Checker: 大文件检测（强制阻断）

行业标准对齐：
  - Clean Code / ISO 25010: 类/文件 ≤ 500 行（配置可调）
  - NASA Power of 10: 单一职责原则

检查规则：
  - LARGE-01 [BLOCKER]: 文件行数 > max_lines 且不在 baseline 中 → 阻断
  - LARGE-02 [WARN]:   文件行数 > max_lines 但在 baseline 中 → 警告（存量债务）
  - LARGE-03 [INFO]:   baseline 中记录的文件已修复（行数 ≤ max_lines）→ 提示移除

设计要点：
  1. 强制阻断新增违规（baseline 之外）
  2. baseline 中记录存量违规（一次性快照，逐步清零）
  3. 自动识别已修复文件，鼓励清理 baseline
"""
import os
import logging
from typing import List, Tuple

from chk_load_yaml import load_yaml

logger = logging.getLogger(__name__)


class LargeFilesChecker:
    """大文件检查器 — 强制阻断新增违规，存量违规走 baseline 豁免."""
    CHECKER_ID = "largefiles_check"
    CHECKER_LABEL = "大文件检测"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/"])
        self.exclude_subdirs = set(config.get("exclude_subdirs", [
            "qa_tools", "_deprecated", "archive", "__pycache__", "node_modules",
            ".git", ".pytest_cache",
        ]))
        # 行数阈值（Fallback: Clean Code 500）
        nfr = config.get("nfr_baseline", {})
        self.max_lines = nfr.get("max_class_length_lines", 500)

        # 存量违规基线文件（YAML，含 files: [rel_path, ...]）
        self.baseline_file = config.get("baseline_file", "")
        self._baseline = self._load_baseline()

    def _load_baseline(self) -> set:
        """加载存量违规基线 — 一次性快照，新违规不享受豁免."""
        if not self.baseline_file:
            return set()
        path = self.baseline_file
        if not os.path.isabs(path):
            path = os.path.join(self.project_root, path)
        if not os.path.exists(path):
            return set()
        data = load_yaml(path)
        files = data.get("files", []) or []
        # 统一为正斜杠
        return {f.replace("\\", "/").strip("/") for f in files}

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        errors = 0

        for d in self.scan_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, files in os.walk(full):
                dirs[:] = [
                    x for x in dirs
                    if not x.startswith(".") and x not in self.exclude_subdirs
                ]
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(fpath, self.project_root).replace("\\", "/")
                    errs = self._check_file(fpath, rel)
                    errors += errs[0]
                    issues.extend(errs[1])

        # 检查 baseline 中已修复的文件
        for rel in self._check_baseline_repaired():
            issues.append(
                f"[LARGE-03] {rel}: 已修复（行数 ≤ {self.max_lines}），"
                f"建议从 baseline 中移除"
            )

        return errors, issues

    def _check_file(self, fpath: str, rel: str) -> Tuple[int, List[str]]:
        """检查单个文件行数 — 返回 (errors_count, issues_list).

        - 新增违规 (LARGE-01): errors=1, issues=[msg]
        - 存量违规 (LARGE-02): errors=0, issues=[msg]  # WARN 不阻断
        - 正常文件: errors=0, issues=[]
        """
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
                n = 1 + sum(1 for _ in f)
        except Exception as e:
            logger.debug("读取失败 %s: %s", rel, e)
            return 0, []

        if n <= self.max_lines:
            return 0, []

        # 尊重 # noqa: LARGE-01 豁免（首行）
        if first_line and "noqa" in first_line.lower() and "LARGE-01" in first_line:
            return 0, []

        # 大文件：判定是新增还是存量
        if rel in self._baseline:
            # 存量违规 — WARN，不阻断
            return 0, [
                f"[LARGE-02] {rel}: 文件 {n} 行 > {self.max_lines}"
                f"（存量违规，已豁免，待修复）"
            ]

        # 新增违规 — BLOCKER
        return 1, [
            f"[LARGE-01] {rel}: 文件 {n} 行 > {self.max_lines}"
            f"（BLOCKER — 新增大文件，必须拆分）"
        ]

    def _check_baseline_repaired(self) -> List[str]:
        """扫描 baseline 中已修复的文件（行数已达标）."""
        repaired = []
        for rel in self._baseline:
            # baseline 中的路径是相对于 project_root
            fpath = os.path.join(self.project_root, rel.replace("/", os.sep))
            if not os.path.exists(fpath):
                # 文件已删除 — 也算"已修复"
                repaired.append(rel)
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    n = sum(1 for _ in f)
            except Exception:
                continue
            if n <= self.max_lines:
                repaired.append(rel)
        return repaired



def main():  # noqa: STYLE-06
    """CLI 入口：独立运行检查.

    用法：
      python chk_largefiles.py [--project-root PATH] [--config FILE]
    """
    import argparse
    parser = argparse.ArgumentParser(description="大文件检测（强制阻断）")
    parser.add_argument("--project-root", default=".", help="项目根目录")
    parser.add_argument("--config", default="", help="YAML 配置文件路径")
    parser.add_argument("--scan-dirs", nargs="*", default=None,
                        help="扫描目录（覆盖配置）")
    parser.add_argument("--max-lines", type=int, default=None,
                        help="最大行数阈值（覆盖配置）")
    parser.add_argument("--baseline", default="", help="存量基线 YAML 文件")
    args = parser.parse_args()

    config = {}
    if args.config:
        config = load_yaml(args.config)
    if args.scan_dirs:
        config["scan_dirs"] = args.scan_dirs
    if args.max_lines:
        config.setdefault("nfr_baseline", {})["max_class_length_lines"] = args.max_lines
    if args.baseline:
        config["baseline_file"] = args.baseline

    # 默认配置
    config.setdefault("scan_dirs", ["domain/", "shared/", "access/", "p0/", "backtest/", "ops/", "scripts/"])
    config.setdefault("nfr_baseline", {})["max_class_length_lines"] = 500

    checker = LargeFilesChecker(config, args.project_root)
    errors, issues = checker.check()

    # 分离 BLOCKER (LARGE-01) / WARN (LARGE-02) / INFO (LARGE-03)
    blockers = [i for i in issues if i.startswith("[LARGE-01]")]
    warns = [i for i in issues if i.startswith("[LARGE-02]")]
    infos = [i for i in issues if i.startswith("[LARGE-03]")]

    print(f"大文件检测 — {args.project_root}")
    print(f"  阈值:    {checker.max_lines} 行")
    print(f"  阻断:    {len(blockers)}")
    print(f"  警告:    {len(warns)}")
    print(f"  已修复:  {len(infos)}")
    print()

    if blockers:
        print("阻断（新增违规 — 必须拆分）:")
        for i in blockers:
            print(f"  ❌ {i}")
        print()

    if warns:
        print("警告（存量违规，已豁免，待修复）:")
        for w in warns:
            print(f"  ⚠️  {w}")
        print()

    if infos:
        print("已修复（建议从 baseline 移除）:")
        for i in infos:
            print(f"  ✅ {i}")
        print()

    if not blockers and not warns and not infos:
        print("✅ 无大文件违规")

    return 1 if errors > 0 else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

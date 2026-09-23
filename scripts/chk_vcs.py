#!/usr/bin/env python3
"""Checker: 版本控制治理（T29 盲区③）

规则：
  VCS-001 跟踪数与工作树严重脱节 — 脏改动/跟踪数 超过阈值，或磁盘文件数与
          跟踪数比例失衡（大量未跟踪文件）
  VCS-002 关键目录整体未入库     — 磁盘上存在且文件数 ≥N 的目录，git 跟踪数为 0

非 git 仓库时整体 skipped 并说明（不阻断）。
接口: check() -> (errors: int, issues: list[str])
"""
import os
import subprocess
from typing import List, Tuple


def _git(root: str, *args, timeout: int = 60):
    try:
        p = subprocess.run(["git", "-C", root] + list(args),
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return None
        return p.stdout
    except Exception:
        return None


def _count_files(path: str, limit: int = 200000) -> int:
    n = 0
    skip = {".git", ".venv", ".deps", "node_modules", "__pycache__", "site-packages"}
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in skip]
        n += len(filenames)
        if n > limit:
            break
    return n


class VcsGovernanceChecker:
    """版本控制治理"""

    CHECKER_ID = "vcs_governance"
    CHECKER_LABEL = "版本控制治理"

    def __init__(self, config: dict, project_root: str):
        self.config = config or {}
        self.project_root = os.path.abspath(project_root)
        self.max_dirty_ratio = float(self.config.get("max_dirty_ratio", 0.5))
        self.min_tracked = int(self.config.get("min_tracked", 50))
        self.critical_dirs = self.config.get("critical_dirs", []) or []
        self.critical_min_files = int(self.config.get("critical_min_files", 5))
        self.min_tracked_ratio = float(self.config.get("min_tracked_ratio", 0.5))

    def _is_repo(self) -> bool:
        top = _git(self.project_root, "rev-parse", "--show-toplevel")
        return bool(top and top.strip())

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        if not self._is_repo():
            return 0, [f"[VCS-000] {self.project_root} 不是 git 仓库 -> 版本控制治理检查跳过"
                       f"（这也意味着无版本历史可审计）"]

        ls = _git(self.project_root, "ls-files") or ""
        tracked = len([x for x in ls.splitlines() if x.strip()])
        st = _git(self.project_root, "status", "--porcelain") or ""
        dirty = len([x for x in st.splitlines() if x.strip()])

        # VCS-001 脱节
        if tracked < self.min_tracked:
            issues.append(
                f"[VCS-001] 仅 {tracked} 个文件被跟踪（阈值 {self.min_tracked}）"
                f" -> 仓库跟踪面过小，工作树与版本库严重脱节")
        if tracked > 0 and dirty / max(tracked, 1) > self.max_dirty_ratio:
            issues.append(
                f"[VCS-001] 脏改动 {dirty} 项 / 跟踪 {tracked} 文件 = "
                f"{dirty / tracked:.0%}（阈值 {self.max_dirty_ratio:.0%}）"
                f" -> 大量改动未提交，版本库不代表实际运行代码")

        # VCS-002 关键目录低跟踪率 / 0 入库
        for d in self.critical_dirs:
            full = os.path.join(self.project_root, d.rstrip("/\\"))
            if not os.path.isdir(full):
                continue
            n_disk = _count_files(full)
            if n_disk < self.critical_min_files:
                continue
            sub = _git(self.project_root, "ls-files", d.rstrip("/\\")) or ""
            n_tracked = len([x for x in sub.splitlines() if x.strip()])
            ratio = n_tracked / max(n_disk, 1)
            if n_tracked == 0:
                issues.append(
                    f"[VCS-002] 关键目录 '{d}' 磁盘上有 {n_disk} 个文件，但 git 跟踪数为 0 "
                    f"-> 整目录未入库，删除或迁移即永久丢失")
            elif ratio < self.min_tracked_ratio:
                issues.append(
                    f"[VCS-002] 关键目录 '{d}' 跟踪率仅 {n_tracked}/{n_disk} = {ratio:.1%}"
                    f"（阈值 {self.min_tracked_ratio:.0%}）-> 绝大部分内容未入库，"
                    f"版本库不代表该目录实际内容")
        return len(issues), issues

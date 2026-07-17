#!/usr/bin/env python3
"""Extracted: CodeDocSyncChecker"""
import os, re
from typing import List, Tuple
from chk_load_yaml import load_yaml


class CodeDocSyncChecker:
    """基于 doc-owned.yaml 映射，检测代码变更但文档未同步

    解决盲区：无反向追踪 — 声明了 1:1/N:1 映射但 CI 不检测
    "代码改了文档没改"的问题。
    """

    def __init__(self, config: dict, project_root: str, changed_files: List[str] = None):
        """
        初始化代码-文档同步检测器

        Args:
            config: review-rules.yaml 中 code_doc_sync 配置段
            project_root: 项目根目录
            changed_files: CI 环境中传入的变更文件列表（git diff）；
                          为 None 时使用文件修改时间比较
        """
        self.project_root = project_root
        self.changed_files = changed_files
        self.max_deduction = config.get("max_deduction", 10)
        self.per_issue = config.get("deduction_per_issue", 5)
        # V2.0-A++ 盲区4修复：变更时间差检测
        self.stale_threshold_hours = config.get("stale_threshold_hours", 24)
        # 加载 doc-owned.yaml 映射
        self.doc_owned = load_yaml(os.path.join(project_root, ".ai/config/doc-owned.yaml"))

    def check(self) -> Tuple[int, List[str]]:
        """
        检测所有映射的代码-文档同步状态

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0

        mappings = self.doc_owned.get("mappings", [])
        for mapping in mappings:
            # 仅检测 1:1 和 N:1 模式（有同步要求）
            mode = mapping.get("mode", "")
            if mode not in ("1:1", "N:1"):
                continue

            source = mapping.get("source", "")
            docs = mapping.get("docs", "")
            violation = mapping.get("violation", "warn")
            mid = mapping.get("id", "")

            source_path = os.path.join(self.project_root, source)
            docs_path = os.path.join(self.project_root, docs)

            # 检查源路径是否存在
            if not os.path.exists(source_path):
                continue

            if self.changed_files is not None:
                # CI 模式：基于 git diff 变更文件列表
                source_changed = self._is_path_in_changed(source, self.changed_files)
                docs_changed = self._is_path_in_changed(docs, self.changed_files)

                if source_changed and not docs_changed:
                    issues.append(
                        f"代码-文档未同步 [{mid}]: PR 修改了 {source}，" f"但未修改对应文档 {docs}（模式: {mode}）"
                    )
                    deduction = min(deduction + self.per_issue, self.max_deduction)
            else:
                # 本地模式：基于文件修改时间比较 + 时间差检测
                source_mtime = self._get_latest_mtime(source_path)
                docs_mtime = self._get_latest_mtime(docs_path) if os.path.exists(docs_path) else 0

                if source_mtime > docs_mtime and source_mtime > 0:
                    # V2.0-A++ 盲区4修复：区分"刚刚未同步"和"长期过期"
                    time_diff_hours = (source_mtime - docs_mtime) / 3600.0

                    if time_diff_hours > self.stale_threshold_hours:
                        # 超过阈值 → "文档可能过期"（更严重）
                        issues.append(
                            f"文档可能过期 [{mid}]: 源码 {source} 比文档 {docs} "
                            f"晚 {time_diff_hours:.1f} 小时 "
                            f"(超过 {self.stale_threshold_hours}h 阈值)"
                        )
                        deduction = min(deduction + self.per_issue, self.max_deduction)
                    else:
                        # 在阈值内 → "可能未同步"（较轻）
                        issues.append(
                            f"代码-文档可能未同步 [{mid}]: 源码 {source} 修改时间"
                            f"晚于文档 {docs} ({time_diff_hours:.1f}h)"
                        )
                        # 轻微问题，扣分减半
                        light_deduction = max(self.per_issue // 2, 1)
                        deduction = min(deduction + light_deduction, self.max_deduction)

        return deduction, issues

    def _is_path_in_changed(self, target_path: str, changed_files: List[str]) -> bool:
        """检查变更文件列表中是否有目标路径下的文件"""
        target_norm = target_path.replace("\\", "/").rstrip("/")
        for f in changed_files:
            f_norm = f.replace("\\", "/")
            if f_norm.startswith(target_norm):
                return True
        return False

    def _get_latest_mtime(self, path: str) -> float:
        """获取目录下文件的最新修改时间"""
        latest = 0.0

        if os.path.isfile(path):
            try:
                return os.path.getmtime(path)
            except OSError:
                return 0.0

        if not os.path.isdir(path):
            return 0.0

        for root, dirs, files in os.walk(path):
            # 跳过 __pycache__ 等
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                    if mtime > latest:
                        latest = mtime
                except OSError:
                    continue
        return latest

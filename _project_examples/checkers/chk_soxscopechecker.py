#!/usr/bin/env python3
"""Extracted: SOXScopeChecker"""
import re
from typing import List, Tuple


class SOXScopeChecker:
    """扩展 SOX 职责分离检测范围

    解决盲区：SOX 范围窄 — 只查 .ai/config/ vs src/，
    未覆盖 tests/、scripts/、.ai/schemas/ 等。

    检测规则:
      同一 PR 不允许同时修改以下任何组合:
      - .ai/config/ + src/     (规则 + 业务代码)
      - .ai/config/ + tests/   (规则 + 测试代码)
      - .ai/config/ + scripts/ (规则 + 脚本代码)
      - .ai/schemas/ + src/    (Schema + 业务代码)
      - .ai/schemas/ + tests/  (Schema + 测试代码)

    归属维度: code_doc_sync（从该维度扣分）
    """

    # 规则目录与代码目录的禁止组合
    FORBIDDEN_COMBOS = [
        (".ai/config/", "src/"),
        (".ai/config/", "tests/"),
        (".ai/config/", "scripts/"),
        (".ai/schemas/", "src/"),
        (".ai/schemas/", "tests/"),
    ]

    def __init__(self, config: dict, project_root: str, changed_files: List[str] = None):
        """
        初始化 SOX 范围检测器

        Args:
            config: review-rules.yaml 中 sox_scope_check 配置段
            project_root: 项目根目录
            changed_files: CI 模式下传入的变更文件列表
        """
        self.project_root = project_root
        self.changed_files = changed_files
        self.max_deduction = config.get("max_deduction", 5)
        self.per_issue = config.get("deduction_per_issue", 3)

    def check(self) -> Tuple[int, List[str]]:
        """
        检测 SOX 职责分离违规

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0

        if self.changed_files is not None:
            # CI 模式：基于变更文件列表
            changed = [f.replace("\\", "/") for f in self.changed_files]
        else:
            # 本地模式：基于 git status
            changed = self._get_git_changed_files()

        if not changed:
            return 0, []

        # 检查每个禁止组合
        for rule_dir, code_dir in self.FORBIDDEN_COMBOS:
            rule_changed = any(f.startswith(rule_dir) for f in changed)
            code_changed = any(f.startswith(code_dir) for f in changed)

            if rule_changed and code_changed:
                # 找出具体文件
                rule_files = [f for f in changed if f.startswith(rule_dir)][:3]
                code_files = [f for f in changed if f.startswith(code_dir)][:3]

                issues.append(
                    f"SOX 职责分离违反: 同一变更同时修改了 "
                    f"规则目录({rule_dir}: {', '.join(rule_files)}...) "
                    f"和代码目录({code_dir}: {', '.join(code_files)}...) "
                    f"— 规则制定者不得同时修改被规则约束的代码"
                )
                deduction = min(deduction + self.per_issue, self.max_deduction)

        return deduction, issues

    def _get_git_changed_files(self) -> List[str]:
        """获取 git 变更文件列表（本地模式）"""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=10,
            )
            if result.returncode == 0:
                return [f.strip() for f in result.stdout.split("\n") if f.strip()]
        except Exception:
            pass
        return []

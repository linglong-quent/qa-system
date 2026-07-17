#!/usr/bin/env python3
"""Checker: CLAUDE.md 合规验证器

CLAUDE.md 是 AI 编码助手的约束文件，定义了代码规范。
本 checker 验证实际生成的代码是否遵守 CLAUDE.md 中声明的规则。

两层验证:
  1. METADATA: CLAUDE.md 是否被项目引用（不读=等于没有）
  2. RULES: CLAUDE.md 中声称的禁止项是否被对应的 checker 实际覆盖

不检查代码本身（那是其他 checker 的工作）。
检查的是 CLAUDE.md → checker 映射关系的一致性。
"""
import os, re
from typing import List, Tuple


class ClaudeValidator:
    """CLAUDE.md 合规验证器"""

    CHECKER_ID = "claude-validator"
    CHECKER_LABEL = "CLAUDE.md 合规验证"

    # CLAUDE.md 规则与 QA checker 的映射
    # 如果 CLAUDE.md 禁止了某件事，必须有 checker 实际覆盖
    RULE_CHECKER_MAP = [
        ("禁止 inplace=True", "inplace_check"),
        ("禁止前视偏差 shift(-N)", "lookahead_check"),
        ("禁止硬编码密钥", "secret_check"),
        ("禁止魔法数字", "code_ban"),
        ("禁止 eval/exec", "code_ban"),
        ("禁止 iterrows", "plugin_quantspec_iterrows_checker"),
        ("类型注解", "未被 checker 覆盖 — 依赖 mypy"),
        ("异常处理 try/except", "code_ban"),
    ]

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0

        # 1. CLAUDE.md 是否存在
        claude_path = os.path.join(self.project_root, ".ai/prompts/CLAUDE.md")
        if not os.path.exists(claude_path):
            issues.append("[CLAUDE] ❌ CLAUDE.md 不存在 — AI 编码无约束")
            return 1, issues

        claude_content = open(claude_path, "r", encoding="utf-8").read()

        # 2. CLAUDE.md 有实质内容（非空模板）
        if len(claude_content.strip()) < 200:
            issues.append("[CLAUDE] ⚠️ CLAUDE.md 内容过短 — 可能未填写")
            errors += 1

        # 3. 读取上次 QA 报告，检查映射是否一致
        report_path = os.path.join(self.project_root, ".ai/logs/qa-report.json")
        active_checkers = set()
        if os.path.exists(report_path):
            import json
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)
                active_checkers = set(report.get("checkers", {}).keys())
            except Exception:
                pass

        for rule_name, expected_checker in self.RULE_CHECKER_MAP:
            # 检查 CLAUDE.md 是否提及此规则
            rule_in_claude = rule_name.lower() in claude_content.lower()
            checker_active = expected_checker in active_checkers

            if rule_in_claude and not checker_active:
                issues.append(
                    f"[CLAUDE] ⚠️ CLAUDE.md 禁止了「{rule_name}」"
                    f"但对应 checker ({expected_checker}) 未在运行"
                )
                errors += 1

        # 4. 检查 CLAUDE.md 头部是否有明确的 AI 指令标记
        has_header = any(
            marker in claude_content[:500]
            for marker in ["# ", "编码规范", "System Prompt", "你必须", "禁止"]
        )
        if not has_header:
            issues.append("[CLAUDE] ⚠️ CLAUDE.md 缺少明确的 AI 指令头部")
            errors += 1

        if errors == 0:
            issues.append("[CLAUDE] ✅ CLAUDE.md 合规 — 规则与 checker 一致")

        return errors, issues

#!/usr/bin/env python3
"""Extracted: DocDebtRatioChecker"""
import os, re
from pathlib import Path
from chk_load_yaml import load_yaml


class DocDebtRatioChecker:
    """文档债务比率检测器 — V2.1 新增

    对齐 SQALE 方法的文档债务维度。
    检测逻辑：
    1. 检查 tech-debt.yaml 中的文档债务条目
    2. 分析 TODO/FIXME/HACK 注释中与文档相关的部分
    3. 计算文档债务修复工时 vs 文档总价值估计

    输出 metrics:
    - doc_debt_items: 登记在册的文档债务条目数
    - doc_debt_hours: 估计修复总工时
    - doc_debt_status: 债务状态（none / tracking / growing）
    """

    def __init__(self, config: dict, project_root: str):
        self.config = config
        self.project_root = project_root

    def check(self) -> tuple:
        """检查文档债务比率

        Returns:
            (deduction, issues): (总扣分, 问题列表)
        """
        deduction = 0
        issues = []

        # 1. 检查 tech-debt.yaml 是否存在以及是否包含文档债务条目
        tech_debt_path = os.path.join(self.project_root, ".ai/config/tech-debt.yaml")
        if not os.path.isfile(tech_debt_path):
            deduction += 2
            issues.append("[DocDebt] tech-debt.yaml 不存在，文档债务未跟踪")
            return deduction, issues

        try:
            tech_debt = load_yaml(tech_debt_path)
        except Exception:
            deduction += 2
            issues.append("[DocDebt] tech-debt.yaml 解析失败")
            return deduction, issues

        # 2. 检查文档债务条目覆盖率
        doc_items = tech_debt.get("doc_debt_items", [])
        if not doc_items:
            deduction += 2
            issues.append("[DocDebt] tech-debt.yaml 中没有文档债务条目")

        # 3. 检查 HIGH 利息的文档债务是否有负责人
        high_no_owner = 0
        for item in doc_items:
            if item.get("interest", "").upper() in ("HIGH", "CRITICAL"):
                if not item.get("owner"):
                    high_no_owner += 1

        if high_no_owner > 0:
            deduction += min(high_no_owner, 3)
            issues.append(f"[DocDebt] {high_no_owner} 个 HIGH/CRITICAL 文档债务缺少负责人")

        # 4. 扫描 TODO/FIXME 中的文档标记
        todo_doc_count = 0
        for root_dir in ["src", "scripts", ".ai"]:
            root_path = os.path.join(self.project_root, root_dir)
            if os.path.isdir(root_path):
                for py_file in Path(root_path).rglob("*.py"):
                    if not py_file.is_file():
                        continue
                    try:
                        text = py_file.read_text(encoding="utf-8")
                        for line in text.splitlines():
                            if re.search(r"TODO.*(doc|document|comment|readme|changelog)", line, re.IGNORECASE):
                                todo_doc_count += 1
                    except (OSError, UnicodeDecodeError):
                        continue

        if todo_doc_count > 5:
            deduction += 1
            issues.append(f"[DocDebt] 代码中存在 {todo_doc_count} 处 TODO 标记文档缺失")

        deduction = min(deduction, self.config.get("max_deduction", 5))
        return deduction, issues

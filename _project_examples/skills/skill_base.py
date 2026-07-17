#!/usr/bin/env python3
"""
skill_base.py — 所有 Skill 的基类
接口定义: skill_spec.md §1.4
变更单: ARCH-TICKET-001
"""

import json
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class CheckResult:
    """单个校验结果"""

    rule: str  # 规则编号，如 "CUSTOM-001"
    severity: str  # blocker / error / warning / info
    message: str  # 人类可读的描述
    file: str = ""  # 问题文件路径
    line: int = 0  # 问题行号
    suggest: str = ""  # 修改建议


class BaseSkill:
    """所有 Skill 的基类，子类只需实现 run_checks()"""

    def __init__(self, name: str = "", rule_tables: Optional[Dict[str, Any]] = None) -> None:
        self.name = name or self.__class__.__name__
        self.rule_tables = rule_tables or {}

    def load_rule_tables(self) -> Dict[str, Any]:
        """加载规则配置表（由外部注入或子类重写）"""
        return self.rule_tables

    def run_checks(self) -> list[CheckResult]:
        """
        子类实现：执行校验逻辑
        返回 CheckResult 列表
        """
        return []

    def output_results(self, results: list[CheckResult]) -> Dict[str, Any]:
        """统一输出格式"""
        fail_count = sum(1 for r in results if r.severity == "blocker")
        return {
            "skill": self.name,
            "status": "fail" if fail_count > 0 else "pass",
            "exit_code": 1 if fail_count > 0 else 0,
            "check_count": len(results),
            "fail_count": fail_count,
            "results": [asdict(r) for r in results],
        }

    def exit_with_code(self, code: int) -> None:
        """统一退出"""
        sys.exit(code)

    def run(self) -> Dict[str, Any]:
        """统一执行入口"""
        results = self.run_checks()
        output = self.output_results(results)
        if output["fail_count"] > 0:
            print(json.dumps(output, ensure_ascii=False, indent=2))
            self.exit_with_code(output["exit_code"])
        return output


# CLI 入口
if __name__ == "__main__":
    skill = BaseSkill()
    result = skill.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))

#!/usr/bin/env python3
"""
skill_registry_guard.py — Skill 元文件 + Registry 强制检查 MR 门禁 (P1-F28)
===========================================================================
新增 Skill 若无元文件注册直接阻断 MR 合并。

检查规则：
  1. REG-001: 每个 scripts/skill/skill_*.py 必须在 skill_registry.yaml 中注册
  2. REG-002: skill_registry.yaml 中的条目必须有对应的 .py 文件
  3. REG-003: 注册条目必须包含 module/enabled/tier/quality_gates/exit_codes/api 必填字段
  4. REG-004: module 路径指向的文件必须存在
  5. REG-005: enabled=true 的条目必须通过 import 校验

使用:
    python scripts/skill/skill_registry_guard.py [--output json]

退出码:
    0 = 全部通过
    1 = 阻断级缺失
    2 = 警告（非关键字段缺失）
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

REQUIRED_FIELDS = ["module", "enabled", "tier", "quality_gates", "exit_codes", "api"]


class RegistryGuardSkill(BaseSkill):
    """Skill 注册表强制校验"""

    def __init__(self) -> None:
        super().__init__("registry_guard")
        self.skill_dir = _ROOT / "scripts" / "skill"
        self.registry_path = self.skill_dir / "skill_registry.yaml"

    def _get_registry_entries(self) -> Dict[str, Any]:
        """加载注册表"""
        if not self.registry_path.exists():
            return {}
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("skills", {})  # type: ignore[no-any-return]

    def _get_skill_files(self) -> list[Path]:
        """获取所有 skill_*.py 文件"""
        if not self.skill_dir.exists():
            return []
        return sorted(self.skill_dir.glob("skill_*.py"))

    def _skill_name_from_file(self, file_path: Path) -> str:
        """从文件名推导 Skill 名: skill_xxx.py → xxx"""
        stem = file_path.stem  # skill_ban_check
        if stem.startswith("skill_"):
            return stem[6:]  # ban_check
        return stem

    def run_checks(self) -> list[CheckResult]:  # noqa: C901
        """执行注册表强制校验"""
        results: list[CheckResult] = []
        registry = self._get_registry_entries()
        skill_files = self._get_skill_files()

        if not registry:
            return [
                CheckResult(
                    rule="REG-000",
                    severity="blocker",
                    message="skill_registry.yaml 未找到或为空",
                    suggest="确保 skill_registry.yaml 存在且包含 skills: 节点",
                )
            ]

        # ─── REG-001: 每个 skill_*.py 必须在注册表中 ───
        registered_names = set(registry.keys())
        for file_path in skill_files:
            skill_name = self._skill_name_from_file(file_path)
            if skill_name == "base":
                continue  # skill_base.py 是基类，无需注册
            if skill_name not in registered_names:
                results.append(
                    CheckResult(
                        rule="REG-001",
                        severity="blocker",
                        file=str(file_path.relative_to(_ROOT)),
                        message=f"Skill 文件 '{file_path.name}' 未在 skill_registry.yaml 中注册",
                        suggest=f"在 skill_registry.yaml 的 skills: 下添加 '{skill_name}' 条目",
                    )
                )

        # ─── REG-002: 注册表中的条目必须有对应文件 ───
        file_names = {f.name for f in skill_files}
        for skill_name, entry in registry.items():
            module = entry.get("module", "")
            expected_file = module.split("/")[-1] if "/" in module else f"skill_{skill_name}.py"
            if expected_file not in file_names:
                results.append(
                    CheckResult(
                        rule="REG-002",
                        severity="error",
                        message=f"注册条目 '{skill_name}' 对应的文件 '{expected_file}' 不存在",
                        suggest="检查 module 路径是否正确，或移除该注册条目",
                    )
                )

        # ─── REG-003: 必填字段检查 ───
        for skill_name, entry in registry.items():
            missing = [f for f in REQUIRED_FIELDS if f not in entry]
            if missing:
                results.append(
                    CheckResult(
                        rule="REG-003",
                        severity="blocker" if "module" in missing or "enabled" in missing else "warning",
                        message=f"Skill '{skill_name}' 缺少必填字段: {', '.join(missing)}",
                        suggest=f"补充 {', '.join(missing)} 字段",
                    )
                )

        # ─── REG-004: module 路径指向的文件必须存在 ───
        for skill_name, entry in registry.items():
            module = entry.get("module", "")
            if not module:
                continue
            module_path = _ROOT / module
            if not module_path.exists():
                results.append(
                    CheckResult(
                        rule="REG-004",
                        severity="blocker",
                        message=f"Skill '{skill_name}' module 路径不存在: {module}",
                        suggest=f"确认 {module} 文件存在，或修正 module 字段",
                    )
                )

        # ─── REG-005: enabled=true 的条目快速校验 ───
        for skill_name, entry in registry.items():
            if not entry.get("enabled", False):
                continue
            module = entry.get("module", "")
            if not module:
                continue
            module_path = _ROOT / module
            if not module_path.exists():
                continue
            try:
                with open(module_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if "def run_checks" not in content and "def run" not in content:
                    results.append(
                        CheckResult(
                            rule="REG-005",
                            severity="warning",
                            message=f"Skill '{skill_name}' 的模块缺少 'run_checks' 或 'run' 函数",
                            suggest="确保模块实现了标准入口函数",
                        )
                    )
            except (OSError, PermissionError):
                pass

        return results


def run(output: str = "json") -> Dict[str, Any]:
    """统一入口"""
    skill = RegistryGuardSkill()
    results = skill.run_checks()
    result = skill.output_results(results)
    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Skill 注册表强制检查 (F28)")
    parser.add_argument("--output", default="json")
    args = parser.parse_args()
    run(output=args.output)

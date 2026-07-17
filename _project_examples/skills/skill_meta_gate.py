#!/usr/bin/env python3
"""
skill_meta_gate.py — Skill 元文件 + Registry 强制检查 (P1-F28)
============================================================
MR 门禁校验脚本：新增 Skill 时校验必须有 SKILL.md 元文件且在 skill_registry.yaml 注册。

校验规则:
  1. 每个 skill_*.py 必须在 scripts/skill/ 目录有对应 SKILL.md
  2. 每个 SKILL.md 对应的 .py 必须已在 skill_registry.yaml 注册
  3. skill_registry.yaml 中已注册的模块文件必须存在
  4. 三者一致性校验：不允许孤立的任意一端

使用:
    python scripts/skill/skill_meta_gate.py [--base <branch>]

退出码:
    0 = 全部通过
    1 = 阻断（Skill 缺失元文件或未注册）
    2 = 警告
    3 = 执行错误

兼容: 可直接作为 pre-commit hook 或 CI script 运行

变更单: ARCH-TICKET-010
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

_SKILL_DIR = _ROOT / "scripts" / "skill"
_REGISTRY_PATH = _SKILL_DIR / "skill_registry.yaml"


class SkillMetaGate(BaseSkill):
    """MR 门禁：Skill 元文件 + Registry 一致性校验"""

    def __init__(self) -> None:
        super().__init__("meta_gate")

    def _load_registry(self) -> Dict[str, Any]:
        """加载 skill_registry.yaml"""
        try:
            import yaml

            if not _REGISTRY_PATH.exists():
                return {"skills": {}}
            with open(_REGISTRY_PATH, encoding="utf-8") as f:
                return yaml.safe_load(f) or {"skills": {}}
        except Exception:
            return {"skills": {}}

    def _find_skill_py_files(self) -> set[str]:
        """扫描 skill_*.py 文件"""
        py_files = set()
        for f in _SKILL_DIR.glob("skill_*.py"):
            if f.name == "skill_base.py":
                continue  # 基类不算
            py_files.add(f.stem)  # 去掉 .py，如 skill_lint_all
        return py_files

    def _find_skill_md_files(self) -> set[str]:
        """扫描 SKILL.md 文件"""
        md_files = set()
        for f in _SKILL_DIR.glob("SKILL.md"):
            md_files.add("SKILL.md")
        # 也在子目录扫描 SKILL.md
        for d in _SKILL_DIR.iterdir():
            if d.is_dir():
                md_path = d / "SKILL.md"
                if md_path.exists():
                    md_files.add(f"{d.name}/SKILL.md")
        return md_files

    def run_checks(self) -> list[CheckResult]:  # noqa: C901
        results: list[CheckResult] = []
        registry = self._load_registry()
        registered_skills = set(registry.get("skills", {}).keys())

        py_files = self._find_skill_py_files()
        md_files = self._find_skill_md_files()

        # ── 规则 G28-001: 每个 skill_*.py 必须有对应 SKILL.md ──
        for py_name in sorted(py_files):
            # SKILL.md 可以放在平级目录或专用子目录
            has_md = False
            # 平级：scripts/skill/SKILL.md
            if "SKILL.md" in md_files:
                has_md = True
            # 子目录：scripts/skill/<name>/SKILL.md
            for md in md_files:
                if md.startswith(py_name.replace("skill_", "")):
                    has_md = True
                    break
            if not has_md:
                results.append(
                    CheckResult(
                        rule="G28-001",
                        severity="blocker",
                        message=f"Skill 缺失 SKILL.md 元文件: {py_name}.py",
                        file=str(_SKILL_DIR / f"{py_name}.py"),
                        suggest=f"在 {_SKILL_DIR} 创建 SKILL.md 或在 {_SKILL_DIR / py_name.replace('skill_', '')} 子目录创建",
                    )
                )

        # ── 规则 G28-002: 每个 skill_*.py 必须在 registry 注册 ──
        for py_name in sorted(py_files):
            if py_name not in registered_skills:
                results.append(
                    CheckResult(
                        rule="G28-002",
                        severity="blocker",
                        message=f"Skill 未在 skill_registry.yaml 注册: {py_name}",
                        file=str(_SKILL_DIR / f"{py_name}.py"),
                        suggest=f"在 skill_registry.yaml 的 skills 下添加 {py_name} 条目",
                    )
                )

        # ── 规则 G28-003: registry 中已注册的模块文件必须存在 ──
        for skill_name in sorted(registered_skills):
            entry = registry["skills"]
            module = entry.get("module", "")
            if not module:
                results.append(
                    CheckResult(
                        rule="G28-003",
                        severity="blocker",
                        message=f"Skill {skill_name}: registry 条目缺少 module 字段",
                        file=str(_REGISTRY_PATH),
                        suggest="补充 module 字段指向实际 .py 文件",
                    )
                )
                continue

            # 解析 module 路径（registry 中 module 路径相对于 linglong 包根）
            module_name = module.replace("/", ".").replace(".py", "")  # noqa: F841
            module_path = Path(module)
            abs_module_path = _ROOT / module_path
            if not abs_module_path.exists():
                results.append(
                    CheckResult(
                        rule="G28-003",
                        severity="blocker",
                        message=f"Skill {skill_name}: 注册的模块文件不存在: {module}",
                        file=str(_REGISTRY_PATH),
                        suggest=f"确认 {abs_module_path} 存在或修正 registry 中的 module 字段",
                    )
                )

        # ── 规则 G28-004: registry 中已注册但无对应 .py 的 Skill ──
        for skill_name in sorted(registered_skills):
            py_name = f"skill_{skill_name}"
            if py_name not in py_files:
                entry = registry["skills"]
                module = entry.get("module", "")
                # 检查 module 路径指向的文件是否存在
                abs_module_path = _ROOT / Path(module) if module else None  # type: ignore[assignment]
                if abs_module_path and abs_module_path.exists():
                    continue  # module 存在但命名不同（兼容）
                if entry.get("enabled", True):
                    results.append(
                        CheckResult(
                            rule="G28-004",
                            severity="warning",
                            message=f"Skill {skill_name}: registry 已注册但 skill_{skill_name}.py 不存在",
                            file=str(_REGISTRY_PATH),
                            suggest=f"创建 skill_{skill_name}.py 或将 registry 中的 enabled 改为 false",
                        )
                    )

        # ── 规则 G28-005: registry YAML 语法校验 ──
        try:
            import yaml

            with open(_REGISTRY_PATH, encoding="utf-8") as f:
                yaml.safe_load(f)
        except Exception as e:
            results.append(
                CheckResult(
                    rule="G28-005",
                    severity="blocker",
                    message=f"skill_registry.yaml 语法错误: {e}",
                    file=str(_REGISTRY_PATH),
                    suggest="修复 YAML 语法",
                )
            )

        return results


def run(output: str = "json", base: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """
    统一入口函数。

    Args:
        output: 输出格式 (json)
        base: 对比基准分支（可选，git diff 用）

    Returns:
        结构化结果 dict
    """
    skill = SkillMetaGate()
    results = skill.run_checks()
    result = skill.output_results(results)
    result["skill"] = "meta_gate"

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Skill 元文件 + Registry 门禁校验 (F28)")
    parser.add_argument("--output", default="json")
    parser.add_argument("--base", default=None, help="对比基准分支")
    args = parser.parse_args()
    sys.exit(run(output=args.output, base=args.base).get("exit_code", 0))

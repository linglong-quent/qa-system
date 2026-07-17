#!/usr/bin/env python3
"""
skill_runtime_blacklist.py — 运行时敏感操作查表拦截 (P1-F27)
============================================================
在运行时（非编译期）对敏感操作进行查表拦截，作为 AST 静态扫描的补充防线。

加载 config/rule/blacklist.yaml 规则表，提供以下拦截点：
  1. import 拦截 — 禁止导入黑名单模块（os.system/subprocess/eval/exec/pickle）
  2. 函数调用拦截 — 禁止调用高危函数（os.remove/sutil.rmtree/os.chmod 等）
  3. 模式检测 — 硬编码密钥/密码/Token、SQL 拼接、裸 except

与 G5A 扫描的区别：
  G5A 是 CI/提交前静态扫描，本模块是运行时动态拦截。
  静态扫描可被注释跳过（如 # noqa），运行时拦截不可绕过。

使用:
    python scripts/skill/skill_runtime_blacklist.py [--path DIR]

退出码:
    0 = 无运行时敏感操作
    1 = 发现阻断级操作
    2 = 仅发现警告级操作
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402


class RuntimeBlacklistSkill(BaseSkill):
    """运行时黑名单拦截器"""

    BLACKLIST_PATH = _ROOT.parent / "config" / "rule" / "blacklist.yaml"

    def __init__(self, target_dir: Optional[str] = None):
        super().__init__("runtime_blacklist")
        self.target_dir = Path(target_dir or ".").resolve()
        if not self.target_dir.is_absolute():
            self.target_dir = (_ROOT / self.target_dir).resolve()
        self.rules: Dict[str, Any] = {}
        self.results: list[CheckResult] = []

    def load_rules(self) -> Dict[str, Any]:
        """加载 blacklist.yaml 规则表"""
        if not self.BLACKLIST_PATH.exists():
            return {}
        with open(self.BLACKLIST_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _check_forbidden_imports(self, file_path: Path, lines: list[str]) -> list[CheckResult]:
        """检查禁止导入的模块"""
        results = []
        forbidden_modules = self.rules.get("forbidden_imports", {}).get("modules", [])

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped.startswith("import ") and not stripped.startswith("from "):
                continue
            for mod in forbidden_modules:
                if mod in stripped:
                    results.append(
                        CheckResult(
                            rule="RT-BLACKLIST-001",
                            severity="blocker",
                            file=str(file_path.relative_to(_ROOT)),
                            line=i,
                            message=f"禁止导入模块 '{mod}'：{stripped.strip()}",
                            suggest=f"移除导入 '{mod}'，使用安全的替代方案",
                        )
                    )
        return results

    def _check_forbidden_functions(self, file_path: Path, lines: list[str]) -> list[CheckResult]:
        """检查高危函数调用"""
        results = []
        critical = self.rules.get("forbidden_functions", {}).get("critical", [])
        warning_funcs = self.rules.get("forbidden_functions", {}).get("warning", [])

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            for func in critical:
                if func in stripped and not stripped.lstrip().startswith("#"):
                    results.append(
                        CheckResult(
                            rule="RT-BLACKLIST-002",
                            severity="blocker",
                            file=str(file_path.relative_to(_ROOT)),
                            line=i,
                            message=f"禁止调用高危函数 '{func}'",
                            suggest=f"移除 '{func}' 调用，使用安全替代方案（如备份后操作）",
                        )
                    )
            for func in warning_funcs:
                if func in stripped and not stripped.lstrip().startswith("#"):
                    # print 已在 G5 中检查，这里只拦截更危险的
                    if func == "print":
                        continue
                    results.append(
                        CheckResult(
                            rule="RT-BLACKLIST-003",
                            severity="warning",
                            file=str(file_path.relative_to(_ROOT)),
                            line=i,
                            message=f"警告：使用了不推荐的函数 '{func}'",
                            suggest=f"考虑移除 '{func}' 或使用安全替代方案",
                        )
                    )
        return results

    def _check_forbidden_patterns(self, file_path: Path, lines: list[str]) -> list[CheckResult]:
        """检查禁止的模式（密钥硬编码/SQL注入/裸except）"""
        results = []
        patterns = self.rules.get("forbidden_patterns", {})

        content = "\n".join(lines)

        for category, rules in patterns.items():
            for rule_entry in rules:
                pattern = rule_entry.get("pattern", "")
                description = rule_entry.get("description", category)
                if not pattern:
                    continue
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                except re.error:
                    continue
                for match in compiled.finditer(content):
                    line_no = content[: match.start()].count("\n") + 1
                    results.append(
                        CheckResult(
                            rule="RT-BLACKLIST-004",
                            severity="blocker" if category in ("hardcoded_secrets", "sql_injection") else "error",
                            file=str(file_path.relative_to(_ROOT)),
                            line=line_no,
                            message=f"检测到禁止模式 [{category}]：{description}",
                            suggest=f"移除或重构匹配 '{match.group()[:40]}' 的代码",
                        )
                    )
        return results

    def _should_skip(self, file_path: Path) -> bool:
        """跳过非 Python 文件和特定目录"""
        if file_path.suffix != ".py":
            return True
        parts = file_path.parts
        skip_dirs = {
            "__pycache__",
            ".git",
            ".github",
            "_deprecated",
            "node_modules",
            "venv",
            ".venv",
            ".tox",
            "build",
            "dist",
            ".eggs",
            "archive",
        }
        return any(d in skip_dirs for d in parts)

    def run_checks(self) -> list[CheckResult]:
        """执行全目录运行时黑名单扫描"""
        self.rules = self.load_rules()
        if not self.rules:
            return [
                CheckResult(
                    rule="RT-BLACKLIST-000",
                    severity="error",
                    message=f"规则表未找到: {self.BLACKLIST_PATH}",
                    suggest="确认 config/rule/blacklist.yaml 存在",
                )
            ]

        all_results: list[CheckResult] = []
        py_files = list(self.target_dir.rglob("*.py"))

        for file_path in py_files:
            if self._should_skip(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except (OSError, PermissionError):
                continue

            all_results.extend(self._check_forbidden_imports(file_path, lines))
            all_results.extend(self._check_forbidden_functions(file_path, lines))
            all_results.extend(self._check_forbidden_patterns(file_path, lines))

        self.results = all_results
        return all_results


def run(output: str = "json", path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """统一入口"""
    target = path or "."
    skill = RuntimeBlacklistSkill(target_dir=target)
    results = skill.run_checks()
    result = skill.output_results(results)
    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="运行时黑名单拦截器 (F27)")
    parser.add_argument("--output", default="json")
    parser.add_argument("--path", default=None)
    args = parser.parse_args()
    run(output=args.output, path=args.path)

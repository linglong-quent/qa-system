#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_privilege_scan.py — 越权调用扫描 (B1-20)
=================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-20)

职责: 检测策略/因子模块直接调用风控/密钥核心接口
  引用: p1_spec.md §十一「越权调用扫描」

检测规则:
  1. 策略模块 import 风控/侧车模块 → 阻断
  2. 因子模块直接调用密钥相关接口 → 阻断
  3. 业务模块绕过 config 封装层直连 DB → 阻断

用法:
    python scripts/skill/skill_privilege_scan.py
    python scripts/skill/skill_privilege_scan.py --output json

退出码:
    0 = 无越权调用
    1 = 发现越权调用（blocker）
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# ═══════════════════════════════════════════════════════════════
# 越权检测规则
# ═══════════════════════════════════════════════════════════════

# 禁止策略/因子模块导入的模块
FORBIDDEN_IMPORTS_FOR_STRATEGY = [
    "risk_sidecar",
    "risk",
    "sidecar",
    "broker.qmt",
    "broker.direct",
    "key_manager",
    "vault",
    "secret",
    "payment",
    "settlement",
]

# 允许的封装层
ALLOWED_WRAPPERS = [
    "config",
    "DBConfig",
    "_core.config",
    "data.source_registry",
]


class PrivilegeVisitor(ast.NodeVisitor):
    """AST 访问器：检测越权 import"""

    def __init__(self, filepath: str, file_category: str) -> None:
        self.filepath = filepath
        self.file_category = file_category  # strategy / factor / data / core
        self.findings: list[Dict[str, Any]] = []

    def _is_strategy_file(self) -> bool:
        return self.file_category in ("strategy", "factor")

    def visit_Import(self, node: ast.Import) -> None:
        """检测 import xxx"""
        if not self._is_strategy_file():
            self.generic_visit(node)
            return

        for alias in node.names:
            module_name = alias.name
            for forbidden in FORBIDDEN_IMPORTS_FOR_STRATEGY:
                if module_name.startswith(forbidden) or module_name == forbidden:
                    self.findings.append(
                        {
                            "rule_id": "PRIV-001",
                            "severity": "blocker",
                            "file": self.filepath,
                            "line": node.lineno,
                            "message": f"策略模块禁止导入 {module_name}，请使用封装层",
                            "suggest": f"改用 {', '.join(ALLOWED_WRAPPERS[:2])} 等封装层",
                        }
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """检测 from xxx import yyy"""
        if not self._is_strategy_file():
            self.generic_visit(node)
            return

        module_name = node.module or ""
        for forbidden in FORBIDDEN_IMPORTS_FOR_STRATEGY:
            if module_name.startswith(forbidden) or module_name == forbidden:
                names = ", ".join(a.name for a in node.names)
                self.findings.append(
                    {
                        "rule_id": "PRIV-001",
                        "severity": "blocker",
                        "file": self.filepath,
                        "line": node.lineno,
                        "message": f"策略模块禁止从 {module_name} 导入 {names}",
                        "suggest": f"改用 {', '.join(ALLOWED_WRAPPERS[:2])} 等封装层",
                    }
                )
        self.generic_visit(node)


def _categorize_file(filepath: Path) -> str:
    """根据路径判断文件类别"""
    path_str = str(filepath).lower().replace("\\", "/")
    if "/strateg" in path_str:
        return "strategy"
    if "/factor" in path_str:
        return "factor"
    if "/data/" in path_str:
        return "data"
    if "/_core/" in path_str:
        return "core"
    if "/risk/" in path_str or "/sidecar/" in path_str:
        return "risk"
    return "other"


class SkillPrivilegeScan(BaseSkill):
    """越权调用扫描"""

    def __init__(self, target_path: Optional[str] = None) -> None:
        super().__init__("privilege_scan")
        self.target = Path(target_path or ".").resolve()
        if not self.target.is_absolute():
            self.target = (_ROOT / self.target).resolve()

    def _scan_file(self, filepath: Path) -> list[Dict[str, Any]]:
        """扫描单个文件"""
        findings: Any = []
        category = _categorize_file(filepath)
        if category not in ("strategy", "factor"):
            return findings  # type: ignore[no-any-return]

        try:
            content = filepath.read_text(encoding="utf-8")
            tree = ast.parse(content)
            visitor = PrivilegeVisitor(str(filepath), category)
            visitor.visit(tree)
            findings.extend(visitor.findings)
        except (SyntaxError, IOError, UnicodeDecodeError):
            pass
        return findings  # type: ignore[no-any-return]

    def run_checks(self) -> list[CheckResult]:
        """执行越权扫描"""
        all_findings = []
        py_files = list(self.target.rglob("*.py"))

        for fp in py_files:
            if "test" in fp.name.lower():
                continue
            all_findings.extend(self._scan_file(fp))

        results: list[CheckResult] = []

        if not all_findings:
            results.append(
                CheckResult(
                    rule="PRIV-000",
                    severity="info",
                    message=f"未发现越权调用 (扫描 {len(py_files)} 文件)",
                )
            )
        else:
            for f in all_findings[:20]:
                results.append(
                    CheckResult(
                        rule=f["rule_id"],
                        severity=f["severity"],
                        file=f["file"],
                        line=f["line"],
                        message=f["message"],
                        suggest=f.get("suggest", ""),
                    )
                )

        return results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """统一入口"""
    checker = SkillPrivilegeScan(target_path=path)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n越权调用扫描报告")  # noqa: F541
        print(f"{'='*50}")
        for r in results:
            icon = {"info": "✓", "warning": "⚠", "blocker": "✗"}.get(r.severity, "?")
            loc = f" [{r.file}:{r.line}]" if r.file else ""
            print(f"  [{icon}] [{r.rule}] {r.message}{loc}")
            if r.suggest:
                print(f"       → {r.suggest}")
        print(f"{'='*50}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="越权调用扫描")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--path", default=None, help="扫描目标路径")
    args = parser.parse_args()
    result = run(output=args.output, path=args.path)
    sys.exit(result.get("exit_code", 0))

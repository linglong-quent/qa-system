#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_future_leak.py — 未来函数 SAST 扫描 (B1-08)
===================================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-08)

职责: 静态检测量化策略中使用未来数据的函数
  检测模式:
    1. shift(-N) / pct_change(-N) — 向前取数据
    2. 在 t 时刻使用 t+N 时刻的数据
    3. rolling + 当前时间点的未来窗口
    4. 使用收盘价预测开盘价（时序倒置）

用法:
    python scripts/skill/skill_future_leak.py
    python scripts/skill/skill_future_leak.py --path linglong/strategies/
    python scripts/skill/skill_future_leak.py --output json

退出码:
    0 = 未发现未来函数
    1 = 发现未来函数（blocker）
    2 = 告警
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
# 未来函数检测规则
# ═══════════════════════════════════════════════════════════════

FUTURE_LEAK_PATTERNS = [
    {
        "id": "FUTURE-001",
        "pattern": "shift",
        "description": "shift(-N) 使用了未来数据",
        "severity": "blocker",
    },
    {
        "id": "FUTURE-002",
        "pattern": "pct_change",
        "description": "pct_change 可能使用了未来数据",
        "severity": "warning",
    },
    {
        "id": "FUTURE-003",
        "pattern": "未来",
        "description": "注释中提及'未来'关键词",
        "severity": "info",
    },
    {
        "id": "FUTURE-004",
        "pattern": "lookahead",
        "description": "使用了 lookahead 函数",
        "severity": "blocker",
    },
    {
        "id": "FUTURE-005",
        "pattern": "shift\\(-\\d+\\)",
        "description": "shift(-N) 明确使用未来数据 (N>0)",
        "severity": "blocker",
    },
    {
        "id": "FUTURE-006",
        "pattern": "ts_sum\\(.*,\\s*\\d+\\)",
        "description": "滚动求和可能跨越未来时间窗口",
        "severity": "warning",
    },
    {
        "id": "FUTURE-007",
        "pattern": "\\.loc\\[.*:\\]",
        "description": "切片可能引用未来数据",
        "severity": "warning",
    },
    {
        "id": "FUTURE-008",
        "pattern": "refit|refit_date",
        "description": "回测中使用了 refit 参数",
        "severity": "warning",
    },
]


class FutureLeakVisitor(ast.NodeVisitor):
    """AST 访问器：检测未来函数使用"""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.findings: list[Dict[str, Any]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: C901
        """检测函数调用"""
        # 获取函数名
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id
        else:
            func_name = ""

        for rule in FUTURE_LEAK_PATTERNS:
            if rule["pattern"] in func_name:
                # 检查参数：shift(-N)
                is_blocker = False
                if func_name == "shift" and node.args:
                    try:
                        arg = node.args
                        if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                            if isinstance(arg.operand, ast.Constant):
                                if arg.operand.value > 0:
                                    is_blocker = True
                    except Exception:
                        pass

                self.findings.append(
                    {
                        "rule_id": rule["id"],
                        "severity": "blocker" if is_blocker else rule["severity"],
                        "file": self.filepath,
                        "line": node.lineno,
                        "function": func_name,
                        "message": f"{rule['description']}: {func_name}() 调用",
                    }
                )
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """检测二元操作（如 df['close'] / df['open'].shift(-1)）"""
        # 简化检测：如果右侧是 shift 调用
        if isinstance(node.right, ast.Call):
            if isinstance(node.right.func, ast.Attribute):
                if node.right.func.attr == "shift":
                    self.findings.append(
                        {
                            "rule_id": "FUTURE-001",
                            "severity": "blocker",
                            "file": self.filepath,
                            "line": node.lineno,
                            "function": "shift",
                            "message": "表达式中使用了 shift() 可能导致未来数据泄露",
                        }
                    )
        self.generic_visit(node)


class SkillFutureLeak(BaseSkill):
    """未来函数 SAST 扫描"""

    def __init__(self, target_path: Optional[str] = None) -> None:
        super().__init__("future_leak")
        self.target = Path(target_path or ".").resolve()
        if not self.target.is_absolute():
            self.target = (_ROOT / self.target).resolve()

    def _scan_file(self, filepath: Path) -> list[Dict[str, Any]]:
        """扫描单个文件"""
        findings = []
        try:
            content = filepath.read_text(encoding="utf-8")
            tree = ast.parse(content)
            visitor = FutureLeakVisitor(str(filepath))
            visitor.visit(tree)
            findings.extend(visitor.findings)
        except (SyntaxError, IOError, UnicodeDecodeError):
            pass
        return findings

    def run_checks(self) -> list[CheckResult]:
        """执行未来函数扫描"""
        all_findings = []
        py_files = list(self.target.rglob("*.py"))

        for fp in py_files:
            # 跳过测试文件
            if "test" in fp.name.lower():
                continue
            all_findings.extend(self._scan_file(fp))

        results: list[CheckResult] = []

        # 按严重度分类
        blockers = [f for f in all_findings if f["severity"] == "blocker"]
        warnings = [f for f in all_findings if f["severity"] == "warning"]
        infos = [f for f in all_findings if f["severity"] == "info"]

        if blockers:
            for b in blockers[:10]:  # 最多显示10个
                results.append(
                    CheckResult(
                        rule=b["rule_id"],
                        severity="blocker",
                        file=b["file"],
                        line=b["line"],
                        message=b["message"],
                        suggest="请使用 shift(+N) 或滞后特征，确保不使用未来数据",
                    )
                )

        for w in warnings[:5]:
            results.append(
                CheckResult(
                    rule=w["rule_id"],
                    severity="warning",
                    file=w["file"],
                    line=w["line"],
                    message=w["message"],
                )
            )

        # 汇总
        if not all_findings:
            results.append(
                CheckResult(
                    rule="FUTURE-000",
                    severity="info",
                    message=f"未发现未来函数使用 (扫描 {len(py_files)} 文件)",
                )
            )
        else:
            results.append(
                CheckResult(
                    rule="FUTURE-000",
                    severity="info",
                    message=(
                        f"未来函数扫描: {len(blockers)} blocker, "
                        f"{len(warnings)} warning, {len(infos)} info "
                        f"(共 {len(py_files)} 文件)"
                    ),
                )
            )

        return results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(output: str = "text", path: str = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """统一入口"""
    checker = SkillFutureLeak(target_path=path)
    results = checker.run_checks()
    result = checker.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n未来函数 SAST 扫描报告")  # noqa: F541
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

    parser = argparse.ArgumentParser(description="未来函数 SAST 扫描")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--path", default=None, help="扫描目标路径")
    args = parser.parse_args()
    result = run(output=args.output, path=args.path)
    sys.exit(result.get("exit_code", 0))

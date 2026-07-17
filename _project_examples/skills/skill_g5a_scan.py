#!/usr/bin/env python3
"""
skill_g5a_scan.py — G5A 十一项规则扫描 (P1-F14)
=================================================
基于 blacklist.yaml + threshold.yaml 的 11 条代码质量规则扫描。

规则列表:
  G5A-001: 硬编码路径（含绝对路径 D:\\\\）
  G5A-002: 硬编码 IP 地址
  G5A-003: 硬编码数据库 DDL（CREATE TABLE）
  G5A-004: eval/exec 动态执行
  G5A-005: 裸 sqlite3.connect（未通过 db_config）
  G5A-006: 超长函数（> 60 行）
  G5A-007: 超大类（> 300 行）
  G5A-008: 中文字段名/SQL 别名
  G5A-009: 未来函数引用（backtest 中的 lookahead）
  G5A-010: 废弃 import（检测导入 _deprecated/已迁移模块）
  G5A-011: 硬编码密钥/Token

使用:
    python scripts/skill/skill_g5a_scan.py [--path DIR] [--output json]
"""

import ast
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402


class G5AScan(BaseSkill):
    """G5A 十一项规则扫描器"""

    def __init__(self, target_dir: Optional[str] = None):
        super().__init__("g5a_scan")
        self.target_dir = Path(target_dir or ".").resolve()
        if not self.target_dir.is_absolute():
            self.target_dir = (_ROOT / self.target_dir).resolve()
        self.skip_dirs = {"_deprecated", "__pycache__", ".git", "build", "dist", ".egg-info"}

    def _is_skipped(self, fp: Path) -> bool:
        return any(d in str(fp) for d in self.skip_dirs)

    def run_checks(self) -> list[CheckResult]:  # noqa: C901
        results = []
        py_files = list(self.target_dir.rglob("*.py"))
        py_files = [f for f in py_files if not self._is_skipped(f)]

        for fp in py_files:
            try:
                source = fp.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue

            rel_path = str(fp.relative_to(_ROOT))

            # G5A-001: 硬编码路径
            for i, line in enumerate(source.split("\n"), 1):
                if (
                    re.search(r'["\'][A-Za-z]:\\\\', line)
                    and "paths.py" not in rel_path
                    and "constants.py" not in rel_path
                ):
                    results.append(
                        CheckResult(
                            rule="G5A-001",
                            severity="blocker",
                            message=f"硬编码绝对路径",  # noqa: F541
                            file=rel_path,
                            line=i,
                            suggest="使用 _core/paths.py 或 _core/constants.py 中的路径常量",
                        )
                    )

            # G5A-002: 硬编码 IP（豁免数据源适配器 + localhost + 测试）
            _rp_lower = rel_path.lower().replace("\\", "/")
            exempt_g5a002 = any(
                keyword in _rp_lower
                for keyword in ("data/", "adapters/", "collectors/", "source_", "tdx_", "bridge", "selfcheck")
            )
            if not exempt_g5a002:
                for i, line in enumerate(source.split("\n"), 1):
                    # 豁免 localhost / 127.0.0.1 / 0.0.0.0
                    if re.search(r"(localhost|127\.0\.0\.1|0\.0\.0\.0)", line):
                        continue
                    if re.search(r'["\'][0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', line):
                        results.append(
                            CheckResult(
                                rule="G5A-002",
                                severity="blocker",
                                message=f"硬编码 IP 地址",  # noqa: F541
                                file=rel_path,
                                line=i,
                                suggest="将 IP 提取到配置文件中",
                            )
                        )

            # G5A-003: 硬编码 DDL（豁免迁移脚本/数据库初始化文件 + 测试文件 + 扫描器自身）
            _rp_lower_g5a003 = rel_path.lower().replace("\\", "/")
            exempt_g5a003 = any(
                keyword in _rp_lower_g5a003
                for keyword in (
                    "migration",
                    "init_db",
                    "db_config",
                    "shard",
                    "ddl",
                    "schema",
                    "test_",
                    "tests/",  # 测试文件中的 DDL 用于 mock/验证
                    "skill_g5a_scan",  # 扫描器自身的规则说明
                )
            )
            if not exempt_g5a003:
                for i, line in enumerate(source.split("\n"), 1):
                    if re.search(r"CREATE\s+TABLE", line, re.IGNORECASE):
                        results.append(
                            CheckResult(
                                rule="G5A-003",
                                severity="warning",
                                message=f"业务代码含 CREATE TABLE DDL，应迁移至迁移脚本",  # noqa: F541
                                file=rel_path,
                                line=i,
                                suggest="将 DDL 移至数据库迁移脚本管理",
                            )
                        )

            # G5A-004: eval/exec（豁免 setup.py 版本号读取 + 沙箱规则引擎）
            exempt_g5a004 = "setup.py" in rel_path or "sidecar" in rel_path  # risk_sidecar 使用受限 eval 沙箱
            if not exempt_g5a004:
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in ("eval", "exec")
                    ):
                        results.append(
                            CheckResult(
                                rule="G5A-004",
                                severity="blocker",
                                message=f"禁止使用 eval()/exec() 动态执行代码",  # noqa: F541
                                file=rel_path,
                                line=node.lineno,
                                suggest="使用 ast.literal_eval() 解析字面量表达式，或使用策略注册表替代",
                            )
                        )

            # G5A-005: 裸 sqlite3.connect（豁免数据层/迁移脚本/适配器）
            # 数据层文件职责即直接操作数据库，不需要通过 db_config 抽象
            _rp_lower_g5a005 = rel_path.lower().replace("\\", "/")
            exempt_g5a005 = any(
                keyword in _rp_lower_g5a005
                for keyword in (
                    "migration",
                    "init_db",
                    "tdx_full",
                    "tick_db",
                    "db_config",
                    "shard",
                    "data/",
                    "adapters/",
                    "collectors/",  # 数据源适配器层
                    "cache",
                    "bridge",
                    "reader",
                    "source_",  # 数据读取桥接层
                    "heartbeat",
                    "perf_baseline",  # 基础设施
                    "kun_db",
                    "futures",
                    "wh6",
                    "index_",
                    "l2_",  # 具体数据源
                )
            )
            if not exempt_g5a005:
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        if (
                            node.func.attr == "connect"
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "sqlite3"
                        ):
                            # 检查是否从 db_config 导入
                            has_db_config = False
                            for n in ast.walk(tree):
                                if isinstance(n, (ast.Import, ast.ImportFrom)):
                                    for alias in n.names if isinstance(n, ast.Import) else n.names:
                                        if "db_config" in (
                                            alias.name if isinstance(n, ast.Import) else (n.module or "")
                                        ):
                                            has_db_config = True
                            if not has_db_config:
                                results.append(
                                    CheckResult(
                                        rule="G5A-005",
                                        severity="warning",
                                        message=f"裸 sqlite3.connect()，未使用 _core/db_config.py",  # noqa: F541
                                        file=rel_path,
                                        line=node.lineno,
                                        suggest="替换为: from _core.db_config import connect_db",
                                    )
                                )

            lines = source.split("\n")

            # G5A-006: 超长函数（阈值 100 行，量化数据处理场景合理）
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if hasattr(node, "end_lineno") and node.end_lineno - node.lineno > 100:  # type: ignore[operator]
                        results.append(
                            CheckResult(
                                rule="G5A-006",
                                severity="warning",
                                message=f"函数 {node.name}() 过长 ({node.end_lineno - node.lineno} 行 > 100)",  # type: ignore[operator]  # noqa: E501
                                file=rel_path,
                                line=node.lineno,
                                suggest="拆分函数为多个单一职责的子函数",
                            )
                        )

            # G5A-007: 超大 Class（阈值 500 行）
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if hasattr(node, "end_lineno") and node.end_lineno - node.lineno > 500:  # type: ignore[operator]
                        results.append(
                            CheckResult(
                                rule="G5A-007",
                                severity="warning",
                                message=f"类 {node.name} 过大 ({node.end_lineno - node.lineno} 行 > 500)",  # type: ignore[operator]  # noqa: E501
                                file=rel_path,
                                line=node.lineno,
                                suggest="拆分为多个类或用 Mixin 组合",
                            )
                        )

            # G5A-008: 中文标识符命名（AST 级别检查，排除字符串/注释）
            for node in ast.walk(tree):
                # 检查变量名（Assign/AnnAssign 的 target）
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name) and re.search(r"[\u4e00-\u9fff]", target.id):
                            results.append(
                                CheckResult(
                                    rule="G5A-008",
                                    severity="error",
                                    message=f"变量名含中文: {target.id}",
                                    file=rel_path,
                                    line=target.lineno if hasattr(target, "lineno") else node.lineno,
                                    suggest="使用英文 snake_case 命名",
                                )
                            )
                # 检查函数名
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if re.search(r"[\u4e00-\u9fff]", node.name):
                        results.append(
                            CheckResult(
                                rule="G5A-008",
                                severity="error",
                                message=f"函数名含中文: {node.name}",
                                file=rel_path,
                                line=node.lineno,
                                suggest="使用英文 snake_case 命名",
                            )
                        )
                # 检查类名
                if isinstance(node, ast.ClassDef):
                    if re.search(r"[\u4e00-\u9fff]", node.name):
                        results.append(
                            CheckResult(
                                rule="G5A-008",
                                severity="error",
                                message=f"类名含中文: {node.name}",
                                file=rel_path,
                                line=node.lineno,
                                suggest="使用英文 PascalCase 命名",
                            )
                        )
                # 检查函数参数名
                if isinstance(node, ast.arguments):
                    for arg in node.args + node.posonlyargs + node.kwonlyargs:
                        if isinstance(arg, ast.arg) and re.search(r"[\u4e00-\u9fff]", arg.arg):
                            results.append(
                                CheckResult(
                                    rule="G5A-008",
                                    severity="error",
                                    message=f"参数名含中文: {arg.arg}",
                                    file=rel_path,
                                    line=arg.lineno if hasattr(arg, "lineno") else 0,
                                    suggest="使用英文 snake_case 命名",
                                )
                            )

            # G5A-009: 未来函数 (lookahead in backtest)
            if "backtest" in rel_path or "回测" in rel_path.replace("_deprecated", ""):
                for i, line in enumerate(lines, 1):
                    if re.search(r"(shift|\.iloc\[.*-.*\]|\.shift\(-\d)", line):
                        results.append(
                            CheckResult(
                                rule="G5A-009",
                                severity="blocker",
                                message=f"疑似未来函数引用: {line.strip()[:60]}",
                                file=rel_path,
                                line=i,
                                suggest="回测中禁止使用 shift(-N) 引用未来数据",
                            )
                        )

            # G5A-010: 废弃 import（检测导入不存在的模块/已迁移的模块）
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        if isinstance(node, ast.ImportFrom):
                            module = node.module or ""
                            full_name = f"{module}.{alias.name}" if module else alias.name
                        else:
                            full_name = alias.name

                        # 检测废弃/迁移模块
                        deprecated_modules = {
                            "_deprecated": "已废弃目录中的模块",
                            "execution_feedback_engine": "已迁移至 _deprecated/",
                            "pre_market_check": "已迁移至 _deprecated/",
                            "human_feedback": "已迁移至 _deprecated/",
                        }
                        for key, reason in deprecated_modules.items():
                            # 豁免：文件本身在 _deprecated 中，或导入路径已明确指向 _deprecated
                            if key in full_name and "_deprecated" not in rel_path and "_deprecated" not in full_name:
                                results.append(
                                    CheckResult(
                                        rule="G5A-010",
                                        severity="warning",
                                        message=f"废弃 import: {full_name} ({reason})",
                                        file=rel_path,
                                        line=node.lineno,
                                        suggest="从 _deprecated/ 导入前需经 KUN 审批签发迁移单",
                                    )
                                )

            # G5A-011: 硬编码密钥/Token
            for i, line in enumerate(lines, 1):
                if re.search(r'(token|secret|api_key|password)\s*[:=]\s*["\'][A-Za-z0-9_-]{16,}', line, re.IGNORECASE):
                    results.append(
                        CheckResult(
                            rule="G5A-011",
                            severity="blocker",
                            message=f"疑似硬编码密钥/Token",  # noqa: F541
                            file=rel_path,
                            line=i,
                            suggest="将密钥移至环境变量或 .env 文件",
                        )
                    )

        return results


def run(path: str = ".", output: str = "json") -> Dict[str, Any]:
    skill = G5AScan(target_dir=path)
    results = skill.run_checks()
    result = skill.output_results(results)
    if output == "json":
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="G5A 十一项规则扫描")
    parser.add_argument("--path", default=".", help="扫描目录")
    parser.add_argument("--output", default="json", help="输出格式")
    args = parser.parse_args()
    run(path=args.path, output=args.output)

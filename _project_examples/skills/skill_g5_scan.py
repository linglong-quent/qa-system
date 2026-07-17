#!/usr/bin/env python3
"""
skill_g5_scan.py — G5 零 print 扫描 (P1-F13)
==============================================
扫描业务代码中的 print() 调用。
入口文件（__main__）和 CLI 工具文件豁免。

使用:
    python scripts/skill/skill_g5_scan.py [--path DIR] [--output json]
"""

import ast
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# 豁免文件列表（允许 print 的入口文件）
EXEMPT_FILES = {
    "__main__.py",
    "setup_dev_env.py",
    "awaken_kun.py",
    # Skill CLI 入口文件
    "skill_base.py",
    "skill_g5_scan.py",
    "skill_g5a_scan.py",
    "skill_readability_check.py",
}


class G5PrintScan(BaseSkill):
    """G5 零 print 扫描器"""

    def __init__(self, target_dir: Optional[str] = None):
        super().__init__("g5_scan")
        self.target_dir = Path(target_dir or ".").resolve()
        if not self.target_dir.is_absolute():
            self.target_dir = (_ROOT / self.target_dir).resolve()

    def run_checks(self) -> list[CheckResult]:  # noqa: C901
        results = []
        py_files = list(self.target_dir.rglob("*.py"))
        py_files = [
            f
            for f in py_files
            if not any(d in str(f) for d in ("_deprecated", "__pycache__", "build", "dist", ".egg-info"))
        ]

        for fp in py_files:
            # 检查是否豁免
            if fp.name in EXEMPT_FILES:
                continue

            try:
                source = fp.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                    # 检查是否在 __main__ 块中
                    in_main = False
                    for parent in ast.walk(tree):
                        if hasattr(parent, "body") and node in ast.walk(parent):
                            if (
                                isinstance(parent, ast.If)
                                and hasattr(parent.test, "left")
                                and isinstance(parent.test.left, ast.Name)
                                and parent.test.left.id == "__name__"
                            ):
                                in_main = True
                                break

                    if not in_main:
                        results.append(
                            CheckResult(
                                rule="G5-001",
                                severity="blocker",
                                message="业务代码禁止使用 print()，请使用 logger",
                                file=str(fp.relative_to(_ROOT)),
                                line=node.lineno,
                                suggest="替换为: from _core.logger import logger; logger.info(...)",
                            )
                        )

        return results


def run(path: str = ".", output: str = "json") -> Dict[str, Any]:
    skill = G5PrintScan(target_dir=path)
    results = skill.run_checks()
    result = skill.output_results(results)
    if output == "json":
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="G5 零 print 扫描")
    parser.add_argument("--path", default=".", help="扫描目录")
    parser.add_argument("--output", default="json", help="输出格式")
    args = parser.parse_args()
    run(path=args.path, output=args.output)

#!/usr/bin/env python3
"""results/latest.md 输出格式固化 Skill (B3-06)

校验 latest.md 是否包含 YAML frontmatter + 标准化字段。
确保每次运行的输出格式一致，下游工具可解析。

审计: CB P1-B3 Batch3 数据与验证 (2026-07-08)
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path
from typing import Any, Dict

# ─── 必需字段规范 ────────────────────────────────────
REQUIRED_FRONTMATTER_FIELDS = [
    "run_id",
    "run_at",
    "pipeline",
    "status",
    "version",
]

REQUIRED_SECTIONS = [
    "## 执行摘要",
    "## 运行结果",
    "## 异常与警告",
    "## 资源使用",
]

OPTIONAL_SECTIONS = [
    "## 数据质量",
    "## 性能分析",
    "## 审计信息",
]

STATUS_VALUES = {"success", "warning", "failure", "partial"}


def parse_frontmatter(content: str) -> dict[str, str] | None:
    """解析 YAML frontmatter"""
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, content, re.DOTALL)
    if not match:
        return None

    fm = {}
    for line in match.group(1).split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def check_latest_format(filepath: str | None = None) -> Dict[str, Any]:  # noqa: C901
    """检查 latest.md 格式合规性"""
    if filepath is None:
        filepath = str(Path(__file__).parent.parent.parent / "_tasks" / "results" / "latest.md")

    fpath = Path(filepath)
    issues = []
    warnings = []

    # 1. 文件存在检查
    if not fpath.exists():
        return {
            "run_at": datetime.datetime.now().isoformat(),
            "file": str(fpath),
            "exists": False,
            "passed": False,
            "issues": [{"type": "missing", "message": f"文件不存在: {fpath}"}],
            "warnings": [],
        }

    try:
        content = fpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {
            "run_at": datetime.datetime.now().isoformat(),
            "file": str(fpath),
            "exists": True,
            "passed": False,
            "issues": [{"type": "read_error", "message": str(e)}],
            "warnings": [],
        }

    # 2. Frontmatter 检查
    fm = parse_frontmatter(content)
    if fm is None:
        issues.append(
            {
                "type": "missing_frontmatter",
                "message": "缺少 YAML frontmatter (--- ... ---)",
            }
        )
    else:
        for field in REQUIRED_FRONTMATTER_FIELDS:
            if field not in fm:
                issues.append(
                    {
                        "type": "missing_field",
                        "field": field,
                        "message": f"frontmatter 缺少必需字段: {field}",
                    }
                )

        # status 值校验
        if "status" in fm and fm["status"] not in STATUS_VALUES:
            issues.append(
                {
                    "type": "invalid_status",
                    "field": "status",
                    "value": fm["status"],
                    "message": f"status 值无效: {fm['status']}，允许值: {STATUS_VALUES}",
                }
            )

        # run_at ISO 8601 格式校验
        if "run_at" in fm:
            try:
                datetime.datetime.fromisoformat(fm["run_at"])
            except ValueError:
                issues.append(
                    {
                        "type": "invalid_datetime",
                        "field": "run_at",
                        "value": fm["run_at"],
                        "message": f"run_at 格式无效，需为 ISO 8601: {fm['run_at']}",
                    }
                )

    # 3. 必需章节检查
    for section in REQUIRED_SECTIONS:
        if section not in content:
            issues.append(
                {
                    "type": "missing_section",
                    "section": section,
                    "message": f"缺少必需章节: {section}",
                }
            )

    # 4. 可选章节检查（仅警告）
    for section in OPTIONAL_SECTIONS:
        if section not in content:
            warnings.append(
                {
                    "type": "missing_optional_section",
                    "section": section,
                    "message": f"建议添加章节: {section}",
                }
            )

    # 5. 内容质量检查
    # 空文件检查
    if len(content.strip()) < 50:
        issues.append(
            {
                "type": "empty_content",
                "message": "文件内容过短 (< 50 字符)",
            }
        )

    # 检查是否有表格
    if "|" not in content:
        warnings.append(
            {
                "type": "no_table",
                "message": "文件中未发现 Markdown 表格",
            }
        )

    passed = len(issues) == 0

    return {
        "run_at": datetime.datetime.now().isoformat(),
        "file": str(fpath),
        "exists": True,
        "passed": passed,
        "frontmatter": fm,
        "issues": issues,
        "warnings": warnings,
        "content_length": len(content),
        "sections_found": [s for s in REQUIRED_SECTIONS + OPTIONAL_SECTIONS if s in content],
    }


def main() -> int:
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="latest.md 格式校验")
    parser.add_argument(
        "--file",
        default=None,
        help="latest.md 文件路径",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 格式输出",
    )
    args = parser.parse_args()

    report = check_latest_format(args.file)

    if args.json:
        import json

        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"latest.md 格式校验: {'PASS' if report['passed'] else 'FAIL'}")
        if report.get("frontmatter"):
            print(f"  Frontmatter: {report['frontmatter']}")
        for i in report.get("issues", []):
            print(f"  ❌ {i['message']}")
        for w in report.get("warnings", []):
            print(f"  ⚠️ {w['message']}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

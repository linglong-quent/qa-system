#!/usr/bin/env python3
"""架构评审 CI 门禁 (B4-04)
规范引用: p1_spec §五 HOOK "架构评审门禁"
功能: CI/MR 阶段自动触发架构审计，检查分层违规/模块耦合/循环依赖
退出码: 0=通过, 1=警告, 2=阻断
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Dict, List, Set

# ─── 架构规则 ─────────────────────────────────────────
LAYER_ORDER = {
    "scripts": 1,
    "tools": 2,
    "data": 3,
    "_core": 0,  # 底层基础
    "adapters": 1,
    "collectors": 1,
}

# 禁止跨层直连规则
FORBIDDEN_IMPORTS: Dict[str, List[str]] = {
    "_core": ["scripts", "tools", "adapters", "collectors"],
    "data": ["scripts", "tools"],
    "adapters": ["scripts", "tools"],
    "collectors": ["scripts", "tools"],
}

# 核心模块名单 (变更这些模块必须触发架构评审)
CORE_MODULES = [
    "_core/config.py",
    "_core/logger.py",
    "_core/trace.py",
    "_core/platform.py",
    "_core/version.py",
    "_core/error_codes.py",
]


def find_python_files(root: Path) -> List[Path]:
    """递归查找所有 Python 文件"""
    return list(root.rglob("*.py"))


def detect_circular_imports(py_files: List[Path]) -> List[str]:  # noqa: C901
    """检测循环依赖 (简化版: 检查 import 图)"""
    issues = []
    import_graph: Dict[str, Set[str]] = {}

    for f in py_files:
        try:
            rel = str(f.relative_to(f.parents[2])) if len(f.parents) > 2 else str(f)
        except ValueError:
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        imports = set()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("from ") or line.startswith("import "):
                # 提取模块名
                parts = line.replace("from ", "").replace("import ", "").split()
                if parts:
                    mod = parts[0].split(".")
                    imports.add(mod)
        import_graph[rel] = imports  # type: ignore[assignment]

    # 检查循环: A import B 且 B import A
    checked = set()
    for mod_a, imports_a in import_graph.items():
        for mod_b in imports_a:
            if (mod_b, mod_a) in checked:
                continue
            checked.add((mod_a, mod_b))
            if mod_b in import_graph:
                imports_b = import_graph
                a_short = Path(mod_a).stem
                b_short = Path(mod_b).stem  # noqa: F841
                if a_short in imports_b or Path(mod_a).parent.name in imports_b:
                    issues.append(f"⚠️  循环依赖: {mod_a} ↔ {mod_b}")
    return issues


def check_layer_violations(py_files: List[Path]) -> List[str]:
    """检查分层违规"""
    issues = []
    for f in py_files:
        parts = f.parts
        # 确定文件所属层
        file_layer = None
        for i, part in enumerate(parts):
            if part in LAYER_ORDER:
                file_layer = part
                break

        if file_layer is None:
            continue

        content = f.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines():
            line = line.strip()
            if not (line.startswith("from ") or line.startswith("import ")):
                continue

            for forbidden_layer in FORBIDDEN_IMPORTS.get(file_layer, []):
                if forbidden_layer in line:
                    issues.append(f"❌ 分层违规: {f.name} ({file_layer}) → {forbidden_layer}: {line[:80]}")

    return issues


def detect_core_changes(changed_files: List[str]) -> List[str]:
    """检测核心模块变更"""
    alerts = []
    for cf in changed_files:
        for core_mod in CORE_MODULES:
            if cf.endswith(core_mod) or core_mod in cf:
                alerts.append(f"🚨 核心模块变更: {cf}")
    return alerts


def generate_report(issues: List[str], core_alerts: List[str], output_dir: Path) -> Path:
    """生成架构评审报告"""
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"arch_review_{ts}.md"

    lines = [
        "# 架构评审报告",
        f"生成时间: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        "",
        f"## 核心模块变更告警 ({len(core_alerts)})",
    ]
    lines.extend(f"- {a}" for a in core_alerts) if core_alerts else lines.append("- 无")

    lines.append(f"")  # noqa: F541
    lines.append(f"## 架构违规 ({len(issues)})")
    lines.extend(f"- {i}" for i in issues) if issues else lines.append("- 无")

    lines.append(f"")  # noqa: F541
    if not issues and not core_alerts:
        lines.append("✅ 架构评审通过")
    elif issues:
        lines.append("❌ 架构评审未通过 — 存在违规项")
    else:
        lines.append("⚠️  架构评审警告 — 核心模块变更需双人评审")

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return report_file


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    print("[B4-04] 架构评审 CI 门禁")
    print("=" * 60)

    # 步骤1: 检测核心模块变更 (从 git diff 获取)
    changed_files = []
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        pass

    core_alerts = detect_core_changes(changed_files)
    if core_alerts:
        print(f"\n🚨 核心模块变更 ({len(core_alerts)}):")
        for a in core_alerts:
            print(f"   {a}")

    # 步骤2: 分层违规检查
    py_files = find_python_files(root)
    layer_issues = check_layer_violations(py_files)

    # 步骤3: 循环依赖检测
    circular_issues = detect_circular_imports(py_files)

    all_issues = layer_issues + circular_issues

    if all_issues:
        print(f"\n❌ 架构违规 ({len(all_issues)}):")
        for i in all_issues:
            print(f"   {i}")

    # 步骤4: 生成报告
    report = generate_report(all_issues, core_alerts, root)
    print(f"\n📄 评审报告: {report}")

    print("=" * 60)

    if all_issues:
        print(f"❌ 共 {len(all_issues)} 项违规 (退出码=2)")
        return 2
    if core_alerts:
        print(f"⚠️  {len(core_alerts)} 核心模块变更需双人评审 (退出码=1)")
        return 1
    print("✅ 架构评审通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

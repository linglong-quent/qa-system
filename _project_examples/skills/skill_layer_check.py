#!/usr/bin/env python3
"""
layer_check.py — 分层架构校验脚本
读取 config/rule/layer_rule.yaml，扫描代码库中的跨层导入违规。
用法: python scripts/skill/skill_layer_check.py
退出码: 0=合规 / 1=阻断级违规 / 2=警告
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent.parent
LAYER_RULE = ROOT / "config" / "rule" / "layer_rule.yaml"
SCAN_DIRS = ["."]


def load_layers() -> Dict[str, Any]:
    if not LAYER_RULE.exists():
        print(f"❌ {LAYER_RULE} 不存在")
        sys.exit(1)
    with open(LAYER_RULE, encoding="utf-8") as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


def classify_file(path: Path, layers: Dict[str, Any]) -> str:
    """根据文件路径判断所属层"""
    rel = path.relative_to(ROOT).as_posix()
    for name, cfg in layers.get("layers", {}).items():
        for p in cfg.get("paths", []):
            if rel.startswith(p.replace("\\", "/")):
                return name  # type: ignore[no-any-return]
    return "unknown"


def check_imports(path: Path, layer: str, layers: Dict[str, Any]) -> List[Any]:
    """扫描文件的 import 语句，检查是否违反跨层规则"""
    issues: Any = []
    cfg = layers.get("layers", {}).get(layer, {})
    forbidden = cfg.get("forbidden_imports", [])
    blacklist = cfg.get("rules", {}).get("import_blacklist", [])

    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IOError):
        return issues  # type: ignore[no-any-return]

    for line in content.splitlines():
        stripped = line.strip()
        # 匹配 import xxx 和 from xxx import yyy
        m = re.match(r"^(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", stripped)
        if not m:
            continue
        imported = m.group(1)
        imported_parts = imported.split(".")

        # 检查禁止导入层
        for fb in forbidden:
            if imported == fb or imported.startswith(fb + "."):
                issues.append(
                    f"  跨层违规: {path.relative_to(ROOT)} 第{content.splitlines().index(line)+1}行 "
                    f"导入 {imported} (层 {layer} 禁止导入 {fb})"
                )

        # 检查导入黑名单
        for bl in blacklist:
            if imported_parts[0] == bl:
                issues.append(f"  黑名单违规: {path.relative_to(ROOT)} 导入禁止模块 {bl}")

    return issues  # type: ignore[no-any-return]


def main() -> None:
    print("=" * 55)
    print("  分层架构 layer_check 扫描")
    print("=" * 55)

    layers = load_layers()
    all_issues = []
    scan_count = 0

    for sd in SCAN_DIRS:
        scan_path = ROOT / sd
        if not scan_path.exists():
            continue
        for py_file in scan_path.rglob("*.py"):
            # 跳过 _deprecated
            if "_deprecated" in py_file.parts:
                continue
            layer = classify_file(py_file, layers)
            if layer == "unknown":
                continue
            scan_count += 1
            issues = check_imports(py_file, layer, layers)
            all_issues.extend(issues)

    print(f"  扫描文件: {scan_count}")
    if all_issues:
        print(f"  违规: {len(all_issues)} 处")
        for issue in all_issues:
            print(issue)
        print("\n❌ 分层架构不合规，请修复后重试")
        sys.exit(1)
    else:
        print("   ✅ 无跨层违规")
        sys.exit(0)


if __name__ == "__main__":
    main()

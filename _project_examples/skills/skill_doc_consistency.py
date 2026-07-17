#!/usr/bin/env python3
"""
skill_doc_consistency.py — 文档一致性自动检查 (P1-R01)

6 项自动检查：
  1. Registry vs 实际 Skill 文件存在性
  2. _docs/ 法典文件版本号一致性
  3. _docs/ 交叉引用有效性（断链检测）
  4. todo.json 任务状态 vs 实际交付物
  5. skill_spec.md Skill 列表 vs Registry
  6. BaseSkill 接口一致性

审计: CB 执行三段式闭环沉淀 (2026-07-08 04:41 P1-R01)
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


# ── BaseSkill 兼容（独立运行时无需导入 BaseSkill） ──
@dataclass
class CheckResult:
    rule: str
    severity: str  # blocker / error / warning / info
    message: str
    file: str = ""
    line: int = 0
    suggest: str = ""


ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/skill/ → linglong/ → workspace/
DOCS_DIR = ROOT.parent / "_docs"
TASKS_DIR = ROOT.parent / "_tasks"
REGISTRY_PATH = ROOT / "scripts" / "skill" / "skill_registry.yaml"


def check_1_registry_files() -> list[CheckResult]:
    """检查 1: Registry 中注册的 Skill 文件是否真实存在"""
    results = []
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = yaml.safe_load(f)
        skills = registry.get("skills", {})
    except Exception as e:
        return [CheckResult("DOC-001", "blocker", f"无法读取 Registry: {e}", str(REGISTRY_PATH))]

    for name, cfg in skills.items():
        module_path = cfg.get("module", "")
        if not module_path:
            results.append(
                CheckResult(
                    "DOC-001",
                    "error",
                    f"Skill '{name}' 缺少 module 字段",
                    str(REGISTRY_PATH),
                    suggest="补全 module 字段指向实际 .py 文件",
                )
            )
            continue
        full_path = ROOT / module_path  # linglong/ + module
        if not full_path.exists():
            results.append(
                CheckResult(
                    "DOC-001",
                    "error",
                    f"Skill '{name}' 注册文件不存在: {module_path}",
                    str(full_path),
                    suggest="创建对应文件或从 Registry 移除",
                )
            )
    if not results:
        results.append(CheckResult("DOC-001", "info", f"Registry 全部 {len(skills)} 个 Skill 文件存在性检查通过"))
    return results


def check_2_doc_versions() -> list[CheckResult]:
    """检查 2: _docs/ 法典文件版本号一致性"""
    results = []
    version_map = {
        "p1_spec.md": "v7.1",
        "roadmap.md": "v1.4",
        "asset_inventory.md": "v2.1",
        "skill_spec.md": "v1.2",
        "SKILL_DEV_GUIDE.md": "v1.1",
        "system_architecture.md": "v1.2",
        "p2p3_plan.md": "v1.4",
    }
    for filename, expected_ver in version_map.items():
        filepath = DOCS_DIR / filename
        if not filepath.exists():
            results.append(
                CheckResult(
                    "DOC-002",
                    "warning",
                    f"法典文件不存在: {filename}",
                    str(filepath),
                    suggest="确认文件是否已删除或重命名",
                )
            )
            continue
        content = filepath.read_text(encoding="utf-8")
        # 查找版本号声明
        import re

        ver_match = re.search(r"版本[：:]\s*(v[\d.]+)", content)
        if ver_match:
            actual_ver = ver_match.group(1)
            if actual_ver != expected_ver:
                results.append(
                    CheckResult(
                        "DOC-002",
                        "warning",
                        f"{filename} 版本号不一致: 期望 {expected_ver}, 实际 {actual_ver}",
                        str(filepath),
                        suggest=f"更新为 {expected_ver}",
                    )
                )
        else:
            results.append(
                CheckResult(
                    "DOC-002",
                    "warning",
                    f"{filename} 缺少版本号声明",
                    str(filepath),
                    suggest="添加 '> 版本: vX.Y' 头部声明",
                )
            )
    if not [r for r in results if r.severity != "info"]:
        results.append(CheckResult("DOC-002", "info", f"_docs/ 版本号一致性检查通过 ({len(version_map)} 文件)"))
    return results


def check_3_cross_references() -> list[CheckResult]:
    """检查 3: _docs/ 交叉引用有效性（断链检测）"""
    results = []
    # 扫描所有 .md 文件中的 `_docs/xxx.md` 和 `_tasks/xxx` 引用
    import re

    ref_pattern = re.compile(r"`(_docs/[\w./-]+)`|`(_tasks/[\w./-]+)`")

    for md_file in sorted(DOCS_DIR.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        refs = ref_pattern.findall(content)
        seen = set()
        for match in refs:
            ref_path_str = match[0] or match
            if ref_path_str in seen:
                continue
            seen.add(ref_path_str)
            ref_path = (DOCS_DIR.parent if "_docs" in ref_path_str else DOCS_DIR.parent) / ref_path_str
            if not ref_path.exists():
                results.append(
                    CheckResult(
                        "DOC-003",
                        "warning",
                        f"断链引用: {ref_path_str}",
                        str(md_file),
                        suggest=f"确认 {ref_path_str} 是否存在或更新路径",
                    )
                )
    if not results:
        results.append(
            CheckResult("DOC-003", "info", f"_docs/ 交叉引用断链检查通过 ({len(list(DOCS_DIR.glob('*.md')))} 文件)")
        )
    return results


def check_4_todo_deliverables() -> list[CheckResult]:  # noqa: C901
    """检查 4: todo.json 任务状态 vs 实际交付物"""
    results = []
    todo_path = TASKS_DIR / "todo.json"
    if not todo_path.exists():
        return [CheckResult("DOC-004", "error", f"todo.json 不存在: {todo_path}")]

    try:
        with open(todo_path, "r", encoding="utf-8") as f:
            todo = json.load(f)
    except Exception as e:
        return [CheckResult("DOC-004", "blocker", f"todo.json 解析失败: {e}")]

    tasks = todo.get("tasks", [])
    done_tasks = [t for t in tasks if t.get("status") == "done"]
    doing_tasks = [t for t in tasks if t.get("status") == "doing"]

    # 检查 done 任务的 deliverables 文件是否存在
    for t in done_tasks:
        deliverables = t.get("deliverables", [])
        if isinstance(deliverables, str):
            deliverables = [deliverables]
        for d in deliverables:
            # 提取文件路径（支持 "filename — description" 格式）
            file_part = d.split(" — ")[0].strip()
            # 跳过非文件路径描述
            if not any(ext in file_part for ext in [".py", ".yaml", ".md", ".json", ".yml"]):
                continue
            for base_dir in [
                ROOT.parent,
                ROOT.parent / "config",
                ROOT.parent / "_docs",
                ROOT.parent / "_tasks",
            ]:
                candidate = base_dir / file_part
                if candidate.exists():
                    break
            else:
                results.append(
                    CheckResult(
                        "DOC-004",
                        "warning",
                        f"{t['id']} 交付物文件不存在: {file_part}",
                        str(todo_path),
                        suggest=f"确认 {file_part} 路径是否正确",
                    )
                )

    # 检查 doing 任务数量
    if len(doing_tasks) > 10:
        results.append(CheckResult("DOC-004", "warning", f"doing 任务过多 ({len(doing_tasks)} 个)，可能存在积压"))

    if not [r for r in results if r.severity != "info"]:
        results.append(
            CheckResult(
                "DOC-004", "info", f"todo.json 交付物检查通过 (done:{len(done_tasks)}, doing:{len(doing_tasks)})"
            )
        )
    return results


def check_5_skill_spec_vs_registry() -> list[CheckResult]:
    """检查 5: skill_spec.md 中 Skill 列表 vs Registry"""
    results = []
    spec_path = DOCS_DIR / "skill_spec.md"
    if not spec_path.exists():
        return [CheckResult("DOC-005", "warning", "skill_spec.md 不存在", str(spec_path))]

    # 从 Registry 读取 Skill 名称
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = yaml.safe_load(f)
        reg_skills = set(registry.get("skills", {}).keys())
    except Exception as e:
        return [CheckResult("DOC-005", "blocker", f"Registry 读取失败: {e}")]

    # 从 skill_spec.md 读取 Skill 列表
    content = spec_path.read_text(encoding="utf-8")
    import re

    spec_skills = set()
    for m in re.finditer(r"`(\w+)`", content):
        name = m.group(1)
        # 只收集以 skill_ 开头的名称或已知的 Skill ID
        if name.startswith("skill_") or name in reg_skills:
            spec_skills.add(name)

    # 交叉比对
    only_in_reg = reg_skills - spec_skills
    only_in_spec = spec_skills - reg_skills

    if only_in_reg:
        results.append(
            CheckResult(
                "DOC-005",
                "warning",
                f"仅在 Registry 中的 Skill: {', '.join(sorted(only_in_reg))}",
                str(spec_path),
                suggest="更新 skill_spec.md 补充这些 Skill",
            )
        )
    if only_in_spec:
        # 过滤掉纯 skill_ 前缀的名称（可能是示例代码中的引用）
        meaningful = [s for s in only_in_spec if s in reg_skills or not s.startswith("skill_")]
        if meaningful:
            results.append(
                CheckResult(
                    "DOC-005",
                    "warning",
                    f"仅在 skill_spec.md 中的 Skill: {', '.join(sorted(meaningful))}",
                    str(REGISTRY_PATH),
                    suggest="在 Registry 中注册这些 Skill",
                )
            )

    if not [r for r in results if r.severity != "info"]:
        results.append(
            CheckResult("DOC-005", "info", f"skill_spec.md ↔ Registry 交叉检查通过 ({len(reg_skills)} 个 Skill)")
        )
    return results


def check_6_base_skill_interface() -> list[CheckResult]:  # noqa: C901
    """检查 6: 所有 Skill 文件是否继承 BaseSkill 且实现 run_checks()"""
    results = []
    skill_dir = ROOT / "scripts" / "skill"
    if not skill_dir.exists():
        return [CheckResult("DOC-006", "error", f"Skill 目录不存在: {skill_dir}")]

    import ast

    for py_file in sorted(skill_dir.glob("skill_*.py")):
        if py_file.name in ("skill_base.py",):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError as e:
            results.append(CheckResult("DOC-006", "error", f"{py_file.name} 语法错误: {e}", str(py_file)))
            continue

        # 查找类定义是否继承 BaseSkill
        has_base = False
        has_run_checks = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "BaseSkill":
                        has_base = True
                        # 检查该类是否有 run_checks 方法
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef) and item.name == "run_checks":
                                has_run_checks = True
                                break
            elif isinstance(node, ast.FunctionDef) and node.name == "run_checks":
                # 顶层函数也有 run_checks 也可接受
                has_run_checks = True

        if not has_base and not has_run_checks:
            results.append(
                CheckResult(
                    "DOC-006",
                    "warning",
                    f"{py_file.name} 未继承 BaseSkill 且无 run_checks()",
                    str(py_file),
                    suggest="继承 BaseSkill 或实现 run_checks() 方法",
                )
            )
        elif not has_base:
            results.append(
                CheckResult(
                    "DOC-006", "info", f"{py_file.name} 有 run_checks() 但未继承 BaseSkill（独立模式）", str(py_file)
                )
            )

    if not [r for r in results if r.severity == "error"]:
        total = len(list(skill_dir.glob("skill_*.py"))) - 1  # 排除 skill_base.py
        results.append(CheckResult("DOC-006", "info", f"BaseSkill 接口一致性检查通过 ({total} 个 Skill 文件)"))
    return results


def run_all_checks() -> tuple[list[CheckResult], int, int]:
    """执行全部 6 项检查"""
    all_results = []
    checks = [
        ("1. Registry 文件存在性", check_1_registry_files),
        ("2. _docs/ 版本号一致性", check_2_doc_versions),
        ("3. 交叉引用断链检测", check_3_cross_references),
        ("4. todo.json 交付物校验", check_4_todo_deliverables),
        ("5. skill_spec ↔ Registry", check_5_skill_spec_vs_registry),
        ("6. BaseSkill 接口一致性", check_6_base_skill_interface),
    ]

    blocker = error = 0
    for name, check_fn in checks:
        try:
            res = check_fn()
            all_results.extend(res)
            for r in res:
                if r.severity == "blocker":
                    blocker += 1
                elif r.severity == "error":
                    error += 1
        except Exception as e:
            all_results.append(CheckResult("DOC-000", "blocker", f"{name} 执行异常: {e}"))

    return all_results, blocker, error


def main() -> Any:
    parser = argparse.ArgumentParser(description="文档一致性自动检查 (P1-R01)")
    parser.add_argument("--check", type=str, default="all", help="指定检查项 (1-6 或 all)")
    parser.add_argument("--output", type=str, choices=["text", "json"], default="text", help="输出格式")
    parser.add_argument("--workspace", type=str, default=None, help="覆盖工作区路径")
    args = parser.parse_args()

    if args.workspace:
        global ROOT, DOCS_DIR, TASKS_DIR, REGISTRY_PATH
        ROOT = Path(args.workspace)
        DOCS_DIR = Path(args.workspace) / "_docs"
        TASKS_DIR = Path(args.workspace) / "_tasks"
        REGISTRY_PATH = ROOT / "scripts" / "skill" / "skill_registry.yaml"

    if args.check == "all":
        results, blocker, error = run_all_checks()
    else:
        check_map = {
            "1": check_1_registry_files,
            "2": check_2_doc_versions,
            "3": check_3_cross_references,
            "4": check_4_todo_deliverables,
            "5": check_5_skill_spec_vs_registry,
            "6": check_6_base_skill_interface,
        }
        fn = check_map.get(args.check)
        if not fn:
            print(f"未知检查项: {args.check}, 可选: 1-6, all", file=sys.stderr)
            sys.exit(1)
        results = fn()
        blocker = sum(1 for r in results if r.severity == "blocker")
        error = sum(1 for r in results if r.severity == "error")

    if args.output == "json":
        output = {
            "status": "fail" if blocker > 0 else ("warn" if error > 0 else "pass"),
            "exit_code": 1 if blocker > 0 else (0 if error == 0 else 2),
            "total": len(results),
            "blocker": blocker,
            "error": error,
            "results": [asdict(r) for r in results],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for r in results:
            icon = {"blocker": "❌", "error": "⚠️", "warning": "⚡", "info": "✅"}.get(r.severity, "  ")
            print(f"  {icon} [{r.rule}] {r.severity.upper()}: {r.message}")
            if r.file:
                print(f"     文件: {r.file}")
            if r.suggest:
                print(f"     建议: {r.suggest}")

        total = len(results)
        status = "❌ FAIL" if blocker > 0 else ("⚠️ WARN" if error > 0 else "✅ PASS")
        print(f"\n{'='*60}")
        print(f"  {status}  总计: {total} 项  blocker: {blocker}  error: {error}")
        print(f"{'='*60}")

    return 1 if blocker > 0 else (0 if error == 0 else 2)


if __name__ == "__main__":
    sys.exit(main())

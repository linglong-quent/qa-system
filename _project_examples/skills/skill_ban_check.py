#!/usr/bin/env python3
"""
skill_ban_check.py — 量化禁令7条判定脚本
读取代码库，扫描 7 条量化编码禁令，返回结构化结果。
用法: python scripts/skill/skill_ban_check.py [--dir <dir>]
退出码: 0=全合规 / 1=阻断级违规
变更单: ARCH-TICKET-003
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent.parent

# ── 命名常量（消除魔法数字）────────────────────────────────
SEP_WIDTH = 60  # 输出分隔线宽度

# ─── 7条禁令规则定义 ────────────────────────────────────────
BAN_RULES = [
    {
        "id": "BAN-001",
        "name": "禁止硬编码路径",
        "severity": "blocker",
        "description": "检测字符串常量中的盘符(C:/D:)和路径分隔符",
        "pattern": re.compile(r'["\'](?:  # type: ignore[A-Za-z]:[/\\]|/home/|/mnt/|\\\\[a-zA-Z]+\\\\)'),
        "suggest": "使用 pathlib.Path 或从 config 读取路径",
    },
    {
        "id": "BAN-002",
        "name": "禁止 print 调试代码",
        "severity": "blocker",  # 新增与存量同标准，严格禁止
        "description": "检测业务代码中的 print() 调用（CLI入口/Skill脚本/测试文件豁免）",
        "pattern": re.compile(r"\bprint\s*\("),
        "suggest": "使用 _core/logger.py 统一日志入口",
        "exempt_files": [
            # 项目入口/CLI 脚本 — print 是其合法功能
            "__main__",
            "setup.py",
            "run_pipeline.py",
            # Skill 脚本自身是 CLI 工具
            "skill_",
            "_skill_",
            # 项目入口
            "backup.py",
            "review_gate.py",
            "review_panel.py",
            "intraday_guard.py",
            # 测试脚本
            "_test",
            "test_",
        ],
    },
    {
        "id": "BAN-003",
        "name": "禁止 eval/exec 动态执行",
        "severity": "blocker",
        "description": "检测 eval()/exec()/compile() 调用（排除 re.compile）",
        "pattern": re.compile(r"(?<!re\.)\b(eval|exec)\s*\("),
        "suggest": "使用安全的替代方案（如 ast.literal_eval 或显式解析器）",
    },
    {
        "id": "BAN-004",
        "name": "禁止密码/密钥硬编码",
        "severity": "blocker",
        "description": "检测 password/secret/api_key/token 等字段的明文赋值",
        "pattern": re.compile(
            r'(?:password|secret|api_key|token|access_key|private_key)\s*=\s*["\'][^\'"]{3,}["\']', re.IGNORECASE
        ),
        "suggest": "使用环境变量 os.environ 或 config 加密存储",
    },
    {
        "id": "BAN-005",
        "name": "禁止裸除零未保护",
        "severity": "blocker",  # 新增与存量同标准
        "description": "检测除法运算缺少除零保护",
        "pattern": re.compile(r"(\w+)\s*/\s*(\w+)(?!\s*if\s+\2\s*!=\s*0)"),
        "suggest": "使用 try/except ZeroDivisionError 或添加 if divisor != 0 检查",
        "extra_check": True,  # 需要额外 AST 分析
    },
    {
        "id": "BAN-006",
        "name": "禁止未处理的无限循环",
        "severity": "error",
        "description": "检测 while True 缺少 break/return/超时退出机制",
        "pattern": re.compile(r"\bwhile\s+True\s*:"),
        "suggest": "添加 break 条件、超时计数器或 signal.alarm 保护",
        "extra_check": True,  # 需要检查循环体内是否有 break/return
    },
    {
        "id": "BAN-007",
        "name": "禁止遗留 TODO/FIXME/XXX",
        "severity": "warning",
        "description": "检测超过 3 个版本周期未处理的 TODO/FIXME/XXX 标记",
        "pattern": re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b"),
        "suggest": "修复遗留问题或升级为正式 Issue 跟踪",
    },
    # V2.1 扩展 7 条 (BAN-008 ~ 014)
    {
        "id": "BAN-008",
        "name": "禁止 except:pass 吞没异常",
        "severity": "blocker",
        "description": "检测裸 except: pass 异常吞没",
        "pattern": re.compile(r"except\s*:\s*pass"),
        "suggest": "记录异常上下文",
    },
    {
        "id": "BAN-009",
        "name": "禁止裸 SQL 拼接",
        "severity": "blocker",
        "description": "检测 f-string 拼接 SQL 查询",
        "pattern": re.compile(r'(?:execute|executemany|cursor\.execute)\s*\(\s*f["\']'),
        "suggest": "使用参数化查询",
    },
    {
        "id": "BAN-010",
        "name": "禁止 import * 通配导入",
        "severity": "error",
        "description": "检测 from module import *",
        "pattern": re.compile(r"^\s*from\s+\S+\s+import\s+\*\s*$", re.MULTILINE),
        "suggest": "显式导入所需名称",
    },
    {
        "id": "BAN-011",
        "name": "禁止 assert 用于业务逻辑",
        "severity": "error",
        "description": "检测 assert 在非测试文件中的使用",
        "pattern": re.compile(r"^\s*assert\s+", re.MULTILINE),
        "suggest": "使用 if + raise 替代 assert",
    },
    {
        "id": "BAN-012",
        "name": "禁止可变对象作为默认参数",
        "severity": "error",
        "description": "检测 def func(x=[])/x={}",
        "pattern": re.compile(r"def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|set\(\))"),
        "suggest": "使用 None 默认值 + 函数体内初始化",
    },
    {
        "id": "BAN-013",
        "name": "禁止 os.system / shell=True",
        "severity": "blocker",
        "description": "检测 os.system() 或 subprocess shell=True",
        "pattern": re.compile(r"(os\.system|subprocess\.\w+.*shell\s*=\s*True)"),
        "suggest": "使用 subprocess.run() 传参数列表",
    },
    {
        "id": "BAN-014",
        "name": "禁止魔法数字",
        "severity": "warning",
        "description": "检测未命名的常量数字",
        "pattern": re.compile(r"(?<!\w)([3-9]\d{2,}|[1-9]\d{3,}|\d+\.\d{2,})(?!\w)"),
        "suggest": "提取为命名常量",
    },
]
# 免检目录
EXEMPT_DIRS = [
    "_deprecated",
    "__pycache__",
    ".git",
    "build",
    "dist",
    ".egg-info",
    "node_modules",
    "auction_data",
    "archive",
]

# 免检文件模式
EXEMPT_PATTERNS = ["__init__.py", "test_", "_test.py"]


def should_skip(file_path: Path) -> bool:
    """判断文件是否应跳过扫描。"""
    rel = file_path.relative_to(ROOT)
    parts = rel.parts

    # 跳过免检目录
    for exempt in EXEMPT_DIRS:
        if exempt in parts:
            return True

    # 跳过免检文件模式
    fname = file_path.name
    for pattern in EXEMPT_PATTERNS:
        if pattern in fname:
            return True

    return False


def _make_issue(rule_id: str, severity: str, file_path: Path, line: int, message: str, suggest: str) -> Dict[str, Any]:
    """构建统一格式的违规记录字典。"""
    return {
        "rule": rule_id,
        "severity": severity,
        "file": str(file_path.relative_to(ROOT)),
        "line": line,
        "message": message,
        "suggest": suggest,
    }


def check_ban_005(content: str, file_path: Path) -> list[Dict[str, Any]]:  # noqa: C901
    """BAN-005: 检查除法是否有除零保护（简易版）"""
    issues = []
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # 跳过注释、字符串、导入语句
        if stripped.startswith("#"):
            continue
        if stripped.startswith("from ") or stripped.startswith("import "):
            continue
        if "Path(" in stripped or "path" in stripped.lower():
            continue
        # 跳过路径类行（含 / 和 \\ 分隔符的行）
        if re.search(r'["\'][^"\']*[/\\][^"\']*["\']', stripped):
            continue
        # 跳过明显是目录路径的行（如 "scripts/skill" 等模块引用）
        if re.match(r'^["\'][\w./\\-]+["\']\s*(?:,|\)|$|#)', stripped):
            continue
        # 匹配 a / b 模式（仅匹配纯变量除法，排除路径中的 /）
        div_match = re.search(r"(\w+)\s*/\s*(\w+)", stripped)
        if not div_match:
            continue
        dividend, divisor = div_match.group(1), div_match.group(2)
        # 排除常见非除法场景
        if dividend in ("ROOT", "Path", "path", "dir", "file", "url"):
            continue
        if divisor in ("ROOT", "Path", "path", "dir", "file", "url"):
            continue
        # 检查除数是否为常量 0
        suggest_msg = "使用 try/except ZeroDivisionError 或添加 if divisor != 0 检查"
        if divisor == "0":
            issues.append(
                _make_issue("BAN-005", "blocker", file_path, i, f"第{i}行: 除零风险 (/{divisor})", suggest_msg)
            )
            continue
        # 检查前一行是否有除零保护
        if i > 1:
            prev = lines[i - 2].strip()
            if re.search(rf"\bif\s+{divisor}\s*(!=|>|<|==)\s*0", prev):
                continue
            if "try:" in prev:
                continue
        # 只对明显是数值除法的场景报 blocker
        if divisor not in ("1", "2", "100", "1000", "10000") and not divisor.startswith("_"):
            issues.append(
                _make_issue(
                    "BAN-005",
                    "blocker",
                    file_path,
                    i,
                    f"第{i}行: 除法运算 {div_match.group(0)} 缺少除零保护",
                    suggest_msg,
                )
            )
    return issues


def check_ban_006(content: str, file_path: Path) -> list[Dict[str, Any]]:
    """BAN-006: 检查 while True 是否有退出机制"""
    issues = []
    lines = content.splitlines()
    in_while_true = False
    while_start = 0
    has_break = False
    has_return = False
    indent_level = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        if in_while_true:
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent_level and stripped:
                # 退出 while 块
                if not has_break and not has_return:
                    issues.append(
                        _make_issue(
                            "BAN-006",
                            "error",
                            file_path,
                            while_start,
                            f"第{while_start}行: while True 缺少 break/return 退出机制",
                            "添加 break 条件、超时计数器或 signal.alarm 保护",
                        )
                    )
                in_while_true = False
                has_break = False
                has_return = False
                continue
            if "break" in stripped:
                has_break = True
            if re.search(r"\breturn\b", stripped):
                has_return = True
            continue

        # 检测 while True
        if re.match(r"\bwhile\s+True\s*:", stripped):
            in_while_true = True
            while_start = i
            has_break = False
            has_return = False
            indent_level = len(line) - len(line.lstrip())

    # 文件末尾仍在 while True 中
    if in_while_true and not has_break and not has_return:
        issues.append(
            _make_issue(
                "BAN-006",
                "error",
                file_path,
                while_start,
                f"第{while_start}行: while True 缺少 break/return 退出机制",
                "添加 break 条件、超时计数器或 signal.alarm 保护",
            )
        )

    return issues


def scan_file(file_path: Path) -> list[Dict[str, Any]]:  # noqa: C901
    """扫描单个文件，返回违规列表"""
    issues: Any = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IOError):
        return issues  # type: ignore[no-any-return]

    lines = content.splitlines()
    fname = file_path.name

    for rule in BAN_RULES:
        rid: str = str(rule["id"])

        # BAN-005 和 BAN-006 需要额外检查逻辑
        if rule.get("extra_check"):
            if rid == "BAN-005":
                issues.extend(check_ban_005(content, file_path))
            elif rid == "BAN-006":
                issues.extend(check_ban_006(content, file_path))
            continue

        # 检查豁免文件
        exempt_files = rule.get("exempt_files", [])
        if any(ef in fname for ef in exempt_files):  # type: ignore[attr-defined]
            continue

        # 正则扫描
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if rule["pattern"].search(stripped):  # type: ignore[attr-defined]
                # BAN-002: print 豁免规则
                #   1) file=sys.stderr — 合法错误输出
                #   2) 在字符串内的 print 不计数
                if rid == "BAN-002":
                    if "file=sys.stderr" in stripped:
                        continue
                    if "file=sys.stdout" in stripped:
                        continue
                # BAN-003: 排除字符串字面量内的 eval/exec（如文档字符串、f-string、测试用例）
                if rid == "BAN-003":
                    # 检查匹配内容是否在引号包围中（字符串字面量，非真实调用）
                    if re.search(r'["\'].*[("]?(?:eval|exec)[)"\']?.*["\']', stripped):
                        continue
                    # 排除 re.compile 行（已被负向断言覆盖，此处双保险）
                    if "re.compile" in stripped:
                        continue
                # BAN-004: 豁免注释中的示例密码（已在前面 skip # 行）
                severity: str = str(rule["severity"])
                suggest: str = str(rule["suggest"])
                issues.append(
                    _make_issue(
                        rid,
                        severity,
                        file_path,
                        i,
                        f"第{i}行: {rule['name']} — {stripped[:80]}",
                        suggest,
                    )
                )

    return issues  # type: ignore[no-any-return]


def scan_directory(target_dir: Path) -> list[Dict[str, Any]]:
    """递归扫描目录下所有 Python 文件，返回禁令违规列表。"""
    all_issues = []
    py_files = list(target_dir.rglob("*.py"))
    for py_file in py_files:
        if should_skip(py_file):
            continue
        all_issues.extend(scan_file(py_file))
    return all_issues


def main() -> None:
    """主入口：解析命令行参数，扫描目录，输出结构化违规报告。

    退出码: 0=全合规 / 1=阻断级违规 / 2=目录不存在。
    """
    parser = argparse.ArgumentParser(description="量化禁令7条判定脚本")
    parser.add_argument("--dir", default=".", help="扫描目录（默认当前目录）")
    args = parser.parse_args()

    target = Path(args.dir).resolve()
    if not target.exists():
        print(f"❌ 目录不存在: {target}")
        sys.exit(2)

    print("=" * SEP_WIDTH)
    print("  量化禁令 7 条判定扫描")
    print("=" * SEP_WIDTH)
    print(f"  扫描目录: {target}")
    print(f"  规则数: {len(BAN_RULES)}")
    print("-" * SEP_WIDTH)

    issues = scan_directory(target)

    # 按规则分组统计
    rule_stats = {}
    for r in BAN_RULES:
        rule_stats[r["id"]] = {"name": r["name"], "count": 0}

    for issue in issues:
        rid = issue["rule"]
        if rid in rule_stats:
            rule_stats[rid]["count"] += 1  # type: ignore[operator]

    # 输出统计
    print(f"\n  扫描结果:")  # noqa: F541
    for rid, stat in rule_stats.items():
        status = "❌" if stat["count"] > 0 else "✅"  # type: ignore[operator]
        print(f"    {status} {rid} {stat['name']}: {stat['count']} 处")

    # 输出详细违规
    if issues:
        print(f"\n  ⚠️  共发现 {len(issues)} 处违规:\n")
        for issue in issues:
            sev_icon = {"blocker": "🔴", "error": "🟡", "warning": "🔵"}
            icon = sev_icon.get(issue["severity"], "⚪")
            print(f"    {icon} [{issue['rule']}] {issue['file']}:{issue['line']}")
            print(f"       {issue['message']}")
            print(f"       → {issue['suggest']}\n")
    else:
        print(f"\n  ✅ 全部 7 条禁令通过，0 违规")  # noqa: F541

    # 退出码: 有 blocker 则 1
    blocker_count = sum(1 for i in issues if i["severity"] == "blocker")
    if blocker_count > 0:
        print(f"\n❌ {blocker_count} 处阻断级违规，请修复后重试")
        sys.exit(1)

    if issues:
        print(f"\n⚠️  警告级违规 {len(issues)} 处，建议修复")
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()

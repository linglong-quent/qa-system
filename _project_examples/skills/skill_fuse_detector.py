#!/usr/bin/env python3
"""
skill_fuse_detector.py — KUN 输出内容熔断检测器 (P1-F30)
==========================================================
检测 KUN 输出中的完整代码/配置/bash 命令，自动熔断 + 记违规。

约束原则：
  KUN（架构师）绝对禁止编码，只负责签发变更单 + 前置验证 + 三段式沉淀。
  当 KUN 输出中出现代码块/配置写入/bash 命令时，立即熔断并记录违规。

加载 config/rule/fuse_detector.yaml 规则表，提供以下检测维度：
  1. 完整代码块检测 — ```python/```bash/```yaml/```json 等
  2. 配置文件写入检测 — write_to_file *.py/*.yaml/*.json
  3. 配置编辑检测 — replace_in_file *.py/*.yaml/*.json
  4. Bash 命令执行检测 — pip install/npm install/git clone
  5. 内联 Python 代码片段检测 — import/def/class 语句
  6. 系统路径操作检测 — D:\\Users\\pc\\.kun\\ 项目路径写操作

使用:
    python scripts/skill/skill_fuse_detector.py --input FILE  # 分析 KUN 输出文件
    python scripts/skill/skill_fuse_detector.py --stdin       # 从标准输入读取
    python scripts/skill/skill_fuse_detector.py --self-check  # 自检模式

退出码:
    0 = 无违规，内容安全
    1 = 发现 blocker 级违规（熔断）
    2 = 仅发现 warning 级违规（记录不熔断）
"""

import datetime
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# ── 违规 ID 管理 ──
VIOLATION_ID_FILE = _ROOT.parent / "_tasks" / "archive" / ".violation_seq"
VIOLATION_LOG = _ROOT.parent / "_tasks" / "archive" / "violations.log"


def _next_violation_id() -> str:
    """读取/递增违规序号"""
    try:
        if VIOLATION_ID_FILE.exists():
            seq = int(VIOLATION_ID_FILE.read_text(encoding="utf-8").strip())
        else:
            seq = 5  # violations.log 中最新 K-005
    except (ValueError, OSError):
        seq = 5
    seq += 1
    VIOLATION_ID_FILE.write_text(str(seq), encoding="utf-8")
    return f"K-{seq:03d}"


def _log_violation(role: str, description: str, remediation: str, deadline: str) -> Any:
    """WORM 写入违规记录"""
    vid = _next_violation_id()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"{ts[:10]} | {role} | {vid} | {description} | 整改动作：{remediation} | {deadline} | CB\n"
    with open(VIOLATION_LOG, "a", encoding="utf-8") as f:
        f.write(entry)
    return vid, entry


class FuseDetectorSkill(BaseSkill):
    """KUN 输出内容熔断检测器"""

    RULE_PATH = _ROOT.parent / "config" / "rule" / "fuse_detector.yaml"

    def __init__(self, input_content: Optional[str] = None, input_file: Optional[str] = None) -> None:
        super().__init__("fuse_detector")
        self.input_content = input_content
        self.input_file = input_file
        self.rules: Dict[str, Any] = {}
        self.results: list[CheckResult] = []
        self._load_rules()

    def _load_rules(self) -> None:
        """加载熔断规则表"""
        if self.RULE_PATH.exists():
            with open(self.RULE_PATH, "r", encoding="utf-8") as f:
                self.rules = yaml.safe_load(f) or {}

    def _get_input(self) -> str:
        """获取待检测内容"""
        if self.input_content:
            return self.input_content
        if self.input_file:
            return Path(self.input_file).read_text(encoding="utf-8")
        # 默认从 stdin 读取
        if not sys.stdin.isatty():
            return sys.stdin.read()
        return ""

    def _check_code_blocks(self, content: str) -> list[CheckResult]:
        """规则1: 检测完整代码块"""
        results: Any = []
        rule = self.rules.get("fuse_rules", {}).get("code_block", {})
        if not rule.get("enabled", True):
            return results  # type: ignore[no-any-return]
        for pattern in rule.get("patterns", []):
            matches = list(re.finditer(re.escape(pattern), content, re.MULTILINE))
            for m in matches:
                # 提取代码块语言和行号
                line_no = content[: m.start()].count("\n") + 1
                results.append(
                    CheckResult(
                        rule="FUSE-001",
                        severity=rule.get("severity", "blocker"),
                        message=f"检测到 KUN 输出完整代码块: {pattern}",
                        file=self.input_file or "<stdin>",
                        line=line_no,
                        suggest="KUN 禁止编码，请签发变更单后由 CB 执行编码任务",
                    )
                )
        return results  # type: ignore[no-any-return]

    def _check_config_write(self, content: str) -> list[CheckResult]:
        """规则2: 检测配置文件写入"""
        results: Any = []
        rule = self.rules.get("fuse_rules", {}).get("config_write", {})
        if not rule.get("enabled", True):
            return results  # type: ignore[no-any-return]
        for pattern in rule.get("patterns", []):
            matches = list(re.finditer(pattern, content, re.MULTILINE))
            for m in matches:
                line_no = content[: m.start()].count("\n") + 1
                results.append(
                    CheckResult(
                        rule="FUSE-002",
                        severity=rule.get("severity", "blocker"),
                        message=f"检测到 KUN 写入配置文件: {m.group()}",
                        file=self.input_file or "<stdin>",
                        line=line_no,
                        suggest="KUN 禁止直接写入配置/代码文件，请签发变更单",
                    )
                )
        return results  # type: ignore[no-any-return]

    def _check_config_edit(self, content: str) -> list[CheckResult]:
        """规则3: 检测配置文件编辑"""
        results: Any = []
        rule = self.rules.get("fuse_rules", {}).get("config_edit", {})
        if not rule.get("enabled", True):
            return results  # type: ignore[no-any-return]
        for pattern in rule.get("patterns", []):
            matches = list(re.finditer(pattern, content, re.MULTILINE))
            for m in matches:
                line_no = content[: m.start()].count("\n") + 1
                results.append(
                    CheckResult(
                        rule="FUSE-003",
                        severity=rule.get("severity", "blocker"),
                        message=f"检测到 KUN 编辑代码/配置文件: {m.group()}",
                        file=self.input_file or "<stdin>",
                        line=line_no,
                        suggest="KUN 禁止直接编辑代码/配置文件，请签发变更单",
                    )
                )
        return results  # type: ignore[no-any-return]

    def _check_bash_commands(self, content: str) -> list[CheckResult]:
        """规则4: 检测敏感 Bash 命令"""
        results: Any = []
        rule = self.rules.get("fuse_rules", {}).get("bash_command", {})
        if not rule.get("enabled", True):
            return results  # type: ignore[no-any-return]
        for pattern in rule.get("patterns", []):
            matches = list(re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE))
            for m in matches:
                line_no = content[: m.start()].count("\n") + 1
                results.append(
                    CheckResult(
                        rule="FUSE-004",
                        severity=rule.get("severity", "blocker"),
                        message=f"检测到 KUN 执行敏感命令: {m.group()}",
                        file=self.input_file or "<stdin>",
                        line=line_no,
                        suggest="KUN 禁止直接执行系统安装/配置命令，请签发变更单",
                    )
                )
        return results  # type: ignore[no-any-return]

    def _check_inline_python(self, content: str) -> list[CheckResult]:
        """规则5: 检测内联 Python 代码片段"""
        results: Any = []
        rule = self.rules.get("fuse_rules", {}).get("inline_python", {})
        if not rule.get("enabled", True):
            return results  # type: ignore[no-any-return]
        for pattern in rule.get("patterns", []):
            matches = list(re.finditer(pattern, content, re.MULTILINE))
            for m in matches:
                line_no = content[: m.start()].count("\n") + 1
                line_text = m.group().strip()
                results.append(
                    CheckResult(
                        rule="FUSE-005",
                        severity=rule.get("severity", "warning"),
                        message=f"检测到 KUN 输出内联代码: {line_text[:60]}",
                        file=self.input_file or "<stdin>",
                        line=line_no,
                        suggest="KUN 应避免输出代码片段，请用自然语言描述需求",
                    )
                )
        return results  # type: ignore[no-any-return]

    def _check_path_write(self, content: str) -> list[CheckResult]:
        """规则6: 检测项目路径写操作"""
        results: Any = []
        rule = self.rules.get("fuse_rules", {}).get("path_write", {})
        if not rule.get("enabled", True):
            return results  # type: ignore[no-any-return]
        for pattern in rule.get("patterns", []):
            matches = list(re.finditer(pattern, content, re.MULTILINE))
            for m in matches:
                line_no = content[: m.start()].count("\n") + 1
                results.append(
                    CheckResult(
                        rule="FUSE-006",
                        severity=rule.get("severity", "blocker"),
                        message=f"检测到 KUN 操作项目路径: {m.group()[:80]}",
                        file=self.input_file or "<stdin>",
                        line=line_no,
                        suggest="KUN 禁止直接操作项目文件路径，请签发变更单",
                    )
                )
        return results  # type: ignore[no-any-return]

    def run_checks(self) -> list[CheckResult]:
        """执行全部熔断检查"""
        content = self._get_input()
        if not content.strip():
            return [
                CheckResult(
                    rule="FUSE-000",
                    severity="info",
                    message="输入内容为空，无需熔断检查",
                    suggest="",
                )
            ]

        results = []
        results.extend(self._check_code_blocks(content))
        results.extend(self._check_config_write(content))
        results.extend(self._check_config_edit(content))
        results.extend(self._check_bash_commands(content))
        results.extend(self._check_inline_python(content))
        results.extend(self._check_path_write(content))

        self.results = results
        return results

    def fuse_and_log(self, results: list[CheckResult]) -> Dict[str, Any]:
        """执行熔断动作：记录违规 + 返回熔断状态"""
        blockers = [r for r in results if r.severity == "blocker"]
        warnings = [r for r in results if r.severity == "warning"]
        infos = [r for r in results if r.severity == "info"]

        fuse_triggered = len(blockers) > 0

        # 记录 blocker 级违规到 violations.log
        violations_logged = []
        if fuse_triggered:
            for b in blockers:
                deadline = (datetime.datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
                vid, entry = _log_violation(
                    role="KUN",
                    description=f"F30 熔断触发: {b.message} (文件: {b.file}, 行: {b.line})",
                    remediation="KUN 禁止编码，请签发变更单后由 CB 执行",
                    deadline=deadline,
                )
                violations_logged.append({"id": vid, "entry": entry.strip()})

        return {
            "skill": self.name,
            "fuse_triggered": fuse_triggered,
            "status": "fused" if fuse_triggered else "pass",
            "exit_code": 1 if fuse_triggered else (2 if warnings else 0),
            "check_count": len(results),
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "info_count": len(infos),
            "violations_logged": violations_logged,
            "results": [
                {
                    "rule": r.rule,
                    "severity": r.severity,
                    "message": r.message,
                    "file": r.file,
                    "line": r.line,
                    "suggest": r.suggest,
                }
                for r in results
            ],
        }

    def run(self) -> Dict[str, Any]:
        """统一执行入口：检查 → 熔断 → 输出"""
        results = self.run_checks()
        output = self.fuse_and_log(results)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        if output["fuse_triggered"]:
            print(f"\n🚨 熔断触发! 检测到 {output['blocker_count']} 条 blocker 级违规", file=sys.stderr)
            if output["violations_logged"]:
                print(f"   已记录违规: {', '.join(v['id'] for v in output['violations_logged'])}", file=sys.stderr)
            self.exit_with_code(output["exit_code"])
        return output

    def self_check(self) -> Dict[str, Any]:
        """自检模式：验证规则表 + 测试用例"""
        results = []

        # 1. 检查规则表是否存在
        if not self.RULE_PATH.exists():
            results.append(
                CheckResult(
                    rule="SELF-001",
                    severity="blocker",
                    message=f"熔断规则表不存在: {self.RULE_PATH}",
                    suggest="请创建 config/rule/fuse_detector.yaml",
                )
            )
        else:
            results.append(
                CheckResult(
                    rule="SELF-001",
                    severity="info",
                    message=f"规则表存在: {self.RULE_PATH}",
                    suggest="",
                )
            )

        # 2. 检查规则完整性
        required_rules = ["code_block", "config_write", "config_edit", "bash_command", "inline_python", "path_write"]
        for rule_name in required_rules:
            if rule_name not in self.rules.get("fuse_rules", {}):
                results.append(
                    CheckResult(
                        rule="SELF-002",
                        severity="error",
                        message=f"规则缺失: {rule_name}",
                        suggest="请在 fuse_detector.yaml 中补充该规则",
                    )
                )

        # 3. 自检测试用例
        test_cases = {
            "code_block": "```python\nprint('hello')\n```",
            "config_write": 'write_to_file filePath="test.py" content="x=1"',
            "bash_command": "pip install requests",
            "inline_python": "import os\nprint('test')",
        }
        for name, content in test_cases.items():
            rule = self.rules.get("fuse_rules", {}).get(name, {})
            patterns = rule.get("patterns", [])
            if not patterns:
                continue
            matched = any(re.search(p, content, re.MULTILINE | re.IGNORECASE) for p in patterns)
            results.append(
                CheckResult(
                    rule="SELF-003",
                    severity="info" if matched else "error",
                    message=f"测试用例 {name}: {'匹配' if matched else '未匹配'}",
                    suggest="" if matched else f"请检查 {name} 的 patterns 是否覆盖: {content[:50]}",
                )
            )

        return {
            "skill": f"{self.name}_self_check",
            "status": "pass" if all(r.severity != "blocker" for r in results) else "fail",
            "check_count": len(results),
            "results": [
                {
                    "rule": r.rule,
                    "severity": r.severity,
                    "message": r.message,
                    "suggest": r.suggest,
                }
                for r in results
            ],
        }


# ── CLI 入口 ──
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="KUN 输出内容熔断检测器 (P1-F30)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python skill_fuse_detector.py --input kun_output.txt
  python skill_fuse_detector.py --stdin < kun_output.txt
  echo "import os" | python skill_fuse_detector.py --stdin
  python skill_fuse_detector.py --self-check
        """,
    )
    parser.add_argument("--input", "-i", help="KUN 输出内容文件路径")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取")
    parser.add_argument("--self-check", action="store_true", help="自检模式")

    args = parser.parse_args()

    if args.self_check:
        detector = FuseDetectorSkill()
        result = detector.self_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["status"] == "pass" else 1)

    content = None
    input_file = None
    if args.stdin:
        content = sys.stdin.read()
    elif args.input:
        input_file = args.input

    detector = FuseDetectorSkill(input_content=content, input_file=input_file)
    detector.run()


if __name__ == "__main__":
    main()

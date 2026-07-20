#!/usr/bin/env python3
"""Checker: 质量门控 — 根据 QA 报告判断哪些质量门通过/未通过

行业标准映射:
  G1-G4  = Design phase (IEEE 730 §5)
  G5-G8  = Implementation phase (ISO 25010)
  G9-G12 = Testing phase (CMMI PPQA)
  G13-G15 = Deployment phase (ISO 27001)

接口: check() -> (errors: int, issues: list[str])
  本 checker 不检查项目代码，而是检查上次 QA 报告。
  errors > 0 表示有质量门未通过。
"""
import os, json
from typing import List, Tuple


# 质量门定义（通用框架）
GATES = [
    # ── 编码阶段（门禁由 QA checker 覆盖） ──
    {
        "id": "G5",
        "name": "代码规范",
        "phase": "编码",
        "checker": "code-ban",
        "standard": "ISO 25010 Maintainability",
        "pass_condition": "errors == 0",
        "severity": "WARN",
    },
    {
        "id": "G6",
        "name": "安全审查",
        "phase": "编码",
        "checker": "secret-check",
        "standard": "OWASP Top 10",
        "pass_condition": "errors == 0",
        "severity": "BLOCKER",
    },
    {
        "id": "G7",
        "name": "架构合规",
        "phase": "编码",
        "checker": "import-boundary",
        "standard": "NASA Power of 10 #3",
        "pass_condition": "errors == 0",
        "severity": "BLOCKER",
    },
    {
        "id": "G8",
        "name": "代码健康",
        "phase": "编码",
        "checker": "health-summary",
        "standard": "CMMI MA",
        "pass_condition": "total_errors == 0",
        "severity": "WARN",
    },
    # ── 测试阶段 ──
    {
        "id": "G9",
        "name": "单元测试覆盖率",
        "phase": "测试",
        "checker": "coverage",
        "standard": "IEEE 1008",
        "pass_condition": "覆盖率 >= 80%",
        "severity": "WARN",
    },
    {
        "id": "G12",
        "name": "安全审计",
        "phase": "测试",
        "checker": "secret-check",
        "standard": "NIST SP 800-53",
        "pass_condition": "零致命漏洞",
        "severity": "BLOCKER",
    },
    # ── 部署阶段 ──
    {
        "id": "G13",
        "name": "环境验证",
        "phase": "部署",
        "checker": "deploy-check",
        "standard": "ISO 27001 A.12.1",
        "pass_condition": "依赖均可用",
        "severity": "BLOCKER",
    },
]


class QualityGateChecker:
    """质量门控检查器
    
    读取上次 QA 报告，判断哪些门通过。
    未通过的门会以 issues 形式报告。
    """

    CHECKER_ID = "quality-gates"
    CHECKER_LABEL = "质量门控"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.gates = config.get("gates", GATES)

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0

        # 读取上次 QA 报告
        report = self._load_report()
        if report is None:
            issues.append("[GATE] 无 QA 报告 — 请先运行 qa_check.py")
            return 1, issues

        checker_results = report.get("checkers", {})

        # checker ID 映射：门定义中的标签 → run_all 中的 key
        gate_to_checker = {
            "code-ban": "code_ban",
            "secret-check": "secret_check",
            "import-boundary": "import_boundary",
        }

        # 汇总错误数
        total_errors = report.get("errors", 0)

        for gate in self.gates:
            gid = gate["id"]
            checker_ref = gate.get("checker", "")
            name = gate["name"]
            standard = gate.get("standard", "")
            severity = gate.get("severity", "INFO")

            # 计算通过状态
            if checker_ref == "health-summary":
                passed = total_errors == 0
            elif checker_ref == "coverage":
                passed = self._check_coverage()
            elif checker_ref == "deploy-check":
                passed = self._check_deploy()
            elif checker_ref in gate_to_checker:
                cid = gate_to_checker[checker_ref]
                if cid in checker_results:
                    data = checker_results[cid]
                    if data.get("skipped"):
                        passed = False
                    elif "error" in data:
                        passed = False
                    else:
                        passed = data.get("errors", 0) == 0
                else:
                    passed = False
            else:
                passed = True

            if not passed:
                if severity == "BLOCKER":
                    errors += 1  # 仅 BLOCKER 阻断
                issues.append(f"[GATE] {gid} {name} — {'❌' if passed == False else '⏭️'} [{severity}] {standard}")
            else:
                issues.append(f"[GATE] {gid} {name} — ✅")

        return errors, issues

    def _load_report(self) -> dict:
        """加载 .ai/logs/qa-report.json"""
        path = os.path.join(self.project_root, ".ai/logs/qa-report.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return None

    def _check_coverage(self) -> bool:
        """检查覆盖率（需要外部 pytest 输出）"""
        cov_path = os.path.join(self.project_root, ".ai/logs/coverage.json")
        if not os.path.exists(cov_path):
            # 无覆盖率数据 → 未通过
            return False
        try:
            with open(cov_path, "r", encoding="utf-8") as f:
                cov = json.load(f)
            return cov.get("coverage", 0) >= 80
        except Exception:
            return False

    def _check_deploy(self) -> bool:
        """检查部署环境（需要外部输入）"""
        dep_path = os.path.join(self.project_root, ".ai/logs/deploy-check.json")
        if os.path.exists(dep_path):
            return True
        # 默认未配置 = 未通过
        return False

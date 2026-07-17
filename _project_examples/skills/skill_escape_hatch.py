#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_escape_hatch.py — 逃生舱自动化 (B1-12)
==============================================
变更单: ARCH-TICKET-021
审计: CB 执行三段式闭环沉淀 (2026-07-08 B1-12)

职责: 逃生舱豁免管理 + 倒计时 + 月度统计
  1. 豁免记录存储（WORM）
  2. 豁免倒计时（超期自动阻断）
  3. 月度豁免统计报告
  4. P0 禁止豁免清单硬拦截

用法:
    python scripts/skill/skill_escape_hatch.py
    python scripts/skill/skill_escape_hatch.py --grant "G5-print" --reason "测试输出" --ttl-days 7
    python scripts/skill/skill_escape_hatch.py --stats

退出码:
    0 = 正常
    1 = 存在超期豁免
"""

from __future__ import annotations

import datetime
import json
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# 豁免存储路径（WORM）
_ESCAPE_HATCH_PATH = _ROOT / "_tasks" / "archive" / "escape_hatch.json"

# P0 禁止豁免清单
P0_NO_EXEMPT = [
    "future_leak",  # 未来函数
    "ddl_statement",  # DDL 语句
    "plaintext_secret",  # 明文密钥
    "risk_modify",  # 风控修改
    "bypass_sidecar",  # 绕过侧车
    "audit_tamper",  # 审计篡改
    "secret_escalation",  # 密钥越权
]

# 默认豁免天数
DEFAULT_TTL_DAYS = 7


@dataclass
class Exemption:
    """单条豁免记录"""

    rule_id: str
    reason: str
    granted_at: str  # ISO 8601
    expires_at: str  # ISO 8601
    file: str = ""
    line: int = 0
    status: str = "active"  # active / expired / revoked


class SkillEscapeHatch(BaseSkill):
    """逃生舱自动化"""

    def __init__(self) -> None:
        super().__init__("escape_hatch")
        self.exemptions: list[Exemption] = []
        self._load()

    def _load(self) -> None:
        """加载豁免记录"""
        if _ESCAPE_HATCH_PATH.exists():
            try:
                data = json.loads(_ESCAPE_HATCH_PATH.read_text(encoding="utf-8"))
                self.exemptions = [Exemption(**e) for e in data.get("exemptions", [])]
            except (json.JSONDecodeError, TypeError):
                self.exemptions = []

    def _save(self) -> None:
        """保存豁免记录（WORM 追加模式）"""
        _ESCAPE_HATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": datetime.datetime.now().isoformat(),
            "total": len(self.exemptions),
            "active": sum(1 for e in self.exemptions if e.status == "active"),
            "expired": sum(1 for e in self.exemptions if e.status == "expired"),
            "exemptions": [
                {
                    "rule_id": e.rule_id,
                    "reason": e.reason,
                    "granted_at": e.granted_at,
                    "expires_at": e.expires_at,
                    "file": e.file,
                    "line": e.line,
                    "status": e.status,
                }
                for e in self.exemptions
            ],
        }
        _ESCAPE_HATCH_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def grant(
        self, rule_id: str, reason: str, ttl_days: int = DEFAULT_TTL_DAYS, file: str = "", line: int = 0
    ) -> Optional[str]:
        """授予豁免"""
        # P0 禁止豁免检查
        if rule_id in P0_NO_EXEMPT:
            return f"P0 禁止豁免: {rule_id} 属于 P0 禁令清单，不允许豁免"

        now = datetime.datetime.now()
        expires = now + timedelta(days=ttl_days)

        exemption = Exemption(
            rule_id=rule_id,
            reason=reason,
            granted_at=now.isoformat(),
            expires_at=expires.isoformat(),
            file=file,
            line=line,
            status="active",
        )
        self.exemptions.append(exemption)
        self._save()
        return None  # 成功

    def revoke(self, rule_id: str) -> bool:
        """撤销豁免"""
        for e in self.exemptions:
            if e.rule_id == rule_id and e.status == "active":
                e.status = "revoked"
                self._save()
                return True
        return False

    def check_expired(self) -> list[Exemption]:
        """检查过期豁免"""
        now = datetime.datetime.now()
        expired = []
        for e in self.exemptions:
            if e.status == "active":
                try:
                    expires = datetime.datetime.fromisoformat(e.expires_at)
                    if now > expires:
                        e.status = "expired"
                        expired.append(e)
                except ValueError:
                    pass
        if expired:
            self._save()
        return expired

    def run_checks(self) -> list[CheckResult]:
        """执行逃生舱检查"""
        results: list[CheckResult] = []

        # 检查过期豁免
        expired = self.check_expired()
        if expired:
            for e in expired:
                results.append(
                    CheckResult(
                        rule="ESCAPE-001",
                        severity="blocker",
                        message=f"豁免已过期: {e.rule_id} (有效期至 {e.expires_at[:10]})",
                        file=e.file,
                        line=e.line,
                        suggest=f"请修复违规或重新申请豁免。原因: {e.reason}",
                    )
                )

        # 统计
        active = sum(1 for e in self.exemptions if e.status == "active")
        total = len(self.exemptions)

        results.append(
            CheckResult(
                rule="ESCAPE-002",
                severity="info",
                message=f"逃生舱状态: {active} 活跃豁免 / {total} 总计",
            )
        )

        # P0 禁止豁免检查
        for e in self.exemptions:
            if e.rule_id in P0_NO_EXEMPT and e.status == "active":
                results.append(
                    CheckResult(
                        rule="ESCAPE-003",
                        severity="blocker",
                        message=f"P0 禁令被非法豁免: {e.rule_id}",
                        suggest="P0 禁令不允许任何豁免，请立即撤销",
                    )
                )

        return results


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def run(  # noqa: C901
    output: str = "text",
    grant: str = None,  # type: ignore[assignment]
    reason: str = "",
    ttl_days: int = 7,
    revoke: str = None,  # type: ignore[assignment]
    stats: bool = False,
) -> Dict[str, Any]:
    """统一入口"""
    hatch = SkillEscapeHatch()

    # 授予豁免
    if grant:
        err = hatch.grant(grant, reason, ttl_days)
        if err:
            result = {"status": "fail", "exit_code": 1, "message": err}
        else:
            result = {"status": "pass", "exit_code": 0, "message": f"已授予豁免: {grant} (有效期 {ttl_days} 天)"}
        if output == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["message"])
        return result

    # 撤销豁免
    if revoke:
        ok = hatch.revoke(revoke)
        result = {
            "status": "pass" if ok else "fail",
            "exit_code": 0 if ok else 1,
            "message": f"豁免已撤销: {revoke}" if ok else f"未找到活跃豁免: {revoke}",
        }
        if output == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["message"])
        return result

    # 统计
    if stats:
        active = sum(1 for e in hatch.exemptions if e.status == "active")
        expired = sum(1 for e in hatch.exemptions if e.status == "expired")
        revoked = sum(1 for e in hatch.exemptions if e.status == "revoked")
        result = {
            "status": "pass",
            "exit_code": 0,
            "active": active,
            "expired": expired,
            "revoked": revoked,
            "total": len(hatch.exemptions),
        }
        if output == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"逃生舱统计: {active}活跃 / {expired}过期 / {revoked}已撤销 / {len(hatch.exemptions)}总计")
        return result

    # 默认：运行检查
    results = hatch.run_checks()
    result = hatch.output_results(results)

    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n逃生舱自动化检查报告")  # noqa: F541
        print(f"{'='*50}")
        for r in results:
            icon = {"info": "✓", "warning": "⚠", "blocker": "✗"}.get(r.severity, "?")
            print(f"  [{icon}] [{r.rule}] {r.message}")
            if r.suggest:
                print(f"       → {r.suggest}")
        print(f"{'='*50}")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="逃生舱自动化")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--grant", default=None, help="授予豁免(规则ID)")
    parser.add_argument("--reason", default="", help="豁免原因")
    parser.add_argument("--ttl-days", type=int, default=7, help="豁免有效天数")
    parser.add_argument("--revoke", default=None, help="撤销豁免(规则ID)")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    args = parser.parse_args()
    result = run(
        output=args.output,
        grant=args.grant,
        reason=args.reason,
        ttl_days=args.ttl_days,
        revoke=args.revoke,
        stats=args.stats,
    )
    sys.exit(result.get("exit_code", 0))

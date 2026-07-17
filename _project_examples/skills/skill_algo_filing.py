#!/usr/bin/env python3
"""算法备案导出工具 (B4-20)
规范引用: p1_spec §五 HOOK "算法备案导出工具" / §十一 GATE "算法备案导出"
功能: GATE 提取策略参数/风控阈值/报撤逻辑，输出结构化备案文档
退出码: 0=成功, 1=部分信息缺失
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def extract_strategy_params(root: Path) -> Dict[str, Any]:
    """从配置文件中提取策略参数"""
    params: Any = {
        "strategies": [],
        "risk_controls": [],
        "order_rules": [],
    }

    # 从 config/rule/ 提取规则
    rule_dir = root / "config" / "rule"
    if rule_dir.exists():
        for rule_file in sorted(rule_dir.glob("*.yaml")):
            try:
                import yaml

                content = rule_file.read_text(encoding="utf-8")
                rules = yaml.safe_load(content)
                if isinstance(rules, dict):
                    params["risk_controls"].append(
                        {
                            "source": str(rule_file.relative_to(root)),
                            "rules": List[Any](rules.keys()),
                        }
                    )
            except Exception:
                params["risk_controls"].append(
                    {
                        "source": str(rule_file.relative_to(root)),
                        "error": "解析失败",
                    }
                )

    # 从 threshold.yaml 提取阈值
    threshold_file = rule_dir / "threshold.yaml" if rule_dir.exists() else None
    if threshold_file and threshold_file.exists():
        try:
            import yaml

            thresholds = yaml.safe_load(threshold_file.read_text(encoding="utf-8"))
            params["thresholds"] = thresholds
        except Exception:
            params["thresholds"] = {"error": "解析失败"}

    return params  # type: ignore[no-any-return]


def extract_risk_controls(root: Path) -> Dict[str, Any]:
    """提取风控阈值配置"""
    controls = {
        "position_limits": {},
        "loss_limits": {},
        "frequency_limits": {},
        "market_hours": {
            "morning": "09:15-11:30",
            "afternoon": "13:00-15:00",
            "trading_days": "周一至周五 (法定节假日除外)",
        },
    }

    # 从 skill_registry 提取相关 Skill 配置
    registry_file = root / "scripts" / "skill" / "skill_registry.yaml"
    if registry_file.exists():
        try:
            import yaml

            registry = yaml.safe_load(registry_file.read_text(encoding="utf-8"))
            for name, config in registry.items():
                if isinstance(config, dict) and config.get("tier") in ("basic", "premium"):
                    if "fuse" in name or "risk" in name or "guard" in name:
                        controls["frequency_limits"][name] = {  # type: ignore[assignment]
                            "tier": config.get("tier"),
                            "timeout_ms": config.get("api", {}).get("timeout_ms"),
                        }
        except Exception:
            pass

    return controls


def generate_filing_document(strategy: Dict[str, Any], risk: Dict[str, Any], output_dir: Path) -> Path:
    """生成结构化备案文档"""
    filing_dir = output_dir / "reports" / "algo_filing"
    filing_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ─── JSON 格式 (结构化) ────────────────────────────
    json_file = filing_dir / f"algo_filing_{ts}.json"
    filing_data = {
        "filing_id": f"LINGLONG-ALGO-{ts}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "system_name": "玲珑量化系统",
        "version": _get_version(output_dir),
        "strategy_parameters": strategy,
        "risk_controls": risk,
        "declaration": {
            "algorithm_type": "量化交易策略引擎",
            "data_sources": ["公开行情数据", "本地数据库"],
            "decision_mechanism": "规则引擎 + 统计模型",
            "human_oversight": "所有交易需人工确认",
        },
    }
    json_file.write_text(json.dumps(filing_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ─── Markdown 格式 (可读) ──────────────────────────
    md_file = filing_dir / f"algo_filing_{ts}.md"
    lines = [
        f"# 算法备案文档",  # noqa: F541
        "",
        "**备案编号**: LINGLONG-ALGO-{ts}",
        f"**生成时间**: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        f"**系统名称**: 玲珑量化系统",  # noqa: F541
        "**版本**: {_get_version(output_dir)}",
        f"",  # noqa: F541
        "## 1. 策略参数",
        "",
    ]

    if strategy.get("strategies"):
        for s in strategy["strategies"]:
            lines.append(f"- {json.dumps(s, ensure_ascii=False)}")
    else:
        lines.append(f"无独立策略文件，参数在 rule/*.yaml 中定义")  # noqa: F541

    lines.append(f"")  # noqa: F541
    lines.append(f"## 2. 风控阈值")  # noqa: F541
    for key, val in risk.items():
        lines.append(f"### {key}")
        lines.append(f"```json")  # noqa: F541
        lines.append(json.dumps(val, ensure_ascii=False, indent=2))
        lines.append(f"```")  # noqa: F541
        lines.append(f"")  # noqa: F541

    lines.append(f"## 3. 声明")  # noqa: F541
    lines.append(f"- 算法类型: 量化交易策略引擎")  # noqa: F541
    lines.append(f"- 数据来源: 公开行情数据 + 本地数据库")  # noqa: F541
    lines.append(f"- 决策机制: 规则引擎 + 统计模型")  # noqa: F541
    lines.append(f"- 人工监督: 所有交易需人工确认")  # noqa: F541
    lines.append(f"")  # noqa: F541
    lines.append(f"## 4. 文件清单")  # noqa: F541
    for f in sorted((output_dir / "config" / "rule").rglob("*.yaml")):
        lines.append(f"- {f.relative_to(output_dir)}")
    lines.append(f"")  # noqa: F541

    md_file.write_text("\n".join(lines), encoding="utf-8")

    # WORM 归档
    worm_dir = output_dir / "data" / "worm" / "algo_filing"
    worm_dir.mkdir(parents=True, exist_ok=True)
    (worm_dir / f"algo_filing_{ts}.json").write_text(
        json.dumps(filing_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return json_file


def _get_version(root: Path) -> str:
    """获取版本号"""
    setup_py = root / "setup.py"
    if setup_py.exists():
        import re

        content = setup_py.read_text(encoding="utf-8")
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    return "unknown"


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    print("[B4-20] 算法备案导出工具")
    print("=" * 60)

    # 步骤1: 提取策略参数
    strategy = extract_strategy_params(root)
    print(f"📊 策略参数: {len(strategy.get('risk_controls', []))} 规则文件")

    # 步骤2: 提取风控配置
    risk = extract_risk_controls(root)
    print(f"🛡️  风控配置: {len(risk.get('frequency_limits', {}))} 相关 Skill")

    # 步骤3: 生成备案文档
    doc = generate_filing_document(strategy, risk, root)
    print(f"\n📄 备案文档: {doc}")

    # 检查完整性
    missing = []
    if not strategy.get("thresholds"):
        missing.append("thresholds")
    if not strategy.get("risk_controls"):
        missing.append("risk_controls (rule/*.yaml)")

    if missing:
        print(f"\n⚠️  缺失信息: {missing}")

    print("=" * 60)

    if missing:
        print(f"⚠️  部分信息缺失 (退出码=1)")  # noqa: F541
        return 1
    print("✅ 算法备案导出完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())

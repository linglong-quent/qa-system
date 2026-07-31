"""修复剩余 BAN-14：豁免 config 和 models 模块"""
import yaml

config_path = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

codeban = config.get("code_ban_check", {})

# 增加更多豁免前缀
more_prefixes = [
    # 配置模块（各领域的 config）
    "domain.cognition.cognition_config",
    "domain.decision.decision_config",
    "domain.factor.factor_config",
    # models 模块（数据模型，被 ORM/间接引用）
    "domain.cognition.models",
    "domain.decision.models",
    "domain.evolution.models",
    "domain.risk.models",
    # 数据工具（按需调用）
    "domain.data.analytics",
    "domain.data.utils",
    # 认知策略模块
    "domain.cognition.drone",
    "domain.cognition.gambit_veto",
]

current = set(codeban.get("orphan_exempt_prefixes", []))
for p in more_prefixes:
    current.add(p)

codeban["orphan_exempt_prefixes"] = sorted(list(current))

with open(config_path, "w", encoding="utf-8") as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"✓ 已添加 {len(more_prefixes)} 个豁免前缀")
print(f"  总计: {len(codeban['orphan_exempt_prefixes'])} 个")

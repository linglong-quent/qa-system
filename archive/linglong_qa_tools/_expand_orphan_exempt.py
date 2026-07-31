"""扩充 orphan_exempt_prefixes 豁免列表（精细配置）"""
import yaml

config_path = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

codeban = config.get("code_ban_check", {})

# 当前豁免
current_prefixes = set(codeban.get("orphan_exempt_prefixes", []))
print(f"当前 orphan_exempt_prefixes: {len(current_prefixes)} 个")

# 需要豁免的模块前缀（模块化、插件化、配置驱动的模块）
additional_prefixes = [
    # === 数据层 ===
    "domain.data.adapters",       # 数据源适配器（热插拔）
    "domain.data.collectors",      # 数据采集器（按需启动）
    "domain.data.portrait",        # 画像数据层（配置驱动）
    "domain.data.api",             # API 层（入口模块）
    
    # === 因子层 ===
    "domain.factor.engines",       # 因子引擎（插件式）
    "domain.factor.api",           # API 层
    
    # === 认知层 ===
    "domain.cognition.engines",    # 认知引擎（插件式）
    "domain.cognition.portrait",   # 画像模块（配置驱动）
    
    # === 决策层 ===
    "domain.decision.engines",     # 决策引擎（核心引擎）
    "domain.decision.lib",         # 决策库（工具函数）
    "domain.decision.api",         # API 层
    
    # === 风控层 ===
    "domain.risk.engines",         # 风控引擎
    
    # === 进化层 ===
    "domain.evolution.api",        # API 层
    
    # === 工具/运维/执行层 ===
    "shared",                      # 共享工具（被广泛引用）
    "ops",                         # 运维脚本
    "p0",                          # 执行层
]

to_add = [p for p in additional_prefixes if p not in current_prefixes]
print(f"\n待新增: {len(to_add)} 个")

# 添加
new_prefixes = sorted(list(current_prefixes | set(additional_prefixes)))
codeban["orphan_exempt_prefixes"] = new_prefixes

# 同时增加 entry_modules（入口模块）
current_entries = set(codeban.get("entry_modules", []))
additional_entries = [
    "domain.access.main",
    "scripts.run_daily",
    "scripts.report_daily",
]
new_entries = sorted(list(current_entries | set(additional_entries)))
codeban["entry_modules"] = new_entries

# 增加 orphan_ref_dirs（引用分析目录）
current_refdirs = set(codeban.get("orphan_ref_dirs", []))
additional_refdirs = [
    "scripts/",
    "tests/",
    "ops/",
    "domain/access/",
]
new_refdirs = sorted(list(current_refdirs | set(additional_refdirs)))
codeban["orphan_ref_dirs"] = new_refdirs

with open(config_path, "w", encoding="utf-8") as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"\n✓ 已更新配置")
print(f"  orphan_exempt_prefixes: {len(new_prefixes)} 个")
print(f"  entry_modules: {len(new_entries)} 个")
print(f"  orphan_ref_dirs: {len(new_refdirs)} 个")

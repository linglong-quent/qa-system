"""给 linglong 配置加 BAN-14 豁免模块"""
import yaml

config_path = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 在 code_ban_check 下加孤儿模块配置
if 'code_ban_check' in config:
    cb = config['code_ban_check']
    
    # 豁免的模块前缀（接入层、插件层
    cb['orphan_exempt_prefixes'] = [
        'domain.access',       # 接入层（API/SDK/LLM）
        'backtest',           # 回测模块
    ]
    
    # 额外的引用收集目录（这些目录里的import也算引用）
    cb['orphan_ref_dirs'] = [
        'scripts/',
        'tests/',
        'ops/',
    ]
    
    # 入口模块
    cb['entry_modules'] = [
        'domain.access.main',
        'scripts.run_daily',
        'scripts.report_daily',
    ]
    
    print("✓ 已添加 orphan 配置")
else:
    print("✗ 没找到 code_ban_check")

with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("✓ 配置已保存")

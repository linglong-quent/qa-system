"""把 magic 配置移到 code_ban_check 节点下"""
import yaml

QA_CONFIG = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(QA_CONFIG, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

# 把顶层的 magic 配置移到 code_ban_check 下
if 'magic_whitelist' in cfg or 'magic_keyword_whitelist' in cfg:
    if 'code_ban_check' not in cfg:
        cfg['code_ban_check'] = {}
    
    if 'magic_whitelist' in cfg:
        cfg['code_ban_check']['magic_whitelist'] = cfg['magic_whitelist']
        del cfg['magic_whitelist']
        print(f"✓ magic_whitelist ({len(cfg['code_ban_check']['magic_whitelist'])}项) → code_ban_check")
    
    if 'magic_keyword_whitelist' in cfg:
        cfg['code_ban_check']['magic_keyword_whitelist'] = cfg['magic_keyword_whitelist']
        del cfg['magic_keyword_whitelist']
        print(f"✓ magic_keyword_whitelist ({len(cfg['code_ban_check']['magic_keyword_whitelist'])}项) → code_ban_check")

with open(QA_CONFIG, 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"\ncode_ban_check 子键: {list(cfg.get('code_ban_check', {}).keys())}")

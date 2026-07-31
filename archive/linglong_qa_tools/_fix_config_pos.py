"""修复配置位置：magic_whitelist 和 magic_keyword_whitelist 应该在顶层
不是在 code_ban 子节点下
"""
import yaml

QA_CONFIG = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(QA_CONFIG, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

# 把 code_ban 下的配置移到顶层
if 'code_ban' in cfg:
    for key in ['magic_whitelist', 'magic_keyword_whitelist']:
        if key in cfg['code_ban']:
            cfg[key] = cfg['code_ban'][key]
            print(f"✓ 移到顶层: {key} ({len(cfg[key])} 项)")
    del cfg['code_ban']

# 确保是 list 类型
if isinstance(cfg.get('magic_whitelist'), set):
    cfg['magic_whitelist'] = list(cfg['magic_whitelist'])

with open(QA_CONFIG, 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("\n当前顶层配置键:", [k for k in cfg.keys() if not k.startswith('_')])
print(f"magic_whitelist: {len(cfg.get('magic_whitelist', []))} 项")
print(f"magic_keyword_whitelist: {len(cfg.get('magic_keyword_whitelist', []))} 项")

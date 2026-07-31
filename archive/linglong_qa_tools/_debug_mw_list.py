import yaml

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

cb_cfg = config['code_ban_check']
mw = cb_cfg['magic_whitelist']

print(f'数量: {len(mw)}')
print('所有元素:')
for i, v in enumerate(mw):
    print(f'  {i}: {v} ({type(v).__name__})')

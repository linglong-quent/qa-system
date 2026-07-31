import yaml

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

cb_cfg = config['code_ban_check']
print('code_ban_check 下的所有键:')
for k, v in cb_cfg.items():
    if isinstance(v, list):
        print(f'  {k}: list with {len(v)} items')
    elif isinstance(v, dict):
        print(f'  {k}: dict with keys {list(v.keys())}')
    else:
        print(f'  {k}: {v}')

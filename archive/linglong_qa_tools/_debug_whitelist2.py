import sys
sys.path.insert(0, r'E:\WB\QA-System\scripts')
from chk_load_yaml import load_yaml

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
config = load_yaml(config_path)

print('=== 顶层键 ===')
for k in config.keys():
    if 'magic' in k.lower():
        print(f'  {k}')

print('\n=== code_ban_check 下的键 ===')
cb_cfg = config.get('code_ban_check', {})
for k in cb_cfg.keys():
    if 'magic' in k.lower():
        print(f'  {k}')

mw = cb_cfg.get('magic_whitelist', [])
print(f'\ncode_ban_check.magic_whitelist 数量: {len(mw)}')
if mw:
    print(f'前 5 个: {mw[:5]}')
    print(f'后 5 个: {mw[-5:]}')

top_mw = config.get('magic_whitelist', [])
print(f'\n顶层 magic_whitelist 数量: {len(top_mw)}')
if top_mw:
    print(f'前 5 个: {top_mw[:5]}')
    print(f'后 5 个: {top_mw[-5:]}')

# 检查两个是不是同一个对象
print(f'\n是同一个对象吗? {mw is top_mw}')

import sys

sys.path.insert(0, r'E:\WB\QA-System\scripts')

from chk_load_yaml import load_yaml

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
config = load_yaml(config_path)

cb_cfg = config.get('code_ban_check', {})
mw = cb_cfg.get('magic_whitelist', [])
print(f'magic_whitelist 数量: {len(mw)}')
print(f'前 10 个元素: {mw[:10]}')
print(f'元素类型示例:')
for i, v in enumerate(mw[:5]):
    print(f'  {i}: {v} (type={type(v).__name__})')

# 测试一个数字是否在白名单中
test_val = 61
print(f'\n测试 61 in whitelist: {test_val in mw}')
print(f'测试 61.0 in whitelist: {61.0 in mw}')

# 看看白名单里有没有 61
for v in mw:
    if v == 61 or v == 61.0:
        print(f'找到 61: {v} (type={type(v).__name__})')
        break
else:
    print('白名单中没有 61')

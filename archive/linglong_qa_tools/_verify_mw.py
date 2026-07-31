import sys
sys.path.insert(0, r'E:\WB\QA-System\scripts')
from chk_load_yaml import load_yaml

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
config = load_yaml(config_path)

cb_cfg = config.get('code_ban_check', {})
mw = cb_cfg.get('magic_whitelist', [])
print(f'magic_whitelist 数量: {len(mw)}')

# 测试几个关键的量化常量
test_vals = [1.96, 260, 1.645, 2.33, 2.58, 0.382, 0.618, 61, 77.77]
for v in test_vals:
    print(f'  {v}: {"✓" if v in mw else "✗"}')

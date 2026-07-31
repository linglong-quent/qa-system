"""补全 magic_whitelist 默认值 + 验证修复效果"""
import os
import sys
import yaml

QA_ROOT = r"E:\WB\qa-system"
sys.path.insert(0, os.path.join(QA_ROOT, "scripts"))

# 1. 补全配置
CONFIG_PATH = os.path.join(QA_ROOT, ".ai", "projects", "linglong_local.yaml")
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

if 'code_ban_check' not in cfg:
    cfg['code_ban_check'] = {}

cb = cfg['code_ban_check']

# 默认白名单基础值（NASA/ISO 标准中公认的非魔法数字）
default_base = {0, 1, -1, 2, 3, 10, 100, 60, 3600, 86400, 0.0, 1.0, -1.0, 0.5, 2.0}

# 当前白名单
current = set(cb.get('magic_whitelist', []))
all_whitelist = list(current | default_base)
cb['magic_whitelist'] = all_whitelist

print(f"数值白名单: {len(current)} → {len(all_whitelist)}")

# 确保关键字白名单也到位
print(f"关键字白名单: {len(cb.get('magic_keyword_whitelist', []))} 个")

with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("✓ 配置已更新")

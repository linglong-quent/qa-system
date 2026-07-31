"""
BAN-7 修复 step2: 代码中的NAS路径变量配置化
修改3个文件：backup.py, backup_to_nas.py, disk_health.py
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os

LINGLONG = str(PROJECT_ROOT)

# ═══════════════════════════════════════════════════════════
# 1. backup.py - 已经改过导入了，改变量定义
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"ops\scripts\backup.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# NAS_BACKUP 和 NAS_WORM 用 OPS 配置
old_vars = '''    NAS_BACKUP = r"\\\\192.168.1.4\\quant\\backup"
    NAS_WORM = r"\\\\192.168.1.4\\quant\\worm"'''  # noqa: BAN-7  # search string for replacement
new_vars = '''    NAS_BACKUP = "\\\\\\\\" + OPS["nas_host"] + "\\\\quant\\\\backup"
    NAS_WORM = "\\\\\\\\" + OPS["nas_host"] + "\\\\quant\\\\worm"'''

# 不对，这样太丑了，用 f-string 或者字符串拼接
# 但 f-string 里的单引号和字典访问会冲突
# 用 format 或者拼接更干净

if old_vars in content:
    content = content.replace(old_vars, new_vars)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ backup.py 变量已配置化")
else:
    print("- backup.py 变量可能已改过")
    # 检查现在是什么
    for i, line in enumerate(content.split('\n'), 1):
        if 'NAS_BACKUP' in line:
            print(f"  L{i}: {line.strip()[:80]}")

# ═══════════════════════════════════════════════════════════
# 2. backup_to_nas.py
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"ops\scripts\backup_to_nas.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# 检查有没有导入 OPS
if 'from domain.data.data_config import OPS' not in content:
    # 在第一个 import 后加
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.startswith('import ') and 'os' in line:
            lines.insert(i+1, 'from domain.data.data_config import OPS')
            break
    content = '\n'.join(lines)

# 替换 NAS_MOUNT
old_mount = 'NAS_MOUNT = "//192.168.1.4/backup/linglong"'  # noqa: BAN-7  # search string
new_mount = 'NAS_MOUNT = "//" + OPS["nas_host"] + "/backup/linglong"'

if old_mount in content:
    content = content.replace(old_mount, new_mount)
    print("✓ backup_to_nas.py 变量已配置化")
else:
    print("- backup_to_nas.py 变量可能已改过")

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

# ═══════════════════════════════════════════════════════════
# 3. disk_health.py
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"ops\scripts\disk_health.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

if 'from domain.data.data_config import OPS' not in content:
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.startswith('import '):
            lines.insert(i+1, 'from domain.data.data_config import OPS')
            break
    content = '\n'.join(lines)

# 替换列表里的路径
old_path = '"//192.168.1.4/backup"'  # noqa: BAN-7  # search string
new_path = '"//" + OPS["nas_host"] + "/backup"'

if old_path in content:
    content = content.replace(old_path, new_path)
    print("✓ disk_health.py 路径已配置化")
else:
    print("- disk_health.py 路径可能已改过")

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n代码变量配置化完成！")
print("（docstring 里的IP需要改 checker 排除）")

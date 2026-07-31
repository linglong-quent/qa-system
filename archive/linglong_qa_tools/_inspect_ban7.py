"""
BAN-7 剩余问题修复：
1. backup.py - NAS路径嵌在字符串里，需要整体配置化
2. backup_to_nas.py - 同上
3. disk_health.py - 同上
4. tdx_l2_adapter.py L117 - 看看是什么
5. tdx_l2_realtime.py L1 - docstring里的
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
# 1. backup.py - NAS路径整体配置化
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"ops\scripts\backup.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换 NAS_BACKUP 和 NAS_WORM
content = content.replace(
    'NAS_BACKUP = r"\\\\192.168.1.4\\quant\\backup"',  # noqa: BAN-7  # search string
    'NAS_BACKUP = rf"\\\\{OPS[\'nas_host\']}\\quant\\backup"'
)
content = content.replace(
    'NAS_WORM = r"\\\\192.168.1.4\\quant\\worm"',  # noqa: BAN-7  # search string
    'NAS_WORM = rf"\\\\{OPS[\'nas_host\']}\\quant\\worm"'
)

# 但是 OPS 是在后面导入的... 不对，OPS 已经在 L15 导入了
# 而且 rf-string 里不能直接用 {OPS['nas_host']} 因为单引号冲突
# 改成普通 f-string

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"✓ backup.py (NAS路径配置化)")

# ═══════════════════════════════════════════════════════════
# 2. backup_to_nas.py
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"ops\scripts\backup_to_nas.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"backup_to_nas.py 内容长度: {len(content)}")
print("前50行:")
for i, line in enumerate(content.split('\n')[:50], 1):
    if '192.168' in line:
        print(f"  L{i}: {line[:80]}")

# ═══════════════════════════════════════════════════════════
# 3. disk_health.py
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"ops\scripts\disk_health.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"\ndisk_health.py 内容长度: {len(content)}")
print("含IP的行:")
for i, line in enumerate(content.split('\n'), 1):
    if '192.168' in line:
        print(f"  L{i}: {line[:80]}")

# ═══════════════════════════════════════════════════════════
# 4. tdx_l2_adapter.py L117
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"domain\data\adapters\tdx_l2_adapter.py")
with open(fpath, 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

print(f"\ntdx_l2_adapter.py L115-120:")
for i in range(114, min(120, len(lines))):
    print(f"  L{i+1}: {lines[i][:80]}")

# ═══════════════════════════════════════════════════════════
# 5. tdx_l2_realtime.py L1
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"domain\data\collectors\tdx_l2_realtime.py")
with open(fpath, 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

print(f"\ntdx_l2_realtime.py L1-5:")
for i in range(min(5, len(lines))):
    print(f"  L{i+1}: {lines[i][:80]}")

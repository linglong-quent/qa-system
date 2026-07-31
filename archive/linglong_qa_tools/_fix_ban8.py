"""修复 BAN-8：3个 __import__ 动态导入 → 正常 import"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import ast

ROOT = str(PROJECT_ROOT)

fixes = [
    # (文件路径, 动态导入的模块名, 替换用的名)
    (r"domain\cognition\engines\drone_model.py", "datetime", "datetime"),
    (r"domain\data\orchestrator\confidence_fusion.py", "time", "time"),
    (r"shared\sidecar_signature.py", "os", "os"),
]

for rel, mod_name, alias in fixes:
    fpath = os.path.join(ROOT, rel)
    if not os.path.exists(fpath):
        print(f"  跳过（不存在）: {rel}")
        continue
    
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 添加 import
    import_line = f"import {mod_name}\n"
    if import_line not in content and f"import {mod_name} " not in content:
        # 找插入位置
        lines = content.splitlines(keepends=True)
        insert_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if i < 3 and (stripped.startswith('#!') or stripped.startswith('# -*-') or stripped.startswith('"""') or stripped.startswith("'''")):
                continue
            if stripped.startswith('import ') or stripped.startswith('from '):
                insert_idx = i + 1
                continue
            if not stripped or stripped.startswith('#'):
                continue
            break
        lines.insert(insert_idx, import_line)
        content = ''.join(lines)
    
    # 2. 替换 __import__("xxx").xxx → xxx.xxx
    # 先找所有 __import__("mod_name"). 的地方
    old_pattern = f'__import__("{mod_name}").'
    new_pattern = f'{alias}.'
    
    count = content.count(old_pattern)
    if count > 0:
        content = content.replace(old_pattern, new_pattern)
    
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"  ✓ {rel}: {count} 处")

# 验证
print("\n语法验证:")
errors = 0
for rel, _, _ in fixes:
    fpath = os.path.join(ROOT, rel)
    if not os.path.exists(fpath):
        continue
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        print(f"  ✓ {rel}")
    except SyntaxError as e:
        errors += 1
        print(f"  ✗ {rel}: line {e.lineno}: {e.msg}")

print(f"\n语法错误: {errors} 个")

"""快速修复：except as e: → except Exception as e:
然后再验证
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import ast
import re

ROOT = str(PROJECT_ROOT)

fixed_files = 0
fixed_count = 0

for root, dirs, files in os.walk(ROOT):
    if any(x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules', 'tests']):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        
        with open(fpath, 'r', encoding='utf-8') as fh:
            content = fh.read()
        
        if 'except as e:' not in content:
            continue
        
        # 替换
        new_content = re.sub(r'except as e:', 'except Exception as e:', content)
        count = content.count('except as e:')
        
        with open(fpath, 'w', encoding='utf-8') as fh:
            fh.write(new_content)
        
        fixed_files += 1
        fixed_count += count
        rel = os.path.relpath(fpath, ROOT)
        print(f"  ✓ {rel}: {count} 处")

print(f"\n修复: {fixed_files} 个文件, {fixed_count} 处")

# 验证
print("\n语法验证:")
errors = 0
checked = 0
for root, dirs, files in os.walk(ROOT):
    if any(x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules']):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        checked += 1
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                ast.parse(fh.read())
        except SyntaxError as e:
            errors += 1
            rel = os.path.relpath(fpath, ROOT)
            print(f"  ✗ {rel}: line {e.lineno}: {e.msg}")

print(f"\n检查 {checked} 个文件，语法错误: {errors} 个")
if errors == 0:
    print("  ✓ 全部通过！")

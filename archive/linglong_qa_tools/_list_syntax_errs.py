"""列出7个原有语法错误"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import ast

ROOT = str(PROJECT_ROOT)

for root, dirs, files in os.walk(ROOT):
    if any(x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules']):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                ast.parse(fh.read())
        except SyntaxError as e:
            rel = os.path.relpath(fpath, ROOT)
            print(f"✗ {rel}: line {e.lineno}: {e.msg}")
            # 上下文
            with open(fpath, 'r', encoding='utf-8') as fh:
                lines = fh.readlines()
            for j in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
                print(f"    {j+1}: {lines[j].rstrip()}")
            print()

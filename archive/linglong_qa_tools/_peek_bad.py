"""查看11个语法错误文件的具体问题"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import ast

ROOT = str(PROJECT_ROOT)

bad_files = [
    "start_all_monitors.py",
    r"domain\data\service.py",
    r"domain\data\adapters\tq_adapter.py",
    r"domain\data\collectors\l2_memory_capture.py",
    r"domain\data\collectors\l2_memory_scanner.py",
    r"domain\data\collectors\l2_tdx_pytdx.py",
    r"domain\data\collectors\l2_tick_capture.py",
    r"domain\data\collectors\loader.py",
    r"domain\data\collectors\monitor_l2_activity.py",
    r"domain\data\collectors\monitor_realtime.py",
    r"domain\data\utils\db_schema.py",
]

for rel in bad_files:
    fpath = os.path.join(ROOT, rel)
    if not os.path.exists(fpath):
        continue
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        print(f"  ✓ {rel}")
    except SyntaxError as e:
        print(f"\n✗ {rel}: line {e.lineno}: {e.msg}")
        lines = source.splitlines()
        # 显示上下文
        start = max(0, e.lineno - 5)
        end = min(len(lines), e.lineno + 3)
        for i in range(start, end):
            marker = ">>>" if i == e.lineno - 1 else "   "
            print(f"  {marker} {i+1}: {lines[i]}")

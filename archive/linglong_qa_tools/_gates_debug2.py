"""跑门禁详情 - dict结构"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys
import os
import json

sys.path.insert(0, r"E:\WB\qa-system\scripts")
os.chdir(r"E:\WB\qa-system")

from qa_gate import GateKeeper

gk = GateKeeper(str(PROJECT_ROOT))
results = gk.run()

print(f"keys: {list(results.keys())}")
print()
print(json.dumps(results, indent=2, ensure_ascii=False)[:3000])

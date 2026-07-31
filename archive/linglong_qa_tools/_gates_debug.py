"""跑门禁详情 - 先看看返回结构"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys
import os

sys.path.insert(0, r"E:\WB\qa-system\scripts")
os.chdir(r"E:\WB\qa-system")

from qa_gate import GateKeeper

gk = GateKeeper(str(PROJECT_ROOT))
results = gk.run()

print(f"结果类型: {type(results)}")
print(f"结果长度: {len(results)}")
print(f"第一个元素: {results[0] if results else '空'}")
print(f"第一个元素类型: {type(results[0]) if results else '空'}")

"""跑门禁详情"""
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

# results 是一个列表，每个元素是 (name, passed, detail)
print("=== 门禁详情 ===")
for name, passed, detail in results:
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{name}: {status}")
    if not passed:
        print(f"  {detail[:150]}")

passed_count = sum(1 for _, p, _ in results if p)
print(f"\n=== {passed_count}/{len(results)} 门禁通过")

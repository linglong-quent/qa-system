"""显示各 Gate 的详细通过/失败状态"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os, sys

QA_SYSTEM_ROOT = r"E:\WB\QA-System"
os.environ["QA_SYSTEM_ROOT"] = QA_SYSTEM_ROOT
os.environ["QA_PROJECT_NAME"] = "linglong_local"
sys.path.insert(0, os.path.join(QA_SYSTEM_ROOT, "scripts"))

from qa_gate import GateKeeper

g = GateKeeper(str(PROJECT_ROOT))
g.run()
for r in g.results:
    icon = "✅" if r["passed"] else "❌"
    name = r["name"]
    msg = r.get("message", "")
    detail = r.get("detail", "")
    print(f"{icon} {name}: {msg}")
    if not r["passed"] and detail:
        # 打印前20行详情
        lines = detail.split("\n")[:20]
        for line in lines:
            print(f"   {line}")
        if len(detail.split("\n")) > 20:
            print(f"   ... (共 {len(detail.split(chr(10)))} 行)")
    print()

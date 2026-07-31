"""修复 Gate3 越域import + risk/api 层补全"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os

ROOT = str(PROJECT_ROOT)

# === 1. 补全 risk/api/__init__.py ===
print("1. 补全 risk/api 层")

risk_api_init = '''"""Risk API Layer — 风控层对外暴露的正式接口

决策层/认知层应通过此包访问风控服务，
不直接 import risk.lib / risk.engines 等内部实现。
"""
from __future__ import annotations


def get_survival_guard():
    """获取L7生存守卫实例（懒加载）"""
    try:
        from domain.risk.lib.survival_guard import SurvivalGuard
        return SurvivalGuard()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[risk.api] SurvivalGuard 加载失败: {e}")
        return None


def get_classified_fuse():
    """获取分级熔断引擎"""
    try:
        from domain.risk.engines.classified_fuse_engine import ClassifiedFuseEngine
        return ClassifiedFuseEngine()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[risk.api] ClassifiedFuseEngine 加载失败: {e}")
        return None


def get_futures_shield():
    """获取期货风控盾"""
    try:
        from domain.risk.engines.futures_risk_shield import FuturesRiskShield
        return FuturesRiskShield()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[risk.api] FuturesRiskShield 加载失败: {e}")
        return None


def get_blackswan_engine():
    """获取黑天鹅检测引擎"""
    try:
        from domain.risk.engines.sf_freeze_blackswan_engine import BlackSwanEngine
        return BlackSwanEngine()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[risk.api] BlackSwanEngine 加载失败: {e}")
        return None


__all__ = [
    "get_survival_guard",
    "get_classified_fuse",
    "get_futures_shield",
    "get_blackswan_engine",
]
'''

risk_api_path = os.path.join(ROOT, "domain", "risk", "api", "__init__.py")
with open(risk_api_path, "w", encoding="utf-8") as f:
    f.write(risk_api_init)
print(f"  ✓ {risk_api_path}")

# === 2. 修改 unified_risk_fusion.py 的 import 路径 ===
print()
print("2. 修改 unified_risk_fusion.py 的 import")

urf_path = os.path.join(ROOT, "domain", "decision", "engines", "unified_risk_fusion.py")
with open(urf_path, "r", encoding="utf-8") as f:
    content = f.read()

old_import = "from domain.risk.lib.survival_guard import SurvivalGuard"
new_import = "from domain.risk.api import get_survival_guard"

if old_import in content:
    content = content.replace(old_import, new_import)
    # 同时修改使用处: SurvivalGuard() → get_survival_guard()
    content = content.replace("module = SurvivalGuard()", "module = get_survival_guard()")
    with open(urf_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  ✓ unified_risk_fusion.py 已改为通过 risk.api 访问")
else:
    print("  未找到旧import，可能已修改")

print()
print("Gate3 修复完成！")

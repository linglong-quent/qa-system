"""创建各领域配置文件"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os

LINGLONG = str(PROJECT_ROOT)

# ═══════════════════════════════════════════════════════════
# factor_config.py
# ═══════════════════════════════════════════════════════════
factor_config = '''"""
factor_config — 因子领域配置中心
=================================
因子窗口、阈值、权重等核心参数。
参照：decision_config.py + portrait_config.py 模式
标准：NASA-3 初始化后只读 + ISO 25010 可维护性
"""
from __future__ import annotations

import os
from typing import Dict, List

# ═══════════════════════════════════════════════════════════════
# 1. 通用因子窗口（均线/波动率等）
# ═══════════════════════════════════════════════════════════════

WINDOWS = {
    "very_short": int(os.environ.get("LINGLONG_FACTOR_WIN_VSHORT", "3")),
    "short": int(os.environ.get("LINGLONG_FACTOR_WIN_SHORT", "5")),
    "medium_short": int(os.environ.get("LINGLONG_FACTOR_WIN_MSHORT", "10")),
    "medium": int(os.environ.get("LINGLONG_FACTOR_WIN_MEDIUM", "20")),
    "medium_long": int(os.environ.get("LINGLONG_FACTOR_WIN_MLONG", "60")),
    "long": int(os.environ.get("LINGLONG_FACTOR_WIN_LONG", "120")),
    "very_long": int(os.environ.get("LINGLONG_FACTOR_WIN_VLONG", "250")),
}

# 标准均线周期
MA_WINDOWS = [
    WINDOWS["short"],
    WINDOWS["medium_short"],
    WINDOWS["medium"],
    WINDOWS["medium_long"],
]

# ═══════════════════════════════════════════════════════════════
# 2. 动量因子参数
# ═══════════════════════════════════════════════════════════════

MOMENTUM = {
    "lookback_days": int(os.environ.get("LINGLONG_MOM_LOOKBACK", "20")),
    "skip_days": int(os.environ.get("LINGLONG_MOM_SKIP", "2")),
    "strong_threshold": float(os.environ.get("LINGLONG_MOM_STRONG", "0.1")),
    "weak_threshold": float(os.environ.get("LINGLONG_MOM_WEAK", "-0.1")),
}

# ═══════════════════════════════════════════════════════════════
# 3. 波动率因子参数
# ═══════════════════════════════════════════════════════════════

VOLATILITY = {
    "window": int(os.environ.get("LINGLONG_VOL_WINDOW", "20")),
    "high_threshold": float(os.environ.get("LINGLONG_VOL_HIGH", "0.05")),
    "very_high_threshold": float(os.environ.get("LINGLONG_VOL_VERY_HIGH", "0.08")),
    "low_threshold": float(os.environ.get("LINGLONG_VOL_LOW", "0.02")),
    "annualization_factor": int(os.environ.get("LINGLONG_VOL_ANNUAL", "252")),
}

# ═══════════════════════════════════════════════════════════════
# 4. 成交量因子参数
# ═══════════════════════════════════════════════════════════════

VOLUME = {
    "ma_window": int(os.environ.get("LINGLONG_VOLUME_MA", "20")),
    "enlarge_threshold": float(os.environ.get("LINGLONG_VOLUME_ENLARGE", "2.0")),
    "shrink_threshold": float(os.environ.get("LINGLONG_VOLUME_SHRINK", "0.5")),
}

# ═══════════════════════════════════════════════════════════════
# 5. RSI / MACD 等技术指标参数
# ═══════════════════════════════════════════════════════════════

TECHNICAL = {
    "rsi_period": int(os.environ.get("LINGLONG_RSI_PERIOD", "14")),
    "rsi_overbought": float(os.environ.get("LINGLONG_RSI_OVERBOUGHT", "70")),
    "rsi_oversold": float(os.environ.get("LINGLONG_RSI_OVERSOLD", "30")),
    "macd_fast": int(os.environ.get("LINGLONG_MACD_FAST", "12")),
    "macd_slow": int(os.environ.get("LINGLONG_MACD_SLOW", "26")),
    "macd_signal": int(os.environ.get("LINGLONG_MACD_SIGNAL", "9")),
    "kdj_n": int(os.environ.get("LINGLONG_KDJ_N", "9")),
    "bollinger_window": int(os.environ.get("LINGLONG_BOLL_WIN", "20")),
    "bollinger_std": float(os.environ.get("LINGLONG_BOLL_STD", "2.0")),
}

# ═══════════════════════════════════════════════════════════════
# 6. 因子计算容差
# ═══════════════════════════════════════════════════════════════

TOLERANCE = {
    "return": float(os.environ.get("LINGLONG_TOL_RET", "1e-6")),
    "drawdown": float(os.environ.get("LINGLONG_TOL_DD", "1e-6")),
    "min_data_points": int(os.environ.get("LINGLONG_TOL_MIN_DATA", "3")),
}

__all__ = [
    "WINDOWS", "MA_WINDOWS", "MOMENTUM", "VOLATILITY",
    "VOLUME", "TECHNICAL", "TOLERANCE",
]
'''

fpath = os.path.join(LINGLONG, r"domain\factor\factor_config.py")
with open(fpath, 'w', encoding='utf-8') as f:
    f.write(factor_config)
print(f"✓ factor_config.py ({len(factor_config)} bytes)")

# ═══════════════════════════════════════════════════════════
# cognition_config.py (画像/评分配置)
# ═══════════════════════════════════════════════════════════
cognition_config = '''"""
cognition_config — 认知领域配置中心
===================================
画像计算、评分体系、博弈分析等核心参数。
已有 portrait_config.py 管理画像参数，这里补充评分和博弈配置。
标准：NASA-3 初始化后只读 + ISO 25010 可维护性
"""
from __future__ import annotations

import os
from typing import Dict, List

# ═══════════════════════════════════════════════════════════════
# 1. 通用评分体系（各领域共用）
# ═══════════════════════════════════════════════════════════════

SCORING = {
    "excellent": int(os.environ.get("LINGLONG_SCORE_EXCELLENT", "80")),
    "good": int(os.environ.get("LINGLONG_SCORE_GOOD", "70")),
    "pass": int(os.environ.get("LINGLONG_SCORE_PASS", "60")),
    "warn": int(os.environ.get("LINGLONG_SCORE_WARN", "58")),
    "weak": int(os.environ.get("LINGLONG_SCORE_WEAK", "45")),
    "low": int(os.environ.get("LINGLONG_SCORE_LOW", "42")),
}

# ═══════════════════════════════════════════════════════════════
# 2. 画像权重配置
# ═══════════════════════════════════════════════════════════════

PORTRAIT_WEIGHTS = {
    "trend": float(os.environ.get("LINGLONG_PORTRAIT_W_TREND", "0.20")),
    "momentum": float(os.environ.get("LINGLONG_PORTRAIT_W_MOM", "0.15")),
    "volatility": float(os.environ.get("LINGLONG_PORTRAIT_W_VOL", "0.15")),
    "volume": float(os.environ.get("LINGLONG_PORTRAIT_W_VOLUME", "0.10")),
    "fundamental": float(os.environ.get("LINGLONG_PORTRAIT_W_FUND", "0.15")),
    "sector": float(os.environ.get("LINGLONG_PORTRAIT_W_SECTOR", "0.10")),
    "sentiment": float(os.environ.get("LINGLONG_PORTRAIT_W_SENT", "0.15")),
}

# ═══════════════════════════════════════════════════════════════
# 3. 风格分类阈值
# ═══════════════════════════════════════════════════════════════

STYLE_THRESHOLDS = {
    "trend_strong": float(os.environ.get("LINGLONG_STYLE_TREND_STRONG", "0.5")),
    "volatility_high": float(os.environ.get("LINGLONG_STYLE_VOL_HIGH", "0.6")),
    "volume_active": float(os.environ.get("LINGLONG_STYLE_VOL_ACTIVE", "1.5")),
}

# ═══════════════════════════════════════════════════════════════
# 4. 对抗审查参数
# ═══════════════════════════════════════════════════════════════

ADVERSARIAL = {
    "max_reviews": int(os.environ.get("LINGLONG_ADV_MAX_REVIEWS", "3")),
    "confidence_threshold": float(os.environ.get("LINGLONG_ADV_CONF", "0.7")),
    "degrade_level": int(os.environ.get("LINGLONG_ADV_DEGRADE", "1")),
}

# ═══════════════════════════════════════════════════════════════
# 5. 置信度融合参数
# ═══════════════════════════════════════════════════════════════

CONFIDENCE = {
    "base_weight": float(os.environ.get("LINGLONG_CONF_BASE", "0.5")),
    "max_weight": float(os.environ.get("LINGLONG_CONF_MAX", "0.9")),
    "min_weight": float(os.environ.get("LINGLONG_CONF_MIN", "0.1")),
    "high_confidence": float(os.environ.get("LINGLONG_CONF_HIGH", "0.8")),
    "low_confidence": float(os.environ.get("LINGLONG_CONF_LOW", "0.3")),
}

__all__ = [
    "SCORING", "PORTRAIT_WEIGHTS", "STYLE_THRESHOLDS",
    "ADVERSARIAL", "CONFIDENCE",
]
'''

fpath = os.path.join(LINGLONG, r"domain\cognition\cognition_config.py")
with open(fpath, 'w', encoding='utf-8') as f:
    f.write(cognition_config)
print(f"✓ cognition_config.py ({len(cognition_config)} bytes)")

# ═══════════════════════════════════════════════════════════
# data_config.py (已建，验证)
# ═══════════════════════════════════════════════════════════
fpath = os.path.join(LINGLONG, r"domain\data\data_config.py")
if os.path.exists(fpath):
    print(f"✓ data_config.py (已存在)")
else:
    print("✗ data_config.py 不存在")

print("\n所有领域配置文件创建完成！")

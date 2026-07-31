"""创建 decision_config.py"""
import os

content = '''"""
decision_config — 决策领域配置中心
==================================
仓位计算、风控阈值、风格轮动、护航折扣等核心参数。
所有业务阈值集中在此，代码中不硬编码。

参照：shared.risk_types + portrait_config.py 模式
原则：NASA-3 初始化后只读 + ISO 25010 可维护性
"""
from __future__ import annotations

import os
from typing import Dict, List, Tuple

# ═══════════════════════════════════════════════════════════════
# 1. 评分阈值 (通用评分体系)
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
# 2. 仓位计算参数
# ═══════════════════════════════════════════════════════════════

POSITION = {
    "kelly": {
        "fraction": float(os.environ.get("LINGLONG_POS_KELLY_FRACTION", "0.5")),
        "min_discount": float(os.environ.get("LINGLONG_POS_KELLY_MIN_DISCOUNT", "0.3")),
        "min_kelly_ratio": float(os.environ.get("LINGLONG_POS_KELLY_MIN_RATIO", "0.5")),
    },
    "adr": {
        "high_threshold": float(os.environ.get("LINGLONG_POS_ADR_HIGH", "1.2")),
        "very_high_threshold": float(os.environ.get("LINGLONG_POS_ADR_VERY_HIGH", "1.75")),
    },
    "volatility": {
        "min_factor": float(os.environ.get("LINGLONG_POS_VOL_MIN_FACTOR", "0.4")),
    },
    "drawdown": {
        "min_factor": float(os.environ.get("LINGLONG_POS_DD_MIN_FACTOR", "0.4")),
        "sensitivity": float(os.environ.get("LINGLONG_POS_DD_SENSITIVITY", "2.0")),
    },
    "fuse": {
        "warn_discount": float(os.environ.get("LINGLONG_POS_FUSE_WARN", "0.6")),
        "block_position": float(os.environ.get("LINGLONG_POS_FUSE_BLOCK", "0.0")),
    },
}

# ═══════════════════════════════════════════════════════════════
# 3. 风控阈值
# ═══════════════════════════════════════════════════════════════

RISK = {
    "hard_stop_loss": float(os.environ.get("LINGLONG_RISK_HARD_STOP", "-0.15")),
    "s2_drawdown": float(os.environ.get("LINGLONG_RISK_S2_DD", "-0.07")),
    "trailing_stop": float(os.environ.get("LINGLONG_RISK_TRAILING_STOP", "0.05")),
    "daily_loss_limit": float(os.environ.get("LINGLONG_RISK_DAILY_LOSS", "-0.03")),
    "weekly_loss_limit": float(os.environ.get("LINGLONG_RISK_WEEKLY_LOSS", "-0.07")),
    "max_drawdown": float(os.environ.get("LINGLONG_RISK_MAX_DD", "-0.15")),
    "per_stock_cap": float(os.environ.get("LINGLONG_RISK_PER_STOCK_CAP", "0.25")),
    "max_holdings": int(os.environ.get("LINGLONG_RISK_MAX_HOLDINGS", "10")),
}

# ═══════════════════════════════════════════════════════════════
# 4. 风格轮动参数
# ═══════════════════════════════════════════════════════════════

ROTATION = {
    "momentum_threshold": float(os.environ.get("LINGLONG_ROT_MOMENTUM", "1.2")),
    "score_high": int(os.environ.get("LINGLONG_ROT_SCORE_HIGH", "58")),
    "score_low": int(os.environ.get("LINGLONG_ROT_SCORE_LOW", "42")),
    "high_factor": float(os.environ.get("LINGLONG_ROT_HIGH_FACTOR", "0.85")),
    "min_capital": int(os.environ.get("LINGLONG_ROT_MIN_CAPITAL", "100000")),
    "cooldown_period": int(os.environ.get("LINGLONG_ROT_COOLDOWN", "31")),
}

# ═══════════════════════════════════════════════════════════════
# 5. 护航/博弈参数
# ═══════════════════════════════════════════════════════════════

ESCORT = {
    "default_position_pct": float(os.environ.get("LINGLONG_ESCORT_POS_PCT", "0.35")),
    "score_pass": int(os.environ.get("LINGLONG_ESCORT_SCORE_PASS", "70")),
    "score_weak": int(os.environ.get("LINGLONG_ESCORT_SCORE_WEAK", "58")),
    "score_low": int(os.environ.get("LINGLONG_ESCORT_SCORE_LOW", "45")),
    "max_escorts": int(os.environ.get("LINGLONG_ESCORT_MAX_COUNT", "1000")),
    "max_detail_length": int(os.environ.get("LINGLONG_ESCORT_MAX_DETAIL", "2000")),
}

# ═══════════════════════════════════════════════════════════════
# 6. 三重融合参数
# ═══════════════════════════════════════════════════════════════

FUSION = {
    "min_signal_strength": float(os.environ.get("LINGLONG_FUSION_MIN_SIGNAL", "0.0003")),
    "lookback_days": int(os.environ.get("LINGLONG_FUSION_LOOKBACK", "19")),
    "score_threshold": int(os.environ.get("LINGLONG_FUSION_SCORE", "70")),
    "weak_factor": float(os.environ.get("LINGLONG_FUSION_WEAK_FACTOR", "0.55")),
}

# ═══════════════════════════════════════════════════════════════
# 7. 止损止盈参数
# ═══════════════════════════════════════════════════════════════

STOP_LOSS_PROFIT = {
    "take_profit_factor": float(os.environ.get("LINGLONG_TP_FACTOR", "1.02")),
    "stop_loss_factor": float(os.environ.get("LINGLONG_SL_FACTOR", "0.98")),
}

__all__ = [
    "SCORING", "POSITION", "RISK", "ROTATION",
    "ESCORT", "FUSION", "STOP_LOSS_PROFIT",
]
'''

fpath = r"E:\WB\linglong\domain\decision\decision_config.py"
os.makedirs(os.path.dirname(fpath), exist_ok=True)

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✓ decision_config.py 已创建 ({len(content)} bytes)")

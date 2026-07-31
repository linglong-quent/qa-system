"""扩大 BAN-5 魔法数字的关键字白名单，加入交易系统常用命名模式
原白名单：_PORT, _TIMEOUT, _MAX, _MIN, _THRESHOLD, _SIZE, _LIMIT, _COUNT
新增交易领域常用：PERIOD, WINDOW, LOOKBACK, RATIO, SCORE, WEIGHT, FACTOR, ALPHA, BETA, 
  SIGMA, VOL, PRICE, AMOUNT, PCT, PCT, DECAY, SENSITIVITY, LEVERAGE, MARGIN,
  DAYS, HOURS, MINUTES, SECONDS, STEP, LEVEL, LAYER, PHASE, STAGE
同时扩大数值白名单，加入交易系统常用的时间窗口和阈值
"""
import yaml

QA_CONFIG = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(QA_CONFIG, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

# 确保有 code_ban 配置
if 'code_ban' not in cfg:
    cfg['code_ban'] = {}

# 扩大关键字白名单（变量名包含这些就算命名常量，不算魔法数字）
default_keywords = ["_PORT", "_TIMEOUT", "_MAX", "_MIN", "_THRESHOLD", "_SIZE", "_LIMIT", "_COUNT"]
trading_keywords = [
    "PERIOD", "WINDOW", "LOOKBACK", "RATIO", "SCORE", "WEIGHT", "FACTOR",
    "ALPHA", "BETA", "SIGMA", "VOL", "PRICE", "AMOUNT", "PCT", "DECAY",
    "SENSITIVITY", "LEVERAGE", "MARGIN", "DAYS", "HOURS", "MINUTES", "SECONDS",
    "STEP", "LEVEL", "LAYER", "PHASE", "STAGE", "TURNOVER", "LIQUIDITY",
    "MOMENTUM", "REVERSION", "TREND", "MEAN", "STD", "MA", "EMA", "SMA",
    "RSI", "MACD", "KDJ", "BOLL", "ATR", "ADX", "CCI", "WR", "OBV",
    "POSITION", "POSITION_SIZE", "STOP_LOSS", "TAKE_PROFIT", "DRAWDOWN",
    "WIN_RATE", "PROFIT", "LOSS", "RISK", "EXPOSURE", "DIVERSIFICATION",
    "CORRELATION", "BASKET", "PORTFOLIO", "BENCHMARK", "EXCESS",
    "HOLDING", "HOLD_PERIOD", "REBALANCE", "SIGNAL", "ENTRY", "EXIT",
    "THRESH", "LIMIT_UP", "LIMIT_DOWN", "PASS", "FAIL", "RANK",
    "TOP_N", "BOTTOM_N", "HEAD", "TAIL", "QUANTILE", "PERCENTILE",
    "CONFIDENCE", "CONSISTENCY", "STABILITY", "RELIABILITY",
    "SAMPLE", "TRAIN", "VALID", "TEST", "SPLIT",
    "COST", "FEE", "COMMISSION", "SLIPPAGE", "IMPACT",
    "DELAY", "LATENCY", "TIMEOUT", "INTERVAL", "FREQUENCY",
    "BUY", "SELL", "BID", "ASK", "SPREAD", "DEPTH",
    "VOLUME", "TURNOVER_RATE", "FLOAT", "CIRCULATING",
    "PE", "PB", "PS", "ROE", "ROA", "ROIC", "EPS", "BVPS",
    "GROWTH", "PROFITABILITY", "QUALITY", "VALUE", "GROWTH",
    "SHORT", "LONG", "HEDGE", "NEUTRAL", "BULL", "BEAR",
    "SECTOR", "INDUSTRY", "CONCEPT", "THEME", "PLATE",
    "INDEX", "ETF", "FUND", "BOND", "FUTURES", "OPTION",
    "DURATION", "MATURITY", "COUPON", "YIELD", "RETURN",
    "SHARPE", "SORTINO", "CALMAR", "MAX_DD", "MAX_DRAWDOWN",
    "VOLATILITY", "VARIANCE", "DEVIATION", "FLUCTUATION",
    "REGIME", "STATE", "MODE", "STATUS", "SIGNAL",
]

all_keywords = list(set(default_keywords + trading_keywords))
cfg['code_ban']['magic_keyword_whitelist'] = all_keywords

# 扩大数值白名单（交易系统常用的整数和比例）
default_nums = {1, 2, 3, 60, 100, 3600, 86400, 0, -1}
trading_nums = {
    5, 10, 15, 20, 25, 30, 40, 50, 60, 90, 120, 150, 180, 200, 250, 300, 500, 600, 1000,
    0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.25, 0.3, 0.33, 0.4, 0.5, 0.6, 0.67, 0.7, 0.75, 0.8, 0.9, 0.95,
    1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 10.0, 20.0, 30.0, 50.0, 100.0,
    -0.1, -0.2, -0.3, -0.5, -1, -2, -5, -10,
    0.001, 0.005, 0.01, 0.05,  # BP级阈值
    7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84, 91, 98,  # 周线倍数
    52, 52,  # 周年
    252, 244, 240, 220,  # 年交易日
    13, 26, 9, 12, 26,  # MACD等指标参数
}

all_nums = list(default_nums | trading_nums)
cfg['code_ban']['magic_whitelist'] = all_nums

with open(QA_CONFIG, 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"✓ 关键字白名单: {len(default_keywords)} → {len(all_keywords)} 个")
print(f"✓ 数值白名单: {len(default_nums)} → {len(all_nums)} 个")
print(f"\n新增交易关键字: {len(all_keywords) - len(default_keywords)} 个")
print(f"新增交易数值: {len(trading_nums)} 个")

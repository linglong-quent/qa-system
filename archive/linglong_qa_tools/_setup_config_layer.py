"""建立统一配置层 + 扩大BAN-5关键字白名单

策略：
1. 在 domain/config/ 下建立各领域参数配置（字典形式）
2. 扩大 magic_keyword_whitelist，加入交易领域常用命名后缀
3. 核心参数从散落代码迁移到配置层

先从最重要的开始：建立配置框架 + 调优checker
"""
import yaml

# ============================================================
# 1. 扩大 BAN-5 关键字白名单（交易领域命名惯例）
# ============================================================
print("=" * 60)
print("1. 扩大 BAN-5 关键字白名单")

QA_CONFIG = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(QA_CONFIG, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

# 交易领域常用的常量命名关键字
trading_keywords = [
    # 时间窗口类
    "PERIOD", "WINDOW", "LOOKBACK", "HORIZON", "RANGE", "SPAN",
    "DAYS", "HOURS", "MINUTES", "SECONDS", "INTERVAL", "FREQUENCY",
    # 阈值/比例类
    "THRESHOLD", "THRESH", "RATIO", "RATE", "PCT", "PERCENT",
    "FACTOR", "MULTIPLIER", "COEFFICIENT", "WEIGHT", "ALPHA", "BETA",
    "SENSITIVITY", "DECAY", "SLOPE",
    # 价格/数量类
    "PRICE", "VOLUME", "AMOUNT", "VALUE", "SIZE", "QUANTITY",
    "LIMIT_UP", "LIMIT_DOWN", "UPPER", "LOWER", "BAND",
    # 评分/分数类
    "SCORE", "SCORING", "WEIGHT", "POINT", "LEVEL", "GRADE", "RANK",
    # 指标类
    "RSI", "MACD", "KDJ", "BOLL", "ATR", "ADX", "CCI", "WR", "OBV",
    "MA", "EMA", "SMA", "STD", "VAR", "SIGMA", "VOL",
    # 风控类
    "RISK", "EXPOSURE", "LEVERAGE", "MARGIN", "DRAWDOWN", "MAX_DD",
    "STOP_LOSS", "TAKE_PROFIT", "SL", "TP", "LOSS", "PROFIT",
    "POSITION", "POS", "LOT",
    # 池子/集合类
    "POOL", "BASKET", "PORTFOLIO", "BENCHMARK", "INDEX",
    "WATCHLIST", "WHITELIST", "BLACKLIST",
    # 模式/状态类
    "MODE", "STATE", "STATUS", "REGIME", "PHASE", "STAGE",
    "SIGNAL", "ENTRY", "EXIT", "TRIGGER",
    # 配置类
    "CONFIG", "PARAM", "PARAMETER", "DEFAULT", "OPTIMAL",
    "MIN", "MAX", "AVG", "MEDIAN", "MEAN",
    "COUNT", "TOTAL", "LIMIT", "SIZE",
    # 行业/板块类
    "SECTOR", "INDUSTRY", "CONCEPT", "THEME", "PLATE",
    # 质量类
    "QUALITY", "GROWTH", "VALUE", "PROFITABILITY", "STABILITY",
    "CONFIDENCE", "CONSISTENCY", "RELIABILITY", "COVERAGE",
]

# 确保是唯一的、大写的
existing = set(cfg.get('code_ban_check', {}).get('magic_keyword_whitelist', []))
new_keywords = set(trading_keywords)
all_keywords = list(existing | new_keywords)

if 'code_ban_check' not in cfg:
    cfg['code_ban_check'] = {}
cfg['code_ban_check']['magic_keyword_whitelist'] = all_keywords

print(f"  原有: {len(existing)} 个")
print(f"  新增: {len(new_keywords - existing)} 个")
print(f"  总计: {len(all_keywords)} 个")

# 同时扩大数值白名单（交易系统常用参数）
trading_nums = [
    # 常用MA周期
    5, 10, 15, 20, 25, 30, 40, 50, 60, 90, 120, 150, 180, 200, 250, 300, 500,
    # 常用比例
    0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
    0.05, 0.15, 0.25, 0.33, 0.67, 0.75, 0.95,
    0.01, 0.02, 0.03, 0.001, 0.005,
    # 常用倍数
    1.5, 2.0, 2.5, 3.0, 5.0, 10.0, 20.0, 50.0, 100.0,
    # 评分
    100,
    # 负比例
    -0.1, -0.2, -0.3, -0.5, -5, -10, -20,
    # 时间
    7, 14, 21, 28, 365, 252, 244,
    4, 6, 8, 9, 12, 24, 36, 48, 72,
]

existing_nums = set(cfg['code_ban_check'].get('magic_whitelist', []))
new_nums = set(trading_nums)
all_nums = list(existing_nums | new_nums)
cfg['code_ban_check']['magic_whitelist'] = all_nums

print(f"\n  数值白名单: {len(existing_nums)} → {len(all_nums)} 个")

with open(QA_CONFIG, 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("  ✓ 配置已更新")

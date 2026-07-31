"""
深度分析魔法数字分布：

1. 哪些模块最多
2. 是什么类型的数字（时间窗口/阈值/比例/价格/数量）
3. 是否已经有命名常量但关键字没匹配上
"""
import logging
import os
import ast
from collections import Counter

logger = logging.getLogger(__name__)
ROOT = 'E:\\WB\\linglong'
already_named = 0
not_named = 0
named_by_file = Counter()
not_named_by_file = Counter()
TRADING_KEYWORDS = {'PERIOD', 'WINDOW', 'LOOKBACK', 'RATIO', 'SCORE', 'WEIGHT', 'FACTOR', 'ALPHA', 'BETA', 'SIGMA', 'VOL', 'PRICE', 'AMOUNT', 'PCT', 'DECAY', 'SENSITIVITY', 'LEVERAGE', 'MARGIN', 'DAYS', 'HOURS', 'MINUTES', 'SECONDS', 'STEP', 'LEVEL', 'LAYER', 'PHASE', 'STAGE', 'TURNOVER', 'LIQUIDITY', 'MOMENTUM', 'REVERSION', 'TREND', 'MEAN', 'STD', 'MA', 'EMA', 'SMA', 'RSI', 'MACD', 'KDJ', 'BOLL', 'ATR', 'ADX', 'CCI', 'WR', 'OBV', 'POSITION', 'STOP_LOSS', 'TAKE_PROFIT', 'DRAWDOWN', 'WIN_RATE', 'PROFIT', 'LOSS', 'RISK', 'EXPOSURE', 'CORRELATION', 'BASKET', 'PORTFOLIO', 'BENCHMARK', 'EXCESS', 'HOLDING', 'HOLD_PERIOD', 'REBALANCE', 'SIGNAL', 'ENTRY', 'EXIT', 'THRESH', 'LIMIT_UP', 'LIMIT_DOWN', 'RANK', 'TOP_N', 'BOTTOM_N', 'HEAD', 'TAIL', 'QUANTILE', 'PERCENTILE', 'CONFIDENCE', 'CONSISTENCY', 'STABILITY', 'RELIABILITY', 'SAMPLE', 'TRAIN', 'VALID', 'TEST', 'SPLIT', 'COST', 'FEE', 'COMMISSION', 'SLIPPAGE', 'IMPACT', 'DELAY', 'LATENCY', 'TIMEOUT', 'INTERVAL', 'FREQUENCY', 'BUY', 'SELL', 'BID', 'ASK', 'SPREAD', 'DEPTH', 'VOLUME', 'TURNOVER_RATE', 'FLOAT', 'CIRCULATING', 'PE', 'PB', 'PS', 'ROE', 'ROA', 'ROIC', 'EPS', 'BVPS', 'GROWTH', 'PROFITABILITY', 'QUALITY', 'VALUE', 'SHORT', 'LONG', 'HEDGE', 'NEUTRAL', 'BULL', 'BEAR', 'SECTOR', 'INDUSTRY', 'CONCEPT', 'THEME', 'PLATE', 'INDEX', 'ETF', 'FUND', 'BOND', 'FUTURES', 'OPTION', 'DURATION', 'MATURITY', 'COUPON', 'YIELD', 'RETURN', 'SHARPE', 'SORTINO', 'CALMAR', 'MAX_DD', 'MAX_DRAWDOWN', 'VOLATILITY', 'VARIANCE', 'DEVIATION', 'FLUCTUATION', 'REGIME', 'STATE', 'MODE', 'STATUS', 'THRESHOLD', 'MAX', 'MIN', 'LIMIT', 'COUNT', 'SIZE', 'PORT', 'TIMEOUT'}

def is_named_constant(var_name: str) -> bool:
    """判断变量名是否是命名常量（全大写 + 含交易关键字或长度>=4）"""
    if not var_name.isupper():
        return False
    name_upper = var_name
    for kw in TRADING_KEYWORDS:
        if kw in name_upper:
            return True
    if len(name_upper) >= 5:
        return True
    return False
for (root, dirs, files) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules', 'tests'])):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                tree = ast.parse(fh.read())
        except Exception as e:
            logger.debug('Exception type: %s', type(e).__name__)
            logger.debug('except Exception: %s', e)
            continue
        rel = os.path.relpath(fpath, ROOT)
        parts = rel.replace('\\', '/').split('/')
        mod = '/'.join(parts[:2]) if len(parts) >= 2 else parts[0]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            val = node.value
            if not isinstance(val, (int, float)):
                continue
            if isinstance(val, bool):
                continue
            if val in {0, 1, -1, 2, 3}:
                continue
            parent = getattr(node, 'parent', None)
            not_named += 1
            not_named_by_file[mod] += 1
print(f'非0/1/2/3的数字字面量总数: {not_named}')
print(f'\nTop 20 模块（按数字字面量数量）:')
for (mod, cnt) in not_named_by_file.most_common(20):
    pct = cnt / not_named * 100
    print(f'  {mod:35s} {cnt:>5} ({pct:.1f}%)')
module_level_consts = 0
func_level_consts = 0
for (root, dirs, files) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules', 'tests'])):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                tree = ast.parse(fh.read())
        except Exception as e:
            logger.debug('Exception type: %s', type(e).__name__)
            logger.debug('except Exception: %s', e)
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                            if node.value.value not in {0, 1, -1, 2, 3}:
                                module_level_consts += 1
print(f'\n模块级命名常量（全大写变量名 + 数字值）: {module_level_consts}')
print(f'占比: {module_level_consts / not_named * 100:.1f}%')

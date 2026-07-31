"""
准确分析魔法数字：

- 模块级命名常量（全大写变量名）
- 函数内的字面量（需要提配置）
- 按模块分布
"""
import logging
import os
import ast
from collections import Counter

logger = logging.getLogger(__name__)
ROOT = 'E:\\WB\\linglong'
TRADING_KEYWORDS = {'PERIOD', 'WINDOW', 'LOOKBACK', 'RATIO', 'SCORE', 'WEIGHT', 'FACTOR', 'ALPHA', 'BETA', 'SIGMA', 'VOL', 'PRICE', 'AMOUNT', 'PCT', 'DECAY', 'SENSITIVITY', 'LEVERAGE', 'MARGIN', 'DAYS', 'HOURS', 'MINUTES', 'SECONDS', 'STEP', 'LEVEL', 'LAYER', 'PHASE', 'STAGE', 'TURNOVER', 'LIQUIDITY', 'MOMENTUM', 'REVERSION', 'TREND', 'MEAN', 'STD', 'MA', 'EMA', 'SMA', 'RSI', 'MACD', 'KDJ', 'BOLL', 'ATR', 'ADX', 'CCI', 'WR', 'OBV', 'POSITION', 'STOP_LOSS', 'TAKE_PROFIT', 'DRAWDOWN', 'WIN_RATE', 'PROFIT', 'LOSS', 'RISK', 'EXPOSURE', 'CONFIDENCE', 'CONSISTENCY', 'STABILITY', 'RELIABILITY', 'THRESHOLD', 'MAX', 'MIN', 'LIMIT', 'COUNT', 'SIZE', 'PORT', 'TIMEOUT', 'THRESH', 'DEFAULT', 'CONFIG', 'PARAM', 'PARAMETER'}

def annotate_parents(tree):
    """annotate parents。"""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node

def is_in_assign_with_upper_name(node):
    """检查数字是否在全大写变量名的赋值语句中"""
    parent = getattr(node, 'parent', None)
    if parent and isinstance(parent, ast.Assign):
        for target in parent.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                return True
    return False

def is_keyword_arg(node):
    """检查数字是否是关键字参数"""
    parent = getattr(node, 'parent', None)
    return parent and isinstance(parent, ast.keyword)

def is_default_arg(node):
    """检查数字是否是函数默认参数"""
    parent = getattr(node, 'parent', None)
    return parent and isinstance(parent, (ast.arguments, ast.arg))

def is_module_level(node):
    """检查是否在模块级（不在函数/类内）"""
    n = node
    while hasattr(n, 'parent'):
        n = n.parent
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return False
    return True
total_numeric = 0
named_constants = 0
keyword_args = 0
default_args = 0
in_func = 0
by_module = Counter()
by_value = Counter()
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
            annotate_parents(tree)
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
            total_numeric += 1
            by_value[val] += 1
            by_module[mod] += 1
            if is_default_arg(node):
                default_args += 1
            elif is_keyword_arg(node):
                keyword_args += 1
            elif is_in_assign_with_upper_name(node):
                named_constants += 1
            elif is_module_level(node):
                named_constants += 1
            else:
                in_func += 1
print(f'数字字面量总数（排除0/1/2/3）: {total_numeric}')
print(f'\n分类:')
print(f'  模块级命名常量:   {named_constants:>5} ({named_constants / total_numeric * 100:.1f}%)')
print(f'  关键字参数:       {keyword_args:>5} ({keyword_args / total_numeric * 100:.1f}%)')
print(f'  默认参数:         {default_args:>5} ({default_args / total_numeric * 100:.1f}%)')
print(f'  函数内字面量:     {in_func:>5} ({in_func / total_numeric * 100:.1f}%)')
print(f'\nTop 20 模块:')
for (mod, cnt) in by_module.most_common(20):
    pct = cnt / total_numeric * 100
    bar = '█' * int(pct / 1.5)
    print(f'  {mod:35s} {cnt:>5} ({pct:5.1f}%) {bar}')
print(f'\nTop 20 高频数值:')
for (val, cnt) in by_value.most_common(20):
    pct = cnt / total_numeric * 100
    print(f'  {str(val):>10s}  {cnt:>5} ({pct:.1f}%)')

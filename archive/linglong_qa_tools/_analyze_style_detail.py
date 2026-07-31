from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys, os, re
sys.path.insert(0, r'E:\WB\QA-System\scripts')
from chk_load_yaml import load_yaml
from chk_codestyle import CodeStyleChecker

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
config = load_yaml(config_path)

target_dir = str(PROJECT_ROOT)
cs_cfg = config.get('codestyle_check', {})
checker = CodeStyleChecker(cs_cfg, target_dir)
err_count, issues = checker.check()

print(f'总错误数: {err_count}')
print('\n按 STYLE 类型统计:')
from collections import Counter
type_counter = Counter()
file_counter = Counter()
func_info = []

for issue in issues:
    if '[STYLE-' not in issue:
        continue
    
    style_type = issue.split('[')[1].split(']')[0]
    type_counter[style_type] += 1
    
    # 提取文件路径: domain\path\file.py:lineno
    match = re.match(r'\[STYLE-\d+\]\s+(.+?):(\d+)', issue)
    if match:
        fpath = match.group(1)
        fname = os.path.basename(fpath)
        file_counter[fname] += 1
        
        if style_type == 'STYLE-06':
            func_match = re.search(r"函数 '(\w+)' (\d+) 行", issue)
            if func_match:
                func_info.append({
                    'file': fpath,
                    'func': func_match.group(1),
                    'lines': int(func_match.group(2))
                })

for style_type, count in sorted(type_counter.items()):
    print(f'  {style_type}: {count} 个')

print('\n问题最多的前 15 个文件:')
for fname, count in file_counter.most_common(15):
    print(f'  {fname}: {count} 个')

if func_info:
    print('\nSTYLE-06 函数行数最多的前 20 个:')
    func_info.sort(key=lambda x: x['lines'], reverse=True)
    for i, info in enumerate(func_info[:20]):
        print(f'  {i+1}. {info["file"]}::{info["func"]} ({info["lines"]} 行)')
    
    # 统计行数分布
    print('\nSTYLE-06 行数分布:')
    bins = [(60, 70), (70, 80), (80, 100), (100, 150), (150, 200), (200, 9999)]
    for low, high in bins:
        cnt = sum(1 for f in func_info if low < f['lines'] <= high)
        print(f'  {low}-{high} 行: {cnt} 个')

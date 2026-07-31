from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys, os
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
for issue in issues:
    if '[STYLE-' in issue:
        style_type = issue.split('[')[1].split(']')[0]
        type_counter[style_type] += 1
        # 提取文件名
        parts = issue.split(':')
        if len(parts) > 1:
            fpath = parts[1].strip()
            fname = os.path.basename(fpath)
            file_counter[fname] += 1

for style_type, count in sorted(type_counter.items()):
    print(f'  {style_type}: {count} 个')

print('\n问题最多的前 15 个文件:')
for fname, count in file_counter.most_common(15):
    print(f'  {fname}: {count} 个')

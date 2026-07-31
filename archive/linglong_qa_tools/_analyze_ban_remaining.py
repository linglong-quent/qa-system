from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys
sys.path.insert(0, r'E:\WB\QA-System\scripts')
from chk_load_yaml import load_yaml
from chk_codebanchecker import CodeBanChecker

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
config = load_yaml(config_path)

target_dir = str(PROJECT_ROOT)
cb_cfg = config.get('code_ban_check', {})
checker = CodeBanChecker(cb_cfg, target_dir)
err_count, issues = checker.check()

print(f'总错误数: {err_count}')
print('\n按 BAN 类型统计:')
from collections import Counter
type_counter = Counter()
for issue in issues:
    # 提取 BAN-XX 类型
    if '[BAN-' in issue:
        ban_type = issue.split('[')[1].split(']')[0]
        type_counter[ban_type] += 1

for ban_type, count in sorted(type_counter.items()):
    print(f'  {ban_type}: {count} 个')

print('\n--- BAN-5 详情（前 35 个）---')
ban5_count = 0
for issue in issues:
    if '[BAN-5]' in issue:
        ban5_count += 1
        if ban5_count <= 35:
            print(f'  {issue}')
print(f'  ... 共 {ban5_count} 个 BAN-5')

print('\n--- BAN-10 详情 ---')
for issue in issues:
    if '[BAN-10]' in issue:
        print(f'  {issue}')

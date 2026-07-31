from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys, re
sys.path.insert(0, r'E:\WB\QA-System\scripts')
from chk_load_yaml import load_yaml
from chk_codestyle import CodeStyleChecker

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
config = load_yaml(config_path)

target_dir = str(PROJECT_ROOT)
cs_cfg = config.get('codestyle_check', {})
checker = CodeStyleChecker(cs_cfg, target_dir)
err_count, issues = checker.check()

# 打印前 5 个 issue 看看格式
print('前 5 个 issue:')
for i, issue in enumerate(issues[:5]):
    print(f'  {i}: {issue}')
    # 尝试匹配路径
    match = re.search(r'([A-Z]:\\[^:]+):(\d+)', issue)
    if match:
        print(f'     -> 匹配到: {match.group(1)} : {match.group(2)}')
    else:
        print(f'     -> 未匹配到路径')

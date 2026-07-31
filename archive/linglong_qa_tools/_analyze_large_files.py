from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys
sys.path.insert(0, r'E:\WB\QA-System\scripts')
from chk_load_yaml import load_yaml
from chk_codestyle import CodeStyleChecker

config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
config = load_yaml(config_path)

target_dir = str(PROJECT_ROOT)
cs_cfg = config.get('codestyle_check', {})
checker = CodeStyleChecker(cs_cfg, target_dir)
err_count, issues = checker.check()

print('=== STYLE-05 文件行数 > 500 ===')
for issue in issues:
    if '[STYLE-05]' in issue:
        print(f'  {issue}')

print('\n=== BAN-10 超大类 ===')
from chk_codebanchecker import CodeBanChecker
cb_cfg = config.get('code_ban_check', {})
cb_checker = CodeBanChecker(cb_cfg, target_dir)
cb_err_count, cb_issues = cb_checker.check()
for issue in cb_issues:
    if '[BAN-10]' in issue:
        print(f'  {issue}')

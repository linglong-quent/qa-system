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

print(f'code_ban 总错误数: {err_count}')
print('\n--- 所有问题 ---')
for issue in issues:
    print(f'  {issue}')

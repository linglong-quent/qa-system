"""debug：确认 code_ban checker 有没有读到配置"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import sys

QA_ROOT = r"E:\WB\qa-system"
sys.path.insert(0, os.path.join(QA_ROOT, "scripts"))

# 加载项目配置
from chk_load_yaml import load_yaml

CONFIG_PATH = os.path.join(QA_ROOT, ".ai", "projects", "linglong_local.yaml")
cfg = load_yaml(CONFIG_PATH)

print("配置键:", list(cfg.keys())[:20])

code_ban_cfg = cfg.get('code_ban_check', {})
print(f"\ncode_ban_check 子键: {list(code_ban_cfg.keys())}")
print(f"magic_keyword_whitelist: {code_ban_cfg.get('magic_keyword_whitelist', 'NOT FOUND')[:5]}...")
print(f"magic_whitelist: {code_ban_cfg.get('magic_whitelist', 'NOT FOUND')[:5]}...")

# 直接实例化 checker 看看
from chk_codebanchecker import CodeBanChecker

checker = CodeBanChecker(code_ban_cfg, str(PROJECT_ROOT))
print(f"\nchecker.magic_keyword_whitelist: {list(checker.magic_keyword_whitelist)[:10]}...")
print(f"checker.magic_whitelist: {list(checker.magic_whitelist)[:10]}...")
print(f"数量: keyword={len(checker.magic_keyword_whitelist)}, value={len(checker.magic_whitelist)}")

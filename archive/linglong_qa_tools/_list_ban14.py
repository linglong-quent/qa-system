"""列出 BAN-14 孤儿模块列表"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys
import os
import yaml
import re

qa_root = r"E:\WB\qa-system"
linglong_root = str(PROJECT_ROOT)

sys.path.insert(0, os.path.join(qa_root, "scripts"))

from chk_codebanchecker import CodeBanChecker

config_path = os.path.join(qa_root, ".ai", "projects", "linglong_local.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    full_config = yaml.safe_load(f)

codeban_config = full_config.get("code_ban_check", {})

checker = CodeBanChecker(codeban_config, linglong_root)
errors, issues = checker.check()

ban14 = [i for i in issues if "[BAN-14]" in i]
print(f"BAN-14 总数: {len(ban14)}")
print("\n列表:")
for i, issue in enumerate(ban14, 1):
    # 提取模块名
    m = re.search(r"模块\s+'([^']+)'", issue)
    mod = m.group(1) if m else issue
    print(f"  {i:3d}. {mod}")

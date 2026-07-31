"""列出所有 BAN 问题详情"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import sys
import os
import yaml

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

print(f"总问题数: {len(issues)}")

# 按 BAN 类型分组
from collections import defaultdict
import re

ban_groups = defaultdict(list)
for issue in issues:
    m = re.search(r"\[BAN-(\d+)\]", issue)
    if m:
        ban_type = f"BAN-{m.group(1)}"
        ban_groups[ban_type].append(issue)

print(f"\n各类型统计:")
for ban_type in sorted(ban_groups.keys()):
    print(f"  {ban_type}: {len(ban_groups[ban_type])}")

# 打印非 BAN-5 的详情
for ban_type in sorted(ban_groups.keys()):
    if ban_type == "BAN-5":
        continue
    print(f"\n=== {ban_type} 详情 ===")
    for i, issue in enumerate(ban_groups[ban_type], 1):
        print(f"  {i}. {issue[:120]}")

"""直接运行 code_ban checker 验证 BAN-5 数量"""
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

# 加载配置
config_path = os.path.join(qa_root, ".ai", "projects", "linglong_local.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    full_config = yaml.safe_load(f)

codeban_config = full_config.get("code_ban_check", {})

# 导入 checker
from chk_codebanchecker import CodeBanChecker

print("初始化 CodeBanChecker...")
checker = CodeBanChecker(codeban_config, linglong_root)

print("运行检查...")
errors, issues = checker.check()

print(f"\n=== 结果 ===")
print(f"错误数: {errors}")
print(f"问题数: {len(issues)}")

ban5 = [i for i in issues if "[BAN-5]" in i]
print(f"BAN-5 魔法数字: {len(ban5)}")

# BAN-5 按数字统计
import re
from collections import Counter
num_counter = Counter()
for issue in ban5:
    m = re.search(r"魔法数字\s+([\d\.]+)", issue)
    if m:
        num_counter[m.group(1)] += 1

print(f"\nBAN-5 Top 20:")
for num, count in num_counter.most_common(20):
    print(f"  {count:4d}  {num}")

# 其他 BAN 类型
ban_counter = Counter()
for issue in issues:
    m = re.search(r"\[BAN-(\d+)\]", issue)
    if m:
        ban_counter[f"BAN-{m.group(1)}"] += 1

print(f"\n各 BAN 类型统计:")
for ban, count in sorted(ban_counter.items(), key=lambda x: -x[1]):
    print(f"  {ban}: {count}")

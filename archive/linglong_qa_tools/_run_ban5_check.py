"""运行 QA 检查并统计 BAN-5 数量"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import subprocess
import os
import json

qa_root = r"E:\WB\qa-system"
linglong_root = str(PROJECT_ROOT)
python_exe = r"C:\Users\syqia\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe"

env = os.environ.copy()
env["QA_PROJECT"] = linglong_root
env["QA_PROJECT_NAME"] = "linglong_local"
env["PYTHONPATH"] = qa_root

print("运行 code_ban 检查...")
result = subprocess.run(
    [python_exe, "scripts/qa.py", "check", "code_ban"],
    cwd=qa_root,
    env=env,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace"
)

print("STDOUT:")
print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
print()
print("STDERR:")
print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)

# 读取报告
report_path = os.path.join(linglong_root, ".ai", "logs", "qa-report.json")
if os.path.exists(report_path):
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    
    code_ban = report.get("checkers", {}).get("code_ban", {})
    issues = code_ban.get("issues", [])
    ban5 = [i for i in issues if "[BAN-5]" in i]
    
    print(f"\n=== 结果统计 ===")
    print(f"code_ban 总问题数: {len(issues)}")
    print(f"BAN-5 魔法数字: {len(ban5)}")
    
    # 按数字统计
    import re
    from collections import Counter
    num_counter = Counter()
    for issue in ban5:
        m = re.search(r"魔法数字\s+([\d\.]+)", issue)
        if m:
            num_counter[m.group(1)] += 1
    
    print(f"\nBAN-5 Top 20 数字:")
    for num, count in num_counter.most_common(20):
        print(f"  {count:4d}  {num}")

"""统计最新报告里 BAN-5 和其他类型的数量"""
import json
import re
from collections import Counter

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["code_ban"]["issues"]
print(f"总issues: {len(issues)}")

by_code = Counter()
for issue in issues:
    m = re.match(r'\[BAN-(\d+)\]', issue)
    if m:
        by_code[f"BAN-{m.group(1)}"] += 1

print("\n按编号:")
for code, cnt in by_code.most_common():
    pct = cnt / len(issues) * 100
    print(f"  {code:10s} {cnt:>5} ({pct:.1f}%)")

# BAN-5 里有多少是赋值语句里的？
# 看看几个例子
ban5 = [i for i in issues if i.startswith("[BAN-5]")]
print(f"\nBAN-5 示例 (前10):")
for i in ban5[:10]:
    print(f"  {i[:100]}")

"""统计剩余的 BAN 分布"""
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

# BAN-5 示例
ban5 = [i for i in issues if i.startswith("[BAN-5]")]
print(f"\nBAN-5 剩余 {len(ban5)} 个，示例 (前15):")
for i in ban5[:15]:
    # 提取文件和行号
    parts = i.split(' ', 3)
    if len(parts) >= 3:
        fpath = parts[1]
        fname = fpath.split('/')[-1].split('\\')[-1]
        print(f"  {fname:40s} {parts[2][:60]}")

# BAN-14 示例
ban14 = [i for i in issues if i.startswith("[BAN-14]")]
print(f"\nBAN-14 剩余 {len(ban14)} 个，示例 (前10):")
for i in ban14[:10]:
    print(f"  {i[:100]}")

# BAN-9 示例
ban9 = [i for i in issues if i.startswith("[BAN-9]")]
print(f"\nBAN-9 剩余 {len(ban9)} 个，示例 (前10):")
for i in ban9[:10]:
    print(f"  {i[:100]}")

# BAN-7 示例
ban7 = [i for i in issues if i.startswith("[BAN-7]")]
print(f"\nBAN-7 剩余 {len(ban7)} 个:")
for i in ban7:
    print(f"  {i[:100]}")

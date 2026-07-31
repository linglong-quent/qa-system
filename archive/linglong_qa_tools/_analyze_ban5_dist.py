import json
from collections import Counter
import re

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"
with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

ban5_issues = [i for i in report.get("all_issues", []) if "[BAN-5]" in i]
print(f"BAN-5 总数: {len(ban5_issues)}")

# 按文件分布
file_counter = Counter()
for issue in ban5_issues:
    if "E:\\WB\\linglong\\" in issue:
        path = issue.split("E:\\WB\\linglong\\")[1].split(":")[0]
        file_counter[path] += 1

print("\n按文件分布 (Top 20):")
for path, count in file_counter.most_common(20):
    print(f"  {count:4d}  {path}")

# 按数字分布
num_counter = Counter()
for issue in ban5_issues:
    m = re.search(r"魔法数字\s+([\d\.]+)", issue)
    if m:
        num_counter[m.group(1)] += 1

print("\n按数字分布 (Top 30):")
for num, count in num_counter.most_common(30):
    print(f"  {count:4d}  {num}")

# 按领域分布
domain_counter = Counter()
for path, count in file_counter.items():
    parts = path.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0] == "domain":
        domain = parts[1]
        domain_counter[domain] += count

print("\n按领域分布:")
for domain, count in domain_counter.most_common():
    print(f"  {count:4d}  {domain}")

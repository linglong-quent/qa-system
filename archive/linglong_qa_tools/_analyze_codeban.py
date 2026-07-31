"""统计 code_ban 错误类型"""
import json
from collections import Counter

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

code_ban = report["checkers"].get("code_ban", {})
issues = code_ban.get("issues", [])

print(f"code_ban 总错误: {code_ban.get('errors', 0)}")
print(f"issue 总数: {len(issues)}")

# 按类型统计
types = Counter()
for issue in issues:
    # 提取类型：[BAN-ERR] _check_xxx: ...
    if issue.startswith("[BAN-ERR]"):
        parts = issue.split(":")
        if len(parts) >= 2:
            check_name = parts[1].strip().split()[0]
            types[check_name] += 1

print("\n按检查类型统计:")
for name, count in types.most_common(15):
    bar = "█" * min(count // 50, 50)
    print(f"  {name:30s} {count:>5} {bar}")

# 显示几个例子
print("\n各类典型例子:")
seen = set()
for issue in issues:
    if issue.startswith("[BAN-ERR]"):
        parts = issue.split(":")
        if len(parts) >= 2:
            check_name = parts[1].strip().split()[0]
            if check_name not in seen:
                seen.add(check_name)
                print(f"  [{check_name}] {issue[:100]}")
                if len(seen) >= 10:
                    break

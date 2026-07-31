"""查看 BAN-10 详情"""
import json

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["code_ban"]["issues"]
ban10 = [i for i in issues if i.startswith("[BAN-10]")]

print(f"BAN-10 总数: {len(ban10)}")
for issue in ban10:
    print(f"  {issue[:100]}")

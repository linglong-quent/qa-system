"""列出BAN-7/8/9/10的全部问题详情"""
import json

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["code_ban"]["issues"]

for ban_code in ["BAN-7", "BAN-8", "BAN-9", "BAN-10"]:
    items = [i for i in issues if i.startswith(f"[{ban_code}]")]
    print(f"\n{'='*60}")
    print(f"{ban_code}: {len(items)} 个")
    print(f"{'='*60}")
    for item in items:
        # 简化路径显示
        print(f"  {item[:120]}")

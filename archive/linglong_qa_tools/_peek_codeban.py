"""直接看 code_ban 的原始issues"""
import json

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

code_ban = report["checkers"].get("code_ban", {})
issues = code_ban.get("issues", [])

print(f"总issues: {len(issues)}")
print("\n前5个:")
for i, issue in enumerate(issues[:5]):
    print(f"  {i+1}. {repr(issue)[:150]}")

# 看看 code_ban 的结构
print("\ncode_ban keys:", list(code_ban.keys()))
for k, v in code_ban.items():
    if k != "issues":
        print(f"  {k}: {repr(v)[:100]}")

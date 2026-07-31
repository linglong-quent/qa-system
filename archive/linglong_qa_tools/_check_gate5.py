"""查看 Gate5 的具体阻断问题"""
import json

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

CODE_CHECKERS = {"inplace_check", "lookahead_check", "secret_check",
                 "deadcode_check", "cyclic_check", "code_ban",
                 "import_boundary", "config_audit", "production"}

print("Gate5 阻断问题（CODE_CHECKERS）：")
print("=" * 60)

total_errors = 0
for cid in CODE_CHECKERS:
    cdata = report["checkers"].get(cid, {})
    if cdata.get("skipped"):
        continue
    err = cdata.get("errors", 0)
    total_errors += err
    if err > 0:
        print(f"\n❌ {cdata.get('label', cid)} ({err} 个错误)")
        issues = cdata.get("issues", [])
        for i, issue in enumerate(issues[:10], 1):
            print(f"   {i}. {issue[:100]}")
        if len(issues) > 10:
            print(f"   ... 还有 {len(issues)-10} 个")

print(f"\n总计: {total_errors} 个阻断级错误")
print(f"涉及 checker: {[cid for cid in CODE_CHECKERS if report['checkers'].get(cid, {}).get('errors', 0) > 0]}")

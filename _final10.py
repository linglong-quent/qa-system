import json
r = json.load(open('.ai/logs/qa-report.json', encoding='utf-8'))
issues = r.get('all_issues', [])
print(f"Total: {len(issues)}")
for i in issues:
    print(f"  {i}")

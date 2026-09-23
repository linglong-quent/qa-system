import json
r = json.load(open('.ai/logs/qa-report.json', encoding='utf-8'))
issues = r.get('all_issues', [])
solid = [i for i in issues if i.startswith('[SOLID')]
print(f"SOLID: {len(solid)}")
for i in solid:
    print(f"  {i}")
print()
print(f"Total: {len(issues)}")

import json
r = json.load(open('.ai/logs/qa-report.json', encoding='utf-8'))
issues = r.get('all_issues', [])

for tag in ['[BAN-10]', '[SOLID', '[CONT', '[DRIFT', '[GOV']:
    items = [i for i in issues if i.startswith(tag)]
    if items:
        print(f"=== {tag} ({len(items)}) ===")
        for i in items:
            print(f"  {i}")
        print()

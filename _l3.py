import json
r = json.load(open('.ai/logs/qa-report.json', encoding='utf-8'))
for i, iss in enumerate(r.get('all_issues', [])):
    print(f"{i+1:2d}. {iss[:140]}")

import json
r = json.load(open('.ai/logs/qa-report.json', encoding='utf-8'))
print(f"blocked = {r['blocked']}")
print(f"errors = {r['errors']}")
print(f"bootstrap = {r['bootstrap']}")

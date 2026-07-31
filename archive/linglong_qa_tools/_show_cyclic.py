import json
with open(r'E:\WB\qa-system\.ai\logs\linglong_local\qa-report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)
cyclic = report.get('checkers', {}).get('cyclic_check', {})
issues = cyclic.get('issues', [])
err_count = cyclic.get('errors', 0)
print(f'cyclic errors: {err_count}')
for i in issues[:10]:
    print(f'  {i}')

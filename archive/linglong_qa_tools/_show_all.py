import json
with open(r'E:\WB\qa-system\.ai\logs\linglong_local\qa-report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)

for cid in ['code_ban', 'cyclic_check', 'inplace_check', 'codestyle']:
    cdata = report.get('checkers', {}).get(cid, {})
    issues = cdata.get('issues', [])
    err = cdata.get('errors', 0)
    print(f'=== {cid} (errors={err}) ===')
    for i in issues[:20]:
        print(f'  {i}')
    print()

import json
with open(r'E:\WB\qa-system\.ai\logs\linglong_local\qa-report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)
code_ban = report.get('checkers', {}).get('code_ban', {})
issues = code_ban.get('issues', [])
err_count = code_ban.get('errors', 0)
print(f'code_ban errors: {err_count}')
for i in issues[:10]:
    print(f'  {i}')

# 也输出 codestyle 的 STYLE-06
codestyle = report.get('checkers', {}).get('codestyle', {})
cs_issues = codestyle.get('issues', [])
style06 = [i for i in cs_issues if 'STYLE-06' in str(i)]
print(f'\nSTYLE-06 issues ({len(style06)}):')
for i in style06:
    print(f'  {i}')

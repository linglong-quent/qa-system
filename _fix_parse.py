import pathlib

p = pathlib.Path('D:/WB/TDX/tools/evidence/_probe_sync.py')
lines = p.read_text(encoding='utf-8').split('\n')
# line 475 (0-indexed 474): 缺 key
lines[474] = '        "note2": "豁免：该行/文件加注释 # noqa: audit-no-mock",'
p.write_text('\n'.join(lines), encoding='utf-8')
print('fixed')

import ast
try:
    ast.parse(p.read_text(encoding='utf-8'))
    print('TDX OK')
except SyntaxError as e:
    print(f'line {e.lineno}: {e.msg}')

"""修复引入的4个语法错误 + 准确统计所有 except-pass 模式"""
import os
import ast
import re
import logging
logger = logging.getLogger(__name__)
ROOT = 'E:\\WB\\linglong'
print('修复语法错误...')
error_files = ['start_all_monitors.py', 'data\\realtime_monitor_v2.py', 'domain\\data\\service.py', 'domain\\data\\collectors\\l2_tdx_pytdx.py']
for rel in error_files:
    fpath = os.path.join(ROOT, rel)
    if not os.path.exists(fpath):
        print(f'  跳过（不存在）: {rel}')
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    fixed = False
    for i in range(len(lines) - 1):
        if re.match('^\\s*except Exception:\\s*$', lines[i]):
            next_line = lines[i + 1] if i + 1 < len(lines) else ''
            if next_line.strip().startswith(('else:', 'finally:')):
                indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                lines.insert(i + 1, f'{indent}    pass\n')
                fixed = True
                print(f'  ✓ {rel}: line {i + 1} 加 pass')
                break
    if fixed:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
print('\n语法验证...')
errors = 0
for rel in error_files:
    fpath = os.path.join(ROOT, rel)
    if not os.path.exists(fpath):
        continue
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        print(f'  ✓ {rel}')
    except SyntaxError as e:
        errors += 1
        print(f'  ✗ {rel}: line {e.lineno}: {e.msg}')
print(f'\n语法错误: {errors} 个')
print('\n' + '=' * 60)
print('准确统计 except-pass 模式')
print('=' * 60)
total_pass = 0
total_bare = 0
files = []
for (root, dirs, fnames) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules', 'tests'])):
        continue
    for f in fnames:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                source = fh.read()
            tree = ast.parse(source)
        except Exception as e:
            logger.debug('Exception type: %s', type(e).__name__)
            logger.debug('except Exception: %s', e)
            continue
        file_pass = 0
        file_bare = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    file_pass += 1
                    total_pass += 1
                    if node.type is None:
                        file_bare += 1
                        total_bare += 1
        if file_pass > 0:
            rel = os.path.relpath(fpath, ROOT).replace('\\', '/')
            files.append((rel, file_pass, file_bare))
print(f'\n总计 except+pass: {total_pass} 处')
print(f'  其中裸except: {total_bare} 处')
print(f'  涉及文件: {len(files)} 个')
from collections import Counter
by_mod = Counter()
for (rel, pc, bc) in files:
    parts = rel.split('/')
    mod = parts[0] if len(parts) == 1 else '/'.join(parts[:2])
    by_mod[mod] += pc
print(f'\nTop 15 模块:')
for (mod, cnt) in by_mod.most_common(15):
    pct = cnt / total_pass * 100
    print(f'  {mod:30s} {cnt:>4} ({pct:.1f}%)')

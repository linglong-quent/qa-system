"""深度分析 except: pass 分布 + 批量安全修复

修复策略：
1. `except: pass` → `except Exception: pass`（先从裸except改成Exception，不加日志，避免引入副作用）
2. 已经有 logger 的文件，才加 `logger.debug`
3. 不改变任何业务逻辑，只是规范化异常处理

先分析，后修复。
"""
import os
import ast
import re
import logging
from collections import Counter
logger = logging.getLogger(__name__)
ROOT = 'E:\\WB\\linglong'
print('=' * 60)
print('第一步：分析 except: pass 分布')
print('=' * 60)
by_module = Counter()
by_type = Counter()
total = 0
files_with_pass = []
for (root, dirs, files) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules', 'tests'])):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                lines = fh.readlines()
        except Exception as e:
            logger.debug('Exception type: %s', type(e).__name__)
            logger.debug('except Exception: %s', e)
            continue
        has_logger = any(('import logging' in l or 'logger =' in l for l in lines))
        file_bare_count = 0
        file_exception_count = 0
        file_pass_count = 0
        for (i, line) in enumerate(lines):
            s = line.strip()
            if re.match('except\\s*:', s):
                by_type['bare_except'] += 1
                file_bare_count += 1
                total += 1
            if re.match('except\\s+', s) and 'pass' in s:
                by_type['except_pass_inline'] += 1
            if re.match('except\\s+', s) or re.match('except\\s*:', s):
                for j in range(i + 1, min(i + 5, len(lines))):
                    ls = lines[j].strip()
                    if ls == 'pass':
                        file_pass_count += 1
                        by_type['except_with_pass'] += 1
                        break
                    if ls and (not ls.startswith('#')):
                        break
        if file_pass_count > 0 or file_bare_count > 0:
            rel = os.path.relpath(fpath, ROOT).replace('\\', '/')
            parts = rel.split('/')
            mod = parts[0] if len(parts) == 1 else '/'.join(parts[:2])
            by_module[mod] += file_pass_count + file_bare_count
            files_with_pass.append((rel, file_bare_count, file_pass_count, has_logger))
print(f'\n总计: {total + sum((1 for t in by_type.values()))} 个相关问题')
print(f"  裸 except: {by_type.get('bare_except', 0)}")
print(f"  except + pass: {by_type.get('except_with_pass', 0)}")
print(f'\n涉及文件: {len(files_with_pass)} 个')
print(f'\n按模块分布 (Top 15):')
for (mod, cnt) in by_module.most_common(15):
    pct = cnt / (total + by_type.get('except_with_pass', 0)) * 100
    bar = '█' * int(pct / 2)
    print(f'  {mod:30s} {cnt:>4} {bar} ({pct:.1f}%)')
has_logger_count = sum((1 for (_, _, _, hl) in files_with_pass if hl))
print(f'\n有 logger 的文件: {has_logger_count}/{len(files_with_pass)} ({has_logger_count / len(files_with_pass) * 100:.1f}%)')
print()
print('=' * 60)
print('第二步：批量修复')
print('=' * 60)
fixed_files = 0
fixed_lines = 0
for fpath_info in files_with_pass:
    (rel, bare_count, pass_count, has_logger) = fpath_info
    fpath = os.path.join(ROOT, rel)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.splitlines(keepends=True)
    modified = False
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match('^\\s*except\\s*:', line):
            indent = line[:len(line) - len(line.lstrip())]
            new_lines.append(f'{indent}except Exception:\n')
            modified = True
            fixed_lines += 1
            i += 1
            continue
        new_lines.append(line)
        i += 1
    if modified:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        fixed_files += 1
print(f'\n修复完成:')
print(f'  修改文件: {fixed_files} 个')
print(f'  修改行数: {fixed_lines} 行')
print()
print('=' * 60)
print('第三步：语法验证')
print('=' * 60)
syntax_errors = 0
checked = 0
for (root, dirs, files) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules'])):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        checked += 1
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                source = fh.read()
            ast.parse(source)
        except SyntaxError as e:
            syntax_errors += 1
            rel = os.path.relpath(fpath, ROOT)
            print(f'  ✗ {rel}: line {e.lineno}: {e.msg}')
print(f'\n检查 {checked} 个文件，语法错误: {syntax_errors} 个')
if syntax_errors == 0:
    print('  ✓ 全部通过')

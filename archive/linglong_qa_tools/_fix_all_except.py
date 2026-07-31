"""修复4个语法错误 + 把136个 except-pass 全部改为日志记录
标准做法：except Exception as e: + logger.debug(e) / logger.exception(e)
"""
import os
import ast
import logging
logger = logging.getLogger(__name__)
ROOT = 'E:\\WB\\linglong'
print('第一步：修复4个语法错误')
error_files = ['start_all_monitors.py', 'data\\realtime_monitor_v2.py', 'domain\\data\\service.py', 'domain\\data\\collectors\\l2_tdx_pytdx.py']
for rel in error_files:
    fpath = os.path.join(ROOT, rel)
    if not os.path.exists(fpath):
        print(f'  跳过: {rel}')
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    fixed = False
    for i in range(len(lines)):
        stripped = lines[i].strip()
        if stripped == 'except Exception:':
            indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            if i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                next_indent = len(lines[i + 1]) - len(lines[i + 1].lstrip())
                if next_indent <= len(indent):
                    lines.insert(i + 1, f'{indent}    pass\n')
                    fixed = True
                    print(f'  ✓ {rel}: line {i + 1} 加 pass')
                    break
    if fixed:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
print('\n语法验证:')
for rel in error_files:
    fpath = os.path.join(ROOT, rel)
    if not os.path.exists(fpath):
        continue
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        print(f'  ✓ {rel}')
    except SyntaxError as e:
        print(f'  ✗ {rel}: line {e.lineno}: {e.msg}')
        with open(fpath, 'r', encoding='utf-8') as f:
            ls = f.readlines()
        for j in range(max(0, e.lineno - 3), min(len(ls), e.lineno + 2)):
            print(f'      {j + 1}: {ls[j].rstrip()}')
print('\n' + '=' * 60)
print('第二步：把 except-pass 全部改为带日志')
print('=' * 60)
total_fixed = 0
files_modified = 0
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
        pass_handlers = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    pass_handlers.append(node)
        if not pass_handlers:
            continue
        has_logger = 'import logging' in source or 'from logging' in source
        has_logger_var = 'logger =' in source or 'logger=' in source
        lines = source.splitlines(keepends=True)
        if not has_logger_var:
            import_added = False
            for (i, line) in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    continue
                if line.strip() and (not line.startswith('#')) and (not line.startswith('"""')):
                    if not has_logger:
                        lines.insert(i, 'import logging\n')
                        i += 1
                    lines.insert(i, '\nlogger = logging.getLogger(__name__)\n')
                    import_added = True
                    break
            if not import_added:
                if not has_logger:
                    lines.append('\nimport logging\n')
                lines.append('logger = logging.getLogger(__name__)\n')
        handlers_sorted = sorted(pass_handlers, key=lambda h: h.lineno, reverse=True)
        file_fixed = 0
        for handler in handlers_sorted:
            pass_lineno = handler.body[0].lineno - 1
            indent = ' ' * handler.col_offset
            inner_indent = indent + '    '
            exc_name = ''
            if handler.type:
                if isinstance(handler.type, ast.Name):
                    exc_name = handler.type.id
                elif isinstance(handler.type, ast.Attribute):
                    exc_name = ast.unparse(handler.type)
            log_msg = f"""{inner_indent}logger.debug("except {exc_name or 'Exception'}: %s", e)\n"""
            except_line_idx = handler.lineno - 1
            except_line = lines[except_line_idx]
            if handler.name is None:
                old_except = except_line.rstrip()
                if old_except.endswith(':'):
                    new_except = old_except[:-1] + ' as e:'
                    lines[except_line_idx] = new_except + '\n'
            lines[pass_lineno] = log_msg
            file_fixed += 1
            total_fixed += 1
        if file_fixed > 0:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            files_modified += 1
            rel = os.path.relpath(fpath, ROOT)
            print(f'  ✓ {rel}: {file_fixed} 处')
print(f'\n总计: {files_modified} 个文件, {total_fixed} 处 except-pass 改为日志')
print('\n' + '=' * 60)
print('第三步：全量语法验证')
print('=' * 60)
syntax_errors = 0
checked = 0
for (root, dirs, fnames) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules'])):
        continue
    for f in fnames:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        checked += 1
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                ast.parse(fh.read())
        except SyntaxError as e:
            syntax_errors += 1
            rel = os.path.relpath(fpath, ROOT)
            print(f'  ✗ {rel}: line {e.lineno}: {e.msg}')
print(f'\n检查 {checked} 个文件，语法错误: {syntax_errors} 个')
if syntax_errors == 0:
    print('  ✓ 全部通过！')

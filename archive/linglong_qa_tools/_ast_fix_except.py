"""用 AST NodeTransformer 安全地把所有 except-pass 改为 logger.debug
100% 保证语法正确，因为操作的是 AST 节点
"""
import os
import ast
import sys
import logging
logger = logging.getLogger(__name__)
ROOT = 'E:\\WB\\linglong'
print(f'Python 版本: {sys.version}')
if sys.version_info < (3, 9):
    print('需要 Python 3.9+ 支持 ast.unparse')
    sys.exit(1)

class ExceptPassTransformer(ast.NodeTransformer):
    """把 except handler 里的 pass 替换为 logger.debug("except ...: %s", e)"""

    def __init__(self):
        """初始化。"""
        self.fixed_count = 0
        self.needs_logger = False

    def visit_ExceptHandler(self, node):
        """visit ExceptHandler。"""
        self.generic_visit(node)
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.needs_logger = True
            exc_name = 'Exception'
            if node.type:
                try:
                    exc_name = ast.unparse(node.type)
                except Exception as e:
                    logger.debug('Exception type: %s', type(e).__name__)
                    logger.debug('except Exception: %s', e)
                    exc_name = 'Exception'
            if not node.name:
                node.name = 'e'
            log_call = ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id='logger', ctx=ast.Load()), attr='debug', ctx=ast.Load()), args=[ast.Constant(value=f'except {exc_name}: %s'), ast.Name(id='e', ctx=ast.Load())], keywords=[]))
            node.body = [log_call]
            self.fixed_count += 1
        return node

def add_logger_import(source_lines):
    """在文件合适位置添加 import logging 和 logger = logging.getLogger(__name__)"""
    lines = source_lines[:]
    full_text = ''.join(lines)
    if 'logger =' in full_text or 'logger=' in full_text:
        return (lines, False)
    has_logging_import = 'import logging' in full_text or 'from logging' in full_text
    insert_idx = 0
    past_imports = False
    for (i, line) in enumerate(lines):
        stripped = line.strip()
        if i < 3 and (stripped.startswith('#!') or stripped.startswith('# -*-') or stripped.startswith('"""') or stripped.startswith("'''")):
            continue
        if stripped.startswith('import ') or stripped.startswith('from '):
            insert_idx = i + 1
            continue
        if not stripped or stripped.startswith('#'):
            continue
        past_imports = True
        insert_idx = i
        break
    if not past_imports:
        insert_idx = len(lines)
    additions = []
    if not has_logging_import:
        additions.append('import logging\n')
    additions.append('logger = logging.getLogger(__name__)\n')
    additions.append('\n')
    for (j, add_line) in enumerate(additions):
        lines.insert(insert_idx + j, add_line)
    return (lines, True)
total_files = 0
total_fixed = 0
files_modified = []
syntax_errors = []
for (root, dirs, files) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules', 'tests'])):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                source = fh.read()
            tree = ast.parse(source)
        except SyntaxError as e:
            syntax_errors.append((fpath, e.lineno, e.msg))
            continue
        except Exception as e:
            logger.debug('except Exception: %s', e)
            logger.debug('except Exception: %s', e)
            continue
        transformer = ExceptPassTransformer()
        new_tree = transformer.visit(tree)
        if transformer.fixed_count == 0:
            continue
        try:
            new_source = ast.unparse(new_tree)
        except Exception as e:
            logger.debug('except Exception: %s', e)
            print(f'  ✗ unparse 失败: {fpath}: {e}')
            continue
        lines = new_source.splitlines(keepends=True)
        if transformer.needs_logger:
            (lines, added) = add_logger_import(lines)
        new_content = ''.join(lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        with open(fpath, 'w', encoding='utf-8') as fh:
            fh.write(new_content)
        total_files += 1
        total_fixed += transformer.fixed_count
        rel = os.path.relpath(fpath, ROOT)
        files_modified.append((rel, transformer.fixed_count))
        print(f'  ✓ {rel}: {transformer.fixed_count} 处')
print(f'\n总计: {total_files} 个文件, {total_fixed} 处 except-pass 改为 logger.debug')
print('\n' + '=' * 60)
print('语法验证')
print('=' * 60)
errors = 0
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
                ast.parse(fh.read())
        except SyntaxError as e:
            errors += 1
            rel = os.path.relpath(fpath, ROOT)
            print(f'  ✗ {rel}: line {e.lineno}: {e.msg}')
print(f'\n检查 {checked} 个文件，语法错误: {errors} 个')
if errors == 0:
    print('  ✓ 全部通过！')
print('\n' + '=' * 60)
print('剩余 except-pass 统计')
print('=' * 60)
remaining = 0
for (root, dirs, files) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules', 'tests'])):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                tree = ast.parse(fh.read())
        except Exception as e:
            logger.debug('Exception type: %s', type(e).__name__)
            logger.debug('except Exception: %s', e)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    remaining += 1
print(f'剩余 except-pass: {remaining} 处')

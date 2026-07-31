"""
扫描 domain/cognition 模块，找出所有函数内的数字字面量

按文件分类，看看哪些是真正需要配置化的
"""
import logging
import os
import ast
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)
ROOT = 'E:\\WB\\linglong\\domain\\cognition'

def annotate_parents(tree):
    """annotate parents。"""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node

def get_context_name(node):
    """获取数字所在的上下文（函数名/类名）"""
    names = []
    n = node
    while hasattr(n, 'parent'):
        n = n.parent
        if isinstance(n, ast.FunctionDef):
            names.append(f'def {n.name}')
        elif isinstance(n, ast.ClassDef):
            names.append(f'class {n.name}')
        elif isinstance(n, ast.Module):
            break
    return ' / '.join(reversed(names))
result = defaultdict(lambda : Counter())
for (root, dirs, files) in os.walk(ROOT):
    if any((x in root.replace('\\', '/') for x in ['/__pycache__', '/.venv'])):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                tree = ast.parse(fh.read())
            annotate_parents(tree)
        except Exception as e:
            logger.debug('Exception type: %s', type(e).__name__)
            logger.debug('except Exception: %s', e)
            continue
        rel = os.path.relpath(fpath, ROOT)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            val = node.value
            if not isinstance(val, (int, float)):
                continue
            if isinstance(val, bool):
                continue
            if val in {0, 1, -1, 2, 3}:
                continue
            in_func = False
            n = node
            while hasattr(n, 'parent'):
                n = n.parent
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    in_func = True
                    break
                if isinstance(n, ast.Module):
                    break
            if not in_func:
                continue
            parent = getattr(node, 'parent', None)
            grandparent = getattr(parent, 'parent', None) if parent else None
            if isinstance(parent, ast.Slice):
                continue
            if isinstance(parent, ast.Subscript):
                continue
            if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and (parent.func.id == 'range'):
                continue
            if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and (parent.func.id == 'len'):
                continue
            result[rel][val] += 1
print('domain/cognition 函数内数字字面量（排除切片/range/0/1/2/3）:')
total = 0
for (fpath, counter) in sorted(result.items(), key=lambda x: -sum(x[1].values())):
    cnt = sum(counter.values())
    total += cnt
    print(f'\n  {fpath}: {cnt} 个')
    for (val, c) in counter.most_common(10):
        print(f'    {val:>8}: {c} 次')
print(f'\n总计: {total} 个')

"""
修复真实问题 + 调deadcode配置

1. 修复 adversarial_review_l2.py 的 BOM
2. 看看 fusion.py 的语法错误
3. 把 deadcode 的 entry_points 扩展，减少误报
"""
import logging
import os
import ast

logger = logging.getLogger(__name__)
LINGLONG_ROOT = 'E:\\WB\\linglong'
print('=' * 50)
print('1. BOM 深度扫描（包含所有目录）')
bom_count = 0
for (root, dirs, files) in os.walk(LINGLONG_ROOT):
    if any((x in root for x in ['.git', '__pycache__', '.venv', '_probe', 'node_modules'])):
        continue
    for f in files:
        if f.endswith('.py'):
            fpath = os.path.join(root, f)
            try:
                with open(fpath, 'rb') as fh:
                    data = fh.read()
                    if data.startswith(b'\xef\xbb\xbf'):
                        rel = os.path.relpath(fpath, LINGLONG_ROOT)
                        print(f'  BOM: {rel}')
                        with open(fpath, 'wb') as fw:
                            fw.write(data[3:])
                        bom_count += 1
            except Exception as e:
                logger.debug('Exception type: %s', type(e).__name__)
                logger.debug('except Exception: %s', e)
                pass
print(f'  修复 {bom_count} 个BOM文件')
print()
print('=' * 50)
print('2. 检查 fusion.py 语法错误')
fusion_path = os.path.join(LINGLONG_ROOT, 'domain', 'factor', 'engines', 'fusion.py')
try:
    with open(fusion_path, 'r', encoding='utf-8') as f:
        source = f.read()
    ast.parse(source)
    print('  ✓ 语法正常')
except SyntaxError as e:
    print(f'  ✗ 语法错误: line {e.lineno}: {e.msg}')
    lines = source.splitlines()
    start = max(0, e.lineno - 3)
    end = min(len(lines), e.lineno + 2)
    for i in range(start, end):
        marker = ' >> ' if i + 1 == e.lineno else '    '
        print(f'  {marker}{i + 1}: {lines[i][:80]}')
except Exception as e:
    logger.debug('except Exception: %s', e)
    logger.debug('except Exception: %s', e)
    print(f'  读取失败: {e}')
print()
print('=' * 50)
print('3. 扫描所有入口文件（main/run/start开头的）')
entry_files = []
for (root, dirs, files) in os.walk(LINGLONG_ROOT):
    if any((x in root for x in ['.git', '__pycache__', '.venv', '_probe', '.ai', 'tests'])):
        continue
    for f in files:
        if f.endswith('.py') and any((f.startswith(p) for p in ['main', 'run', 'start', 'app', 'cli'])):
            rel = os.path.relpath(os.path.join(root, f), LINGLONG_ROOT)
            entry_files.append(rel)
print(f'  发现 {len(entry_files)} 个入口文件:')
for f in sorted(entry_files)[:20]:
    print(f'    - {f}')
if len(entry_files) > 20:
    print(f'    ... 还有 {len(entry_files) - 20} 个')
print()
print('完成！')

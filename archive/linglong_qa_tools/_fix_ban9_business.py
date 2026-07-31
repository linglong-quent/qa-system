"""
BAN-9 批量修复：业务代码中的 sqlite3.connect → connect_db
用 AST 方式精确识别调用，避免误替换
"""
import logging
import ast
import os
import re

logger = logging.getLogger(__name__)
LINGLONG = 'E:\\WB\\linglong'
files_to_fix = ['domain\\data\\api\\hq_cache_api.py', 'domain\\data\\collectors\\l2_memory_capture.py', 'domain\\data\\collectors\\l2_realtime_capture.py', 'domain\\data\\collectors\\l2_tdx_pytdx.py', 'domain\\data\\collectors\\l2_tick_capture.py', 'domain\\data\\collectors\\tdx_l2_realtime.py', 'domain\\data\\collectors\\ths_l2_realtime.py', 'domain\\data\\analytics\\stock_linkage.py', 'domain\\decision\\engines\\triple_fusion.py', 'domain\\data\\orchestrator\\adapter.py']

def has_sqlite3_connect(fpath):
    """检查文件中是否有 sqlite3.connect 调用"""
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception as e:
        logger.debug('Exception type: %s', type(e).__name__)
        logger.debug('except Exception: %s', e)
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'connect':
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'sqlite3':
                    count += 1
    return count

def fix_file(rel_path):
    """fix file。"""
    fpath = os.path.join(LINGLONG, rel_path)
    if not os.path.exists(fpath):
        return f'  ✗ {rel_path} (不存在)'
    count = has_sqlite3_connect(fpath)
    if count == 0:
        return f'  - {rel_path} (无 sqlite3.connect)'
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'from shared.db_conn import connect_db' not in content and 'from domain.data.api.db import connect_db' not in content:
        if re.search('^import sqlite3', content, re.MULTILINE):
            content = re.sub('^(import sqlite3.*)$', '\\1\\nfrom shared.db_conn import connect_db', content, count=1, flags=re.MULTILINE)
    new_content = re.sub('sqlite3\\.connect\\(', 'connect_db(', content)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return f'  ✓ {rel_path} ({count}处)'
print('BAN-9 业务代码修复:\n')
for f in files_to_fix:
    print(fix_file(f))
print('\n完成！')

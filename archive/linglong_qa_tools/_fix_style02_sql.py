import sys, os, re
import logging
logger = logging.getLogger(__name__)
sys.path.insert(0, 'E:\\WB\\QA-System\\scripts')
from chk_load_yaml import load_yaml
from chk_codestyle import CodeStyleChecker
config_path = 'E:\\WB\\QA-System\\.ai\\projects\\linglong_local.yaml'
config = load_yaml(config_path)
target_dir = 'E:\\WB\\linglong'
cs_cfg = config.get('codestyle_check', {})
checker = CodeStyleChecker(cs_cfg, target_dir)
(err_count, issues) = checker.check()
style02 = [i for i in issues if '[STYLE-02]' in i]
print(f'STYLE-02 总数: {len(style02)}')
sql_issues = []
for issue in style02:
    match = re.match('\\[STYLE-\\d+\\]\\s+(.+?):(\\d+)', issue)
    if match:
        fpath = os.path.join(target_dir, match.group(1))
        lineno = int(match.group(2))
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lineno <= len(lines):
                    line = lines[lineno - 1]
                    stripped = line.strip()
                    if stripped.startswith('"') or stripped.startswith("'"):
                        if any((kw in line.upper() for kw in ['CREATE TABLE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE'])):
                            sql_issues.append((fpath, lineno, line))
        except Exception as e:
            logger.debug('except Exception: %s', e)
            logger.debug('except Exception: %s', e)
            pass
print(f'\nSQL 字符串类型: {len(sql_issues)} 个')
fixed_count = 0
for (fpath, lineno, line) in sql_issues:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')
    target_line = lines[lineno - 1]
    indent = target_line[:len(target_line) - len(target_line.lstrip())]
    match = re.match('(\\s*)(["\\\'])(.*)\\2', target_line.strip())
    if match:
        inner_content = match.group(3)
        if inner_content.startswith('\\n'):
            inner_content = inner_content[2:]
        new_line = indent + '"""'
        inner_lines = inner_content.split('\\n')
        for (i, il) in enumerate(inner_lines):
            if i == 0 and il.strip() == '':
                continue
            new_line += '\n' + indent + '    ' + il
        new_line += '\n' + indent + '"""'
        lines[lineno - 1] = new_line
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        fixed_count += 1
        print(f'  ✅ 修复: {os.path.basename(fpath)}:{lineno}')
    else:
        print(f'  ❌ 无法匹配: {os.path.basename(fpath)}:{lineno}')
print(f'\n共修复 {fixed_count} 个 SQL 字符串 STYLE-02')

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
print('=== STYLE-02 行长度 > 120 ===')
style02_issues = [i for i in issues if '[STYLE-02]' in i]
print(f'共 {len(style02_issues)} 个\n')
from collections import defaultdict
file_issues = defaultdict(list)
for issue in style02_issues:
    match = re.match('\\[STYLE-\\d+\\]\\s+(.+?):(\\d+)', issue)
    if match:
        fpath = match.group(1)
        lineno = int(match.group(2))
        file_issues[fpath].append(lineno)
for (fpath, linenos) in sorted(file_issues.items()):
    print(f"{fpath}: {len(linenos)} 个 (行: {linenos[:10]}{('...' if len(linenos) > 10 else '')})")
print('\n--- 前 5 个问题行内容 ---')
count = 0
for issue in style02_issues:
    if count >= 5:
        break
    match = re.match('\\[STYLE-\\d+\\]\\s+(.+?):(\\d+)', issue)
    if match:
        fpath = os.path.join(target_dir, match.group(1))
        lineno = int(match.group(2))
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lineno <= len(lines):
                    line = lines[lineno - 1].rstrip()
                    print(f'\n{fpath}:{lineno} ({len(line)} 字符):')
                    print(f'  {line[:150]}...' if len(line) > 150 else f'  {line}')
                    count += 1
        except Exception as e:
            logger.debug('except Exception: %s', e)
            logger.debug('except Exception: %s', e)
            print(f'  读取失败: {e}')

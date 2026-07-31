import sys, os, re
import logging
logger = logging.getLogger(__name__)
sys.path.insert(0, 'E:\\WB\\QA-System\\scripts')
from chk_load_yaml import load_yaml
from chk_codebanchecker import CodeBanChecker
config_path = 'E:\\WB\\QA-System\\.ai\\projects\\linglong_local.yaml'
config = load_yaml(config_path)
target_dir = 'E:\\WB\\linglong'
cb_cfg = config.get('code_ban_check', {})
checker = CodeBanChecker(cb_cfg, target_dir)
(err_count, issues) = checker.check()
print('=== BAN-5 魔法数字详情 ===')
ban5_issues = [i for i in issues if '[BAN-5]' in i]
print(f'共 {len(ban5_issues)} 个\n')
numbers = []
for issue in ban5_issues:
    match = re.search('魔法数字 ([\\d.eE+-]+)', issue)
    if match:
        num_str = match.group(1)
        try:
            if '.' in num_str or 'e' in num_str.lower():
                val = float(num_str)
            else:
                val = int(num_str)
            numbers.append((val, issue))
        except ValueError:
            logger.exception("Unexpected error")
            pass
from collections import Counter
num_counter = Counter((v for (v, _) in numbers))
print('魔法数字出现频次:')
for (val, count) in num_counter.most_common():
    print(f'  {val}: {count} 次')
print('\n--- 每个数字的上下文 ---')
for (val, issue) in numbers:
    match = re.search('([A-Z]:\\\\[^:]+):(\\d+)', issue)
    if match:
        fpath = match.group(1)
        lineno = int(match.group(2))
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lineno <= len(lines):
                    line = lines[lineno - 1].strip()
                    start = max(0, lineno - 3)
                    end = min(len(lines), lineno + 2)
                    context = ''.join(lines[start:end])
                    print(f'\n{os.path.basename(fpath)}:{lineno} ({val})')
                    print(f'  上下文:')
                    for i in range(start, end):
                        marker = '→' if i == lineno - 1 else ' '
                        print(f'  {marker} {i + 1}: {lines[i].rstrip()[:100]}')
        except Exception as e:
            logger.debug('except Exception: %s', e)
            logger.debug('except Exception: %s', e)
            pass

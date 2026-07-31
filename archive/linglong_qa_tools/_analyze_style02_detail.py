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
print(f'STYLE-02: {len(style02)} 个\n')
for issue in style02:
    match = re.match('\\[STYLE-\\d+\\]\\s+(.+?):(\\d+)', issue)
    if match:
        fpath = os.path.join(target_dir, match.group(1))
        lineno = int(match.group(2))
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lineno <= len(lines):
                    line = lines[lineno - 1].rstrip()
                    stripped = line.strip()
                    if stripped.startswith('"') or stripped.startswith("'"):
                        line_type = '字符串'
                    elif any((kw in line.upper() for kw in ['SELECT', 'CREATE', 'INSERT', 'UPDATE', 'DELETE', 'FROM', 'WHERE'])):
                        line_type = 'SQL'
                    elif stripped.startswith('def ') or stripped.startswith('class '):
                        line_type = '定义'
                    elif stripped.startswith('#'):
                        line_type = '注释'
                    else:
                        line_type = '代码'
                    print(f'  {os.path.basename(fpath)}:{lineno} ({len(line)}ch) [{line_type}]: {stripped[:90]}')
        except Exception as e:
            logger.debug('except Exception: %s', e)
            logger.debug('except Exception: %s', e)
            print(f'  读取失败: {e}')

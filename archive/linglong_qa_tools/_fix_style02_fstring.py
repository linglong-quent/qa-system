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
fstring_issues = []
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
                    if 'f"' in stripped or "f'" in stripped:
                        fstring_issues.append((fpath, lineno, line))
        except Exception as e:
            logger.debug('except Exception: %s', e)
            logger.debug('except Exception: %s', e)
            pass
print(f'\nf-string 类型: {len(fstring_issues)} 个')
fixed_count = 0
for (fpath, lineno, line) in fstring_issues:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')
    target_line = lines[lineno - 1]
    indent = target_line[:len(target_line) - len(target_line.lstrip())]
    if '=' in target_line:
        parts = target_line.split('=', 1)
        var_name = parts[0].strip()
        fstring = parts[1].strip()
        if fstring.startswith('f"') or fstring.startswith("f'"):
            quote_char = fstring[1]
            inner_content = fstring[2:-1]
            if len(inner_content) > 100:
                new_lines = []
                new_lines.append(f'{indent}{var_name} = f{quote_char}{inner_content[:50]}{quote_char}')
                remaining = inner_content[50:]
                while remaining:
                    new_lines.append(f'{indent}    f{quote_char}{remaining[:50]}{quote_char}')
                    remaining = remaining[50:]
                lines[lineno - 1] = '\n'.join(new_lines)
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                fixed_count += 1
                print(f'  ✅ 修复: {os.path.basename(fpath)}:{lineno}')
            else:
                print(f'  ⏭️  太短无需修复: {os.path.basename(fpath)}:{lineno}')
        else:
            print(f'  ❌ 不是 f-string: {os.path.basename(fpath)}:{lineno}')
    else:
        print(f'  ❌ 不含等号: {os.path.basename(fpath)}:{lineno}')
print(f'\n共修复 {fixed_count} 个 f-string STYLE-02')

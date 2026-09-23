import pathlib

p = pathlib.Path("scripts/chk_healthscorer.py")
lines = p.read_text(encoding='utf-8').split('\n')

# 找配置加载段
config_start = None
layer_a = None
for i, line in enumerate(lines):
    if '0-污染模式：配置在 QA 系统中' in line:
        config_start = i
    if 'Layer A: 内置 checker' in line and config_start is not None:
        layer_a = i
        break

print(f"config: {config_start+1}, layer_a: {layer_a+1}")

# 提取成方法（缩进不变，都是类方法体 8 空格）
func_lines = lines[config_start:layer_a]
new_method = ['',
              '    def _load_config(self, profile: str, bootstrap: bool):',
              '        """加载项目配置（0-污染模式优先）"""']
new_method.extend(func_lines)

# __init__ 里替换
new_init = lines[:config_start] + [
    '',
    '        self._load_config(profile, bootstrap)',
    '',
] + lines[layer_a:]

result = new_init + new_method
p.write_text('\n'.join(result), encoding='utf-8')
print("extracted _load_config()")

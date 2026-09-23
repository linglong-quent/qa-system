import pathlib

p = pathlib.Path("scripts/chk_healthscorer.py")
lines = p.read_text(encoding='utf-8').split('\n')

layer_a = None
layer_b = None
for i, line in enumerate(lines):
    if 'Layer A: 内置 checker' in line:
        layer_a = i
    if 'Layer B: 项目插件' in line:
        layer_b = i
        break

print(f"A: {layer_a+1}, B: {layer_b+1}")

func_lines = lines[layer_a:layer_b]
new_method = ['',
              '    def _register_checkers(self):',
              '        """注册所有内置 checker"""']
new_method.extend(func_lines)

new_init = lines[:layer_a] + [
    '',
    '        self._register_checkers()',
    '',
] + lines[layer_b:]

result = new_init + new_method
p.write_text('\n'.join(result), encoding='utf-8')
print("extracted _register_checkers()")

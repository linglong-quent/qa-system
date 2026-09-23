import pathlib

p = pathlib.Path('D:/WB/TDX/tools/evidence/_probe_sync.py')
lines = p.read_text(encoding='utf-8').split('\n')

# 从 line 281 (0-indexed 280) 开始，跟踪括号深度
depth = 0
for i in range(280, min(480, len(lines))):
    line = lines[i]
    for ch in line:
        if ch in '{[(':
            depth += 1
        elif ch in '}])':
            depth -= 1
    if depth <= 0 and i > 280:
        print(f'line {i+1}: depth={depth}: {line[:60]}')
        break

print(f'final depth at 478: ', end='')
depth = 0
for i in range(280, 478):
    line = lines[i]
    for ch in line:
        if ch in '{[(':
            depth += 1
        elif ch in '}])':
            depth -= 1
print(depth)

import pathlib
t = pathlib.Path("scripts/qa_self_test.py").read_text(encoding='utf-8')
lines = t.split('\n')
for i, line in enumerate(lines, 1):
    if line.startswith('def main') or (line.startswith('    print("') and any(c.isdigit() for c in line[:20])):
        print(f"{i}: {line.strip()[:60]}")

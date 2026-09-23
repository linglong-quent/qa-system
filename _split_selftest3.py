import pathlib

p = pathlib.Path("scripts/qa_self_test.py")
t = p.read_text(encoding='utf-8')

# 找 main() 开头到 section 2 结束
old = '''def main():  # noqa: STYLE-06
    global passed, failed
    base = _PROJECT_ROOT
    scripts_dir = _SCRIPTS_DIR

    print("=" * 60)
    print("  QA System Self-Test")
    print(f"  Project root: {base}")
    print("=" * 60)
    print()

    # =============================================
    print("1. File integrity")
    print("  " + "-" * 50)'''

new = '''def _test_file_and_ast(base: str, scripts_dir: str):
    """Sections 1-2: file integrity + AST parse"""
    print("=" * 60)
    print("  QA System Self-Test")
    print(f"  Project root: {base}")
    print("=" * 60)
    print()
    print("1. File integrity")
    print("  " + "-" * 50)'''

assert old in t
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("extracted _test_file_and_ast() start")

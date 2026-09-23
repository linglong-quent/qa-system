import pathlib, re

p = pathlib.Path("scripts/qa_self_test.py")
t = p.read_text(encoding='utf-8')

# 提取文件完整性检查为函数
old_main_start = "def main():  # noqa: STYLE-06\n    global passed, failed\n    base = _PROJECT_ROOT\n    scripts_dir = _SCRIPTS_DIR"
new_func = '''def _test_file_integrity(base: str, scripts_dir: str):
    """1. File integrity check"""
    print("=" * 60)
    print("  QA System Self-Test")
    print(f"  Project root: {base}")
    print("=" * 60)
    print()

    print("1. File integrity")
    print("  " + "-" * 50)

    core_files = [
        "scripts/qa_check.py",
        "scripts/chk_healthscorer.py",
        "scripts/chk_inplacechecker.py",
        "scripts/chk_lookaheadchecker.py",
        "scripts/chk_secretchecker.py",
        "scripts/chk_deadcodechecker.py",
        "scripts/chk_cyclicchecker.py",
        "scripts/chk_codebanchecker.py",
        "scripts/chk_codeban_a.py",
        "scripts/chk_codeban_b.py",
        "scripts/chk_importboundary.py",
        "scripts/chk_configauditchecker.py",
        "scripts/chk_load_yaml.py",
        ".ai/config/review-rules.yaml",
        ".ai/config/secrets-scan.yaml",
        ".ai/config/dead-code.yaml",
        ".ai/config/ai-pipeline.yaml",
        ".ai/config/ai-whitelist.yaml",
        ".ai/config/arch-review.yaml",
        ".ai/schemas/qa-report.schema.json",
        ".ai/schemas/qa-gate-report.schema.json",
        ".pre-commit-config.yaml",
        ".github/workflows/ai-code-review.yml",
        ".github/workflows/ai-nightly-scan.yml",
        "docs/01_核心文档/SPEC-ai-coding-compliance.md",
        "docs/01_核心文档/SPEC-quality-gates.md",
    ]
    for f in core_files:
        check_file(os.path.join(base, f), f)
    check_dir(os.path.join(base, ".ai/plugins"), ".ai/plugins/")
    print()


def _test_ast_parse(base: str, scripts_dir: str):
    """2. Python AST parse check"""
    print("2. Python AST parse")
    print("  " + "-" * 50)

    for f in sorted(os.listdir(scripts_dir)):
        if not f.endswith(".py"):
            continue
        path = os.path.join(scripts_dir, f)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                ast.parse(fh.read())
            check(True, f)
        except SyntaxError as e:
            check(False, f, str(e))

    plugin_dir = os.path.join(base, ".ai/plugins")
    if os.path.isdir(plugin_dir):
        for root, dirs, files in os.walk(plugin_dir):
            for f in files:
                if not f.endswith(".py") or f == "__init__.py":
                    continue
                path = os.path.join(root, f)
                rel = os.path.relpath(path, base)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        ast.parse(fh.read())
                    check(True, rel)
                except SyntaxError as e:
                    check(False, rel, str(e))
    print()


def main():  # noqa: STYLE-06
    global passed, failed
    base = _PROJECT_ROOT
    scripts_dir = _SCRIPTS_DIR'''

assert old_main_start in t
t = t.replace(old_main_start, new_func)

p.write_text(t, encoding='utf-8')
print("extracted _test_file_integrity and _test_ast_parse from main()")

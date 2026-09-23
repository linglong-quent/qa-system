import pathlib

p = pathlib.Path("scripts/qa_self_test.py")
t = p.read_text(encoding='utf-8')

# 找 main() 里的第一段（文件完整性检查）
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
    print("1. File integrity")'''

new = '''def _test_file_integrity(base: str, scripts_dir: str):
    """1. File integrity"""
    print("=" * 60)
    print("  QA System Self-Test")
    print(f"  Project root: {base}")
    print("=" * 60)
    print()
    print("1. File integrity")'''

assert old in t, "old not found"
t = t.replace(old, new)

# 把 core_files 列表和检查循环也提取
old2 = '''    core_files = [
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
        # v1.1 修复 T03-R7：docs 已迁入编号目录，自检清单同步迁移后布局
        "docs/01_核心文档/SPEC-ai-coding-compliance.md",
        "docs/01_核心文档/SPEC-quality-gates.md",
    ]
    for f in core_files:
        check_file(os.path.join(base, f), f)
    check_dir(os.path.join(base, ".ai/plugins"), ".ai/plugins/")

    print()

    # =============================================
    print("2. Python AST parse")'''

# 这部分已经在函数里了，不需要重复

p.write_text(t, encoding='utf-8')
print("extracted _test_file_integrity()")

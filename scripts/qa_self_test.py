#!/usr/bin/env python3
"""QA 绯荤粺鑷宸ュ叿 鈥?楠岃瘉绯荤粺鐨勫畬鏁存€с€佷竴鑷存€с€佸彲杩愯鎬?
涓嶄緷璧栦换浣曢」鐩唬鐮侊紝鍙鏌?QA 绯荤粺鑷韩銆?鐢ㄤ簬锛氬畨瑁呭悗楠岃瘉 / CI 鑷 / 鐗堟湰鍗囩骇鍚庣‘璁?
妫€鏌ラ」:
  1. 鏂囦欢瀹屾暣鎬?鈥?鎵€鏈夋牳蹇冩枃浠跺瓨鍦?  2. 璇硶姝ｇ‘鎬?鈥?鎵€鏈?.py 鍙?AST 瑙ｆ瀽
  3. 鎺ュ彛涓€鑷存€?鈥?姣忎釜 checker 鏈?check() 骞惰繑鍥?(int, list)
  4. 閰嶇疆涓€鑷存€?鈥?review-rules.yaml 涓?checker 涓€涓€瀵瑰簲
  5. Schema 鏈夋晥鎬?鈥?qa-report.schema.json 鍚堟硶
  6. YAML 璇硶 鈥?鎵€鏈?.yaml .yml 鍙В鏋?  7. 鎻掍欢鍙彂鐜?鈥?.ai/plugins/ 鐩綍缁撴瀯姝ｅ父
  8. 杩愯娴嬭瘯 鈥?瀹屾暣璺戜竴杞紝纭涓嶅穿婧?"""
import ast, json, os, sys, importlib, importlib.util

# yaml 仅在 YAML 语法检查时使用，非安装时自测不阻塞
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_OK = "\033[92mOK\033[0m"
_FAIL = "\033[91mFAIL\033[0m"
_SKIP = "\033[93mSKIP\033[0m"

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)

passed = 0
failed = 0
warnings = []


def check(condition: bool, label: str, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  [{_OK}] {label}")
        passed += 1
    else:
        print(f"  [{_FAIL}] {label}" + (f" 鈥?{detail}" if detail else ""))
        failed += 1


def check_dir(path: str, label: str) -> bool:
    ok = os.path.isdir(path)
    check(ok, label, f"not found: {path}")
    return ok


def check_file(path: str, label: str) -> bool:
    ok = os.path.isfile(path)
    check(ok, label, f"not found: {path}")
    return ok


def main():
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
    print("  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

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
        ".pre-commit-config.yaml",
        ".github/workflows/ai-code-review.yml",
        ".github/workflows/ai-nightly-scan.yml",
        "docs/ai-coding-compliance.md",
        "docs/quality-gates.md",
    ]
    for f in core_files:
        check_file(os.path.join(base, f), f)
    check_dir(os.path.join(base, ".ai/plugins"), ".ai/plugins/")
    check_dir(os.path.join(base, "_project_examples"), "_project_examples/")

    print()

    # =============================================
    print("2. Python AST parse")
    print("  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

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

    # AST check for plugins
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

    # =============================================
    print("3. YAML syntax")
    print("  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

    if not _HAS_YAML:
        print("  [SKIP] 未安装 pyyaml，跳过 YAML 语法检查")
    else:
        yaml_dirs = [
            os.path.join(base, ".ai/config"),
            os.path.join(base, ".github/workflows"),
        ]
        for d in yaml_dirs:
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if not (f.endswith(".yaml") or f.endswith(".yml")):
                    continue
                path = os.path.join(d, f)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        yaml.safe_load(fh)
                    check(True, os.path.relpath(path, base))
                except yaml.YAMLError as e:
                    check(False, os.path.relpath(path, base), str(e))

        # pre-commit config
        try:
            with open(os.path.join(base, ".pre-commit-config.yaml"), "r", encoding="utf-8") as f:
                yaml.safe_load(f)
            check(True, ".pre-commit-config.yaml")
        except yaml.YAMLError as e:
            check(False, ".pre-commit-config.yaml", str(e))

    print()

    # =============================================
    print("4. Interface contract (all checkers)")
    print("  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

    checker_modules = [
        ("chk_inplacechecker",    "InplaceChecker"),
        ("chk_lookaheadchecker",  "LookaheadChecker"),
        ("chk_secretchecker",     "SecretChecker"),
        ("chk_deadcodechecker",   "DeadCodeChecker"),
        ("chk_cyclicchecker",     "CyclicImportChecker"),
        ("chk_codebanchecker",    "CodeBanChecker"),
        ("chk_importboundary",    "ImportBoundaryChecker"),
    ]
    for mod_name, cls_name in checker_modules:
        try:
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            instance = cls({}, base)
            result = instance.check()
            ok = (
                isinstance(result, tuple)
                and len(result) == 2
                and isinstance(result[0], int)
                and isinstance(result[1], list)
            )
            check(ok, f"{mod_name}.{cls_name}.check()", "must return (int, list)")
        except Exception as e:
            check(False, f"{mod_name}.{cls_name}", str(e))

    print()

    # =============================================
    print("5. Schema validation")
    print("  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

    schema_path = os.path.join(base, ".ai/schemas/qa-report.schema.json")
    if os.path.exists(schema_path):
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            check("properties" in schema, "qa-report.schema.json", "missing properties")
            check("required" in schema, "qa-report.schema.json", "missing required")
        except json.JSONDecodeError as e:
            check(False, "qa-report.schema.json", str(e))
    else:
        check(False, "qa-report.schema.json", "file not found")

    print()

    # =============================================
    print("6. Config consistency")
    print("  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

    config_path = os.path.join(base, ".ai/config/review-rules.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        expected_checker_ids = {
            "inplace_check", "lookahead_check", "secret_check",
            "deadcode_check", "cyclic_check", "code_ban_check",
            "import_boundary_check",
        }
        for cid in expected_checker_ids:
            section = config.get(cid)
            check(section is not None, f"config has '{cid}'",
                  f"section not found in review-rules.yaml")

        # Verify plugin config
        plugins_config = config.get("plugins")
        check(plugins_config is not None, "config has 'plugins' section")

        # Verify profiles match current checkers
        profiles = config.get("profiles", {})
        check(len(profiles) >= 2, "profiles >= 2 (full/dev/quick)")

    print()

    # =============================================
    print("7. Runtime smoke test")
    print("  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

    try:
        sys.path.insert(0, scripts_dir)
        from chk_healthscorer import HealthScorer
        scorer = HealthScorer(base)
        report = scorer.run_all()
        check("errors" in report, "HealthScorer.run_all() returns 'errors'")
        check("checkers" in report, "HealthScorer.run_all() returns 'checkers'")
        check(report["errors"] >= 0, f"errors >= 0 (got {report['errors']})")

        # Verify at least built-in checkers present
        core_ids = {"inplace_check", "lookahead_check", "secret_check",
                     "deadcode_check", "cyclic_check", "code_ban",
                     "import_boundary"}
        present = set(report["checkers"].keys())
        missing = core_ids - present
        check(len(missing) == 0, f"All built-in checkers present",
              f"missing: {missing}")

    except Exception as e:
        check(False, f"Runtime smoke test failed", str(e))

    print()

    # =============================================
    print("8. Entry point test")
    print("  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(scripts_dir, "qa_check.py"), "list"],
            capture_output=True, cwd=base, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        check(result.returncode == 0, "scripts/qa_check.py list 鈥?exit=0")
        check("import_boundary" in stdout, "list shows import_boundary")
    except Exception as e:
        check(False, "scripts/qa_check.py list", str(e))

    print()

    # =============================================
    print("=" * 60)
    print(f"  Result: {passed} passed, {failed} failed")
    if failed > 0:
        print(f"  鈿狅笍  {failed} check(s) failed 鈥?review above")
    else:
        print("  鉁?All checks passed")
    print("=" * 60)

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

    print("9. Gate end-to-end")
    print("  ----------------------------")
    try:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(scripts_dir, "qa_gate.py"), "--report"],
                          capture_output=True, timeout=30, cwd=base)
        passed_test = r.returncode == 0
        # Even if gate denies, it should exit with code 1, not crash
        stdout = r.stdout.decode("utf-8", errors="replace")
        check("PASS" in stdout, "qa_gate.py produces output")
        check("VERDICT" in stdout or "Verdict" in stdout, "qa_gate produces verdict")
    except Exception as e:
        check(False, "qa_gate end-to-end", str(e))

    print()

#!/usr/bin/env python3
"""
Pre-Push Hook: 推送前本地验证能过 CI

安装（在项目根目录运行）:
    python scripts/pre_push_hook.py --install

之后每次 git push origin 前会自动跑本地检查，不过不让推。
"""

import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def check(desc: str, cmd: list[str]) -> bool:
    print(f"  ⟳ {desc}...", end=" ", flush=True)
    code, out = run_cmd(cmd)
    if code == 0:
        print("✅")
        return True
    print(f"❌\n{out[:500]}")
    return False


def main() -> int:
    # git pre-push hook 传入参数: remote, url
    if len(sys.argv) < 2 or sys.argv[1] != "origin":
        return 0  # 只检查推送到 origin

    print("\n=== Pre-Push 本地验证 ===")

    ok = True

    ok &= check(
        "black format",
        [
            sys.executable,
            "-m",
            "black",
            "--check",
            "--line-length",
            "120",
            "--target-version",
            "py312",
            "--exclude",
            "_deprecated|archive|build|\\.venv|_tmp",
            ".",
        ],
    )

    ok &= check(
        "isort import",
        [
            sys.executable,
            "-m",
            "isort",
            "--check-only",
            "--profile",
            "black",
            "--line-length",
            "120",
            "--skip",
            "_deprecated",
            "--skip",
            "archive",
            "--skip",
            "build",
            "--skip",
            ".venv",
            ".",
        ],
    )

    ok &= check(
        "flake8 lint",
        [
            sys.executable,
            "-m",
            "flake8",
            "--max-line-length",
            "120",
            "--max-complexity",
            "10",
            "--extend-ignore",
            "E203,W503",
            "--exclude",
            "_deprecated,archive,build,.venv,_dev,_ci_*,_tmp_*,_still_*,"
            "_e2e_*,_test_*,linglong/linglong,linglong/_still_*,"
            "linglong/_e2e_*,linglong/_test_*,bailian,"
            "scripts,data,logs,runtime,archive,tools",
            ".",
        ],
    )

    ok &= check("mypy type", [sys.executable, "-m", "mypy", "--ignore-missing-imports", "."])

    if ok:
        print("\n=== ✅ Pre-Push 全部通过，继续推送 ===")
        return 0
    else:
        print("\n=== ❌ 检查未通过，推送已阻止 ===")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--install":
        hook_path = Path(".git/hooks/pre-push")
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_script = f"""#!/usr/bin/env bash
python {__file__} "$1" "$2"
"""
        hook_path.write_text(hook_script)
        hook_path.chmod(0o755)
        print(f"✅ Pre-push hook 已安装到 {hook_path}")
        sys.exit(0)

    sys.exit(main())

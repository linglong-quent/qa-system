#!/usr/bin/env python3
"""git_safe_branch: 从远程 main 安全建分支，杜绝本地脏 main

用法:
    python scripts/git_safe_branch.py feat/my-feature

流程:
    1. fetch origin main（确保最新）
    2. 检查本地工作区是否干净（阻止脏提交）
    3. 从 origin/main 建分支
"""

import subprocess
import sys


def run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def main() -> int:
    if len(sys.argv) < 2:
        print("❌ 用法: python scripts/git_safe_branch.py <branch-name>")
        return 1

    branch_name = sys.argv[1]

    # 1. fetch 远程 main
    print("⟳ Fetching origin/main...")
    r = run(["git", "fetch", "origin", "main"])
    if r.returncode != 0:
        print(f"❌ git fetch 失败:\n{r.stderr}")
        return 1
    print("✅ origin/main 已更新")

    # 2. 检查本地工作区是否干净
    r = run(["git", "status", "--porcelain"])
    if r.stdout.strip():
        print("❌ 本地工作区有未提交的变更，请先 stash 或 commit:")
        print(r.stdout)
        return 1
    print("✅ 工作区干净")

    # 3. 确保当前不在 feat/qa-clean 等脏分支上
    r = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = r.stdout.strip()
    print(f"  当前分支: {current_branch}")

    # 4. 从 origin/main 建分支
    r = run(["git", "checkout", "-b", branch_name, "origin/main"])
    if r.returncode != 0:
        print(f"❌ 建分支失败:\n{r.stderr}")
        return 1

    print(f"✅ 分支 {branch_name} 已从 origin/main 创建")
    return 0


if __name__ == "__main__":
    sys.exit(main())

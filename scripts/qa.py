#!/usr/bin/env python3
"""QA CLI v4.0 — 统一命令行入口（Gate0-Gate9 · 本地/双模运行）

用法:
  qa [--project <路径>] <命令> [参数]

命令:
  plan  init|check|feedback         — 质量规划 (PDCA)
  check [checker名] [--bootstrap]    — 全量/单条检查
  classify                          — 问题分类
  gate [--report] [--gate=N]        — Gate0-Gate9 十层门禁
  gate --gate=3.1                   — 仅运行框架手册自审
  local                             — 本地模式: 全量检查 + 门禁 + 分类
  defect summary|close|suspend      — 不良品追踪
  self-test                         — 系统自检
  setup [--project <路径>]          — 项目初始化
  list                              — 列出所有 checker
  ai integrate|handoff|status       — AI 集成

环境变量:
  QA_PROJECT=<路径>    — 指定目标项目（替代 --project）
  QA_ENV=production    — 生产模式（门禁自动通过）
  QA_SYSTEM_ROOT=<路径> — QA 系统根目录（0-污染模式）
  QA_PROJECT_NAME=<名> — 目标项目名（0-污染模式）
"""
import os, sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _resolve_project() -> str:
    """解析目标项目路径（支持环境变量和 --project 参数）"""
    # 优先环境变量
    env_project = os.environ.get("QA_PROJECT", "")
    if env_project:
        return env_project

    # 检查命令行 --project 参数
    for i, arg in enumerate(sys.argv):
        if arg == "--project" and i + 1 < len(sys.argv):
            return os.path.abspath(sys.argv[i + 1])

    # 默认：QA 系统自身目录（当检查自身时）或 CWD
    return _PROJECT_ROOT


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return

    cmd = sys.argv[1]

    # 跳过 --project 参数（已被解析）
    rest = [a for a in sys.argv[2:] if not a.startswith("--project") and a != sys.argv[2] if any(
        sys.argv[i] == "--project" and sys.argv[i+1] == a for i in range(len(sys.argv))
    ) is False]

    # 更简单的过滤
    filtered_rest = []
    skip_next = False
    for i, a in enumerate(sys.argv[2:]):
        if skip_next:
            skip_next = False
            continue
        if a == "--project":
            skip_next = True
            continue
        filtered_rest.append(a)
    rest = filtered_rest

    project_root = _resolve_project()

    if cmd == "list":
        from qa_check import list_checkers
        list_checkers(project_root)

    elif cmd == "check":
        if rest and rest[0] in ("inplace", "lookahead", "secret", "deadcode",
                                 "cyclic", "code-ban", "boundary", "config", "gates",
                                 "claude", "prod", "codestyle", "governance",
                                 "securityplus", "documentation", "zeroprint",
                                 "customrules", "fusedetect", "docconsistency"):
            from qa_check import run_single
            failed = run_single(rest[0], project_root)
            sys.exit(1 if failed else 0)
        else:
            os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_check.py health --project-root {project_root}")

    elif cmd == "plan":
        action = rest[0] if rest else "check"
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_plan.py {action} --project {project_root}")

    elif cmd == "classify":
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_classify.py --project {project_root}")

    elif cmd == "gate":
        # 支持 --gate=N 单门禁运行
        gate_args = " ".join(rest)
        if "--project" not in gate_args:
            gate_args += f" --project {project_root}"
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_gate.py {gate_args}")

    elif cmd == "local":
        """本地一体化模式: check → classify → gate"""
        print("=" * 60)
        print(f"  QA 本地全流程 — {project_root}")
        print("=" * 60)

        # P0: 全量检查
        print("\n[Step 1/3] 全量检查...")
        ret = os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_check.py health --project-root {project_root}")
        if ret != 0:
            print("  ⚠️  检查发现问题，继续执行门禁...")

        # P1: 问题分类
        print("\n[Step 2/3] 问题分类...")
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_classify.py --project {project_root}")

        # P2: 门禁
        print("\n[Step 3/3] 十层门禁...")
        ret = os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_gate.py --project {project_root}")

        print("\n" + "=" * 60)
        sys.exit(ret)

    elif cmd == "defect":
        action = rest[0] if rest else "summary"
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_defect.py {action} {' '.join(rest[1:])}")

    elif cmd == "self-test":
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_self_test.py")

    elif cmd == "setup":
        project = project_root if project_root != _PROJECT_ROOT else "."
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_setup.py --project {project}")

    elif cmd == "ai":
        action = rest[0] if rest else "status"
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_ai.py {action} {' '.join(rest[1:])}")

    elif cmd == "validate-config":
        """验证所有配置文件的完整性和一致性"""
        from chk_load_yaml import load_yaml
        config_dir = os.path.join(_PROJECT_ROOT, ".ai/config")
        if not os.path.isdir(config_dir):
            print(f"❌ 无配置目录: {config_dir}")
            sys.exit(1)
        errors = 0
        for f in sorted(os.listdir(config_dir)):
            if not f.endswith((".yaml", ".yml")):
                continue
            fpath = os.path.join(config_dir, f)
            try:
                data = load_yaml(fpath)
                print(f"  ✅ {f} — {len(data)} 个顶级键")
            except Exception as e:
                print(f"  ❌ {f} — {e}")
                errors += 1
        print(f"\n{errors} 个错误")
        sys.exit(errors if errors > 0 else 0)

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

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
import os, sys, subprocess, logging

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _run(script_name, *args):
    """运行 scripts/ 下的模块（用 subprocess 自动处理路径中的空格）."""
    script_path = os.path.join(_SCRIPTS_DIR, script_name)
    return subprocess.call([sys.executable, script_path] + list(args))


def _parse_argv():
    """解析命令行参数，剥离 --project <路径>，返回 (project_root, cmd, rest).

    支持两种形式:
      --project <路径>   空格分隔
      --project=<路径>   等号分隔

    命令行优先于环境变量 QA_PROJECT。
    """
    project_root = None
    cmd = None
    rest = []
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--project":
            if i + 1 < len(args):
                project_root = os.path.abspath(args[i + 1])
                i += 2
                continue
            print("错误: --project 需要参数")
            sys.exit(1)
        elif a.startswith("--project="):
            project_root = os.path.abspath(a.split("=", 1)[1])
            i += 1
            continue
        if cmd is None:
            cmd = a
        else:
            rest.append(a)
        i += 1

    # 环境变量作为回退（仅在命令行未指定时）
    env_project = os.environ.get("QA_PROJECT", "")
    if env_project and not project_root:
        project_root = env_project

    if not project_root:
        project_root = _PROJECT_ROOT

    return project_root, cmd, rest


def main():  # noqa: STYLE-06
    project_root, cmd, rest = _parse_argv()

    if cmd is None or cmd in ("-h", "--help"):
        print(__doc__)
        return

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
            args = ["health", "--project-root", project_root]
            if "--bootstrap" in rest:
                args.append("--bootstrap")
            sys.exit(_run("qa_check.py", *args))

    elif cmd == "plan":
        action = rest[0] if rest else "check"
        sys.exit(_run("qa_plan.py", action, "--project", project_root))

    elif cmd == "classify":
        sys.exit(_run("qa_classify.py", "--project", project_root))

    elif cmd == "gate":
        # 支持 --gate=N 单门禁运行；rest 透传
        gate_args = list(rest)
        if not any(a.startswith("--project") for a in gate_args):
            gate_args.extend(["--project", project_root])
        sys.exit(_run("qa_gate.py", *gate_args))

    elif cmd == "local":
        """本地一体化模式: check → classify → gate"""
        print("=" * 60)
        print(f"  QA 本地全流程 — {project_root}")
        print("=" * 60)

        # P0: 全量检查
        print("\n[Step 1/3] 全量检查...")
        ret = _run("qa_check.py", "health", "--project-root", project_root)
        if ret != 0:
            print("  ⚠️  检查发现问题，继续执行门禁...")

        # P1: 问题分类
        print("\n[Step 2/3] 问题分类...")
        _run("qa_classify.py", "--project", project_root)

        # P2: 门禁
        print("\n[Step 3/3] 十层门禁...")
        ret = _run("qa_gate.py", "--project", project_root)

        print("\n" + "=" * 60)
        sys.exit(ret)

    elif cmd == "defect":
        action = rest[0] if rest else "summary"
        sys.exit(_run("qa_defect.py", action, *rest[1:]))

    elif cmd == "self-test":
        sys.exit(_run("qa_self_test.py"))

    elif cmd == "setup":
        project = project_root if project_root != _PROJECT_ROOT else "."
        sys.exit(_run("qa_setup.py", "--project", project))

    elif cmd == "ai":
        action = rest[0] if rest else "status"
        sys.exit(_run("qa_ai.py", action, *rest[1:]))

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
            except Exception:
                logger.warning("配置文件解析失败: %s", f, exc_info=True)
                errors += 1
        print(f"\n{errors} 个错误")
        sys.exit(errors if errors > 0 else 0)

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

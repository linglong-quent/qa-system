#!/usr/bin/env python3
"""QA CLI — 统一命令行入口

用法:
  qa plan init|check|feedback    — 质量规划
  qa check [单条checker]         — 全量/单条检查
  qa classify                    — 问题分类
  qa gate [--report]             — 总闸门
  qa defect summary|close|suspend — 不良品追踪
  qa self-test                   — 系统自检
  qa setup [--project <path>]    — 项目初始化
  qa list                        — 列出 checker
  qa ai integrate|handoff|status  — AI 集成
"""
import os, sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    # Map commands to their script modules
    if cmd == "list":
        from qa_check import list_checkers
        list_checkers(os.environ.get("QA_PROJECT", _PROJECT_ROOT))

    elif cmd == "check":
        if rest and rest[0] in ("inplace","lookahead","secret","deadcode",
                                 "cyclic","code-ban","boundary","config","gates","claude"):
            from qa_check import run_single
            failed = run_single(rest[0], os.environ.get("QA_PROJECT", _PROJECT_ROOT))
            sys.exit(1 if failed else 0)
        else:
            os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_check.py health")

    elif cmd == "plan":
        action = rest[0] if rest else "check"
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_plan.py {action}")

    elif cmd == "classify":
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_classify.py")

    elif cmd == "gate":
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_gate.py {' '.join(rest)}")

    elif cmd == "defect":
        action = rest[0] if rest else "summary"
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_defect.py {action} {' '.join(rest[1:])}")

    elif cmd == "self-test":
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_self_test.py")

    elif cmd == "setup":
        project = rest[1] if len(rest) >= 2 and rest[0] == "--project" else "."
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_setup.py --project {project}")

    elif cmd == "ai":
        action = rest[0] if rest else "status"
        os.system(f"{sys.executable} {_SCRIPTS_DIR}/qa_ai.py {action} {' '.join(rest[1:])}")

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

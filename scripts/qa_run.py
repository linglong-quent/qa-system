#!/usr/bin/env python3
"""QA 运行上下文（run-id 产物隔离）— 编排契约 v1.1

设计目标（T03 §6.4 B3 / T12 ②③）：
  * 每次调用拥有独占的 run 目录，并行 DAG 分支互不覆盖；
  * run 目录固定位于一个基准目录（默认 QA 系统自己的 .ai/runs/），
    与目标项目目录解耦 —— 保持 0-污染；
  * 所有门禁/检查产物路径都由本模块解析，禁止再出现"全局单例"路径。

目录布局：
  {base}/.ai/runs/{run_id}/
      run.json          # 运行元数据（run_id / 命令 / 参数 / 状态 / 产物清单）
      qa-report.json    # 采集阶段产物（qa_check --run-id）
      gate-report.json  # 裁决阶段产物（qa_gate --run-id --json）
      tasks.json        # 分类后的可执行任务（qa_classify --run-id）
"""
import json
import os
import re
import uuid
from datetime import datetime

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def new_run_id(prefix: str = "qa") -> str:
    """生成可排序、可读、可并发唯一的 run-id：{prefix}-{YYYYmmdd-HHMMSS}-{6hex}"""
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def validate_run_id(run_id: str) -> str:
    """校验 run-id 只含安全字符（防目录穿越 / 注入）"""
    if not RUN_ID_RE.match(run_id or ""):
        raise ValueError(
            f"非法 run-id: {run_id!r}（允许 1-64 位 [A-Za-z0-9._-]，且不以 . 或 - 开头）"
        )
    return run_id


def runs_base(project_root: str, qa_system_root: str = "", runs_dir: str = "") -> str:
    """解析 run 基准目录：--runs-dir > QA_SYSTEM_ROOT/.ai/runs > {project}/.ai/runs"""
    if runs_dir:
        return os.path.abspath(runs_dir)
    root = qa_system_root or os.environ.get("QA_SYSTEM_ROOT", "")
    if root:
        return os.path.join(os.path.abspath(root), ".ai", "runs")
    return os.path.join(os.path.abspath(project_root), ".ai", "runs")


def resolve_run_dir(run_id: str, project_root: str, qa_system_root: str = "",
                    runs_dir: str = "") -> str:
    """run-id → 绝对 run 目录（不存在则创建）"""
    d = os.path.join(runs_base(project_root, qa_system_root, runs_dir), validate_run_id(run_id))
    os.makedirs(d, exist_ok=True)
    return d


def write_run_meta(run_dir: str, **fields) -> str:
    """写/合并 run.json（运行元数据）。失败不阻断主流程。"""
    path = os.path.join(run_dir, "run.json")
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data.update(fields)
    data["updated_at"] = datetime.now().isoformat()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        return ""
    return path


def latest_run_id(project_root: str, qa_system_root: str = "", runs_dir: str = "") -> str:
    """返回最近一次 run-id（按 mtime），无则空串。供队长/成员"接手最近一轮"使用。"""
    base = runs_base(project_root, qa_system_root, runs_dir)
    if not os.path.isdir(base):
        return ""
    cands = []
    for name in os.listdir(base):
        p = os.path.join(base, name)
        if os.path.isdir(p) and RUN_ID_RE.match(name):
            cands.append((os.path.getmtime(p), name))
    return max(cands)[1] if cands else ""

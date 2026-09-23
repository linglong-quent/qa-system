#!/usr/bin/env python3
"""Checker: 运行态与进程层（T29 盲区②）

规则：
  DRIFT-PROC-001 代码-进程版本漂移 — 监听端口所属进程加载的脚本已被修改，
                  但进程启动时间早于文件 mtime ⇒ 进程仍在跑旧代码
  DEP-001        依赖端点无守护/停摆 — 被多处依赖的 host:port 不可达，
                  或声明的守护任务未处于 Ready/Running

平台：Windows 用 Get-NetTCPConnection / Get-CimInstance / Get-ScheduledTask；
      非 Windows 或探测失败时整体 skipped（不阻断），并在 issues 里说明。
接口: check() -> (errors: int, issues: list[str])
"""
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Tuple

PORT_LITERAL = re.compile(r"\b(?:127\.0\.0\.1|localhost|0\.0\.0\.0|host\.docker\.internal|"
                          r"(?:\d{1,3}\.){3}\d{1,3})[:：](\d{2,5})\b")
SCRIPT_IN_CMD = re.compile(r"([A-Za-z]:[\\/][^\s\"']+\.(?:py|js|ts|ps1|bat|sh))", re.I)


def _iter_py_files(root: str, scan_dirs: List[str]):
    skip = {".git", ".venv", ".deps", "node_modules", "__pycache__", "backups",
            "site-packages", "build", "dist"}
    targets = [os.path.join(root, d.rstrip("/\\")) for d in scan_dirs] or [root]
    for base in targets:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for fn in filenames:
                if fn.endswith((".py", ".js", ".ts", ".yaml", ".yml", ".json")):
                    yield os.path.join(dirpath, fn)


def _ps(cmd: str, timeout: int = 25):
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return None
        return p.stdout
    except Exception:
        return None


def _listening_ports() -> List[dict]:
    out = _ps("Get-NetTCPConnection -State Listen | "
              "Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Compress")
    if not out:
        return []
    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    return data or []


def _process_info(pid: int) -> dict:
    out = _ps(f"Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\" | "
              "Select-Object ProcessId,Name,CommandLine,CreationDate | ConvertTo-Json -Compress")
    if not out:
        return {}
    try:
        return json.loads(out) or {}
    except Exception:
        return {}


def _task_states() -> Dict[str, str]:
    """守护任务名 → 状态名。

    注意：`Get-ScheduledTask` 的 State 是 enum，`ConvertTo-Json` 会序列化成**整数**
    （1=Disabled 2=Queued 3=Ready 4=Running）——首轮实跑因此把 Ready 误判为
    "非 Ready/Running"，产生假阳性。这里在 PS 侧显式转字符串，并在 Python 侧
    对整数做兜底映射。
    """
    out = _ps("Get-ScheduledTask | Select-Object TaskName,"
              "@{n='State';e={[string]$_.State}} | ConvertTo-Json -Compress", timeout=60)
    if not out:
        return {}
    try:
        data = json.loads(out)
    except Exception:
        return {}
    if isinstance(data, dict):
        data = [data]
    num_map = {"1": "Disabled", "2": "Queued", "3": "Ready", "4": "Running", "0": "Unknown"}
    return {d.get("TaskName", ""): num_map.get(str(d.get("State", "")), str(d.get("State", "")))
            for d in data if d}


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


class RuntimeDriftChecker:
    """运行态：代码-进程漂移 + 端点守护/可达性"""

    CHECKER_ID = "runtime_drift"
    CHECKER_LABEL = "运行态与进程层"

    def __init__(self, config: dict, project_root: str):
        self.config = config or {}
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = self.config.get("scan_dirs", ["src/", "scripts/", "domain/"])
        self.min_dependents = int(self.config.get("min_dependents", 3))
        self.guardians = self.config.get("endpoint_guardians", {}) or {}
        self.probe = bool(self.config.get("probe_endpoints", True))

    # ── DRIFT-PROC-001 ────────────────────────────────────────
    def _drift(self) -> List[str]:
        out: List[str] = []
        if not sys.platform.startswith("win"):
            return out
        for conn in _listening_ports():
            pid = conn.get("OwningProcess")
            port = conn.get("LocalPort")
            if not pid:
                continue
            info = _process_info(pid)
            cmdline = info.get("CommandLine") or ""
            m = SCRIPT_IN_CMD.search(cmdline)
            if not m:
                continue
            script = m.group(1).replace("/", os.sep)
            if not os.path.isfile(script):
                continue
            created = info.get("CreationDate")
            try:
                # CreationDate 形如 /Date(1757...)/  或 ISO
                if isinstance(created, str) and created.startswith("/Date("):
                    start_ts = int(created[6:created.index(")")].split("+")[0]) / 1000.0
                else:
                    start_ts = datetime.fromisoformat(str(created).replace("Z", "")).timestamp()
            except Exception:
                continue
            mtime = os.path.getmtime(script)
            if mtime > start_ts + 1:
                out.append(
                    f"[DRIFT-PROC-001] 端口 {port} 由 PID {pid} 持有，其加载脚本 "
                    f"{script} 的磁盘 mtime({datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M:%S}) "
                    f"晚于进程启动({datetime.fromtimestamp(start_ts):%Y-%m-%d %H:%M:%S}) "
                    f"-> 进程仍运行旧代码，需重启（磁盘修复未生效）")
        return out

    # ── DEP-001 ───────────────────────────────────────────────
    def _dependents(self) -> Dict[int, List[str]]:
        deps: Dict[int, List[str]] = {}
        for path in _iter_py_files(self.project_root, self.scan_dirs):
            try:
                src = open(path, "r", encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for m in PORT_LITERAL.finditer(src):
                port = int(m.group(1))
                if 1 <= port <= 65535:
                    deps.setdefault(port, []).append(os.path.relpath(path, self.project_root))
        return deps

    def _deployment(self) -> List[str]:
        out: List[str] = []
        tasks = _task_states() if sys.platform.startswith("win") else {}
        deps = self._dependents()
        for port, files in sorted(deps.items(), key=lambda kv: -len(kv[1])):
            if len(files) < self.min_dependents:
                continue
            guardians = self.guardians.get(str(port)) or self.guardians.get(port) or []
            if guardians:
                alive = [t for t in guardians if tasks.get(t) in ("Ready", "Running")]
                if not alive:
                    out.append(
                        f"[DEP-001] 端点 {port} 被 {len(files)} 处依赖，但其守护任务 "
                        f"{guardians} 均非 Ready/Running（实测状态 "
                        f"{ {t: tasks.get(t, 'NOT-FOUND') for t in guardians} }）"
                        f" -> 停摆无告警")
            if self.probe and not _port_open("127.0.0.1", port):
                out.append(
                    f"[DEP-001] 端点 127.0.0.1:{port} 被 {len(files)} 处依赖但不可达 "
                    f"（示例：{files[:2]}）-> 依赖方将在运行期失败")
        return out

    def check(self) -> Tuple[int, List[str]]:
        issues = self._drift() + self._deployment()
        return len(issues), issues

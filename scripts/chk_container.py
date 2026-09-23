#!/usr/bin/env python3
"""Checker: 容器平面（T51 新增，关闭 T29「容器类规则未验证」）

规则：
  CONT-001 崩溃循环 / 停摆     — 容器处于 Restarting、或退出码非 0 的 Exited
  CONT-002 健康探针失败        — Health.Status == unhealthy（探针能报出来才算数）
  CONT-003 声明服务缺失        — compose/清单声明的服务在 docker 中不存在或未运行
  DRIFT-CONT-001 容器运行旧代码 — 容器 StartedAt 早于其 **bind mount 宿主目录内最新
                                 文件 mtime**（宿主代码改了、容器没重建）或早于镜像构建时间

设计要点（对齐 T29 精度原则）：
  * 一次性初始化容器（ExitCode==0 的 Exited）不算停摆；
  * 无 Health 配置的容器不参与 CONT-002（避免把"没配探针"当成"探针失败"）；
  * Docker 不可用 → 整体 skipped 并说明，不阻断。
接口: check() -> (errors: int, issues: list[str])
"""
import logging
logger = logging.getLogger(__name__)
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Tuple


def _docker(*args, timeout: int = 40) -> str:
    try:
        p = subprocess.run(["docker"] + list(args), capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        if p.returncode != 0:
            return ""
        return p.stdout
    except Exception:
        return ""


def _docker_available() -> bool:
    return bool(_docker("version", "--format", "{{.Server.Version}}", timeout=20).strip())


def _containers() -> List[dict]:
    out = _docker("ps", "-a", "--format", "{{json .}}")
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _inspect(names: List[str]) -> Dict[str, dict]:
    if not names:
        return {}
    out = _docker("inspect", *names, timeout=60)
    if not out.strip():
        return {}
    try:
        data = json.loads(out)
    except Exception:
        return {}
    res = {}
    for d in data:
        res[d.get("Name", "").lstrip("/")] = d
    return res


def _parse_ts(s: str):
    if not s or s.startswith("0001-"):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


CODE_EXT = (".py", ".js", ".ts", ".sql", ".sh")
CODE_DEST = ("/app/src", "/app/scripts", "/app/domain", "/app/ops", "/app/linglong",
             "/app/shared", "/app/config", "/src", "/scripts", "/domain", "/ops")
DATA_HINT = re.compile(
    r"(log|data|backup|heartbeat|registry|collect|cache|upload|download|tmp|"
    r"prometheus|grafana|clickhouse|postgres|redis|models|wheels|\.git)", re.I)


def _is_code_mount(m: dict) -> bool:
    """判断一个 bind mount 是否承载**代码**。

    首版 DRIFT-CONT-001 对所有 bind mount 都比较 mtime，实测 23 条命中全是
    日志/数据/备份目录（`logs`/`backups`/`heartbeat`）——它们本来就一直在写，
    与"代码是否更新"无关。现只认代码型挂载：
      * Destination 落在代码目录（/app/src、/app/scripts …），且
      * 宿主路径不含 data/log/backup/heartbeat 等数据语义词
    """
    dest = (m.get("Destination") or "").replace("\\", "/").rstrip("/")
    src = (m.get("Source") or "").replace("\\", "/")
    if m.get("Type") != "bind":
        return False
    if not any(dest == d or dest.startswith(d + "/") for d in CODE_DEST):
        return False
    if DATA_HINT.search(src.rsplit("/", 1)[-1] or ""):
        return False
    return True


def _newest_code_mtime(path: str, limit: int = 8000) -> float:
    """只统计代码文件的 mtime（排除数据/日志/备份）"""
    newest = 0.0
    n = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if not DATA_HINT.search(d)]
        for fn in filenames:
            if not fn.endswith(CODE_EXT):
                continue
            n += 1
            if n > limit:
                return newest
            try:
                m = os.path.getmtime(os.path.join(dirpath, fn))
                if m > newest:
                    newest = m
            except OSError:
                continue
    return newest


class ContainerPlaneChecker:
    """容器平面检查器"""

    CHECKER_ID = "container_plane"
    CHECKER_LABEL = "容器平面"

    def __init__(self, config: dict, project_root: str):
        self.config = config or {}
        self.project_root = os.path.abspath(project_root)
        self.max_restarts = int(self.config.get("max_restarts", 3))
        self.watch = self.config.get("watch_containers", []) or []
        self.required = self.config.get("required_services", []) or []
        self.mount_map = self.config.get("container_code_mounts", {}) or {}
        self.drift_grace_seconds = int(self.config.get("drift_grace_seconds", 60))

    def check(self) -> Tuple[int, List[str]]:
        if not _docker_available():
            return 0, ["[CONT-000] Docker 不可用 → 容器平面检查跳过（该平面未部署或守护未起）"]

        issues: List[str] = []
        rows = _containers()
        if not rows:
            return 0, ["[CONT-000] Docker 可用但无容器 → 容器平面为空，无缺陷可检"]

        names = [r.get("Names", "") for r in rows if r.get("Names")]
        insp = _inspect(names)

        for r in rows:
            name = r.get("Names", "")
            # 只检查量化项目相关容器（TDX/NEWSFORGE/FACTOR_FORGE/QA-SYSTEM/LINGLONG）
            _keep_prefixes = ("linglong-", "grafana", "tdx", "newsforge", "factor-forge", "qa-")
            if not name.startswith(_keep_prefixes):
                continue
            status = r.get("Status", "")
            state = (r.get("State") or "").lower()
            d = insp.get(name, {})
            st = d.get("State", {}) or {}
            exit_code = st.get("ExitCode")
            restarts = d.get("RestartCount", 0) or 0
            health = ((st.get("Health") or {}).get("Status") or "").lower()

            # 一次性初始化容器豁免（正常退出且未在重启）
            one_shot = (state == "exited" and exit_code == 0 and restarts == 0)

            # ── CONT-001 崩溃循环 / 停摆 ──
            if state == "restarting" or restarts > self.max_restarts:
                issues.append(
                    f"[CONT-001] 容器 '{name}' 处于崩溃循环：state={state} "
                    f"restarts={restarts}（阈值 {self.max_restarts}）status={status}")
            elif state == "exited" and not one_shot:
                issues.append(
                    f"[CONT-001] 容器 '{name}' 异常退出未恢复：exit_code={exit_code} "
                    f"restarts={restarts} status={status}")

            # ── CONT-002 健康探针失败 ──
            if health == "unhealthy":
                log = ""
                try:
                    hlog = st.get("Health", {}).get("Log", [])
                    if hlog:
                        log = (hlog[-1].get("Output") or "").strip().replace("\n", " ")[:120]
                except Exception as e:
                    logger.warning("container log fetch skipped: %s", e)
                issues.append(
                    f"[CONT-002] 容器 '{name}' 健康探针报 unhealthy -> 探针判定失败 "
                    f"{('最近输出: ' + log) if log else ''}")

            # ── DRIFT-CONT-001 容器运行旧代码 ──
            # 只比较**代码型挂载**（见 _is_code_mount）；显式配置的 container_code_mounts
            # 优先，自动探测仅作补充。
            started = _parse_ts(st.get("StartedAt", ""))
            mounts = list(self.mount_map.get(name) or [])
            for m in (d.get("Mounts") or []):
                if _is_code_mount(m) and m.get("Source"):
                    mounts.append(m["Source"])
            if started and mounts:
                for host_path in sorted(set(mounts)):
                    if not os.path.isdir(host_path):
                        continue
                    newest = _newest_code_mtime(host_path)
                    if newest <= 0:
                        continue
                    started_utc = started.replace(tzinfo=timezone.utc)
                    newest_dt = datetime.fromtimestamp(newest, tz=timezone.utc)
                    delta = (newest_dt - started_utc).total_seconds()
                    if delta > self.drift_grace_seconds:
                        issues.append(
                            f"[DRIFT-CONT-001] 容器 '{name}' 运行旧代码：启动于 "
                            f"{started_utc.strftime('%Y-%m-%d %H:%M:%S')}，但宿主代码目录 {host_path} 内"
                            f"最新 .py/.js/.sql/.sh 文件 mtime 为 "
                            f"{newest_dt.strftime('%Y-%m-%d %H:%M:%S')}（晚 {delta / 3600:.1f} 小时）"
                            f" -> 宿主代码已改、容器未重建")

        # ── CONT-003 声明服务缺失 ──
        running = {r.get("Names", "") for r in rows if (r.get("State") or "").lower() == "running"}
        for svc in self.required:
            if svc not in running:
                issues.append(
                    f"[CONT-003] 清单声明的服务 '{svc}' 未在运行（当前 running={len(running)} 个）"
                    f" -> 该服务缺失或停摆")

        return len(issues), issues

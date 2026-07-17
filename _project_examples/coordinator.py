#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P-A4 Coordinate — 原子锁管理器

设计文档: _spec/design-qa-closed-loop.md §P-A4
配置: .ai/config/coordinator-config.yaml
Schema: .ai/schemas/coordinator.schema.json

核心机制: os.open(O_CREAT | O_EXCL) + PID 心跳 + TTL 30 分钟
"""

import glob
import json
import os
import time
from datetime import datetime
from pathlib import Path

LOCK_DIR = ".ai/locks"
DEFAULT_TTL = 1800  # 30 分钟
PID_HEARTBEAT_INTERVAL = 120  # 2 分钟


def _lock_dir(project_root: str) -> str:
    return os.path.join(project_root, LOCK_DIR)


def _lock_path(project_root: str, filename: str) -> str:
    return os.path.join(_lock_dir(project_root), f"{filename}.lock")


def _ensure_lock_dir(project_root: str):
    path = _lock_dir(project_root)
    os.makedirs(path, exist_ok=True)
    return path


def _read_lock(lock_path: str) -> dict:
    """读取锁文件内容，失败返回空字典"""
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return {}


def _write_lock(lock_path: str, data: dict):
    """写入锁文件"""
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _pid_exists(pid: int) -> bool:
    """检查 PID 是否存活（跨平台）"""
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def _is_zombie(lock_path: str, ttl: int = DEFAULT_TTL) -> bool:
    """检查锁是否为僵尸锁（PID 不存活 或 超 TTL）"""
    data = _read_lock(lock_path)
    if not data:
        return True

    # PID 不存活
    pid = data.get("pid", -1)
    if pid > 0 and not _pid_exists(pid):
        return True

    # 超 TTL
    locked_at = data.get("locked_at", 0)
    if locked_at and (time.time() - locked_at) > ttl:
        return True

    return False


def _clean_zombie(lock_path: str, ttl: int = DEFAULT_TTL) -> bool:
    """清理僵尸锁，返回 True 表示清理成功"""
    if os.path.exists(lock_path) and _is_zombie(lock_path, ttl):
        try:
            os.remove(lock_path)
            return True
        except OSError:
            return False
    return False


def acquire_lock(project_root: str, filename: str, agent_id: str = "cli", ttl: int = DEFAULT_TTL) -> dict:
    """
    获取原子锁。

    返回:
        {"success": True, "lock_path": "..."}  — 成功
        {"success": False, "reason": "BUSY", "locked_by": "...", "locked_at": ...}  — 被占用
        {"success": False, "reason": "ERROR", "message": "..."}  — 异常
    """
    _ensure_lock_dir(project_root)
    lock_path = _lock_path(project_root, filename)

    # 先尝试清理僵尸锁
    _clean_zombie(lock_path, ttl)

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        now = time.time()
        lock_data = {
            "locked_by": agent_id,
            "locked_at": now,
            "pid": os.getpid(),
            "filename": filename,
            "ttl": ttl,
        }
        os.write(fd, json.dumps(lock_data, ensure_ascii=False).encode("utf-8"))
        os.close(fd)
        return {"success": True, "lock_path": lock_path}
    except FileExistsError:
        # 被占用，读取占有者信息
        data = _read_lock(lock_path)
        return {
            "success": False,
            "reason": "BUSY",
            "lock_path": lock_path,
            "locked_by": data.get("locked_by", "unknown"),
            "locked_at": data.get("locked_at", 0),
        }
    except Exception as e:
        return {"success": False, "reason": "ERROR", "message": str(e)}


def release_lock(project_root: str, filename: str, force: bool = False) -> dict:
    """
    释放锁。

    返回:
        {"success": True}  — 成功
        {"success": False, "reason": "NOT_LOCKED"}  — 未被锁定
        {"success": False, "reason": "NOT_OWNER"}  — 不是锁持有者
    """
    lock_path = _lock_path(project_root, filename)
    if not os.path.exists(lock_path):
        return {"success": False, "reason": "NOT_LOCKED"}

    if not force:
        data = _read_lock(lock_path)
        owner_pid = data.get("pid", -1)
        if owner_pid > 0 and owner_pid != os.getpid() and _pid_exists(owner_pid):
            return {"success": False, "reason": "NOT_OWNER", "locked_by": data.get("locked_by", "unknown")}

    try:
        os.remove(lock_path)
        return {"success": True}
    except OSError as e:
        return {"success": False, "reason": "ERROR", "message": str(e)}


def status(project_root: str) -> list:
    """查看所有锁状态"""
    lock_dir = _lock_dir(project_root)
    if not os.path.isdir(lock_dir):
        return []

    result = []
    for lock_file in sorted(glob.glob(os.path.join(lock_dir, "*.lock"))):
        data = _read_lock(lock_file)
        filename = os.path.basename(lock_file).replace(".lock", "")
        now = time.time()
        locked_at = data.get("locked_at", 0)
        age = now - locked_at if locked_at > 0 else 0
        is_zombie = _is_zombie(lock_file)

        result.append(
            {
                "filename": filename,
                "locked_by": data.get("locked_by", "unknown"),
                "locked_at": locked_at,
                "age_seconds": int(age),
                "pid": data.get("pid", -1),
                "ttl": data.get("ttl", DEFAULT_TTL),
                "is_zombie": is_zombie,
            }
        )
    return result


def cleanup(project_root: str, ttl: int = DEFAULT_TTL) -> dict:
    """
    清理所有僵尸锁。

    返回:
        {"cleaned": int, "remaining": int, "details": [文件名列表]}
    """
    locks = status(project_root)
    cleaned = 0
    details = []

    for lock in locks:
        if lock["is_zombie"]:
            lock_path = _lock_path(project_root, lock["filename"])
            if _clean_zombie(lock_path, ttl):
                cleaned += 1
                details.append(lock["filename"])

    remaining = len(status(project_root))
    return {"cleaned": cleaned, "remaining": remaining, "details": details}


def history(project_root: str) -> dict:
    """
    查看冲突历史。

    从 .ai/logs/coordinator/ 读取历史记录。
    """
    history_dir = os.path.join(project_root, ".ai/logs/coordinator")
    records = []
    if os.path.isdir(history_dir):
        for hf in sorted(glob.glob(os.path.join(history_dir, "*.json")), reverse=True)[:50]:
            try:
                with open(hf, "r", encoding="utf-8") as f:
                    records.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
    return {"total_records": len(records), "records": records}


def watch(project_root: str, interval: int = 30, callback: callable = None):
    """
    Agent Watch 模式 — 持续监控锁状态，发现变化时通知。

    参数:
        interval: 轮询间隔（秒）
        callback: 可选回调函数，每次扫描后调用 (locks) -> None
    """
    import time

    last_state = {}
    print(f"  🔍 Agent Watch 启动 (间隔 {interval}s)")
    print(f"  Ctrl+C 退出")
    try:
        while True:
            locks = status(project_root)
            current = {l["filename"]: l for l in locks}
            # 检测新锁
            for name, lock in current.items():
                if name not in last_state:
                    print(f"  🔒 新锁: {name} (by {lock['locked_by']})")
            # 检测释放
            for name in last_state:
                if name not in current:
                    print(f"  🔓 释放: {name}")
            # 检测僵尸
            for name, lock in current.items():
                if lock["is_zombie"] and name in last_state and not last_state[name]["is_zombie"]:
                    print(f"  🧟 僵尸锁: {name}")
            last_state = current
            if callback:
                callback(locks)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  ⏹  Agent Watch 停止")


def notify(project_root: str, message: str, level: str = "INFO"):
    """
    Agent 通知 — 记录到 .ai/logs/coordinator/notify.jsonl

    用于 Agent 间通信：锁释放、任务完成、冲突告警等。
    """
    log_dir = os.path.join(project_root, ".ai/logs/coordinator")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "notify.jsonl")
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "agent": os.environ.get("AGENT_ID", "unknown"),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def register_agent(project_root: str, agent_id: str, role: str) -> dict:
    """
    Agent 注册 — 启动时在 .ai/agents/ 注册自身。

    注册信息: agent_id, role, pid, host, timestamp
    心跳: 每 2 分钟调用 beat 刷新
    """
    agents_dir = os.path.join(project_root, ".ai/agents")
    os.makedirs(agents_dir, exist_ok=True)
    reg_path = os.path.join(agents_dir, f"{agent_id}.json")
    import socket

    reg = {
        "agent_id": agent_id,
        "role": role,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "registered_at": datetime.now().isoformat(),
        "last_heartbeat": datetime.now().isoformat(),
        "status": "active",
    }
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    return reg


def list_agents(project_root: str) -> list:
    """列出所有已注册 Agent"""
    agents_dir = os.path.join(project_root, ".ai/agents")
    agents = []
    if os.path.isdir(agents_dir):
        for fname in sorted(glob.glob(os.path.join(agents_dir, "*.json"))):
            try:
                with open(fname, encoding="utf-8") as f:
                    agents.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
    return agents


def task_push(project_root: str, task: dict) -> dict:
    """
    任务入队 — 写入 .ai/queues/<agent>/ 目录。

    task 格式:
        {"id": "TASK-001", "action": "...", "target": "...", "priority": "HIGH"}
    """
    agent_id = task.get("agent", "default")
    queue_dir = os.path.join(project_root, ".ai/queues", agent_id)
    os.makedirs(queue_dir, exist_ok=True)
    task_id = task.get("id", f"TASK-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    task_path = os.path.join(queue_dir, f"{task_id}.json")
    task["pushed_at"] = datetime.now().isoformat()
    with open(task_path, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    return {"task_id": task_id, "path": task_path}


def task_poll(project_root: str, agent_id: str = "default") -> list:
    """任务出队 — Agent 轮询自己的任务队列"""
    queue_dir = os.path.join(project_root, ".ai/queues", agent_id)
    tasks = []
    if os.path.isdir(queue_dir):
        for fname in sorted(glob.glob(os.path.join(queue_dir, "*.json"))):
            try:
                with open(fname, encoding="utf-8") as f:
                    task = json.load(f)
                os.remove(fname)  # 取走后删除
                tasks.append(task)
            except (json.JSONDecodeError, OSError):
                continue
    return tasks


def beat(project_root: str, filename: str) -> dict:
    """
    PID 心跳：刷新锁的 locked_at 时间，防止被 TTL 清理。

    锁持有者应每 2 分钟调用一次。
    """
    lock_path = _lock_path(project_root, filename)
    data = _read_lock(lock_path)
    if not data:
        return {"success": False, "reason": "NOT_LOCKED"}

    if data.get("pid", -1) != os.getpid():
        return {"success": False, "reason": "NOT_OWNER"}

    data["locked_at"] = time.time()
    data["last_heartbeat"] = time.time()
    try:
        _write_lock(lock_path, data)
        return {"success": True}
    except Exception as e:
        return {"success": False, "reason": "ERROR", "message": str(e)}

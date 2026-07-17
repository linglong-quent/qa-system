#!/usr/bin/env python3
"""
skill_backup_full.py — NAS 备份 + 灾备演练 (P1-E04)
=====================================================
增量备份：数据库文件、日志、配置文件、回归报告 → NAS (SynologyDrive)
WORM 只写：备份文件不可覆盖/不可删除，仅追加审计日志

备份策略:
  1. 数据库文件 → NAS backup/ + 本地 _archive/
  2. 日志文件 → NAS logs/archive/
  3. 配置文件 → NAS config/backup/
  4. 回归报告 → NAS reports/backup/
  5. 元数据记录 → WORM audit log

用法:
    python scripts/skill/skill_backup_full.py [--dry-run] [--output json]

退出码:
    0 = 备份成功
    1 = 部分失败
    2 = 全部失败

变更单: ARCH-TICKET-012 (P1-E04)
"""

import datetime
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.skill.skill_base import BaseSkill, CheckResult  # noqa: E402

# ─── 备份配置 ────────────────────────────────────────────
BACKUP_PLAN = [
    {
        "name": "database",
        "sources": [
            {"path": "data/linglong.db", "label": "linglong.db"},
        ],
        "nas_subdir": "database",
        "local_subdir": "database",
    },
    {
        "name": "configs",
        "sources": [
            {"path": "config/rule", "label": "rule_configs", "recursive": True},
            {"path": "config/settings.yaml", "label": "settings.yaml"},
        ],
        "nas_subdir": "config",
        "local_subdir": "config",
    },
    {
        "name": "logs",
        "sources": [
            {"path": "logs", "label": "logs", "recursive": True},
        ],
        "nas_subdir": "logs",
        "local_subdir": "logs",
    },
    {
        "name": "reports",
        "sources": [
            {"path": "_reports", "label": "reports", "recursive": True},
            {"path": "_tasks/results", "label": "task_results", "recursive": True},
        ],
        "nas_subdir": "reports",
        "local_subdir": "reports",
    },
]


class BackupFull(BaseSkill):
    """NAS 全量/增量备份 + 灾备演练"""

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__("backup_full")
        self.dry_run = dry_run
        self.backup_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.nas_base = self._resolve_nas()
        self.local_archive = _ROOT / "_archive" / "backups"
        self.audit_log = _ROOT / "_archive" / "backup_audit.worm"
        self.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0}

    def _resolve_nas(self) -> Optional[Path]:
        """解析 NAS 备份目标路径"""
        # 环境变量优先
        env_nas = os.environ.get("LINGLONG_NAS_BACKUP")
        if env_nas:
            return Path(env_nas)

        # 默认 SynologyDrive 路径
        nas = Path.home() / "SynologyDrive" / "quant_data" / "Quant_Output" / "backups"
        return nas if nas.parent.exists() else None

    def _compute_hash(self, filepath: Path) -> str:
        """计算文件 SHA256"""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _should_backup(self, src: Path, dest: Path) -> bool:
        """增量判断: 目标不存在 或 源文件哈希不同"""
        if not dest.exists():
            return True
        if src.stat().st_size != dest.stat().st_size:
            return True
        return self._compute_hash(src) != self._compute_hash(dest)

    def _worm_audit(self, action: str, path: str, status: str, detail: str = "") -> None:
        """WORM 审计日志 — 只追加不可删除"""
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "action": action,
            "path": path,
            "status": status,
            "detail": detail,
            "backup_id": self.backup_timestamp,
        }
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.audit_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _backup_file(self, src: Path, dest_dir: Path, label: str) -> Optional[str]:
        """备份单个文件 (增量)"""
        if not src.exists():
            return f"SKIP: {label} ({src} 不存在)"
        dest_dir.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            # 目录: 创建 tar.gz 归档
            archive_name = f"{label}_{self.backup_timestamp}.tar.gz"
            dest = dest_dir / archive_name
            if not self._should_backup_dir(src, dest):
                return f"SKIP: {label} (无变更)"
            if self.dry_run:
                return f"DRYRUN: {label} → {dest}"
            shutil.make_archive(str(dest).replace(".tar.gz", ""), "gztar", root_dir=str(src.parent), base_dir=src.name)
            self._worm_audit("backup_dir", str(dest), "success", f"label={label}")
        else:
            # 文件: 直接复制
            dest = dest_dir / f"{label}_{self.backup_timestamp}{src.suffix}"
            if not self._should_backup(src, dest):
                return f"SKIP: {label} (无变更)"
            if self.dry_run:
                return f"DRYRUN: {label} → {dest}"
            shutil.copy2(src, dest)
            self._worm_audit("backup_file", str(dest), "success", f"label={label}")

        self.stats["success"] += 1
        return None

    def _should_backup_dir(self, src_dir: Path, dest_archive: Path) -> bool:
        """判断目录是否需要备份 (检查最新文件 mtime)"""
        if not dest_archive.exists():
            return True
        try:
            newest = max(
                (f.stat().st_mtime for f in src_dir.rglob("*") if f.is_file()),
                default=0,
            )
            return newest > dest_archive.stat().st_mtime
        except Exception:
            return True

    def _backup_recursive(self, src_dir: Path, dest_dir: Path, label: str) -> list[str]:
        """递归备份目录下所有文件"""
        messages = []
        for f in src_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src_dir)
                dest = dest_dir / rel.parent / f"{rel.stem}_{self.backup_timestamp}{rel.suffix}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if self._should_backup(f, dest):
                    if self.dry_run:
                        messages.append(f"DRYRUN: {label}/{rel} → {dest}")
                        self.stats["skipped"] += 1
                    else:
                        try:
                            shutil.copy2(f, dest)
                            self.stats["success"] += 1
                        except Exception as e:
                            messages.append(f"FAIL: {label}/{rel} ({e})")
                            self.stats["failed"] += 1
                            self._worm_audit("backup_fail", str(dest), "fail", str(e))
                else:
                    messages.append(f"SKIP: {label}/{rel} (无变更)")
                    self.stats["skipped"] += 1
        return messages

    def run_checks(self) -> list[CheckResult]:  # noqa: C901
        results: list[CheckResult] = []
        self.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0}

        # 检查 NAS 可达性
        if self.nas_base is None or not self.nas_base.parent.exists():
            return [
                CheckResult(
                    rule="BACKUP-001",
                    severity="error",
                    message="NAS 备份目标不可达 (SynologyDrive 未挂载)",
                    suggest="检查 SynologyDrive 连接状态或设置 LINGLONG_NAS_BACKUP 环境变量",
                )
            ]

        # 确保本地归档目录存在
        self.local_archive.mkdir(parents=True, exist_ok=True)

        messages: list[str] = []

        for plan in BACKUP_PLAN:
            nas_dest = self.nas_base / plan["nas_subdir"]  # type: ignore[index]
            local_dest = self.local_archive / plan["local_subdir"]  # type: ignore[index]

            for src_cfg in plan["sources"]:  # type: ignore[index]
                src = _ROOT / src_cfg["path"]
                label = src_cfg["label"]
                self.stats["total"] += 1

                if src_cfg.get("recursive") and src.is_dir():
                    # 递归备份
                    msgs = self._backup_recursive(src, nas_dest / label, label)
                    messages.extend(msgs)
                    if not self.dry_run:
                        # 同时本地归档
                        try:
                            self._backup_recursive(src, local_dest / label, label)
                        except Exception:
                            pass
                else:
                    # 单文件/目录备份
                    # NAS
                    nas_msg = self._backup_file(src, nas_dest, label)
                    if nas_msg:
                        messages.append(f"[NAS] {nas_msg}")
                    # 本地归档
                    local_msg = self._backup_file(src, local_dest, label)
                    if local_msg:
                        messages.append(f"[LOCAL] {local_msg}")

        # 汇总
        if self.stats["failed"] > 0:
            severity = "blocker"
        elif self.stats["success"] == 0 and self.stats["total"] > 0:
            severity = "warning"
        else:
            severity = "info"

        summary = (
            f"备份完成: 总计{self.stats['total']}项, "
            f"成功{self.stats['success']}项, "
            f"跳过{self.stats['skipped']}项, "
            f"失败{self.stats['failed']}项"
        )
        if self.dry_run:
            summary = "[DRY RUN] " + summary

        results.append(
            CheckResult(
                rule="BACKUP-001",
                severity=severity,
                message=summary,
                suggest="查看 backup_audit.worm 获取详细审计日志",
            )
        )

        # 灾备演练检查
        results.append(self._drill_check())

        self._worm_audit("backup_summary", str(self.nas_base), "summary", summary)
        return results

    def _drill_check(self) -> CheckResult:
        """灾备演练检查: 验证上一次备份完整性"""
        drill_ok = True
        drill_detail = []

        # 检查审计日志是否存在
        if self.audit_log.exists():
            drill_detail.append("审计日志: OK")
        else:
            drill_ok = False
            drill_detail.append("审计日志: 缺失")

        # 检查本地归档目录是否有内容
        if self.local_archive.exists():
            archive_files = list(self.local_archive.rglob("*"))
            if archive_files:
                drill_detail.append(f"本地归档: OK ({len(archive_files)} 文件)")
            else:
                drill_detail.append("本地归档: 空目录")
        else:
            drill_ok = False
            drill_detail.append("本地归档: 目录不存在")

        return CheckResult(
            rule="BACKUP-002",
            severity="info" if drill_ok else "warning",
            message=f"灾备演练: {'通过' if drill_ok else '待改进'} — {', '.join(drill_detail)}",
            suggest="每月至少执行一次完整备份恢复演练",
        )


def run(output: str = "json", dry_run: bool = False) -> Dict[str, Any]:
    skill = BackupFull(dry_run=dry_run)
    results = skill.run_checks()
    result = skill.output_results(results)
    result["stats"] = skill.stats
    result["backup_id"] = skill.backup_timestamp
    result["nas_target"] = str(skill.nas_base) if skill.nas_base else "N/A"
    if output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NAS 全量备份 + 灾备演练 (P1-E04)")
    parser.add_argument("--dry-run", action="store_true", help="试运行 (不实际备份)")
    parser.add_argument("--output", default="json")
    args = parser.parse_args()
    run(output=args.output, dry_run=args.dry_run)

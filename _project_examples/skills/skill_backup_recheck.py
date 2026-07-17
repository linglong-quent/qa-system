#!/usr/bin/env python3
"""历史备份复检 cron 任务 (B4-09)
规范引用: p1_spec §八 DB #28 "历史备份复检"
功能: 凌晨 cron 自动复检历史备份完整性 (30天/90天/180天/365天分层抽样)
退出码: 0=通过, 1=警告(部分损坏), 2=阻断(全部损坏)
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

# 复检抽样策略: (天数, 抽样比例)
SAMPLING_PLAN = [
    (7, 1.0),  # 最近7天: 全量检查
    (30, 0.5),  # 8-30天: 50% 抽样
    (90, 0.2),  # 31-90天: 20% 抽样
    (180, 0.1),  # 91-180天: 10% 抽样
    (365, 0.05),  # 181-365天: 5% 抽样
]


def compute_sha256(file_path: Path) -> str:
    """计算文件 SHA256"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_backup_files(backup_dir: Path) -> Dict[str, List[Path]]:
    """按日期分组备份文件"""
    groups: Dict[str, List[Path]] = {}

    if not backup_dir.exists():
        return groups

    for f in backup_dir.rglob("*"):
        if not f.is_file():
            continue
        # 从文件名提取日期
        date_key = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
        groups.setdefault(date_key, []).append(f)

    return groups


def sample_files(groups: Dict[str, List[Path]]) -> List[Path]:
    """按分层抽样策略选择复检文件"""
    import random

    random.seed(42)

    now = datetime.now(timezone.utc)
    sampled = []

    for f_date, files in sorted(groups.items()):
        try:
            file_dt = datetime.strptime(f_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        age_days = (now - file_dt).days

        for threshold, ratio in SAMPLING_PLAN:
            if age_days <= threshold:
                n = max(1, int(len(files) * ratio))
                sampled.extend(random.sample(files, min(n, len(files))))
                break

    return sampled


def verify_backups(sampled: List[Path]) -> Tuple[int, int, List[str]]:
    """逐文件校验 SHA256"""
    ok = 0
    fail = 0
    details = []

    for f in sampled:
        try:
            actual_hash = compute_sha256(f)

            # 查找对应的 .sha256 清单文件
            hash_file = f.with_suffix(f.suffix + ".sha256")
            if hash_file.exists():
                expected_hash = hash_file.read_text(encoding="utf-8").strip().split()[0]
                if actual_hash == expected_hash:
                    ok += 1
                else:
                    fail += 1
                    details.append(f"❌ 哈希不匹配: {f.name}")
            else:
                # 无清单文件则记录哈希
                hash_file.write_text(f"{actual_hash}  {f.name}\n", encoding="utf-8")
                ok += 1
        except (OSError, IOError) as e:
            fail += 1
            details.append(f"❌ 读取失败: {f.name} — {e}")

    return ok, fail, details


def generate_report(ok: int, fail: int, total: int, details: List[str], output_dir: Path) -> Path:
    """生成复检报告"""
    report_dir = output_dir / "reports" / "backup_verify"
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_file = report_dir / f"backup_recheck_{ts}.json"

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_sampled": total,
        "ok": ok,
        "fail": fail,
        "pass_rate": f"{ok/total*100:.1f}%" if total > 0 else "N/A",
        "details": details,
    }

    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 同时写入 WORM
    worm_dir = output_dir / "data" / "worm"
    worm_dir.mkdir(parents=True, exist_ok=True)
    worm_file = worm_dir / f"backup_recheck_{ts}.json"
    worm_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report_file


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    print("[B4-09] 历史备份复检 cron 任务")
    print("=" * 60)

    # 备份目录
    backup_dir = root / "data" / "backup"
    if not backup_dir.exists():
        print(f"⚠️  备份目录不存在: {backup_dir}")
        print("   (无历史备份需要复检)")
        return 0

    # 步骤1: 查找备份文件
    groups = find_backup_files(backup_dir)
    total_files = sum(len(v) for v in groups.values())
    print(f"📁 备份目录: {backup_dir}")
    print(f"   日期分组: {len(groups)} 天, 共 {total_files} 文件")

    # 步骤2: 分层抽样
    sampled = sample_files(groups)
    print(f"   抽样复检: {len(sampled)}/{total_files} 文件")

    # 步骤3: 校验
    ok, fail, details = verify_backups(sampled)
    print(f"\n📋 校验结果: ✅ {ok} | ❌ {fail} | 📊 {len(sampled)}")

    if details:
        for d in details:
            print(f"   {d}")

    # 步骤4: 生成报告
    report = generate_report(ok, fail, len(sampled), details, root)
    print(f"\n📄 报告: {report}")

    print("=" * 60)

    if fail > len(sampled) * 0.5:
        print(f"❌ 超过50%备份损坏 (退出码=2)")  # noqa: F541
        return 2
    if fail > 0:
        print(f"⚠️  {fail} 个备份损坏 (退出码=1)")
        return 1
    print("✅ 历史备份复检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker: 镜像来源可解释性（M20 盲区）

规则：
  IMG-PROV-001  镜像必须"可由 Dockerfile 构建"或"被显式记录为 commit 派生"。
                判定：
                  (A) 层历史里能看到 Dockerfile 类构建步骤（apt-get / pip install /
                      COPY / RUN 等）→ 合法，来源可解释；
                  (B) 顶层是单个巨层且 CreatedBy 为空或仅 tail/Cmd 之类
                      → 视为 docker commit 派生，**必须在来源记录文件中登记**
                      （tag 或 Image ID 出现即可）；
                  (C) 既非 (A) 也未登记 → **报错**（来源不明，不得用于生产编排）。

为什么需要这条规则：
  实测 `linglong/factor-forge:gpu` 是 `docker commit` 产物（11 层，顶层单层 9.95GB，
  CreatedBy 仅 `bash -c tail -f /dev/null`），而仓库里的 Dockerfile 从未参与构建。
  若无人知道这一点，照 Dockerfile 去"修镜像"是无效动作，且可能诱导一次
  破坏性重建（丢掉 commit 进去的依赖）。这类"隐形来源"必须变成有据可查的事实。

平台：依赖 `docker` CLI；不可用或探测失败时整体 skipped（不阻断），并在 issues 说明。
接口: check(config) -> (errors, issues)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Tuple

# Dockerfile 类构建步骤的特征（出现即倾向判 (A)）
BUILDSTEP = re.compile(
    r"apt-get|pip\s+install|/bin/sh -c|COPY |ADD |RUN |set -eux", re.I)
# "无信息"的 CreatedBy（commit 层常见）
NOINFO = re.compile(r"^\s*$|^bash -c |^/bin/sh -c #\(nop\)|^CMD |^ENTRYPOINT ", re.I)

DEFAULT_PROVENANCE_FILES = (
    r"D:\WB\linglong\docker\factor-forge\IMAGE_PROVENANCE.md",
)
HUGE_LAYER_BYTES = 1024 ** 3  # 1GB 以上视为"巨层"


def _run(args: List[str], timeout: int = 60) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError:
        return 127, "", "docker CLI not found"
    except Exception as e:  # noqa: BLE001
        return 1, "", "{}: {}".format(type(e).__name__, e)


def _size_to_bytes(s: str) -> int:
    m = re.match(r"^([\d.]+)\s*([kMGT]?B)$", (s or "").strip(), re.I)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).upper()
    mult = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
    return int(val * mult.get(unit, 1))


class ImageProvenanceChecker:
    """检查镜像来源是否可解释/已登记"""

    def __init__(self, config: Dict | None = None):
        cfg = config or {}
        self.images: List[str] = cfg.get("images") or []
        self.provenance_files: List[str] = cfg.get(
            "provenance_files", list(DEFAULT_PROVENANCE_FILES))

    # ── 读取登记文件 ────────────────────────────────
    def _recorded_text(self) -> str:
        blob = []
        for p in self.provenance_files:
            try:
                blob.append(open(p, encoding="utf-8", errors="replace").read())
            except OSError:
                continue
        return "\n".join(blob)

    def _is_recorded(self, image: str, image_id: str, text: str) -> bool:
        if not text:
            return False
        short_id = (image_id or "").replace("sha256:", "")[:12]
        tags = [image]
        if ":" in image:
            tags.append(image.split(":")[-1])       # 只留 tag 名
        for t in tags:
            if t and t in text:
                return True
        if short_id and short_id in text:
            return True
        return False

    # ── 单镜像判定 ──────────────────────────────────
    def _classify(self, image: str) -> Dict:
        rc, out, err = _run(["docker", "history", image, "--no-trunc",
                             "--format", "{{.Size}}\t{{.CreatedBy}}"])
        if rc != 0:
            return {"image": image, "error": (err or out).strip()[:160]}

        rows = []
        for ln in out.splitlines():
            if "\t" not in ln:
                continue
            size, created = ln.split("\t", 1)
            rows.append((size.strip(), created.strip()))
        if not rows:
            return {"image": image, "error": "history 为空"}

        rc2, out2, _ = _run(
            ["docker", "inspect", image, "--format", "{{.Id}}|{{.Parent}}|{{.Created}}"])
        img_id, parent, created_at = "", "", ""
        if rc2 == 0 and "|" in out2:
            parts = out2.strip().split("|")
            img_id = parts[0]
            parent = parts[1] if len(parts) > 1 else ""
            created_at = parts[2] if len(parts) > 2 else ""

        # (A)? 任一层显出 Dockerfile 步骤
        has_buildstep = any(BUILDSTEP.search(c or "") for _, c in rows)
        # 顶层（新→旧的第一条）形态
        top_size, top_created = rows[0]
        top_bytes = _size_to_bytes(top_size)
        top_noinfo = bool(NOINFO.match(top_created or "")) or not top_created
        is_commit_like = (not has_buildstep) or (top_bytes >= HUGE_LAYER_BYTES and top_noinfo) \
            or bool(parent)

        return {
            "image": image, "image_id": img_id, "parent": parent,
            "created": created_at, "layers": len(rows),
            "top_size": top_size, "top_created": (top_created or "")[:80],
            "has_buildstep": has_buildstep,
            "commit_like": bool(is_commit_like),
        }

    # ── 主检查 ──────────────────────────────────────
    def check(self) -> Tuple[int, List[str]]:
        rc, _, _ = _run(["docker", "version", "--format", "{{.Server.Version}}"])
        if rc != 0:
            return 0, ["[IMG-PROV-001] skipped: docker 不可用（不阻断）"]

        images = self.images
        if not images:
            rc, out, _ = _run(["docker", "ps", "--format",
                               "{{.Image}}|{{.Names}}"])
            if rc == 0:
                for ln in out.splitlines():
                    img = ln.split("|", 1)[0].strip()
                    if img and img not in images:
                        images.append(img)

        text = self._recorded_text()
        errors, issues = 0, []
        for image in images:
            info = self._classify(image)
            if info.get("error"):
                issues.append("[IMG-PROV-001] {} 无法判定: {}".format(
                    image, info["error"]))
                continue
            recorded = self._is_recorded(image, info["image_id"], text)
            if info["commit_like"] and not recorded:
                errors += 1
                issues.append(
                    "[IMG-PROV-001] 镜像 {} 是 commit 派生（parent={}，{} 层，顶层 {} "
                    "CreatedBy='{}'）但**未在任何来源记录文件中登记** → 来源不明，"
                    "不得用于生产编排。请在 {} 中登记 tag/Image ID/血缘/变更内容/回滚方式。".format(
                        image, (info["parent"] or "-")[:20], info["layers"],
                        info["top_size"], info["top_created"],
                        ", ".join(os.path.basename(p) for p in self.provenance_files)))
            elif info["commit_like"] and recorded:
                issues.append("[IMG-PROV-001] {} 为 commit 派生，已登记 ✅（parent={}，{} 层）".format(
                    image, (info["parent"] or "-")[:20], info["layers"]))
            else:
                issues.append("[IMG-PROV-001] {} 可由 Dockerfile 构建（层历史含构建步骤）✅".format(
                    image))
        return errors, issues


def check(config: Dict | None = None) -> Tuple[int, List[str]]:
    return ImageProvenanceChecker(config).check()


if __name__ == "__main__":
    cfg = {"images": sys.argv[1:]} if len(sys.argv) > 1 else {}
    e, i = check(cfg)
    print("errors =", e)
    for x in i:
        print("  -", x)
    sys.exit(1 if e else 0)

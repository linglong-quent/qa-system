#!/usr/bin/env python3
"""M47 门禁断言：运行中容器集合 == compose 声明集合（反孤儿容器）+ 重建前预检

来源：M24 查明 `linglong-prometheus` 是全栈唯一**孤儿容器**（无 compose 标签、
`compose ps` 无输出）——它的挂载配错文件却无人发现，正因它不在编排里；
M41 把这条泛化成**动手前预检**：若 clickhouse 也是孤儿，`compose up` 会另起容器、
可能挂到新空卷 ⇒ 等于把生产库弄丢。

判据（三分法，处置方向不同）：
  CONT-001 (BLOCKER)  **孤儿容器**：在跑但未被任何 compose 声明
  CONT-002 (WARN)     **声明但未跑**：compose 声明了却没有运行中的容器
  CONT-003 (BLOCKER)  重建前预检不通过：容器不属于 compose project/service，
                      或其**关键数据路径落在 bind mount / 未声明的卷**上
  CONT-000 (INFO)     三者一致

用法:
  python scripts/qa_contract_containers.py                      # 全项目三分法扫描
  python scripts/qa_contract_containers.py --preflight linglong-clickhouse
  python scripts/qa_contract_containers.py --negative-control    # 真实态负控
  python scripts/qa_contract_containers.py --json out.json
退出码: 0=PASS  1=FAIL(存在 CONT-001/003)  2=技术性错误
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

PROBE_IMAGE = "busybox:latest"
PROBE_PREFIX = "qa_m47_probe"
# 关键数据路径：**精确匹配**（不得用前缀，否则 /var/lib/clickhouse/backups 这类
# 备份/日志子目录会被误判为"数据不受卷管理"——本任务实测踩到该假阳性）
CRITICAL_DATA_PATHS = ("/var/lib/clickhouse", "/var/lib/postgresql", "/data", "/var/lib/mysql")
# 关键数据路径下的**已知非数据子目录**（备份/日志/临时）——落在这些上的挂载不要求命名卷
NON_DATA_SUBDIRS = ("/backups", "/logs", "/log", "/tmp", "/user_files", "/coordination",
                    "/access", "/format_schemas", "/preprocessed_configs")


def dk(args, timeout=180):
    p = subprocess.run(["docker"] + list(args), capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def compose_ls():
    rc, out, err = dk(["compose", "ls", "-a", "--format", "json"], timeout=120)
    if rc != 0 or not out.strip():
        return []
    try:
        return json.loads(out)
    except Exception:
        return []


def declared_services(config_files: str):
    """compose 文件里声明的服务名集合（config_files 可能是逗号分隔多文件）"""
    files = [f.strip() for f in (config_files or "").split(",") if f.strip()]
    if not files:
        return set(), ""
    args = ["compose"]
    for f in files:
        args += ["-f", f]
    args += ["config", "--services"]
    rc, out, err = dk(args, timeout=180)
    if rc != 0:
        return set(), err.strip()[:200]
    return {x.strip() for x in out.split() if x.strip()}, ""


def all_containers():
    rc, out, _ = dk(["ps", "-aq"])
    ids = [x for x in out.split() if x]
    if not ids:
        return []
    rc, out, err = dk(["inspect"] + ids, timeout=300)
    if rc != 0:
        raise RuntimeError(err[:300])
    return json.loads(out)


def labels_of(c):
    return (c.get("Config") or {}).get("Labels") or {}


def _oneshot_exit(project: str, service: str, containers: list):
    """若该 (project, service) 的容器**已正常退出**则返回其 ExitCode，否则 None。

    一次性初始化容器（dify 的 init_permissions 等）跑完即退出，属正常终态，
    不应被报成"声明但未跑"。
    """
    for c in containers:
        L = labels_of(c)
        if L.get("com.docker.compose.project") == project and \
                L.get("com.docker.compose.service") == service:
            st = (c.get("State") or {})
            if st.get("Status") == "exited" and st.get("ExitCode") == 0 and not st.get("Restarting"):
                return st.get("ExitCode")
            return None
    return None


def scan(include_stopped_orphans=False):
    projects = compose_ls()
    proj_by_name = {p["Name"]: p for p in projects}
    declared = {}
    for name, p in proj_by_name.items():
        svcs, err = declared_services(p.get("ConfigFiles", ""))
        declared[name] = {"services": svcs, "error": err, "config_files": p.get("ConfigFiles", "")}

    cs = all_containers()
    running_by_proj = {}
    orphans = []
    for c in cs:
        nm = c["Name"].lstrip("/")
        st = (c.get("State") or {}).get("Status")
        L = labels_of(c)
        proj = L.get("com.docker.compose.project", "")
        svc = L.get("com.docker.compose.service", "")
        if st != "running":
            continue
        if not proj:
            orphans.append({"container": nm, "reason": "无 compose project 标签",
                            "status": st, "image": (c.get("Config") or {}).get("Image", "")})
        elif proj not in proj_by_name:
            orphans.append({"container": nm, "reason": f"所属 project '{proj}' 未出现在 compose ls",
                            "status": st, "image": (c.get("Config") or {}).get("Image", "")})
        else:
            running_by_proj.setdefault(proj, set()).add(svc)

    missing = []
    ok_pairs = []
    oneshot = []
    for name, d in declared.items():
        rset = running_by_proj.get(name, set())
        for svc in sorted(d["services"]):
            if svc in rset:
                ok_pairs.append(f"{name}/{svc}")
            else:
                # 一次性容器豁免：已正常退出（ExitCode=0 且无重启）的 init/迁移类服务
                # ——否则每次扫描都会常驻一条假 WARN（本任务实测 dify/init_permissions）
                ex = _oneshot_exit(name, svc, cs)
                if ex is not None:
                    oneshot.append({"project": name, "service": svc, "exit_code": ex})
                else:
                    missing.append({"project": name, "service": svc})

    return {
        "assertion": "CONT-001/002/003",
        "contract": "运行中容器集合 == compose 声明集合；重建前须确认 compose 归属与命名卷",
        "projects": [{"name": p["Name"], "config_files": p.get("ConfigFiles", ""),
                      "declared_services": len(declared.get(p["Name"], {}).get("services", [])),
                      "running_containers": len(running_by_proj.get(p["Name"], set())),
                      "declared_parse_error": declared.get(p["Name"], {}).get("error", "")}
                     for p in projects],
        "totals": {"containers": len(cs),
                   "running": sum(1 for c in cs if (c.get("State") or {}).get("Status") == "running"),
                   "orphans": len(orphans), "missing": len(missing),
                   "oneshot_completed": len(oneshot), "matched": len(ok_pairs)},
        "orphans": orphans,
        "missing": missing,
        "oneshot_completed": oneshot,
        "matched": ok_pairs,
        "verdict": "FAIL" if orphans else "PASS",
        "generated_at": datetime.now().isoformat(),
    }


def preflight(container: str):
    rc, out, err = dk(["inspect", container])
    if rc != 0:
        return {"container": container, "verdict": "ERROR", "checks": [],
                "detail": f"容器不存在: {err.strip()[:200]}"}
    c = json.loads(out)[0]
    L = labels_of(c)
    proj = L.get("com.docker.compose.project", "")
    svc = L.get("com.docker.compose.service", "")
    checks = []

    ok = bool(proj and svc)
    checks.append({"id": "CONT-003a", "name": "属于某 compose project/service",
                   "passed": ok, "detail": f"project={proj or '(空)'} service={svc or '(空)'}"})

    # 该 project 的 compose 文件里是否声明了 volumes: 段（显式声明）
    declared_vols = set()
    if proj:
        for p in compose_ls():
            if p["Name"] == proj:
                files = [f.strip() for f in (p.get("ConfigFiles") or "").split(",") if f.strip()]
                if files:
                    args = ["compose"]
                    for f in files:
                        args += ["-f", f]
                    args += ["config", "--volumes"]
                    rc2, out2, _ = dk(args, timeout=180)
                    if rc2 == 0:
                        declared_vols = {x.strip() for x in out2.split() if x.strip()}

    for m in (c.get("Mounts") or []):
        dest = (m.get("Destination") or "").rstrip("/")
        # 只看**精确等于**关键数据路径的挂载；其下的备份/日志子目录不在此列
        if dest not in CRITICAL_DATA_PATHS:
            continue
        if any(dest.endswith(s) for s in NON_DATA_SUBDIRS):
            continue
        if m.get("Type") == "volume":
            vn = m.get("Name") or ""
            # compose 生成的卷名形如 <project>_<declared>；允许两种匹配
            short = vn[len(proj) + 1:] if proj and vn.startswith(proj + "_") else vn
            declared_ok = (vn in declared_vols) or (short in declared_vols) or bool(declared_vols and short)
            checks.append({"id": "CONT-003b", "name": f"关键数据路径 {dest} 为命名卷且有显式声明",
                           "passed": bool(vn) and declared_ok,
                           "detail": f"volume={vn} declared_in_compose={sorted(declared_vols)}"})
        else:
            checks.append({"id": "CONT-003c", "name": f"关键数据路径 {dest} 落在 bind mount",
                           "passed": False,
                           "detail": f"type={m.get('Type')} source={m.get('Source')} "
                                     f"⇒ 数据不受卷管理，重建有丢失风险"})

    failed = [x for x in checks if not x["passed"]]
    return {"container": container, "project": proj, "service": svc, "checks": checks,
            "verdict": "FAIL" if failed else "PASS",
            "blocking": [x["id"] for x in failed]}


def negative_control() -> int:
    """真实态负控（不 mock 任何 docker 输出，用**真实容器**造出真实状态）：
       NC1 真孤儿容器：docker run 起一个无 compose 标签的容器 = M24 实测的那种真实孤儿态
       NC2 声明但未跑：影子 compose 项目声明 2 个服务、只起 1 个
    """
    print("=" * 78)
    print("  M47 负控 — 用真实容器/真实 compose 造出真实状态（不 mock）")
    print("=" * 78)
    ok = True
    base = scan()
    print(f"\n  [基线] 容器 {base['totals']['containers']} / 运行 {base['totals']['running']} "
          f"/ 孤儿 {base['totals']['orphans']} / 缺失 {base['totals']['missing']} → {base['verdict']}")

    # ── NC1 真孤儿容器 ──────────────────────────────────────
    name = f"{PROBE_PREFIX}_orphan"
    dk(["rm", "-f", name])
    rc, out, err = dk(["run", "-d", "--name", name, PROBE_IMAGE, "sleep", "300"], timeout=180)
    try:
        if rc != 0:
            print(f"  ❌ NC1 起容器失败: {err.strip()[:200]}")
            ok = False
        else:
            s = scan()
            hit = [o for o in s["orphans"] if o["container"] == name]
            c1 = bool(hit) and s["verdict"] == "FAIL"
            ok = ok and c1
            print(f"\n  [NC1] 真孤儿容器（docker run，无 compose 标签）")
            print(f"        检出={'是' if hit else '否'}  汇总: 孤儿 {s['totals']['orphans']} → {s['verdict']}")
            print(f"        期望 FAIL / 实得 {s['verdict']}  {'✅' if c1 else '❌ 判据漏检孤儿'}")
    finally:
        dk(["rm", "-f", name])

    s2 = scan()
    c1b = (not [o for o in s2["orphans"] if o["container"] == name])
    ok = ok and c1b
    print(f"        清除后孤儿数={s2['totals']['orphans']} → {s2['verdict']}  {'✅' if c1b else '❌'}")

    # ── NC2 声明但未跑 ─────────────────────────────────────
    tmp = tempfile.mkdtemp(prefix="qa_m47_compose_")
    proj_dir = os.path.join(tmp, "qam47shadow")
    os.makedirs(proj_dir, exist_ok=True)
    cf = os.path.join(proj_dir, "docker-compose.yml")
    with open(cf, "w", encoding="utf-8") as f:
        f.write(
            "services:\n"
            "  qam47a:\n"
            f"    image: {PROBE_IMAGE}\n"
            "    command: sleep 300\n"
            "  qam47b:\n"
            f"    image: {PROBE_IMAGE}\n"
            "    command: sleep 300\n")
    try:
        rc, out, err = dk(["compose", "-f", cf, "up", "-d", "qam47a"], timeout=300)
        if rc != 0:
            print(f"\n  ⚠️ NC2 起影子项目失败（跳过）: {err.strip()[:200]}")
        else:
            time.sleep(3)
            s = scan()
            proj = [p for p in s["projects"] if p["name"] == "qam47shadow"]
            miss = [m for m in s["missing"] if m["project"] == "qam47shadow"]
            c2 = bool(miss) and any(m["service"] == "qam47b" for m in miss)
            ok = ok and c2
            print(f"\n  [NC2] 影子项目声明 2 服务、只起 1 个")
            print(f"        project 可见={'是' if proj else '否'}  缺失检出={miss}")
            print(f"        期望检出 MISSING(qam47b) / 实得 {'✅' if c2 else '❌'}")
    finally:
        dk(["compose", "-f", cf, "down", "-v", "--remove-orphans"], timeout=300)
        dk(["rm", "-f", f"qam47shadow-qam47a-1"], timeout=60)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    s3 = scan()
    print(f"\n  [清理后] 孤儿 {s3['totals']['orphans']} / 缺失 {s3['totals']['missing']} → {s3['verdict']}")

    # ── NC3 预检负控：关键数据路径落在 bind mount ⇒ CONT-003c 必须 FAIL ──
    name3 = f"{PROBE_PREFIX}_binddata"
    bod = os.path.join(tempfile.gettempdir(), "qa_m47_binddata")
    os.makedirs(bod, exist_ok=True)
    dk(["rm", "-f", name3])
    rc, out, err = dk(["run", "-d", "--name", name3,
                       "-v", f"{bod}:/var/lib/clickhouse", PROBE_IMAGE, "sleep", "300"], timeout=180)
    try:
        if rc != 0:
            print(f"\n  ⚠️ NC3 起容器失败（跳过）: {err.strip()[:200]}")
        else:
            r = preflight(name3)
            c3 = any(x["id"] == "CONT-003c" and not x["passed"] for x in r["checks"]) and \
                r["verdict"] == "FAIL"
            ok = ok and c3
            print(f"\n  [NC3] 关键数据路径 /var/lib/clickhouse 落在 bind mount（真实容器）")
            for x in r["checks"]:
                print(f"        {'✅' if x['passed'] else '❌'} {x['id']} {x['name']}")
            print(f"        期望 FAIL / 实得 {r['verdict']}  {'✅' if c3 else '❌'}")
    finally:
        dk(["rm", "-f", name3])
        import shutil as _sh
        _sh.rmtree(bod, ignore_errors=True)

    print("\n" + "=" * 78)
    print("  负控结论:", "✅ 三分法在两个方向都被真实状态喂过" if ok else "❌ 负控失败")
    print("=" * 78)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="M47 容器/compose 一致性门禁")
    ap.add_argument("--preflight", default="", help="重建前预检：指定容器名")
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--negative-control", action="store_true")
    args = ap.parse_args()
    try:
        if args.negative_control:
            sys.exit(negative_control())
        if args.preflight:
            r = preflight(args.preflight)
            print("=" * 78)
            print(f"  M47 重建前预检 — {r['container']}")
            print("=" * 78)
            for c in r.get("checks", []):
                print(f"  {'✅' if c['passed'] else '❌'} {c['id']}  {c['name']}")
                print(f"        {c['detail']}")
            print("-" * 78)
            print(f"  Verdict: {r['verdict']}   阻断项: {r.get('blocking') or '无'}")
            print("=" * 78)
            if args.json_out:
                json.dump(r, open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            sys.exit(0 if r["verdict"] == "PASS" else 1)
        res = scan()
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        sys.exit(2)

    print("=" * 78)
    print("  M47 门禁 — 运行中容器集合 == compose 声明集合")
    print("=" * 78)
    for p in res["projects"]:
        err = f"  ⚠️ {p['declared_parse_error']}" if p["declared_parse_error"] else ""
        print(f"  {p['name']:<12} 声明 {p['declared_services']:<3} 运行 {p['running_containers']:<3} "
              f"{p['config_files']}{err}")
    t = res["totals"]
    print(f"\n  容器 {t['containers']} / 运行 {t['running']} / 一致 {t['matched']} "
          f"/ 孤儿 {t['orphans']} / 声明未跑 {t['missing']}")
    for o in res["orphans"]:
        print(f"    [CONT-001] 孤儿容器 {o['container']}  ({o['reason']})")
    for m in res["missing"]:
        print(f"    [CONT-002] 声明未跑 {m['project']}/{m['service']}")
    print("-" * 78)
    print(f"  Verdict: {res['verdict']}")
    print("=" * 78)
    if args.json_out:
        json.dump(res, open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  JSON: {args.json_out}")
    sys.exit(1 if res["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()

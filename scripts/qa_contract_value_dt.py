#!/usr/bin/env python3
"""M39 数据契约断言：value_dt / available_at 对齐语义（向前对齐）

契约口径（M3 §3 判定）：
  · `value_dt`   = **所描述交易日**（不是写入日、不是发布日）；
  · `available_at` = 该行**实际可用时刻**（可用性由它承担）；
  · 现行消费是**同日 join**（`WHERE value_dt >= .. AND value_dt <= ..`，join 中零约束）
    ⇒ 一旦出现「T+1 才发布」的行，同日 join 会**静默**引入 look-ahead：不报错、只让回测虚高。

判据（**全部在查询侧**，不依赖写入方自述）：
  ALIGN-001 (BLOCKER)  toDate(available_at) > value_dt
        该行在其所描述交易日**尚不可用** ⇒ 同日 join 必引入 look-ahead。
  ALIGN-002 (ADVISORY) toDate(available_at) = value_dt AND available_at > value_dt 当日 09:30
        该行在**当日盘中**才可用 ⇒ 对「当日开盘决策」构成风险、对 T+1 消费无风险。
        需消费语义才能定性，故只提示不阻断（边界写死在此，避免误判为阻断级）。

★判据精度要点（本任务实测踩到）：
  · 必须按 **日期** 比较（`toDate(available_at) > value_dt`）；
    若按**时间戳**比较（`available_at > toDateTime(value_dt)`），
    会把「当日 13:54 可用」的 6,396 行全部误报为 ALIGN-001（假阳性）。

用法:
  python scripts/qa_contract_value_dt.py
  python scripts/qa_contract_value_dt.py --json out.json
  python scripts/qa_contract_value_dt.py --negative-control     # 必交负控
退出码: 0=PASS  1=FAIL(存在 ALIGN-001)  2=技术性错误
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime

CH = "linglong-clickhouse"
SHADOW = "qa_m39_align_probe"
SCRATCH_DB = "qa_m39_scratch"
# 当日开盘时点（用于 ALIGN-002 的口径；A 股 09:30）
OPEN_HHMM = "09:30:00"
# 需要排除的系统/临时对象
EXCLUDE_DBS = ("system", "INFORMATION_SCHEMA", "information_schema", "default")


def sh(args, timeout=1800, stdin_bytes=None):
    p = subprocess.run(args, capture_output=True, timeout=timeout, input=stdin_bytes)
    return p.returncode, (p.stdout or b"").decode("utf-8", "replace") + \
        (p.stderr or b"").decode("utf-8", "replace")


def ch(sql, timeout=1800):
    rc, out = sh(["docker", "exec", "-i", CH, "clickhouse-client", "--query", sql], timeout)
    if rc != 0:
        raise RuntimeError(out.strip()[:500])
    return out


def chj(sql, timeout=1800):
    out = ch(sql.rstrip().rstrip(";") + " FORMAT JSONEachRow", timeout)
    return [json.loads(l) for l in out.strip().splitlines() if l.strip()]


def discover_tables():
    """动态发现所有同时含 value_dt 与 available_at 的表（非硬编码单表）"""
    rows = chj("""
        SELECT c.database AS db, c.table AS tbl
        FROM system.columns AS c
        INNER JOIN system.tables AS t
                ON t.database = c.database AND t.name = c.table
        WHERE t.engine NOT LIKE '%View%'
        GROUP BY c.database, c.table
        HAVING countIf(c.name = 'value_dt') > 0
           AND countIf(c.name = 'available_at') > 0
        ORDER BY db, tbl
    """)
    return [(r["db"], r["tbl"]) for r in rows
            if r["db"] not in EXCLUDE_DBS and not r["tbl"].startswith("qa_")]


def check_table(db, tbl, timeout=1800):
    sql = f"""
    SELECT
      count() AS n,
      countIf(toDate(available_at) > value_dt) AS n_align001,
      countIf(toDate(available_at) = value_dt
              AND available_at > toDateTime(concat(toString(value_dt),' {OPEN_HHMM}'))) AS n_align002,
      countIf(toDate(available_at) < value_dt) AS n_before,
      min(value_dt) AS d0, max(value_dt) AS d1
    FROM {db}.{tbl}
    """
    r = chj(sql, timeout)[0]
    n = int(r["n"])
    a1 = int(r["n_align001"])
    a2 = int(r["n_align002"])
    return {
        "table": f"{db}.{tbl}",
        "rows": n,
        "align001_violations": a1,
        "align002_intraday": a2,
        "available_before_value_dt": int(r["n_before"]),
        "value_dt_range": [str(r["d0"]), str(r["d1"])],
        "blocking": a1 > 0,
        "verdict": "FAIL" if a1 > 0 else "PASS",
    }


def run(tables=None):
    tabs = tables if tables is not None else discover_tables()
    results = [check_table(db, t) for db, t in tabs]
    blocking = [r for r in results if r["blocking"]]
    return {
        "assertion": "ALIGN-001/002",
        "contract": "value_dt=所描述交易日；available_at=实际可用时刻；同日 join 要求 toDate(available_at) <= value_dt",
        "open_cutoff": OPEN_HHMM,
        "tables_scanned": len(results),
        "results": results,
        "verdict": "FAIL" if blocking else "PASS",
        "blocking_tables": [r["table"] for r in blocking],
        "generated_at": datetime.now().isoformat(),
    }


def negative_control(src_db="linglong_factor", src_tbl="factor_values") -> int:
    """★必交负控：构造一行 T+1 ⇒ ALIGN-001 必须 FAIL；清除后必须 PASS。

    负控在**影子表**上做（同 DDL/同引擎），不触碰生产表。
    """
    print("=" * 78)
    print("  M39 负控 — 构造一行 T+1 ⇒ 断言必须 FAIL；清除后必须 PASS")
    print("=" * 78)
    ok = True

    def _v(tag):
        r = check_table(SCRATCH_DB, src_tbl)
        print(f"\n  [{tag}] rows={r['rows']} ALIGN-001={r['align001_violations']} "
              f"ALIGN-002={r['align002_intraday']} → {r['verdict']}")
        return r

    try:
        ch(f"CREATE DATABASE IF NOT EXISTS {SCRATCH_DB}")
        ch(f"DROP TABLE IF EXISTS {SCRATCH_DB}.{src_tbl}")
        ch(f"CREATE TABLE {SCRATCH_DB}.{src_tbl} AS {src_db}.{src_tbl}")
        print(f"\n  影子表 {SCRATCH_DB}.{src_tbl} 已建（同 DDL，空表）")

        r0 = _v("C0 空表基线")
        c0 = (r0["align001_violations"] == 0)
        print(f"     期望 PASS / 实得 {r0['verdict']}  {'✅' if c0 else '❌'}")
        ok = ok and c0

        # C1 正常行：available_at 早于 value_dt
        ch(f"""INSERT INTO {SCRATCH_DB}.{src_tbl}
               (value_dt, available_at, factor_name, symbol, factor_value,
                factor_rank, factor_zscore, factor_decile, version, params_hash, computed_at)
               VALUES (toDate('2026-09-10'), toDateTime('2026-09-09 20:00:00'),
                       'qa_align', 'QA.SZ', 1.0, 1, 0.0, 1, 'v1', 'qa', now())""")
        r1 = _v("C1 正常行（available_at 早于 value_dt）")
        c1 = (r1["align001_violations"] == 0)
        print(f"     期望 PASS / 实得 {r1['verdict']}  {'✅' if c1 else '❌'}")
        ok = ok and c1

        # C2 ★T+1 行：available_at 在 value_dt 次日 ⇒ ALIGN-001 必须 FAIL
        ch(f"""INSERT INTO {SCRATCH_DB}.{src_tbl}
               (value_dt, available_at, factor_name, symbol, factor_value,
                factor_rank, factor_zscore, factor_decile, version, params_hash, computed_at)
               VALUES (toDate('2026-09-10'), toDateTime('2026-09-11 09:00:00'),
                       'qa_align_t1', 'QA.SZ', 1.0, 1, 0.0, 1, 'v1', 'qa', now())""")
        r2 = _v("C2 ★T+1 行（value_dt=09-10, available_at=09-11 09:00）")
        c2 = (r2["align001_violations"] >= 1 and r2["verdict"] == "FAIL")
        print(f"     期望 FAIL / 实得 {r2['verdict']} (违例 {r2['align001_violations']}) "
              f"{'✅ 判据已被负控喂过' if c2 else '❌ 判据恒真，不可用'}")
        ok = ok and c2

        # C3 清除 T+1 行 ⇒ 必须回到 PASS
        ch(f"ALTER TABLE {SCRATCH_DB}.{src_tbl} DELETE WHERE factor_name = 'qa_align_t1'")
        ch(f"SELECT count() FROM {SCRATCH_DB}.{src_tbl} FORMAT TSV")
        r3 = _v("C3 清除 T+1 行后")
        c3 = (r3["align001_violations"] == 0)
        print(f"     期望 PASS / 实得 {r3['verdict']}  {'✅' if c3 else '❌'}")
        ok = ok and c3

        # C4 同日盘中行 ⇒ ALIGN-002 必须触发（advisory 级）
        ch(f"""INSERT INTO {SCRATCH_DB}.{src_tbl}
               (value_dt, available_at, factor_name, symbol, factor_value,
                factor_rank, factor_zscore, factor_decile, version, params_hash, computed_at)
               VALUES (toDate('2026-09-10'), toDateTime('2026-09-10 14:00:00'),
                       'qa_align_intraday', 'QA.SZ', 1.0, 1, 0.0, 1, 'v1', 'qa', now())""")
        r4 = _v("C4 同日盘中行（当日 14:00 才可用）")
        c4 = (r4["align002_intraday"] >= 1 and r4["verdict"] == "PASS")
        print(f"     期望 PASS 且 ALIGN-002 触发 / 实得 {r4['verdict']} (ALIGN-002={r4['align002_intraday']}) "
              f"{'✅' if c4 else '❌'}")
        ok = ok and c4
    finally:
        ch(f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
        print(f"\n  已清理影子库 {SCRATCH_DB}")

    print("\n" + "=" * 78)
    print("  负控结论:", "✅ 判据在两个方向都被真实样本喂过" if ok else "❌ 负控失败，判据不可用")
    print("=" * 78)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="M39 value_dt/available_at 对齐契约断言")
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--negative-control", action="store_true")
    args = ap.parse_args()
    try:
        if args.negative_control:
            sys.exit(negative_control())
        res = run()
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        sys.exit(2)

    print("=" * 78)
    print("  M39 契约断言 — value_dt / available_at 向前对齐")
    print(f"  口径: 同日 join 要求 toDate(available_at) <= value_dt；盘中阈值 {OPEN_HHMM}")
    print("=" * 78)
    for r in res["results"]:
        mark = "❌ FAIL" if r["verdict"] == "FAIL" else "✅ PASS"
        print(f"  {mark}  {r['table']:<44} rows={r['rows']:<10} "
              f"ALIGN-001={r['align001_violations']:<6} ALIGN-002={r['align002_intraday']}")
    print("-" * 78)
    print(f"  扫描表数 {res['tables_scanned']}   Verdict: {res['verdict']}   "
          f"阻断表: {res['blocking_tables'] or '无'}")
    print("=" * 78)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"  JSON: {args.json_out}")
    sys.exit(1 if res["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()

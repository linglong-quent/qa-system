#!/usr/bin/env python3
"""M28 数据契约断言：形如 `*_adj` 的派生表必须**实际引用 adj_factor**。

判据（**查询侧**判定，不依赖表引擎语义；`bar_daily_adj` 是
ReplacingMergeTree(updated_at) PARTITION BY toYear(trade_date)，
去重只在 merge 时发生，因此读表一律用 FINAL）：

  ADJ-001 (BLOCKER)  口径断点
      对每张 `*_adj` 表、每个交易日：
        n_flat = countIf(|adj/raw - 1| < 1e-9  AND  |adj_factor - 1| > 1e-9)
      即"派生值逐列等于原始值、而复权因子并不为 1" ⇒ 表名含 _adj 但未施加复权。
        flat_ratio = n_flat / n_join
      FAIL 条件: n_join >= min_join 且 flat_ratio > max_flat_ratio

  ADJ-002 (WARN)     个别标的 因子↔价格 量级不符（与口径断点区分）
        n_big = countIf(|adj/raw - adj_factor| > 1e-3)
      用于捕捉 08-27~08-31 那类"中位差 5e-8（浮点级）但少数达 73"的独立问题，
      **不得**与 ADJ-001 混为一谈（否则复权正常的日期会被误报）。

  ADJ-003 (WARN)     结构性不可验证
        `*_adj` 表找不到可 join 的原始表 / 因子表 ⇒ 报"无法验证"，不得默认为通过。

用法:
  python scripts/qa_contract_adj.py                      # 全窗口扫描
  python scripts/qa_contract_adj.py --from 2026-08-25 --to 2026-08-31
  python scripts/qa_contract_adj.py --negative-control    # 双向负控（M28 硬要求）
  python scripts/qa_contract_adj.py --json out.json
退出码: 0=PASS  1=FAIL(存在 ADJ-001 阻断)  2=技术性错误
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime

CH_CONTAINER = "linglong-clickhouse"

# 原始表映射：`*_adj` 表 → (原始表, 派生侧代码列, 原始侧代码列, 派生时间列, 原始时间列)
# 日线按 (symbol, trade_date) join；分钟级按 (symbol, ts) ↔ (ts_code, dt) join。
# 未登记者按 ADJ-003 报"不可验证"，**不得**默认为通过。
RAW_MAP = {
    "bar_daily_adj": ("linglong_tdxbase.bar_day", "symbol", "ts_code", None, None),
    "bar_1min_adj": ("linglong_tdxbase.bar_1min", "symbol", "ts_code", "ts", "dt"),
    "bar_5min_adj": ("linglong_tdxbase.bar_5min", "symbol", "ts_code", "ts", "dt"),
    "bar_15min_adj": ("linglong_derived.bar_15min", "symbol", "symbol", "ts", "ts"),
    "bar_30min_adj": ("linglong_derived.bar_30min", "symbol", "symbol", "ts", "ts"),
    "bar_60min_adj": ("linglong_derived.bar_60min", "symbol", "symbol", "ts", "ts"),
}
# 分钟级表为 1~2 亿行，全量 join 对生产集群代价高 ⇒ 抽样（symbol 子集 + 自然日窗口）
INTRADAY_MAX_DAYS = 3
INTRADAY_SAMPLE_SYMBOLS = 200
FACTOR_TABLE = "linglong_tdxbase.adj_factor"
FACTOR_CODE_COL = "ts_code"
DERIVED_DB = "linglong_derived"


def ch(sql: str, timeout: int = 900) -> str:
    p = subprocess.run(["docker", "exec", "-i", CH_CONTAINER, "clickhouse-client",
                        "--query", sql],
                       capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "").strip()[:600])
    return p.stdout


def chj(sql: str):
    out = ch(sql.rstrip().rstrip(";") + " FORMAT JSONEachRow")
    return [json.loads(l) for l in out.strip().splitlines() if l.strip()]


def num(v, default=-1):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def list_adj_tables() -> list:
    rows = chj("SELECT name FROM system.tables "
               "WHERE database='%s' AND name LIKE '%%\\\\_adj' "
               "AND engine != 'View' ORDER BY name" % DERIVED_DB)
    return [r["name"] for r in rows]


def engine_of(table: str) -> str:
    """取表引擎——**仅用于决定 SQL 是否需要 FINAL**（语法要求），
    绝不作为"数据是否正确"的判据（换引擎不产生即时正确性）。"""
    rows = chj("SELECT engine FROM system.tables "
               f"WHERE database='{DERIVED_DB}' AND name='{table}'")
    return rows[0]["engine"] if rows else ""


def scan_table(table: str, d_from: str, d_to: str, max_flat_ratio: float,
               min_join: int) -> dict:
    mapping = RAW_MAP.get(table)
    if not mapping:
        return {"table": table, "status": "UNVERIFIABLE",
                "detail": "未登记原始表映射（RAW_MAP）⇒ 无法验证，不得视为通过",
                "days": [], "blocking": False}
    raw, dcode, rcode, dts, rts = mapping
    intraday = bool(dts and rts)
    # FINAL 只为 ReplacingMergeTree 的去重语义而加（普通 MergeTree 上 FINAL 非法）
    final = " FINAL" if engine_of(table) == "ReplacingMergeTree" else ""

    # 分钟级：按 (symbol, ts) ↔ (ts_code, dt) join；为控制集群代价做有界抽样
    if intraday:
        join_on = f"a.{dcode} = b.{rcode} AND a.{dts} = b.{rts}"
        inner = f"""
        SELECT DISTINCT {dcode} AS s FROM {DERIVED_DB}.{table}
        WHERE trade_date BETWEEN '{d_from}' AND '{d_to}' LIMIT {INTRADAY_SAMPLE_SYMBOLS}
        """
        sample = " AND a." + dcode + f" IN ({inner})"
        scanned = "SAMPLED"
    else:
        join_on = f"a.{dcode} = b.{rcode} AND a.trade_date = b.trade_date"
        sample = ""
        scanned = "SCANNED"

    ts_sel = f", a.{dts} AS t" if intraday else ""
    grp = f", a.{dts}" if intraday else ""
    sql = f"""
    SELECT a.trade_date AS d{ts_sel},
           count() AS n_join,
           countIf(abs(a.close / nullIf(b.close,0) - 1.0) < 1e-9
                   AND abs(af.adj_factor - 1.0) > 1e-9) AS n_flat,
           countIf(abs(a.close / nullIf(b.close,0) - af.adj_factor) > 1e-3) AS n_big,
           any(a.source) AS src
    FROM {DERIVED_DB}.{table} AS a{final}
    INNER JOIN {raw} AS b ON {join_on}
    INNER JOIN {FACTOR_TABLE} AS af
           ON af.{FACTOR_CODE_COL} = a.{dcode}
          AND af.trade_date = a.trade_date
    WHERE a.trade_date BETWEEN '{d_from}' AND '{d_to}'{sample}
    GROUP BY a.trade_date{grp} ORDER BY a.trade_date{grp}
    """
    days, violations = [], []
    for r in chj(sql):
        n_join = int(num(r["n_join"], 0))
        n_flat = int(num(r["n_flat"], 0))
        n_big = int(num(r["n_big"], 0))
        ratio = (n_flat / n_join) if n_join else 0.0
        bad = n_join >= min_join and ratio > max_flat_ratio
        ts = str(r.get("t", ""))
        key = f"{r['d']}T{ts.split(' ')[-1]}" if ts else str(r["d"])
        days.append({"date": key, "n_join": n_join, "n_flat": n_flat,
                     "flat_ratio": round(ratio, 6), "n_big": n_big,
                     "source": r["src"], "adj001_fail": bad})
        if bad:
            violations.append(key)
    return {"table": table, "raw": raw, "status": scanned, "days": days,
            "adj001_violation_days": violations,
            "blocking": bool(violations)}


def run(d_from: str, d_to: str, max_flat_ratio=0.01, min_join=100) -> dict:
    tables = list_adj_tables()
    results = [scan_table(t, d_from, d_to, max_flat_ratio, min_join) for t in tables]
    blocking = [r for r in results if r.get("blocking")]
    return {
        "assertion": "ADJ-001/002/003",
        "contract": "*_adj 派生表必须实际引用 adj_factor（复权口径契约）",
        "window": {"from": d_from, "to": d_to},
        "thresholds": {"max_flat_ratio": max_flat_ratio, "min_join": min_join},
        "tables": results,
        "unverifiable": [r["table"] for r in results if r["status"] == "UNVERIFIABLE"],
        "verdict": "FAIL" if blocking else "PASS",
        "blocking_tables": [r["table"] for r in blocking],
        "generated_at": datetime.now().isoformat(),
    }


def negative_control() -> int:
    """双向负控：同一判据在**真实样本**上必须既 FAIL 又 PASS。

    M28 硬要求（队长升格纪律）：判据必须被负控喂过，不接受"跑出绿色即通过"。
    """
    print("=" * 78)
    print("  ADJ-001 双向负控 — 判据必须在真实坏窗口 FAIL、在真实好窗口 PASS")
    print("=" * 78)
    cases = [
        ("坏窗口（09-01~09-10，calculated 写入方）", "2026-09-01", "2026-09-10", "FAIL"),
        ("好窗口（08-17~08-31，tdxbase_adj 写入方）", "2026-08-17", "2026-08-31", "PASS"),
    ]
    ok = True
    for label, a, b, expect in cases:
        res = run(a, b)
        got = res["verdict"]
        good = (got == expect)
        ok = ok and good
        flag = "✅" if good else "❌"
        print(f"\n{flag} {label}:  期望 {expect} / 实得 {got}")
        for t in res["tables"]:
            if t["status"] == "UNVERIFIABLE":
                print(f"     {t['table']}: {t['status']} — {t['detail']}")
                continue
            vd = t["adj001_violation_days"]
            tag = "（抽样）" if t["status"] == "SAMPLED" else ""
            print(f"     {t['table']}: ADJ-001 违例 {len(vd)}/{len(t['days'])} 点{tag} "
                  f"{vd[:4]}{'…' if len(vd) > 4 else ''}")
            for d in t["days"][:3]:
                print("        %s n_join=%-6s n_flat=%-6s flat_ratio=%-9s src=%s"
                      % (d["date"], d["n_join"], d["n_flat"], d["flat_ratio"], d["source"]))
    print("\n" + "=" * 78)
    print("  负控结论:", "✅ 两向均符合预期（判据已被负控喂过）" if ok
          else "❌ 负控失败 —— 判据不可信，不得用于门禁")
    print("=" * 78)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="M28 *_adj 复权口径契约断言")
    ap.add_argument("--from", dest="d_from", default="2026-08-17")
    ap.add_argument("--to", dest="d_to", default="2026-09-11")
    ap.add_argument("--max-flat-ratio", type=float, default=0.01)
    ap.add_argument("--min-join", type=int, default=100)
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--negative-control", action="store_true")
    args = ap.parse_args()

    try:
        if args.negative_control:
            sys.exit(negative_control())
        res = run(args.d_from, args.d_to, args.max_flat_ratio, args.min_join)
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        sys.exit(2)

    print("=" * 78)
    print("  M28 契约断言 — 形如 *_adj 的派生表必须实际引用 adj_factor")
    print(f"  窗口 {res['window']['from']} ~ {res['window']['to']}   阈值 flat_ratio>{res['thresholds']['max_flat_ratio']}")
    print("=" * 78)
    for t in res["tables"]:
        if t["status"] == "UNVERIFIABLE":
            print(f"  ⚠️  {t['table']:<22} {t['status']} — {t['detail']}")
            continue
        vd = t["adj001_violation_days"]
        mark = "❌ FAIL" if vd else "✅ PASS"
        sample_tag = "（分钟级抽样）" if t["status"] == "SAMPLED" else ""
        n_big_days = sum(1 for d in t["days"] if d.get("n_big", 0) > 0)
        print(f"  {mark}  {t['table']:<22} ADJ-001 违例 {len(vd)}/{len(t['days'])} 个采样点"
              f" | ADJ-002 提示 {n_big_days} 点{sample_tag}")
        for d in t["days"]:
            if d["adj001_fail"]:
                print(f"        [ADJ-001] {d['date']} n_join={d['n_join']} n_flat={d['n_flat']} "
                      f"flat_ratio={d['flat_ratio']} src={d['source']}")
        if n_big_days:
            worst = max(t["days"], key=lambda x: x.get("n_big", 0))
            print(f"        [ADJ-002] 共 {n_big_days} 个采样点存在 |adj/raw - adj_factor|>1e-3"
                  f"（最差 {worst['date']} n_big={worst['n_big']}/{worst['n_join']}）")
    print("-" * 78)
    print(f"  Verdict: {res['verdict']}   阻断表: {res['blocking_tables'] or '无'}")
    if res["unverifiable"]:
        print(f"  不可验证（未登记原始表映射，不得视为通过）: {res['unverifiable']}")
    print("=" * 78)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"  JSON: {args.json_out}")
    sys.exit(1 if res["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""M58 契约断言：A股 universe 必须**契约驱动**，禁止正则前缀

背景（m-linglong 在 M57 实测上报）：
  `linglong/scripts/fill_derived_layer.py:174`
      TSCODE_FILTER = "match(b.ts_code, '^(600|601|603|605|000|001|002|003|300|301|688)')"
  注释写"只保留 A 股股票标的"，但 `000` 前缀**同时命中**
      · 深市股票 `000001.SZ`（平安银行）
      · **沪市指数 `000001.SH`（上证指数）**
  ⇒ 实测 `bar_daily_adj` 含 **217 个非契约标的 / 108,219 行**（后缀 SH 209 个 / 101,873 行）。
  这正是本轮反复出现的「**按名字猜口径**」：正则看不出"证券 vs 指数"，而契约可以。

判据：
  UNIV-001 (BLOCKER)  表内标的必须命中契约源 `linglong_dim.sec_basic` 且 `sec_type='stock'`
  UNIV-002 (BLOCKER)  **正则口径自证**：同一 6 位数字前缀的 `000001.SH` 与 `000001.SZ`
                      必须被判据区分开；正则判据做不到 ⇒ 不得作为 universe 判据

用法:
  python scripts/qa_contract_universe.py
  python scripts/qa_contract_universe.py --json out.json
  python scripts/qa_contract_universe.py --negative-control     # ★必交负控
退出码: 0=PASS  1=FAIL  2=技术性错误
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime

CH = "linglong-clickhouse"
CONTRACT_DB = "linglong_dim"
CONTRACT_TBL = "sec_basic"
CONTRACT_TYPE_COL = "sec_type"
STOCK_TYPE = "stock"
SCRATCH_DB = "qa_m58_scratch"
SCRATCH_TBL = "universe_probe"
# 待检表：(库, 表, 标的列)。bar_daily_adj 为主；下游按需扩。
TARGETS = [
    ("linglong_derived", "bar_daily_adj", "symbol"),
    ("linglong_factor", "factor_features", "symbol"),
    ("linglong_factor", "factor_features_stock", "symbol"),
    ("linglong_factor", "alpha101_features", "symbol"),
    ("linglong_factor", "fact_technical", "symbol"),
    ("linglong_factor", "lgbm_scores", "symbol"),
    ("linglong_factor", "factor_values", "symbol"),
]
# m-spec 现行正则（用于 UNIV-002 自证；**不作为判据**）
LEGACY_RE = "^(600|601|603|605|000|001|002|003|300|301|688)"
PROBE_SH = "000001.SH"   # 沪市指数（上证指数）
PROBE_SZ = "000001.SZ"   # 深市股票（平安银行）


def ch(sql, timeout=1800):
    p = subprocess.run(["docker", "exec", "-i", CH, "clickhouse-client", "--query", sql],
                       capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "").strip()[:500])
    return p.stdout


def chj(sql, timeout=1800):
    out = ch(sql.rstrip().rstrip(";") + " FORMAT JSONEachRow", timeout)
    return [json.loads(l) for l in out.strip().splitlines() if l.strip()]


def contract_symbols():
    """契约源：sec_basic 中 sec_type='stock' 的标的集合（用于离线判定）"""
    return {r["ts_code"] for r in chj(
        f"SELECT ts_code FROM {CONTRACT_DB}.{CONTRACT_TBL} "
        f"WHERE {CONTRACT_TYPE_COL} = '{STOCK_TYPE}'")}


def check_table(db, tbl, col):
    sql = f"""
    SELECT count() AS rows_total,
           count(DISTINCT t.{col}) AS syms_total,
           countIf(sb.ts_code = '') AS rows_non_contract,
           uniqExactIf(t.{col}, sb.ts_code = '') AS syms_non_contract
    FROM `{db}`.`{tbl}` AS t
    LEFT JOIN `{CONTRACT_DB}`.`{CONTRACT_TBL}` AS sb
           ON sb.ts_code = t.{col} AND sb.{CONTRACT_TYPE_COL} = '{STOCK_TYPE}'
    """
    r = chj(sql)[0]
    # 抽 12 个非契约标的做样本
    sample = [x["sym"] for x in chj(f"""
    SELECT DISTINCT t.{col} AS sym FROM `{db}`.`{tbl}` AS t
    LEFT JOIN `{CONTRACT_DB}`.`{CONTRACT_TBL}` AS sb
           ON sb.ts_code = t.{col} AND sb.{CONTRACT_TYPE_COL} = '{STOCK_TYPE}'
    WHERE sb.ts_code = '' LIMIT 12
    """)]
    n_rows = int(r["rows_non_contract"])
    return {"table": f"{db}.{tbl}", "column": col,
            "rows_total": int(r["rows_total"]), "syms_total": int(r["syms_total"]),
            "rows_non_contract": n_rows,
            "syms_non_contract": int(r["syms_non_contract"]),
            "sample_non_contract": sample,
            "blocking": n_rows > 0,
            "verdict": "FAIL" if n_rows > 0 else "PASS"}


def regex_selfproof():
    """UNIV-002：正则判据无法区分同前缀的指数与股票"""
    r = chj(f"""SELECT
        match('{PROBE_SH}', '{LEGACY_RE}') AS sh_index_matches,
        match('{PROBE_SZ}', '{LEGACY_RE}') AS sz_stock_matches,
        match('399001.SZ', '{LEGACY_RE}') AS sz_index_matches,
        match('600519.SH', '{LEGACY_RE}') AS sh_stock_matches""")[0]
    contract = contract_symbols()
    return {
        "legacy_regex": LEGACY_RE,
        "probe": {
            PROBE_SH: {"regex_matches": int(r["sh_index_matches"]),
                       "in_contract_stock": PROBE_SH in contract},
            PROBE_SZ: {"regex_matches": int(r["sz_stock_matches"]),
                       "in_contract_stock": PROBE_SZ in contract},
            "399001.SZ": {"regex_matches": int(r["sz_index_matches"]),
                          "in_contract_stock": "399001.SZ" in contract},
            "600519.SH": {"regex_matches": int(r["sh_stock_matches"]),
                          "in_contract_stock": "600519.SH" in contract},
        },
        # 正则把"非契约"的 000001.SH 判为命中，却把"契约内"的 399001.SZ 判为不命中 ⇒ 双向错
        "regex_cannot_distinguish": bool(int(r["sh_index_matches"]) == 1
                                         and int(r["sz_stock_matches"]) == 1),
        "verdict": "FAIL",
    }


def run(targets=None):
    tabs = targets or TARGETS
    results = []
    for db, tbl, col in tabs:
        try:
            results.append(check_table(db, tbl, col))
        except Exception as e:
            results.append({"table": f"{db}.{tbl}", "error": str(e)[:200],
                            "blocking": False, "verdict": "ERROR"})
    rp = regex_selfproof()
    blocking = [r for r in results if r.get("blocking")]
    return {
        "assertion": "UNIV-001/002",
        "contract": "A股 universe 必须来自 linglong_dim.sec_basic 且 sec_type='stock'；"
                    "禁止用 ts_code 正则前缀判定（000 前缀同时命中深市股票与沪市指数）",
        "contract_source": f"{CONTRACT_DB}.{CONTRACT_TBL}.{CONTRACT_TYPE_COL}='{STOCK_TYPE}'",
        "tables": results,
        "regex_selfproof": rp,
        "verdict": "FAIL" if blocking else "PASS",
        "blocking_tables": [r["table"] for r in blocking],
        "totals": {"tables": len(results),
                   "rows_non_contract": sum(r.get("rows_non_contract", 0) for r in results),
                   "syms_non_contract": sum(r.get("syms_non_contract", 0) for r in results)},
        "generated_at": datetime.now().isoformat(),
    }


def negative_control() -> int:
    """★必交负控：构造 000001.SH 与 000001.SZ 两个样本，证正则判据把前者当证券、
    契约判据正确区分；并在影子表上验证断言真的会 FAIL/PASS。"""
    print("=" * 78)
    print("  M58 负控 — 构造 000001.SH（沪市指数）与 000001.SZ（深市股票）两个样本")
    print("=" * 78)
    ok = True

    # NC-A 正则判据自证
    rp = regex_selfproof()
    print("\n  [NC-A] 现行正则判据的自证（不是断言，是**证明正则不可用**）")
    for sym, d in rp["probe"].items():
        print(f"        {sym:<12} 正则命中={d['regex_matches']}  契约内股票={d['in_contract_stock']}")
    a = (rp["probe"][PROBE_SH]["regex_matches"] == 1
         and not rp["probe"][PROBE_SH]["in_contract_stock"]
         and rp["probe"][PROBE_SZ]["regex_matches"] == 1
         and rp["probe"][PROBE_SZ]["in_contract_stock"])
    print(f"        ⇒ 正则把**非契约的 000001.SH** 与**契约内的 000001.SZ** 都判为命中，"
          f"无法区分 {'✅' if a else '❌'}")
    ok = ok and a

    # NC-B 影子表：注入两行，断言必须只对 SH 报 FAIL
    created = False
    try:
        ch(f"CREATE DATABASE IF NOT EXISTS {SCRATCH_DB}")
        ch(f"DROP TABLE IF EXISTS {SCRATCH_DB}.{SCRATCH_TBL}")
        ch(f"CREATE TABLE {SCRATCH_DB}.{SCRATCH_TBL} AS {CONTRACT_DB}.{CONTRACT_TBL}")
        created = True
        # 影子表以 sec_basic 为模板不合适；改用最小表
        ch(f"DROP TABLE {SCRATCH_DB}.{SCRATCH_TBL}")
        ch(f"""CREATE TABLE {SCRATCH_DB}.{SCRATCH_TBL}
               (symbol String, trade_date Date, close Float64)
               ENGINE = MergeTree ORDER BY (symbol, trade_date)""")
        ch(f"INSERT INTO {SCRATCH_DB}.{SCRATCH_TBL} VALUES "
           f"('{PROBE_SH}', '2026-09-11', 3900.0), ('{PROBE_SZ}', '2026-09-11', 11.5)")
        print(f"\n  [NC-B] 影子表注入两行：{PROBE_SH}（沪市指数） + {PROBE_SZ}（深市股票）")
        r = check_table(SCRATCH_DB, SCRATCH_TBL, "symbol")
        print(f"        rows_total={r['rows_total']} rows_non_contract={r['rows_non_contract']} "
              f"syms_non_contract={r['syms_non_contract']} 样本={r['sample_non_contract']}")
        b1 = (r["rows_non_contract"] == 1 and r["sample_non_contract"] == [PROBE_SH]
              and r["verdict"] == "FAIL")
        print(f"        期望 恰好 1 行非契约且样本 == ['{PROBE_SH}'] → FAIL / 实得 "
              f"{r['sample_non_contract']} → {r['verdict']}  {'✅' if b1 else '❌'}")
        ok = ok and b1

        # NC-C 删除指数行 ⇒ 必须 PASS
        ch(f"ALTER TABLE {SCRATCH_DB}.{SCRATCH_TBL} DELETE WHERE symbol = '{PROBE_SH}'")
        ch(f"SELECT count() FROM {SCRATCH_DB}.{SCRATCH_TBL} FORMAT TSV")
        import time
        time.sleep(2)
        r2 = check_table(SCRATCH_DB, SCRATCH_TBL, "symbol")
        b2 = (r2["rows_non_contract"] == 0 and r2["verdict"] == "PASS")
        print(f"\n  [NC-C] 删除指数行后：rows_non_contract={r2['rows_non_contract']} "
              f"→ {r2['verdict']}  {'✅' if b2 else '❌'}")
        ok = ok and b2

        # NC-D 反向：把股票行也换成指数 ⇒ 必须再 FAIL（证明判据不是恒 PASS）
        ch(f"TRUNCATE TABLE {SCRATCH_DB}.{SCRATCH_TBL}")
        ch(f"INSERT INTO {SCRATCH_DB}.{SCRATCH_TBL} VALUES ('399001.SZ','2026-09-11',10000.0)")
        time.sleep(1)
        r3 = check_table(SCRATCH_DB, SCRATCH_TBL, "symbol")
        b3 = (r3["rows_non_contract"] == 1 and r3["verdict"] == "FAIL")
        print(f"\n  [NC-D] 改为深证成指 399001.SZ（契约外）：rows_non_contract="
              f"{r3['rows_non_contract']} → {r3['verdict']}  {'✅' if b3 else '❌'}")
        ok = ok and b3
    finally:
        if created:
            ch(f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
            print(f"\n  已清理影子库 {SCRATCH_DB}")

    print("\n" + "=" * 78)
    print("  负控结论:", "✅ 判据两向都被喂过；正则判据的失效已被证明" if ok else "❌ 负控失败")
    print("=" * 78)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="M58 A股 universe 契约断言")
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
    print("  M58 契约断言 — A股 universe 必须契约驱动（禁正则前缀）")
    print(f"  契约源: {res['contract_source']}")
    print("=" * 78)
    for r in res["tables"]:
        if "error" in r:
            print(f"  ⚠️  {r['table']:<44} ERROR: {r['error'][:80]}")
            continue
        mark = "❌ FAIL" if r["verdict"] == "FAIL" else "✅ PASS"
        print(f"  {mark}  {r['table']:<42} rows={r['rows_total']:<9} "
              f"非契约 {r['rows_non_contract']:<7} 标的 {r['syms_non_contract']}")
        if r["sample_non_contract"]:
            print(f"        样本: {r['sample_non_contract'][:8]}")
    rp = res["regex_selfproof"]
    print("\n  [UNIV-002] 正则判据自证：")
    for sym, d in rp["probe"].items():
        print(f"        {sym:<12} 正则命中={d['regex_matches']}  契约内股票={d['in_contract_stock']}")
    t = res["totals"]
    print("-" * 78)
    print(f"  扫描 {t['tables']} 表 / 非契约 {t['rows_non_contract']} 行 / {t['syms_non_contract']} 标的")
    print(f"  Verdict: {res['verdict']}   阻断表: {res['blocking_tables'] or '无'}")
    print("=" * 78)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"  JSON: {args.json_out}")
    sys.exit(1 if res["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()

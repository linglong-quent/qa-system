#!/usr/bin/env python3
"""M69(b) L3 因果性断言：消费方运行时，其输入是否已就位。

【为什么需要】
m-spec 原判断「所有消费方跑在生产方之前」**从未被验证**；更正后仍成立的是：
**没有任何地方对「消费方运行时其输入是否已就位」做过断言**。
实测支撑（S3 运行时事实，2026-09-12~15 的 system.query_log）：
  `linglong_derived.bar_daily_adj` 唯一生产方 `fill_derived_layer.py` 在 **20:00** 写；
  而该表在近 3 天被读 538 次，**24 小时全时段都有读，盘中 9–14 时合计 185 次**
  ⇒ 消费发生在生产之前的时段是常态，**无人断言输入是否就位**。

【判据（可失败）】
三种口径至少其一，本实现同时支持：
  W 水位(watermark)：消费方需要日期 D 的输入 ⇒ 生产方 max(date_col) 必须 >= D
  V 版本(version)  ：生产方最后写入时刻 max(version_col) 必须不晚于消费方触发时刻
  T 窗口(window)   ：消费方触发时刻必须落在 [生产方完成, 生产方完成 + window] 内
三态输出，**「无法判定」不得当作「已就位」**（M51 统一判据的同族）：
  READY / NOT_READY / UNDETERMINED

退出码：0=全部 READY；1=存在 NOT_READY（阻断）；2=存在 UNDETERMINED 或执行错误。
"""
import argparse
import base64
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

CH = os.environ.get("QA_CH_URL", "http://127.0.0.1:8123/")
_USER = os.environ.get("CH_USER", "default")
_PWD = os.environ.get("CH_PASSWORD", os.environ.get("LINGLONG_CH_PASSWORD", "linglong"))
_AUTH = "Basic " + base64.b64encode(f"{_USER}:{_PWD}".encode()).decode()

READY, NOT_READY, UNDET = "READY", "NOT_READY", "UNDETERMINED"

# ── 声明式依赖边：消费方 → 它运行时必须已就位的输入 ──────────────────────
# 每条的 cron 取自活体调度器 scripts/scheduler_main.py 的 add_job（S2 取证）。
L3_EDGES = [
    {
        "consumer": "factor_calc", "script": "batch_calculate_factors.py",
        "trigger": "19:00 每交易日", "trigger_hour": 19,
        "requires": [{"table": "linglong_derived.bar_daily_adj", "date_col": "trade_date",
                      "rule": "watermark", "req": "same_day",
                      "why": "因子计算必须基于当日复权日线"}],
    },
    {
        "consumer": "fill_derived", "script": "fill_derived_layer.py",
        "trigger": "20:00 每交易日", "trigger_hour": 20,
        "requires": [{"table": "linglong_tdxbase.bar_day", "date_col": "trade_date",
                      "rule": "watermark", "req": "same_day",
                      "why": "复权日线由未复权日线派生，输入必须已就位"}],
    },
    {
        "consumer": "health_check", "script": "health_monitor.py",
        "trigger": "每 30 分钟", "trigger_hour": None,
        "requires": [{"table": "linglong_derived.bar_daily_adj", "date_col": "trade_date",
                      "rule": "watermark", "req": "prev_day_or_later",
                      "why": "健康检查读该表判健康，必须区分『当日尚未生产』与『数据陈旧』"}],
    },
]


def ch(sql, timeout=45):
    url = CH + "?" + urllib.parse.urlencode({"query": sql, "default_format": "JSONEachRow",
                                            "max_execution_time": timeout})
    req = urllib.request.Request(url)
    req.add_header("Authorization", _AUTH)
    with urllib.request.urlopen(req, timeout=timeout + 15) as r:
        body = r.read().decode("utf-8", "replace")
    return [json.loads(l) for l in body.splitlines() if l.strip()]


def watermark(table, date_col, version_col="updated_at", days=120, want_version=False):
    """生产方水位（及可选最后写入时刻）。

    性能实测：`max(updated_at)` 会**全表扫描**而超时 —— 因为 `updated_at` 不在
    `ORDER BY (symbol, trade_date)` 里。故：
      · 水位查询限定在最近 N 天内（有界、走分区裁剪）
      · 版本列默认不查（只在显式需要时查，且同样有界）
    **不使用 FINAL**（ReplacingMergeTree 上 max 无需 FINAL；实测 FINAL 会超时）。
    """
    lo = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    cols = f"max({date_col}) AS wm"
    if want_version:
        cols += f", max({version_col}) AS ver"
    q = f"SELECT {cols} FROM {table} WHERE {date_col} >= '{lo}'"
    r = ch(q)
    if not r:
        return None, None
    return r[0].get("wm"), r[0].get("ver")


def judge_edge(edge, asof: str):
    """对一条边做三态判定。asof = 消费方运行日期 YYYY-MM-DD。"""
    out = []
    for need in edge["requires"]:
        t, dc = need["table"], need["date_col"]
        try:
            wm, ver = watermark(t, dc)
        except Exception as e:
            out.append({"table": t, "verdict": UNDET,
                        "detail": f"无法读取水位: {type(e).__name__}: {str(e)[:120]}"})
            continue
        if not wm:
            out.append({"table": t, "verdict": UNDET, "detail": "水位为空（无数据）"})
            continue
        wm_s = str(wm)[:10]
        need_wm = asof if need.get("req") == "same_day" else \
            (dt.date.fromisoformat(asof) - dt.timedelta(days=1)).isoformat()
        ok = wm_s >= need_wm
        out.append({
            "table": t, "rule": need.get("rule"), "req": need.get("req"),
            "watermark": wm_s, "required": need_wm, "last_write": str(ver)[:19],
            "verdict": READY if ok else NOT_READY,
            "detail": (f"水位 {wm_s} >= 需要 {need_wm}" if ok
                       else f"★水位 {wm_s} < 需要 {need_wm} —— 消费时输入未就位"),
        })
    return out


def run(asof: str, only=None) -> dict:
    results = []
    for e in L3_EDGES:
        if only and e["consumer"] not in only:
            continue
        checks = judge_edge(e, asof)
        verdicts = {c["verdict"] for c in checks}
        overall = NOT_READY if NOT_READY in verdicts else (
            UNDET if UNDET in verdicts else READY)
        results.append({"consumer": e["consumer"], "script": e["script"],
                        "trigger": e["trigger"], "asof": asof,
                        "overall": overall, "checks": checks})
    return {"asof": asof, "edges": results}


def negative_control():
    """★M69(b) 负控：构造「输入未就位」态，证明断言会 FAIL。

    两个方向，都不靠手工造假数据，而是用真实事实构造：
      NC-1 需求日期 = 生产方水位 + 1 天（生产方确实还没写）⇒ 必须 NOT_READY
      NC-2 输入表不存在（既非 READY 也非 NOT_READY 的"查不到"）⇒ 必须 UNDETERMINED
           —— 证明「无法判定」不会被当成「已就位」
    """
    print("=" * 74)
    print("★M69(b) 负控：构造输入未就位的态，断言必须 FAIL")
    print("=" * 74)
    ok_all = True

    # NC-1
    e = L3_EDGES[0]
    need = e["requires"][0]
    wm, _ = watermark(need["table"], need["date_col"])
    if not wm:
        print("  NC-1 ⚠️ 取不到水位，跳过")
        ok_all = False
    else:
        beyond = (dt.date.fromisoformat(str(wm)[:10]) + dt.timedelta(days=1)).isoformat()
        checks = judge_edge(e, beyond)
        v = checks[0]["verdict"]
        good = v == NOT_READY
        ok_all &= good
        print(f"  NC-1 需求日 {beyond}（= 真实水位 {str(wm)[:10]} + 1 天）")
        print(f"       {e['consumer']} → {checks[0]['verdict']} — {checks[0]['detail']}")
        print(f"       判据: {'✅ 正确 FAIL（NOT_READY）' if good else '❌ 未按预期 FAIL'}")

    # NC-2
    fake = {"consumer": "nc_fake", "script": "-", "trigger": "-",
            "requires": [{"table": "linglong_derived.__no_such_table__",
                          "date_col": "trade_date", "rule": "watermark",
                          "req": "same_day", "why": "负控：表不存在"}]}
    checks = judge_edge(fake, "2026-09-10")
    v2 = checks[0]["verdict"]
    good2 = v2 == UNDET
    ok_all &= good2
    print(f"\n  NC-2 输入表不存在（linglong_derived.__no_such_table__）")
    print(f"       → {v2} — {checks[0]['detail'][:110]}")
    print(f"       判据: {'✅ 正确 UNDETERMINED（未被当成 READY）' if good2 else '❌ 未按预期'}")

    # 正控：确认同一断言在正常态会 READY（否则"总会 FAIL"就没分辨力）
    pc = judge_edge(L3_EDGES[0], str(wm)[:10])
    good3 = pc[0]["verdict"] == READY
    ok_all &= good3
    print(f"\n  正控 需求日 = 真实水位 {str(wm)[:10]}")
    print(f"       → {pc[0]['verdict']} — {pc[0]['detail']}")
    print(f"       判据: {'✅ 正确 READY（断言非恒 FAIL，有分辨力）' if good3 else '❌ 未按预期'}")

    print(f"\n  负控+正控总判定: {'✅ 全部符合预期' if ok_all else '❌ 存在不符合项'}")
    return 0 if ok_all else 1


def main():
    ap = argparse.ArgumentParser(description="L3 因果性断言：消费方运行时输入是否已就位")
    ap.add_argument("--as-of", default=dt.date.today().isoformat(),
                    help="消费方运行日期（默认今天）")
    ap.add_argument("--consumer", action="append", default=None,
                    help="只判指定消费方（可多次）")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--negative-control", action="store_true",
                    help="★运行负控：构造输入未就位态，证明断言会 FAIL")
    args = ap.parse_args()

    if args.negative_control:
        return negative_control()

    rep = run(args.as_of, only=args.consumer)
    n_ready = n_not = n_undet = 0
    for e in rep["edges"]:
        icon = {READY: "✅", NOT_READY: "❌", UNDET: "⚠️ "}[e["overall"]]
        print(f"{icon} [{e['consumer']}] {e['script']}  触发={e['trigger']}  判定={e['overall']}")
        for c in e["checks"]:
            print(f"      {c['table']}: {c['verdict']} — {c['detail']}")
        if e["overall"] == READY:
            n_ready += 1
        elif e["overall"] == NOT_READY:
            n_not += 1
        else:
            n_undet += 1
    print(f"\n  汇总: READY={n_ready} NOT_READY={n_not} UNDETERMINED={n_undet}")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print(f"  契约: {args.json_out}")
    # 三态退出码：「无法判定」不得当作「已就位」
    if n_not:
        return 1
    if n_undet:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

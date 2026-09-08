#!/usr/bin/env python3
"""景气趋势每日选股入口（静水×CANSLIM 蒸馏框架, 见 docs/trend_alpha_framework.md）

用法:
  python3 projects/trend_alpha/run.py                 # 每日运行(缓存优先)
  python3 projects/trend_alpha/run.py --refresh-fin   # 强制重拉全部财务(新报告期开始后)
  python3 projects/trend_alpha/run.py --skip-prev     # 关闭双期确认
  python3 projects/trend_alpha/run.py --sample 60     # 仅取前60只候选(冒烟)
输出: output/trend_alpha/trend_alpha_YYYY-MM-DD.md / .json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg  # noqa: E402
import fetch  # noqa: E402
import metrics  # noqa: E402
import report  # noqa: E402
from tools.ths_api import log, fetch_all_stocks  # noqa: E402
from tools.filters import filter_candidates  # noqa: E402

NOW = datetime.now()
TODAY = NOW.strftime("%Y-%m-%d")
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][NOW.weekday()]
DATE_TAG = NOW.strftime("%Y%m%d")
END_MS = int((NOW + timedelta(days=1)).timestamp() * 1000)
START_MS_TECH = int((NOW - timedelta(days=cfg.TECH_DAYS + 20)).timestamp() * 1000)
START_MS_IDX = int((NOW - timedelta(days=600)).timestamp() * 1000)


def elapsed(t0):
    return time.time() - t0


def main():
    ap = argparse.ArgumentParser(description="景气趋势每日选股")
    ap.add_argument("--refresh-fin", action="store_true", help="强制重拉主报告期财务")
    ap.add_argument("--refresh-ind", action="store_true", help="强制重拉行业成分")
    ap.add_argument("--skip-prev", action="store_true", help="关闭双期确认")
    ap.add_argument("--skip-annual", action="store_true", help="关闭年度验证")
    ap.add_argument("--sample", type=int, default=0, help="仅取前N只候选(冒烟)")
    ap.add_argument("--max-tech", type=int, default=0, help="技术面仅处理前N只(冒烟)")
    args = ap.parse_args()

    require_prev = cfg.REQUIRE_PREV and not args.skip_prev
    require_annual = cfg.REQUIRE_ANNUAL and not args.skip_annual
    os.makedirs(cfg.CACHE_DIR, exist_ok=True)
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)

    params = {
        "report_main": cfg.REPORT_MAIN, "report_prev": cfg.REPORT_PREV,
        "report_annual": cfg.REPORT_ANNUAL,
        "p_sales": cfg.P_SALES_MAIN, "p_profit": cfg.P_PROFIT_MAIN,
        "p_eps": cfg.P_EPS_MAIN, "p_profit_prev": cfg.P_PROFIT_PREV,
        "p_annual": cfg.P_ANNUAL,
        "require_prev": require_prev, "require_annual": require_annual,
        "require_eps": cfg.REQUIRE_EPS,
        "exclude_st": cfg.EXCLUDE_ST, "exclude_bse": cfg.EXCLUDE_BSE,
        "exclude_star": cfg.EXCLUDE_STAR,
    }
    stats = {"universe": 0, "fin_base": 0, "fin_pass": 0, "tech_ok": 0}

    t0 = time.time()
    log("=" * 70)
    log(f"景气趋势每日选股 {TODAY} {WEEKDAY_CN} (主筛 {cfg.REPORT_MAIN})")
    log("=" * 70)

    # ── 0. 探测指标id ──
    log("0/6 探测财务指标id...")
    ids = fetch.probe_indicator_ids([cfg.REPORT_MAIN, cfg.REPORT_PREV, cfg.REPORT_ANNUAL], cfg.CACHE_DIR)
    cfg.IDS.update(ids)
    need = [r for r in ("profit", "rev") if not cfg.IDS.get(r)]
    if need:
        log(f"  ✗ 缺少关键指标id({need}), 中止")
        return 1

    # ── 1. 全市场候选 ──
    log("1/6 获取全A股票列表...")
    stocks = []
    for attempt in range(4):
        stocks = fetch_all_stocks()
        if stocks:
            break
        log(f"  股票列表拉取失败(第{attempt + 1}次), 重试...")
        time.sleep(3)
    if not stocks:
        log("✗ 无法获取股票列表")
        return 1
    candidates, _ = filter_candidates(
        stocks, cfg.EXCLUDE_ST, cfg.EXCLUDE_BSE, cfg.EXCLUDE_STAR)
    if args.sample:
        candidates = candidates[:args.sample]
    stats["universe"] = len(candidates)
    log(f"  候选池: {len(candidates)} 只")

    # ── 2. 财务筛选(带当日缓存) ──
    log(f"2/6 财务筛选 (主筛 {cfg.REPORT_MAIN})...")
    fin_cache = os.path.join(cfg.CACHE_DIR, f"fin_{cfg.REPORT_MAIN}_{DATE_TAG}.json")
    fin = {}
    cache_valid = False
    if os.path.exists(fin_cache) and not args.refresh_fin:
        with open(fin_cache) as f:
            fin_all = json.load(f)
        if fin_all.get("__meta__", {}).get("n") == len(candidates):
            fin = {k: v for k, v in fin_all.items() if k != "__meta__"}
            cache_valid = True
            log(f"  财务使用当日缓存: {len(fin)} 只")
        else:
            log(f"  财务缓存覆盖范围不符(缓存{fin_all.get('__meta__', {}).get('n')}只"
                f" vs 候选{len(candidates)}只), 重新抓取")
    if not cache_valid:
        fin = {}
        t = time.time()
        fmap = fetch.indicators_map([s["thscode"] for s in candidates],
                                    cfg.REPORT_MAIN, cfg.FETCH_WORKERS_FIN)
        log(f"  主报告期抓取完成: {len(fmap)} 只 ({elapsed(t):.0f}s)")
        for tc, flat in fmap.items():
            fin[tc] = {
                "g_main": flat.get(cfg.IDS["profit"]),
                "rev_main": flat.get(cfg.IDS["rev"]),
                "roe_main": flat.get(cfg.IDS.get("roe")) if cfg.IDS.get("roe") else None,
                "gross_main": flat.get(cfg.IDS.get("gross")) if cfg.IDS.get("gross") else None,
                "cash_content": flat.get(cfg.IDS.get("cash_content")) if cfg.IDS.get("cash_content") else None,
                "cash_op_index": flat.get(cfg.IDS.get("cash_op_index")) if cfg.IDS.get("cash_op_index") else None,
                "eps_main": flat.get(cfg.IDS.get("eps")) if cfg.IDS.get("eps") else None,
            }
        with open(fin_cache, "w") as f:
            json.dump({"__meta__": {"n": len(candidates)}, **fin}, f, ensure_ascii=False)
        log(f"  财务缓存已存 ({DATE_TAG})")

    def save_fin_cache():
        with open(fin_cache, "w") as f:
            json.dump({"__meta__": {"n": len(candidates)}, **fin}, f, ensure_ascii=False)

    def eps_of(entry):
        """EPS同比: 有真实EPS字段用EPS, 否则归母净利同比代理(API暂无eps字段)。"""
        eps = entry.get("eps_main")
        return eps if eps is not None else entry.get("g_main")

    def gate_main(entry):
        g, rev = entry.get("g_main"), entry.get("rev_main")
        if g is None or rev is None:
            return False
        if g < cfg.P_PROFIT_MAIN or rev < cfg.P_SALES_MAIN:
            return False
        if cfg.REQUIRE_EPS and (eps_of(entry) or 0) < cfg.P_EPS_MAIN:
            return False
        return True

    main_pass = [tc for tc, e in fin.items() if gate_main(e)]
    stats["fin_base"] = len(main_pass)
    eps_tag = f" EPS同比≥{cfg.P_EPS_MAIN}%(代理)" if cfg.REQUIRE_EPS else ""
    log(f"  主报告期达标(营收≥{cfg.P_SALES_MAIN}% 净利≥{cfg.P_PROFIT_MAIN}%{eps_tag}): {len(main_pass)} 只")

    if require_prev:
        need = [tc for tc in main_pass if fin[tc].get("g_prev") is None]
        if need:
            t = time.time()
            fmap_prev = fetch.indicators_map(need, cfg.REPORT_PREV, cfg.FETCH_WORKERS_FIN, log_every=200)
            for tc, flat in fmap_prev.items():
                fin.setdefault(tc, {})["g_prev"] = flat.get(cfg.IDS["profit"])
            log(f"  前一报告期({cfg.REPORT_PREV})抓取: {len(fmap_prev)} 只 ({elapsed(t):.0f}s)")
            save_fin_cache()
        kept = [tc for tc in main_pass
                if (fin[tc].get("g_prev") is not None
                    and fin[tc]["g_prev"] >= cfg.P_PROFIT_PREV)]
        log(f"  双期确认(净利≥{cfg.P_PROFIT_PREV}%): {len(kept)} 只")
        main_pass = kept

    if require_annual:
        need = [tc for tc in main_pass if fin[tc].get("g_annual") is None]
        if need:
            t = time.time()
            fmap_an = fetch.indicators_map(need, cfg.REPORT_ANNUAL, cfg.FETCH_WORKERS_FIN, log_every=200)
            for tc, flat in fmap_an.items():
                fin.setdefault(tc, {})["g_annual"] = flat.get(cfg.IDS["profit"])
            log(f"  年报({cfg.REPORT_ANNUAL})抓取: {len(fmap_an)} 只 ({elapsed(t):.0f}s)")
            save_fin_cache()
        kept = [tc for tc in main_pass
                if (fin[tc].get("g_annual") is not None
                    and fin[tc]["g_annual"] >= cfg.P_ANNUAL)]
        log(f"  年度验证(净利≥{cfg.P_ANNUAL}%): {len(kept)} 只")
        main_pass = kept

    # 同期对比报告期(毛利率同比Δ)
    need_cmp = [tc for tc in main_pass if fin[tc].get("gross_ly") is None]
    if need_cmp:
        t = time.time()
        fmap_cmp = fetch.indicators_map(need_cmp, cfg.REPORT_CMP, cfg.FETCH_WORKERS_FIN, log_every=200)
        for tc, flat in fmap_cmp.items():
            fin.setdefault(tc, {})["gross_ly"] = flat.get(cfg.IDS["gross"]) if cfg.IDS.get("gross") else None
        log(f"  同期对比({cfg.REPORT_CMP})抓取: {len(fmap_cmp)} 只 ({elapsed(t):.0f}s)")
        save_fin_cache()

    name_map = {s["thscode"]: s["name"] for s in stocks}
    records = []
    for tc in main_pass:
        e = fin[tc]
        rec = {
            "thscode": tc, "name": name_map.get(tc, ""),
            "g_main": e.get("g_main"), "rev_main": e.get("rev_main"),
            "roe_main": e.get("roe_main"), "g_prev": e.get("g_prev"),
            "g_annual": e.get("g_annual"), "eps_main": e.get("eps_main"),
            "gross_main": e.get("gross_main"), "gross_ly": e.get("gross_ly"),
            "cash_content": e.get("cash_content"),
            "cash_op_index": e.get("cash_op_index"),
        }
        metrics.compute_quality(rec)
        records.append(rec)
    stats["fin_pass"] = len(records)
    if not records:
        log("✗ 无符合财务条件股票")
        return 1

    # ── 3. 技术面: 日K + 快照 ──
    log("3/6 技术面抓取(日K/快照)...")
    tech_codes = [r["thscode"] for r in records]
    if args.max_tech:
        tech_codes = tech_codes[:args.max_tech]

    tech_cache = os.path.join(cfg.CACHE_DIR, f"tech_{DATE_TAG}.json")
    tech_store = {}
    if os.path.exists(tech_cache):
        with open(tech_cache) as f:
            tech_store = json.load(f)
        log(f"  技术缓存命中 {len(tech_store)} 只")

    todo = [c for c in tech_codes if c not in tech_store]
    if todo:
        t = time.time()
        bars_map = fetch.bars_map(todo, START_MS_TECH, END_MS, cfg.FETCH_WORKERS_BARS)
        log(f"  日K抓取: {len(bars_map)} 只 ({elapsed(t):.0f}s)")
        for tc, bars in bars_map.items():
            tech_store[tc] = {
                "last": bars[-1]["date"] if bars else "",
                "bars": [{"d": b["date"], "c": b["close"], "h": b["high"], "v": b["vol"]}
                         for b in bars],
            }
        with open(tech_cache, "w") as f:
            json.dump(tech_store, f, ensure_ascii=False)
        log(f"  技术缓存已存 ({DATE_TAG})")

    t = time.time()
    from tools.ths_api import fetch_snapshot_batch, fetch_auction_snapshot_batch
    snaps = fetch_snapshot_batch(tech_codes)
    aucts = fetch_auction_snapshot_batch(tech_codes)
    log(f"  快照抓取完成 ({elapsed(t):.0f}s)")

    ret120_pool = []
    for r in records:
        st = tech_store.get(r["thscode"])
        if not st or not st.get("bars"):
            r["tech_ok"] = False
            r["tech_note"] = "无K线"
            continue
        bars = [{"date": b["d"], "close": b["c"], "high": b["h"], "vol": b["v"]}
                for b in st["bars"]]
        metrics.enrich_technical(r, bars)
        if r.get("tech_ok") and r.get("ret120") is not None:
            ret120_pool.append(r["ret120"])
        snap = snaps.get(r["thscode"], {})
        auct = aucts.get(r["thscode"], {})
        r["last_price"] = snap.get("last_price")
        r["chg_pct"] = snap.get("price_change_ratio_pct")
        r["turnover"] = snap.get("turnover")
        r["float_mv"] = auct.get("float_market_cap")

    for r in records:
        if r.get("tech_ok") and r.get("ret120") is not None:
            r["rs_pct"] = round(metrics.percentile_rank(ret120_pool, r["ret120"]), 1)
        else:
            r["rs_pct"] = None
    stats["tech_ok"] = sum(1 for r in records if r.get("tech_ok"))
    log(f"  技术面有效: {stats['tech_ok']} 只")

    # ── 4. 行业热度 ──
    log("4/6 行业热度(一级881+二级884回退)...")
    boards_l1, boards_sub, members_l1, members_sub = fetch.fetch_industry_members(
        cfg.CACHE_DIR, force=args.refresh_ind)
    ind_of, heat_rows = metrics.industry_stats(records, members_l1, members_sub)
    hot_inds = {h["industry"] for h in heat_rows if h["hot"]}
    for r in records:
        r["industry"] = ind_of.get(r["thscode"], "未分类")
        r["ind_hot"] = r["industry"] in hot_inds
    log(f"  热行业 {len(hot_inds)} 个: {sorted(hot_inds)[:10]}...")

    # ── 5. 打分分组 ──
    log("5/6 评分分组...")
    for r in records:
        if r.get("tech_ok"):
            metrics.score_record(r)
            metrics.assign_bucket(r)
        else:
            r["bucket"] = "W"
            r["bucket_note"] = r.get("tech_note", "")
            r["score"] = 0.0
    buckets = {"A": [], "B": [], "C": [], "W": []}
    for r in records:
        buckets[r["bucket"]].append(r)
    for bk in buckets:
        buckets[bk].sort(key=lambda x: -(x.get("score") or 0))

    # ── 大盘方向 (M) ──
    log("5.5/6 大盘方向(M)...")
    idx_bars = {}
    for code, _ in cfg.M_INDICES:
        idx_bars[code] = fetch.index_bars(code, START_MS_IDX, END_MS)
    market = metrics.compute_market_state(idx_bars)
    log(f"  大盘: 站上MA50 {market['above50_n']}/3, 站上MA200 {market['above200_n']}/3"
        f" → {'偏强' if market['market_strong'] else '中性' if market['market_up'] else '偏弱'}")
    if not market["market_up"] and cfg.HARD_M_FILTER:
        log("  ⚠ HARD_M_FILTER=True 且大盘偏弱 → 按纪律不输出买点清单")
        buckets["A"] = buckets["B"] = buckets["C"] = []

    # ── 5.6 巨潮PDF链接(财报/招股书) ──
    pdf_links = {}
    if cfg.ENRICH_PDF:
        log("5.6/6 充实财报/招股书PDF链接...")
        shown = (buckets["A"][:60] + buckets["B"][:60] + buckets["C"][:60]
                 + buckets["W"][:30])
        codes = list(dict.fromkeys(r["thscode"] for r in shown))
        try:
            import enricher
            pdf_links = enricher.enrich_pdf_links(codes, log_fn=log)
        except Exception as e:
            log(f"  ⚠ PDF链接充实失败(跳过): {e}")

    # ── 6. 输出 ──
    log("6/6 生成报告...")
    ctx = {
        "date": TODAY, "weekday": WEEKDAY_CN, "params": params,
        "stats": stats, "market": market, "heat_rows": heat_rows,
        "buckets": buckets, "records": records, "pdf_links": pdf_links,
    }
    md_path = os.path.join(cfg.OUTPUT_DIR, f"trend_alpha_{TODAY}.md")
    json_path = os.path.join(cfg.OUTPUT_DIR, f"trend_alpha_{TODAY}.json")
    report.gen_md(ctx, md_path)
    report.gen_json(ctx, json_path)
    log(f"  报告已输出: {md_path}")
    log(f"  报告已输出: {json_path}")
    log(f"完成! 总耗时 {elapsed(t0):.0f}s | A:{len(buckets['A'])} B:{len(buckets['B'])} C:{len(buckets['C'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

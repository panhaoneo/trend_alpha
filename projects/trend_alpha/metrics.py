"""纯计算层: 均线/RS代理/行业热度/综合分/分组 (无IO)"""

import statistics

import config as cfg


def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def ret_over(vals, n):
    """最近n根K线收益率(小数)。需 >n 根。"""
    if len(vals) <= n:
        return None
    base = vals[-1 - n]
    if base <= 0:
        return None
    return vals[-1] / base - 1.0


def percentile_rank(vals, x):
    """x 在 vals 中的百分位 (0-100), vals 为全体样本。"""
    if not vals:
        return 50.0
    below = sum(1 for v in vals if v <= x)
    return below / len(vals) * 100.0


def enrich_technical(rec, bars):
    """把日K计算出的技术指标并入 rec (原地)。rec 须含 thscode。"""
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    vols = [b["vol"] for b in bars]
    n = len(closes)
    rec["n_bars"] = n
    if n < cfg.MIN_BARS or closes[-1] <= 0:
        rec["tech_ok"] = False
        return rec
    rec["tech_ok"] = True
    close = closes[-1]
    rec["close"] = round(close, 2)

    window = min(cfg.HIGH52_LOOKBACK, n)
    yh = max(highs[-window:])
    rec["high_52w"] = round(yh, 2)
    rec["off_high"] = round(close / yh - 1.0, 4) if yh > 0 else None

    mas = {}
    for w in cfg.MA_WINDOWS:
        m = sma(closes, w)
        mas[w] = round(m, 2) if m else None
        rec[f"ma{w}"] = mas[w]
    rec["above_ma150"] = bool(mas[150] and close > mas[150])
    rec["above_ma200"] = bool(mas[200] and close > mas[200])
    ma50, ma150 = mas[50], mas[150]
    rec["uptrend"] = bool(ma50 and ma150 and ma50 > ma150 and close > ma50)

    rec["ret120"] = ret_over(closes, cfg.RS_WINDOW)
    rec["ret250"] = ret_over(closes, 250)

    if n >= cfg.VOL_LONG + cfg.VOL_SHORT:
        short = sum(vols[-cfg.VOL_SHORT:]) / cfg.VOL_SHORT
        long_ = sum(vols[-(cfg.VOL_LONG + cfg.VOL_SHORT):-cfg.VOL_SHORT]) / cfg.VOL_LONG
        rec["vol_surge"] = round(short / long_, 2) if long_ > 0 else None
    else:
        rec["vol_surge"] = None
    return rec


def compute_market_state(idx_bars_map):
    """idx_bars_map: {code: bars}; 返回 {code:{...}, market_up, above50_n, above200_n}"""
    rows = []
    above50 = above200 = 0
    for code, name in cfg.M_INDICES:
        bars = idx_bars_map.get(code, [])
        closes = [b["close"] for b in bars]
        row = {"code": code, "name": name, "close": closes[-1] if closes else None}
        for w in cfg.M_MA:
            m = sma(closes, w)
            key = f"ma{w}"
            row[key] = round(m, 2) if m else None
            row[f"above{w}"] = bool(m and closes[-1] > m)
        if row.get("above50"):
            above50 += 1
        if row.get("above200"):
            above200 += 1
        rows.append(row)
    return {
        "rows": rows,
        "above50_n": above50,
        "above200_n": above200,
        "market_up": above50 >= 2,
        "market_strong": above50 >= 2 and above200 >= 2,
    }


def resolve_industry(tc, members_l1, members_sub):
    """行业归属: 一级(881)优先, 缺失回退二级(884·二级), 均无记未分类。"""
    name = members_l1.get(tc)
    if name:
        return name
    name = members_sub.get(tc)
    return f"{name}·二级" if name else "未分类"


def industry_stats(records, members_l1, members_sub):
    """按行业统计过线家数与平均增速。返回 (ind_of, heat_rows)。"""
    ind_of = {}
    for r in records:
        ind_of[r["thscode"]] = resolve_industry(r["thscode"], members_l1, members_sub)

    groups = {}
    for r in records:
        ind = ind_of.get(r["thscode"], "未分类")
        groups.setdefault(ind, []).append(r)

    rows = []
    for ind, stocks in groups.items():
        gs = [s.get("g_main") for s in stocks if s.get("g_main") is not None]
        rows.append({
            "industry": ind,
            "count": len(stocks),
            "avg_g": round(statistics.mean(gs), 1) if gs else 0.0,
        })
    rows.sort(key=lambda x: (-x["count"], -x["avg_g"]))
    for row in rows:
        row["hot"] = bool(row["industry"] != "未分类"
                          and row["count"] >= cfg.HOT_IND_MIN_COUNT
                          and row["avg_g"] >= cfg.HOT_IND_MIN_AVG)
    return ind_of, rows


def compute_quality(rec):
    """利润质量/现金流匹配指标 (API可得):
    - margin_pp: 毛利率同比变化(百分点)
    - cash_flag: 净现比&现金营运指数 → 优/良/一般/差
    - eps_eff: EPS同比(利润表basic_eps同报告期同比; None=无同期基数/未披露)"""
    gm, gl = rec.get("gross_main"), rec.get("gross_ly")
    if gm is not None and gl is not None:
        rec["margin_pp"] = round(gm - gl, 1)
    else:
        rec["margin_pp"] = None
    content = rec.get("cash_content")
    opidx = rec.get("cash_op_index")
    if content is None:
        rec["cash_flag"] = None
    else:
        if content >= 100 and (opidx is None or opidx >= 0.8):
            rec["cash_flag"] = "优"
        elif content >= 60:
            rec["cash_flag"] = "良"
        elif content >= 30:
            rec["cash_flag"] = "一般"
        else:
            rec["cash_flag"] = "差"
    rec["eps_eff"] = rec.get("eps_main")
    return rec


def score_record(rec):
    """0-100 综合分 (权重见 config W_*)。增速极端值截断并标记。"""
    g = rec.get("g_main") or 0
    if g > cfg.EXTREME_PROFIT:
        rec["extreme"] = True
        g = cfg.EXTREME_PROFIT
    else:
        rec["extreme"] = False
    rev = rec.get("rev_main") or 0
    roe = rec.get("roe_main")
    rs_pct = rec.get("rs_pct", 0) or 0
    off = rec.get("off_high")
    vs = rec.get("vol_surge")

    s_profit = min(max(g / 100.0, 0), 1.0) * cfg.W_PROFIT
    s_rev = min(max(rev / 100.0, 0), 1.0) * cfg.W_REV
    s_roe = 0.0
    if roe is not None and roe > 0:
        s_roe = min(roe / cfg.ROE_TARGET, 1.0) * cfg.W_ROE
    s_rs = min(max(rs_pct, 0), 100) / 100.0 * cfg.W_RS
    s_off = 0.0
    if off is not None:
        s_off = min(max((cfg.BAND_PULLBACK_LO - off) / (-cfg.BAND_PULLBACK_LO), 0), 1.0) * cfg.W_OFF_HIGH
    s_vol = 0.0
    if vs is not None:
        s_vol = min(vs / 2.0, 1.0) * cfg.W_VOL
    s_hot = cfg.W_HOT if rec.get("ind_hot") else 0.0
    rec["score"] = round(s_profit + s_rev + s_roe + s_rs + s_off + s_vol + s_hot, 1)
    rec["score_parts"] = [round(s_profit, 1), round(s_rev, 1), round(s_roe, 1),
                          round(s_rs, 1), round(s_off, 1), round(s_vol, 1),
                          round(s_hot, 1)]
    return rec


def assign_bucket(rec):
    """A 景气核心α / B 一年新高附近 / C 回调观察 / W 待观察。需先 score_record。"""
    if not rec.get("tech_ok"):
        rec["bucket"] = "W"
        rec["bucket_note"] = "K线不足/停牌"
        return rec
    off = rec.get("off_high")
    if off is None:
        rec["bucket"] = "W"
        rec["bucket_note"] = "无有效高点"
        return rec
    off = min(off, 0.0)  # 盘中价高于所记高点时按新高计
    rec["off_high"] = round(off, 4)
    in_strong = cfg.BAND_STRONG <= off <= 0
    if rec.get("ind_hot") and in_strong and rec.get("above_ma150"):
        rec["bucket"] = "A"
    elif cfg.BAND_NEW_HIGH <= off <= 0:
        rec["bucket"] = "B"
    elif cfg.BAND_PULLBACK_LO <= off < cfg.BAND_STRONG and rec.get("above_ma150"):
        rec["bucket"] = "C"
    else:
        rec["bucket"] = "W"
        rec["bucket_note"] = "不满足A/B/C形态条件"
    return rec

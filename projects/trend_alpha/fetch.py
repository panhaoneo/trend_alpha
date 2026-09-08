"""数据抓取层: 指标/日K/指数/行业成分 (带重试与进度)"""

import json
import os
import sys
import time
import concurrent.futures
from datetime import datetime, timedelta

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.ths_api import api_get, safe_items, log  # noqa: E402

PROBE_CODE = "300750.SZ"


def ms_to_date(ms):
    """date_ms → YYYY-MM-DD。兼容两种语义(UTC零点/本地零点)：
    本地转换后若时刻≥16点则视为UTC零点, 日期+1。"""
    dt = datetime.fromtimestamp(ms / 1000.0)
    d = dt.date()
    if dt.hour >= 16:
        d = d + timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _retry_get(endpoint, params, timeout, retries=2):
    for i in range(retries + 1):
        data = api_get(endpoint, params, timeout=timeout)
        if data is not None:
            return data
        if i < retries:
            time.sleep(0.5)
    return None


# ── 探测: 真实指标 id ──

def probe_indicator_ids(reports, dump_dir):
    """抓取样本股多个报告期, dump 原始 indicators, 按子串候选回填 id。"""
    import config as cfg
    os.makedirs(dump_dir, exist_ok=True)
    raw = {}
    for rep in reports:
        data = _retry_get("/api/a-share/financials/indicators",
                          {"thscode": PROBE_CODE, "report": rep}, 20)
        raw[rep] = data
    with open(os.path.join(dump_dir, "probe_dump.json"), "w") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
    log(f"  探测dump已存: {dump_dir}/probe_dump.json")

    seen = {}
    for rep, data in raw.items():
        if not data or data.get("code") != 0:
            continue
        for ab in data.get("data", {}).get("abilities", []):
            for ind in ab.get("indicators", []):
                seen[ind["index_id"]] = seen.get(ind["index_id"], 0) + 1

    found = {}
    for role, candidates in cfg.ROLE_CANDIDATES.items():
        hit = next((c for c in candidates if c in seen), None)
        if not hit:
            hint = {"profit": "net_profit", "rev": "income", "roe": "roe",
                    "gross": "gross", "eps": "eps", "cash_content": "cash_content",
                    "cash_op_index": "operating_index"}[role]
            hit = next((k for k in seen if hint in k), None)
        if hit:
            found[role] = hit
    for role, cid in found.items():
        log(f"  指标id[{role}] = {cid}")
    miss = [r for r in cfg.ROLE_CANDIDATES if r not in found]
    if miss:
        log(f"  ⚠ 未找到指标id: {miss} (该维度按0/代理计)")
    return found


# ── 财务指标 ──

def indicators_map(codes, report, workers=25, log_every=500):
    """codes → {thscode: {index_id: float}}"""
    from tools.ths_api import fetch_indicators

    def one(code):
        return code, fetch_indicators(code, report, timeout=15)

    out = {}
    done = [0]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        fmap = {ex.submit(one, c): c for c in codes}
        for f in concurrent.futures.as_completed(fmap):
            done[0] += 1
            if done[0] % log_every == 0:
                log(f"    财务进度 {done[0]}/{len(codes)} ({report})")
            code, flat = f.result()
            if flat:
                out[code] = flat
    return out


# ── 日K ──

def _fetch_bars_one(thscode, start_ms, end_ms):
    data = _retry_get("/api/a-share/prices/historical",
                      {"thscode": thscode, "interval": "1d",
                       "start": start_ms, "end": end_ms, "adjust": "forward"}, 20)
    bars = []
    for b in safe_items(data):
        ms = b.get("date_ms") or 0
        if not ms:
            continue
        bars.append({"date": ms_to_date(ms),
                     "close": float(b.get("close_price") or 0),
                     "high": float(b.get("high_price") or 0),
                     "low": float(b.get("low_price") or 0),
                     "vol": float(b.get("volume") or 0)})
    bars.sort(key=lambda x: x["date"])
    return bars


def bars_map(codes, start_ms, end_ms, workers=30, log_every=200):
    """codes → {thscode: [bar,...]}"""
    out = {}
    done = [0]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        fmap = {ex.submit(_fetch_bars_one, c, start_ms, end_ms): c for c in codes}
        for f in concurrent.futures.as_completed(fmap):
            done[0] += 1
            if done[0] % log_every == 0:
                log(f"    日K进度 {done[0]}/{len(codes)}")
            code = fmap[f]
            try:
                bars = f.result()
            except Exception:
                bars = []
            if bars:
                out[code] = bars
    return out


def index_bars(thscode, start_ms, end_ms):
    """单指数日K"""
    data = _retry_get("/api/a-share-index/prices/historical",
                      {"thscode": thscode, "interval": "1d",
                       "start": start_ms, "end": end_ms}, 20)
    bars = []
    for b in safe_items(data):
        ms = b.get("date_ms") or 0
        if ms:
            bars.append({"date": ms_to_date(ms),
                         "close": float(b.get("close_price") or 0)})
    bars.sort(key=lambda x: x["date"])
    return bars


# ── 行业成分 ──

def fetch_industry_members(cache_dir, force=False):
    """行业分类数据: 881xxx 一级行业 + 884xxx 二级行业(一级成分缺失时的回退)。
    返回 (boards_l1, boards_sub, members_l1{tc:一级名}, members_sub{tc:二级名})。
    成分股按日缓存。"""
    import config as cfg
    today = datetime.now().strftime("%Y-%m-%d")
    cache_path = os.path.join(cache_dir, f"industry_members_{today}.json")
    if not force and os.path.exists(cache_path):
        with open(cache_path) as f:
            d = json.load(f)
        log(f"  行业成分使用当日缓存: 一级{len(d['members_l1'])}条/二级{len(d['members_sub'])}条")
        return d["boards_l1"], d["boards_sub"], d["members_l1"], d["members_sub"]

    data = _retry_get("/api/a-share-index/catalog/ths-index-list",
                      {"tag": "industry"}, 30)
    boards_l1 = [(i["thscode"], i["name"]) for i in safe_items(data)
                 if i["thscode"].startswith("881")]
    boards_sub = [(i["thscode"], i["name"]) for i in safe_items(data)
                  if i["thscode"].startswith("884")]
    log(f"  一级行业 {len(boards_l1)} 个 + 二级行业 {len(boards_sub)} 个, 拉取成分股...")

    from tools.ths_api import fetch_constituents
    members_l1, members_sub = {}, {}
    done = [0]
    all_boards = [(code, name, "l1") for code, name in boards_l1] + \
                 [(code, name, "sub") for code, name in boards_sub]
    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.FETCH_WORKERS_IND) as ex:
        fmap = {ex.submit(fetch_constituents, code): (code, name, lv)
                for code, name, lv in all_boards}
        for f in concurrent.futures.as_completed(fmap):
            done[0] += 1
            if done[0] % 50 == 0:
                log(f"    行业成分进度 {done[0]}/{len(all_boards)}")
            code, name, lv = fmap[f]
            try:
                mlist = f.result()
            except Exception:
                mlist = []
            bucket = members_l1 if lv == "l1" else members_sub
            for tc, _ in mlist:
                if tc not in bucket:
                    bucket[tc] = name

    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump({"boards_l1": boards_l1, "boards_sub": boards_sub,
                   "members_l1": members_l1, "members_sub": members_sub},
                  f, ensure_ascii=False)
    log(f"  行业成分已缓存: 一级 {len(members_l1)} 条, 二级 {len(members_sub)} 条")
    return boards_l1, boards_sub, members_l1, members_sub

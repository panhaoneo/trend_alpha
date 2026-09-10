"""数据抓取层: 指标/日K/指数/行业成分/重组公告 (带重试与进度)"""

import json
import os
import re
import sys
import time
import requests
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

def _probe_ids_path():
    return os.path.join(_REPO, "data", "probe_ids.json")


def probe_indicator_ids(reports, dump_dir):
    """抓取样本股多个报告期, dump 原始 indicators, 按子串候选回填 id。
    网络/限流失败时回退 data/probe_ids.json 中上次成功的 id(随仓库提交)。"""
    import config as cfg
    os.makedirs(dump_dir, exist_ok=True)
    raw = {}
    for rep in reports:
        data = _retry_get("/api/a-share/financials/indicators",
                          {"thscode": PROBE_CODE, "report": rep}, 15)
        raw[rep] = data
    with open(os.path.join(dump_dir, "probe_dump.json"), "w") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)

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

    if found.get("profit") and found.get("rev"):
        os.makedirs(os.path.dirname(_probe_ids_path()), exist_ok=True)
        with open(_probe_ids_path(), "w") as f:
            json.dump(found, f, ensure_ascii=False, indent=1)
        for role, cid in found.items():
            log(f"  指标id[{role}] = {cid}")
    else:
        cached = {}
        p = _probe_ids_path()
        if os.path.exists(p):
            with open(p) as f:
                cached = json.load(f)
        if cached.get("profit") and cached.get("rev"):
            log("  ⚠ 探测失败(接口限流/异常), 回退 data/probe_ids.json 上次成功指标id")
            found = cached
            for role, cid in found.items():
                log(f"  指标id[{role}] = {cid} (回退)")
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


# ── EPS同比 (利润表 basic_eps, 同报告期对上年同期) ──

def report_to_fp(report):
    """'2026-2' → (2026, 'Q2'); '2025-4' → (2025, 'FY')"""
    y, q = report.split("-")
    return int(y), {"1": "Q1", "2": "Q2", "3": "Q3", "4": "FY"}[q]


def _fetch_eps_series(thscode):
    data = _retry_get("/api/a-share/financials/income-statements",
                      {"thscode": thscode, "period": "quarterly", "limit": 6}, 15)
    series = {}
    for it in safe_items(data):
        series[(it.get("fiscal_year"), it.get("fiscal_period"))] = it.get("basic_eps")
    return series


def eps_yoy_map(codes, report, workers=25, log_every=200):
    """codes → {thscode: EPS同比% 或 None(无同期基数/未披露)}"""
    y, fp = report_to_fp(report)

    def one(tc):
        s = _fetch_eps_series(tc)
        cur, prev = s.get((y, fp)), s.get((y - 1, fp))
        val = None
        try:
            if prev is not None and float(prev) > 0 and cur is not None:
                val = round((float(cur) / float(prev) - 1) * 100, 2)
        except (TypeError, ValueError):
            val = None
        return tc, val

    out = {}
    done = [0]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        fmap = {ex.submit(one, c): c for c in codes}
        for f in concurrent.futures.as_completed(fmap):
            done[0] += 1
            if done[0] % log_every == 0:
                log(f"    EPS进度 {done[0]}/{len(codes)}")
            tc, val = f.result()
            out[tc] = val
    return out


# ── 行业成分 ──

def fetch_industry_members(force=False):
    """行业分类数据: 881xxx 一级 + 884xxx 二级(回退)。跨日缓存 data/industry_members.json,
    有效期 cfg.IND_TTL_DAYS 天(随仓库提交)。返回 (boards_l1, boards_sub, members_l1, members_sub)。"""
    import config as cfg
    cache_path = cfg.IND_CACHE
    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                d = json.load(f)
            saved_on = d.get("saved_on")
            fresh = (datetime.now() - datetime.strptime(saved_on, "%Y-%m-%d")).days <= cfg.IND_TTL_DAYS
            if fresh and d.get("members_l1"):
                log(f"  行业成分缓存有效(保存于 {saved_on}): 一级{len(d['members_l1'])}条/二级{len(d['members_sub'])}条")
                return d["boards_l1"], d["boards_sub"], d["members_l1"], d["members_sub"]
        except Exception:
            pass

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

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump({"saved_on": datetime.now().strftime("%Y-%m-%d"),
                   "boards_l1": boards_l1, "boards_sub": boards_sub,
                   "members_l1": members_l1, "members_sub": members_sub},
                  f, ensure_ascii=False)
    log(f"  行业成分已缓存: 一级 {len(members_l1)} 条, 二级 {len(members_sub)} 条")
    return boards_l1, boards_sub, members_l1, members_sub


# ── 重大资产重组公告 (巨潮全文检索) ──

_CNINFO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "http://www.cninfo.com.cn",
    "Referer": "http://www.cninfo.com.cn/",
}


def fetch_restruct_announcements(days=90, page_cap=25):
    """巨潮全文检索近N天 '重大资产重组' 公告, 按公告时间降序返回。
    每条: {code, name, title, date(YYYY-MM-DD), url(PDF), type}"""
    today = datetime.now()
    se = f"{(today - timedelta(days=days)).strftime('%Y-%m-%d')}~{today.strftime('%Y-%m-%d')}"
    out = []
    for page in range(1, page_cap + 1):
        data = {
            "stock": "", "tabName": "fulltext", "pageSize": "30",
            "pageNum": str(page), "column": "", "category": "", "plate": "",
            "seDate": se, "searchkey": "重大资产重组", "secid": "",
            "sortName": "", "sortType": "", "isHLtitle": "true",
        }
        try:
            resp = requests.post("http://www.cninfo.com.cn/new/hisAnnouncement/query",
                                 data=data, headers=_CNINFO_HEADERS, timeout=20)
            d = resp.json()
        except Exception:
            time.sleep(0.5)
            continue
        anns = d.get("announcements") or []
        if not anns:
            break
        for a in anns:
            title = re.sub(r"<[^>]+>", "", a.get("announcementTitle") or "").strip()
            if "重大资产重组" not in title:
                continue
            ms = a.get("announcementTime") or 0
            date = datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d") if ms else ""
            adj = a.get("adjunctUrl") or ""
            out.append({
                "code": a.get("secCode", ""), "name": a.get("secName", ""),
                "title": title, "date": date,
                "url": f"http://static.cninfo.com.cn/{adj}" if adj else "",
                "type": a.get("announcementTypeName", ""),
            })
        if not d.get("hasMore"):
            break
        time.sleep(0.15)
    out.sort(key=lambda x: (x["date"], x["code"]), reverse=True)
    return out

"""巨潮资讯网 API 客户端 + PDF链接获取"""

import requests
import json
import time
import os

CNINFO_API = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "http://www.cninfo.com.cn",
    "Referer": "http://www.cninfo.com.cn/",
}

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _cache_path():
    return os.path.join(CACHE_DIR, "cninfo_pdf_cache.json")


def load_cache():
    try:
        with open(_cache_path()) as f:
            return json.load(f)
    except:
        return {}


def save_cache(cache):
    with open(_cache_path(), "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def query_cninfo(search_key, page_size=20):
    data = {
        "stock": "", "tabName": "fulltext", "pageSize": str(page_size),
        "pageNum": "1", "column": "", "category": "", "plate": "",
        "seDate": "", "searchkey": search_key, "secid": "",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    try:
        resp = requests.post(CNINFO_API, data=data, headers=HEADERS, timeout=15)
        return resp.json()
    except:
        return {}


def find_latest_report(anns, stock_code):
    for ann in anns:
        if ann.get("secCode") != stock_code:
            continue
        title = ann.get("announcementTitle", "")
        if "摘要" in title or "英文" in title or "补充" in title or "修订" in title:
            continue
        if "年度报告" in title or "半年度报告" in title:
            adjunct = ann.get("adjunctUrl", "")
            if adjunct and adjunct.lower().endswith(".pdf"):
                return f"http://static.cninfo.com.cn/{adjunct}"
    return ""


def find_prospectus(anns, stock_code):
    for ann in anns:
        if ann.get("secCode") != stock_code:
            continue
        title = ann.get("announcementTitle", "")
        if "招股说明书" in title or "招股意向书" in title:
            if "摘要" in title or "补充" in title or "修订" in title or "更新" in title:
                continue
            adjunct = ann.get("adjunctUrl", "")
            if adjunct and adjunct.lower().endswith(".pdf"):
                return f"http://static.cninfo.com.cn/{adjunct}"
    return ""


def get_pdf_links(stock_code, cache):
    if stock_code in cache:
        return cache[stock_code].get("report", ""), cache[stock_code].get("prospectus", "")

    result = query_cninfo(f"{stock_code} 年度报告", 20)
    anns = result.get("announcements") or []
    report_url = find_latest_report(anns, stock_code)

    if not report_url:
        result = query_cninfo(f"{stock_code} 半年度报告", 20)
        anns = result.get("announcements") or []
        report_url = find_latest_report(anns, stock_code)

    time.sleep(0.15)

    result = query_cninfo(f"{stock_code} 招股说明书", 20)
    anns = result.get("announcements") or []
    prospectus_url = find_prospectus(anns, stock_code)

    cache[stock_code] = {"report": report_url, "prospectus": prospectus_url}
    return report_url, prospectus_url


def enrich_codes(codes, cache, log_fn=print, save_every=20):
    missing = [c for c in codes if c not in cache]
    log_fn(f"  巨潮PDF: 需查询 {len(missing)}/{len(codes)}")
    for i, code in enumerate(missing):
        get_pdf_links(code, cache)
        if (i + 1) % save_every == 0:
            log_fn(f"    {i+1}/{len(missing)}")
            save_cache(cache)
        time.sleep(0.1)
    save_cache(cache)
    return cache

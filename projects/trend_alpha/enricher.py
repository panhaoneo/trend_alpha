"""入选标的 财报/招股书 PDF 链接充实（巨潮资讯网）"""

import re
import sys
import os
import time
import requests

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import cninfo_api as cn  # noqa: E402

_FIN_TITLE_RE = re.compile(r"(第[一二三四]季度报告|半年度报告|年度报告)")
_FIN_TITLE_SKIP = ("摘要", "英文", "补充", "修订", "更新", "取消", "已取消", "更正")


def _url_ok(url):
    """空串视为可展示(无PDF); 有URL则必须是指向可下载PDF的200响应。"""
    if not url:
        return True
    if not url.lower().endswith(".pdf"):
        return False
    try:
        r = requests.head(url, timeout=8, allow_redirects=True)
        if r.status_code != 200:
            return False
        ct = r.headers.get("content-type", "").lower()
        if "html" in ct:
            return False
        return True
    except Exception:
        return False


def enrich_pdf_links(thscodes, log_fn=print, concurrency_safe=True):
    """为入选 thscode 列表补充 财报(最新定期报告)/招股书 PDF 链接。
    返回 {thscode: {report, prospectus}}; 结果写入 data/cninfo_pdf_cache.json。
    缓存项若URL已失效则剔除重查(自愈)。"""
    cache = cn.load_cache()
    need = []
    skipped = 0
    for tc in thscodes:
        c = tc.split(".")[0]
        hit = cache.get(c)
        if hit and _url_ok(hit.get("report", "")) and _url_ok(hit.get("prospectus", "")):
            skipped += 1
            continue
        cache.pop(c, None)   # 失效项剔除, 触发重查
        need.append(c)

    log_fn(f"  巨潮PDF: 需展示 {len(thscodes)} 只 | 缓存直接可用 {skipped} | 需查询 {len(need)}")
    for i, c in enumerate(need):
        try:
            cn.get_pdf_links(c, cache)
        except Exception:
            cache.setdefault(c, {"report": "", "prospectus": ""})
        if (i + 1) % 15 == 0:
            log_fn(f"    巨潮查询进度 {i + 1}/{len(need)}")
            cn.save_cache(cache)
        time.sleep(0.1)
    cn.save_cache(cache)

    out = {}
    for tc in thscodes:
        e = cache.get(tc.split(".")[0], {})
        out[tc] = {"report": e.get("report", ""), "prospectus": e.get("prospectus", "")}
    covered = sum(1 for v in out.values() if v["report"] or v["prospectus"])
    log_fn(f"  巨潮PDF完成: {covered}/{len(out)} 只至少有一个可用链接")
    return out


def enrich_latest_fin(codes6, log_fn=print):
    """最新定期报告(季报/中报/年报中最新一期) PDF 链接。
    结果写入 data/cninfo_pdf_cache.json 的 "latest_fin" 字段(增量复用)。"""
    cache = cn.load_cache()
    out, need = {}, []
    for c in codes6:
        e = cache.setdefault(c, {"report": "", "prospectus": ""})
        u = e.get("latest_fin") or ""
        if u.lower().endswith(".pdf"):
            out[c] = u
        else:
            need.append(c)

    log_fn(f"  最新财报: 需展示 {len(codes6)} 只 | 缓存可用 {len(codes6) - len(need)} | 需查询 {len(need)}")
    for i, c in enumerate(need):
        best_ms, best_url = 0, ""
        res = cn.query_cninfo(f"{c} 报告", 30)
        for a in (res.get("announcements") or []):
            if a.get("secCode") != c:
                continue
            t = re.sub(r"<[^>]+>", "", a.get("announcementTitle") or "")
            if any(k in t for k in _FIN_TITLE_SKIP) or not _FIN_TITLE_RE.search(t):
                continue
            adj = a.get("adjunctUrl") or ""
            if not adj.lower().endswith(".pdf"):
                continue
            ms = a.get("announcementTime") or 0
            if ms > best_ms:
                best_ms, best_url = ms, f"http://static.cninfo.com.cn/{adj}"
        cache[c]["latest_fin"] = best_url
        out[c] = best_url
        if (i + 1) % 15 == 0:
            log_fn(f"    最新财报查询进度 {i + 1}/{len(need)}")
            cn.save_cache(cache)
        time.sleep(0.12)
    cn.save_cache(cache)
    covered = sum(1 for v in out.values() if v)
    log_fn(f"  最新财报完成: {covered}/{len(out)} 只已定位")
    return out

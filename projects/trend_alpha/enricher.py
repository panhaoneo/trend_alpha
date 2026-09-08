"""入选标的 财报/招股书 PDF 链接充实（巨潮资讯网）"""

import sys
import os
import time
import requests

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import cninfo_api as cn  # noqa: E402


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

"""同花顺 iFinD REST API 客户端"""

import os
import requests
from datetime import datetime

BASE = "https://fuyao.aicubes.cn"

def _load_api_key():
    key_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "THS_API_KEY")
    if os.path.exists(key_file):
        with open(key_file) as f:
            return f.read().strip()
    return os.environ.get("FUYAO_API_KEY", "")

API_KEY = _load_api_key()
HEADERS = {"X-api-key": API_KEY}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def api_get(endpoint, params=None, timeout=30):
    try:
        r = requests.get(f"{BASE}{endpoint}", params=params, headers=HEADERS, timeout=timeout)
        return r.json()
    except Exception:
        return None


def safe_items(data):
    if data and isinstance(data, dict) and data.get("code") == 0:
        d = data.get("data")
        if isinstance(d, dict):
            return d.get("item") or []
    return []


def fetch_all_stocks():
    stocks, offset = [], 0
    while True:
        data = api_get("/api/meta/tickers/list",
                       {"asset_type": "a-share", "limit": 10000, "offset": offset})
        items = safe_items(data)
        if not items:
            break
        stocks.extend(items)
        offset += len(items)
        if len(items) < 10000:
            break
    return stocks


def fetch_snapshot_batch(thscodes):
    result = {}
    for i in range(0, len(thscodes), 100):
        batch = thscodes[i:i + 100]
        data = api_get("/api/a-share/prices/snapshot", {"thscodes": ",".join(batch)})
        for item in safe_items(data):
            result[item["thscode"]] = item
    return result


def fetch_auction_snapshot_batch(thscodes):
    result = {}
    for i in range(0, len(thscodes), 100):
        batch = thscodes[i:i + 100]
        data = api_get("/api/a-share/auction/snapshot", {"thscodes": ",".join(batch)})
        for item in safe_items(data):
            result[item["thscode"]] = item
    return result


def fetch_growth(thscode, report):
    try:
        data = api_get("/api/a-share/financials/indicators",
                       {"thscode": thscode, "report": report}, timeout=15)
        if not data or data.get("code") != 0:
            return None
        for ab in data["data"].get("abilities", []):
            if ab["ability"] == "growth":
                for ind in ab["indicators"]:
                    if ind["index_id"] == "calculate_parent_holder_net_profit_yoy_growth_ratio":
                        return float(ind["value"])
    except Exception:
        pass
    return None


def fetch_indicators(thscode, report, timeout=15):
    """Fetch all financial indicators for one stock/report period.
    Returns flat {index_id: float} across every ability, or {} on failure."""
    try:
        data = api_get("/api/a-share/financials/indicators",
                       {"thscode": thscode, "report": report}, timeout=timeout)
        if not data or data.get("code") != 0:
            return {}
        out = {}
        for ab in data["data"].get("abilities", []):
            for ind in ab.get("indicators", []):
                v = ind.get("value")
                if v is not None:
                    try:
                        out[ind["index_id"]] = float(v)
                    except (TypeError, ValueError):
                        pass
        return out
    except Exception:
        return {}


def fetch_constituents(thscode):
    data = api_get("/api/a-share-index/constituents/ths-stock-list",
                   {"thscode": thscode}, timeout=20)
    return [(item.get("thscode"), item.get("name", ""))
            for item in safe_items(data) if item.get("thscode")]

"""报告生成: MD + JSON 输出"""

import json
import os
from datetime import datetime

import config as cfg
from tools.formatting import fmt_n, fmt_pct, fmt_price

BUCKET_TITLES = {
    "A": "A. 景气核心α（热行业 × 强势形态 × 站上MA150）",
    "B": "B. 一年新高 / 接近新高（距52周高点≤5%）",
    "C": "C. 回调观察（距高点15%~35%，仍站上MA150）",
}


def _fmt_off(off):
    return "-" if off is None else fmt_pct(off * 100)


def _link_cell(url, label):
    return f"[{label}]({url})" if url else "—"


def _table(records, pdf_links=None):
    head = ("| # | 代码 | 名称 | 行业 | 净利同比 | 营收同比 | ROE | 现价 | 距52周高 | 当日涨跌 | RS%ile | 放量比 | 得分 | 财报 | 招股书 |")
    sep = "|---|------|------|------|----------|----------|-----|------|----------|----------|--------|--------|------|------|--------|"
    lines = [head, sep]
    for i, r in enumerate(records, 1):
        code = r["thscode"]
        name = r["name"]
        ind = r.get("industry", "-")
        g = "-" if r.get("g_main") is None else fmt_pct(r["g_main"])
        rev = "-" if r.get("rev_main") is None else fmt_pct(r["rev_main"])
        roe = "-" if r.get("roe_main") is None else fmt_pct(r["roe_main"])
        price = fmt_price(r.get("close") or r.get("last_price"))
        off = _fmt_off(r.get("off_high"))
        chg = "-" if r.get("chg_pct") is None else fmt_pct(r["chg_pct"])
        rs = "-" if r.get("rs_pct") is None else f"{r['rs_pct']:.0f}"
        vs = "-" if r.get("vol_surge") is None else f"{r['vol_surge']:.1f}"
        score = r.get("score", 0)
        pdf = (pdf_links or {}).get(code, {})
        lines.append(f"| {i} | {code} | {name} | {ind} | {g} | {rev} | {roe} | {price} | {off} | {chg} | {rs} | {vs} | {score} |"
                     f" {_link_cell(pdf.get('report', ''), '财报PDF')} | {_link_cell(pdf.get('prospectus', ''), '招股书PDF')} |")
    return "\n".join(lines)


def gen_md(ctx, path):
    today = ctx["date"]
    p = ctx["params"]
    s = ctx["stats"]
    mkt = ctx["market"]
    heat = ctx["heat_rows"]
    buckets = ctx["buckets"]

    L = []
    L.append(f"# 景气趋势每日选股（静水×CANSLIM 蒸馏框架 v1.0）")
    L.append("")
    L.append(f"- 日期: {today} {ctx['weekday']}")
    L.append(f"- 财务口径: 主筛 {p['report_main']} 净利同比≥{p['p_profit']}% 且 营收同比≥{p['p_rev']}%"
             + (f"，双期确认 {p['report_prev']} 净利≥{p['p_profit_prev']}%" if p['require_prev'] else "")
             + (f"，年报 {p['report_annual']} 净利≥{p['p_annual']}%" if p['require_annual'] else ""))
    L.append(f"- 候选池: 全A − ST − 北交所 − 科创板 | 方法文档: `docs/trend_alpha_framework.md`")
    L.append("")

    # 大盘
    L.append("## 大盘方向 (M)\n")
    L.append("| 指数 | 收盘 | MA50 | MA200 | 站上MA50 | 站上MA200 |")
    L.append("|------|------|------|-------|----------|-----------|")
    for row in mkt["rows"]:
        L.append(f"| {row['name']} | {fmt_price(row['close'])} | {fmt_price(row.get('ma50'))} | {fmt_price(row.get('ma200'))} | {'✓' if row.get('above50') else '✗'} | {'✓' if row.get('above200') else '✗'} |")
    L.append("")
    if mkt["market_strong"]:
        L.append(f"**大盘状态: 偏强**（{mkt['above50_n']}/3 站上MA50，{mkt['above200_n']}/3 站上MA200）→ 趋势投资可参与")
    elif mkt["market_up"]:
        L.append(f"**大盘状态: 中性偏多**（{mkt['above50_n']}/3 站上MA50）→ 精选个股")
    else:
        L.append(f"**大盘状态: 偏弱**（仅 {mkt['above50_n']}/3 站上MA50）→ 静水法则: 熊市等待, 谨慎/空仓")
    L.append("")

    # 家数统计
    L.append(f"## 统计\n")
    if p["require_prev"] or p["require_annual"]:
        L.append(f"- 候选池 {s['universe']} 只 → 主报告期双达标 {s['fin_base']} 只"
                 f" → 全部财务门槛后 {s['fin_pass']} 只 → 技术面有效 {s['tech_ok']} 只")
    else:
        L.append(f"- 候选池 {s['universe']} 只 → 财务双达标 {s['fin_pass']} 只 → 技术面有效 {s['tech_ok']} 只")
    L.append(f"- 分组: A 核心α {len(buckets['A'])} | B 新高附近 {len(buckets['B'])} | C 回调观察 {len(buckets['C'])} | 待观察 {len(buckets['W'])}")
    L.append(f"- PDF链接: 财报=最新定期报告, 招股书=上市招股文件（来源: 巨潮资讯; — 表示暂无可用PDF）")
    L.append("")

    # 行业热度
    hot_rows = [h for h in heat if h["hot"]]
    L.append("## 行业热度榜（板块效应）\n")
    L.append("> 热行业定义: 财务双达标家数≥5 且 行业平均净利同比≥40%（批量超预期=景气验证）\n")
    L.append("| 行业 | 达标家数 | 平均净利同比 | 热度 |")
    L.append("|------|----------|--------------|------|")
    for h in heat[:cfg.TOP_HOT_DISPLAY]:
        L.append(f"| {h['industry']} | {h['count']} | {fmt_pct(h['avg_g'])} | {'🔥热' if h['hot'] else ''} |")
    L.append("")

    # 各分组清单
    pdf_links = ctx.get("pdf_links", {})
    for bk in ("A", "B", "C"):
        recs = buckets[bk]
        L.append(f"## {BUCKET_TITLES[bk]}（{len(recs)} 只）\n")
        if recs:
            L.append(_table(recs[:60], pdf_links))
            if len(recs) > 60:
                L.append(f"\n*(仅显示前60只, 完整见 json)*")
        else:
            L.append("*暂无*\n")
        L.append("")

    if buckets["W"]:
        L.append("## 待观察（无分组）\n")
        L.append("> 以下标的财务双达标但技术形态不满足（次新/停牌/跌破MA150/远离新高），仍具基本面跟踪价值：\n")
        L.append(_table(buckets["W"][:30], pdf_links))
        L.append("")

    L.append("---")
    L.append("## 人工核验清单（API不可量化, 买入前逐项确认）\n")
    L.append("1. 财报/公告关键词: 供不应求 / 订单饱满 / 量价齐升 / 产品涨价 / 新产品·新市场放量")
    L.append("2. 毛利率与经营现金流是否与利润增速匹配（利润质量）")
    L.append("3. 行业景气是否仍在向上（产业趋势未转向）")
    L.append("4. 管理层增持、机构调研纪要积极、优质机构新进")
    L.append("5. 商业模式: 垄断性 / 定价权 / 持续性（长期持有前提）\n")
    L.append("---")
    L.append(f"*评分权重(0-100): 净利{cfg.W_PROFIT:.0f}+营收{cfg.W_REV:.0f}+ROE{cfg.W_ROE:.0f}+RS{cfg.W_RS:.0f}+距新高{cfg.W_OFF_HIGH:.0f}+放量{cfg.W_VOL:.0f}+热行业{cfg.W_HOT:.0f}"
             f" | RS代理=池内{cfg.RS_WINDOW}日收益百分位 | 前复权K线 | 净利润为归母口径(真实id见 cache/probe_dump.json) | 本报告为自动化辅助, 非投资建议*")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def gen_json(ctx, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "date": ctx["date"],
        "params": ctx["params"],
        "market": ctx["market"],
        "industry_heat": ctx["heat_rows"],
        "records": ctx["records"],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return path

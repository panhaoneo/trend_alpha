#!/usr/bin/env python3
"""将 output/trend_alpha/*.md 渲染为 GitHub Pages 静态站点 (docs/)。
每日报告 → docs/YYYY-MM-DD.html; docs/index.html 为全部历史索引。
纯标准库, 无第三方依赖。"""

import glob
import html
import os
import re

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_DIR = os.path.join(_REPO, "output", "trend_alpha")
OUT_DIR = os.path.join(_REPO, "docs")

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#0d1117;color:#c9d1d9;padding:24px;line-height:1.6}
.wrap{max-width:1280px;margin:0 auto}
h1{color:#58a6ff;font-size:1.5em;margin:18px 0 8px;border-bottom:1px solid #21262d;padding-bottom:10px}
h1:first-child{margin-top:0}
h2{color:#58a6ff;font-size:1.2em;margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid #21262d}
h3{color:#79c0ff;font-size:1.05em;margin:18px 0 8px}
a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}
table{border-collapse:collapse;width:100%;margin:10px 0 18px;font-size:.82em}
th,td{border:1px solid #30363d;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#161b22;color:#8b949e;font-weight:600;white-space:nowrap}
tr:nth-child(even){background:#161b22}
tr:hover{background:#1c2128}
code{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:1px 5px;font-size:.9em}
blockquote{border-left:4px solid #30363d;color:#8b949e;padding:4px 14px;margin:10px 0;font-size:.88em}
hr{border:none;border-top:1px solid #30363d;margin:22px 0}
ul,ol{padding-left:26px;margin:8px 0}
li{margin:3px 0}
p{margin:8px 0}
.empty{color:#8b949e;text-align:center}
.sub{color:#8b949e;font-size:.85em;margin:6px 0 14px}
.nav{margin-bottom:18px;font-size:.9em}
.up{color:#3fb950}.down{color:#f85149}
"""

INLINE_RE = re.compile(
    r"\[([^\]]+)\]\((https?://[^)]+)\)"   # markdown 链接
    r"|\*\*(.+?)\*\*"                      # 粗体
    r"|`([^`]+)`")                         # 行内代码


def inline(text):
    out, pos = [], 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            out.append(html.escape(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append(f'<a href="{html.escape(m.group(2))}">{html.escape(m.group(1))}</a>')
        elif m.group(3) is not None:
            out.append(f"<b>{html.escape(m.group(3))}</b>")
        else:
            out.append(f"<code>{html.escape(m.group(4))}</code>")
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def is_sep_row(cells):
    return all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells if c.strip())


def md_to_body(md_text):
    body, lines = [], md_text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("|") and "|" in s[1:]:
            table = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                table.append(cells)
                i += 1
            rows = []
            for k, cells in enumerate(table):
                if is_sep_row(cells):
                    continue
                tag = "th" if k == 0 else "td"
                rows.append("<tr>" + "".join(
                    f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
            body.append('<div style="overflow-x:auto"><table>' + "".join(rows) + "</table></div>")
            continue
        if s.startswith("###"):
            body.append(f"<h3>{inline(s[3:].strip())}</h3>")
        elif s.startswith("##"):
            body.append(f"<h2>{inline(s[2:].strip())}</h2>")
        elif s.startswith("#"):
            body.append(f"<h1>{inline(s[1:].strip())}</h1>")
        elif s == "---":
            body.append("<hr>")
        elif s.startswith(">"):
            body.append(f"<blockquote>{inline(s[1:].strip())}</blockquote>")
        elif s.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(f"<li>{inline(lines[i].strip()[2:])}</li>")
                i += 1
            body.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif re.match(r"^\d+\. ", s):
            items = []
            while i < n and re.match(r"^\d+\. ", lines[i].strip()):
                it = re.sub(r"^\d+\. ", "", lines[i].strip())
                items.append(f"<li>{inline(it)}</li>")
                i += 1
            body.append("<ol>" + "".join(items) + "</ol>")
            continue
        else:
            body.append(f"<p>{inline(s)}</p>")
        i += 1
    return "\n".join(body)


def page(title, content, extra=""):
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style></head>
<body><div class="wrap">
{content}
</div></body></html>"""


def build():
    os.makedirs(OUT_DIR, exist_ok=True)
    mds = sorted(glob.glob(os.path.join(MD_DIR, "trend_alpha_*.md")), reverse=True)
    entries = []
    for md_path in mds:
        stem = os.path.splitext(os.path.basename(md_path))[0]  # trend_alpha_2026-09-08
        day = stem.replace("trend_alpha_", "")
        with open(md_path, encoding="utf-8") as f:
            text = f.read()
        title_m = re.search(r"^# (.+)$", text, re.M)
        title = title_m.group(1).strip() if title_m else f"每日选股 {day}"
        body = md_to_body(text)
        with open(os.path.join(OUT_DIR, f"{day}.html"), "w", encoding="utf-8") as f:
            f.write(page(title, body))
        entries.append((day, title))
        print(f"  → docs/{day}.html ({title})")

    rows = "".join(
        f'<tr><td><a href="{day}.html">{day}</a></td><td>{html.escape(title)}</td></tr>'
        for day, title in entries)
    index = page(
        "景气趋势每日选股 · 报告存档",
        f'<h1>景气趋势每日选股（静水×CANSLIM 蒸馏框架）</h1>'
        f'<p class="sub">方法文档见仓库 <a href="https://github.com/panhaoneo/trend_alpha/blob/main/docs/trend_alpha_framework.md">docs/trend_alpha_framework.md</a> · 自动化辅助, 非投资建议</p>'
        f'<table><tr><th>日期</th><th>标题</th></tr>{rows}</table>')
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)
    with open(os.path.join(OUT_DIR, ".nojekyll"), "w") as f:
        f.write("")
    print(f"站点完成: {len(entries)} 页 → {OUT_DIR}/")


if __name__ == "__main__":
    build()

"""数据格式化工具"""


def fmt_n(n, d=2):
    if n is None or n == "-":
        return "-"
    if abs(n) >= 1e8:
        return f"{n/1e8:,.{d}f}亿"
    if abs(n) >= 1e4:
        return f"{n/1e4:,.{d}f}万"
    return f"{n:,.{d}f}"


def fmt_pct(n):
    if n is None or n == "-":
        return "-"
    return f"{'+' if n > 0 else ''}{n:.2f}%"


def fmt_price(n):
    return f"{n:,.2f}" if n is not None and n != "-" else "-"


def fmt_mv(mv):
    if not mv:
        return "-"
    return f"{mv/1e8:,.1f}"


def color_cls(n):
    return "up" if n and n > 0 else "down" if n and n < 0 else ""

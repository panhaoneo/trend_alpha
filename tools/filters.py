"""股票过滤工具"""


def is_st(name):
    return "ST" in name.upper()


def is_bse(thscode):
    return thscode.endswith(".BJ")


def is_star(thscode):
    return thscode.startswith("688")


def filter_candidates(stocks, exclude_st=True, exclude_bse=True, exclude_star=True):
    excluded = {"st": 0, "bse": 0, "star": 0}
    result = []
    for s in stocks:
        tc, name = s["thscode"], s["name"]
        if exclude_st and is_st(name):
            excluded["st"] += 1
            continue
        if exclude_bse and is_bse(tc):
            excluded["bse"] += 1
            continue
        if exclude_star and is_star(tc):
            excluded["star"] += 1
            continue
        result.append(s)
    return result, excluded

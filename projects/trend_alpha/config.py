"""景气趋势选股配置 — 所有参数集中于此（对应 docs/trend_alpha_framework.md v1.0）"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PROJECT_DIR, "cache")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "trend_alpha")

# ── 报告期 ──
REPORT_MAIN = "2026-2"       # 主筛: 2026中报
REPORT_PREV = "2026-1"       # 双期确认: 2026一季报
REPORT_ANNUAL = "2025-4"     # 年度验证(可选): 2025年报
REPORT_CMP = "2025-2"        # 同期对比(毛利率同比Δ): 2025中报

# ── 财务硬门槛 (sales/net income/EPS 三率体系) ──
P_SALES_MAIN = 30.0     # 主报告期 营收同比(%)       [C: 营收≥25~30, 用户要求≥30]
P_PROFIT_MAIN = 40.0    # 主报告期 归母净利同比(%)   [静水≥40 / C:18-25+]
P_EPS_MAIN = 30.0       # 主报告期 EPS同比(%)        [C: 每股收益≥18-25+, 用户要求≥30]
P_PROFIT_PREV = 40.0    # 前一报告期 净利同比(%)     [双期确认]
P_ANNUAL = 25.0         # 年度净利同比(%)            [A 要素, REQUIRE_ANNUAL 时启用]
P_ROE = 15.0            # ROE 质量线(%)              [A 要素: 17; 默认仅计分]
REQUIRE_PREV = True
REQUIRE_ANNUAL = False
REQUIRE_ROE = False
REQUIRE_EPS = True      # EPS同比≥P_EPS_MAIN (API暂无EPS字段时以归母净利同比为代理)

# ── 排除规则 ──
EXCLUDE_ST = True
EXCLUDE_BSE = True
EXCLUDE_STAR = True

# ── 指标 id 角色探测候选子串（探测后按此顺序在真实响应中匹配，运行时回填 IDS）──
ROLE_CANDIDATES = {
    "profit": ["calculate_parent_holder_net_profit_yoy_growth_ratio",
               "net_profit_yoy_growth_ratio",
               "parent_holder_net_profit_yoy_growth_ratio"],
    "rev": ["operating_income_yoy_growth_ratio",
            "calculate_operating_revenue_yoy_growth_ratio",
            "revenue_yoy_growth_ratio"],
    "roe": ["index_weighted_avg_roe", "weight_avg_roe"],
    "gross": ["sale_gross_margin"],
    "eps": ["eps_yoy_growth_ratio", "basic_eps_yoy_growth_ratio",
            "calculate_eps_yoy_growth_ratio", "earnings_per_share_yoy_growth_ratio"],
    "cash_content": ["net_profit_cash_content"],
    "cash_op_index": ["cash_operating_index"],
}
IDS = {"profit": None, "rev": None, "roe": None, "gross": None,
       "eps": None, "cash_content": None, "cash_op_index": None}

# ── 技术面参数 ──
TECH_DAYS = 400            # 抓取日K窗口(自然日)
MIN_BARS = 120             # 最少K线数(不足视为次新, 不参与分组)
HIGH52_LOOKBACK = 252      # "一年新高"回溯K线数
MA_WINDOWS = (50, 150, 200)
VOL_SHORT, VOL_LONG = 5, 60   # 放量比窗口
RS_WINDOW = 120            # RS代理收益窗口(K线数)
BAND_NEW_HIGH = -0.05      # B: 距52周高点≤5%
BAND_STRONG = -0.15        # A: 距高点≤15%
BAND_PULLBACK_LO = -0.35   # C: 回调15%~35%
FLOAT_MV_MIN = 30e8        # 计分用流通市值下限(元)
TURNOVER_MIN = 3000e4      # 计分用成交额下限(元)

# ── 大盘方向 (M) ──
M_INDICES = [("000001.SH", "上证指数"), ("000300.SH", "沪深300"), ("399006.SZ", "创业板指")]
M_MA = (50, 200)
HARD_M_FILTER = False      # True 时大盘弱市直接终止输出

# ── 行业热度 ──
HOT_IND_MIN_COUNT = 5      # 热行业: 过线家数≥5
HOT_IND_MIN_AVG = 40.0     # 且行业平均净利增速≥40%
TOP_HOT_DISPLAY = 15       # 热度榜展示数量

# ── 重大资产重组观察组 (CANSLIM N属性: 新业务/新管理层/重组) ──
RESTRUCT_ENABLE = True
RESTRUCT_DAYS = 90         # 公告回溯窗口(天)
RESTRUCT_PAGE_CAP = 25     # 巨潮检索分页上限(每页30条)
RESTRUCT_MAX = 80          # 展示上限(按公告时间降序)
RESTRUCT_APPLY_EXCLUDES = True   # 应用 ST/北交所/科创板 排除(与其他清单一致)

# ── 综合评分权重(0-100) ──
W_PROFIT = 25.0    # 主报告期净利同比
W_REV = 15.0       # 主报告期营收同比
W_ROE = 10.0       # ROE(按17%封顶)
W_RS = 20.0        # RS百分位
W_OFF_HIGH = 15.0  # 距52周高点(越近越高)
W_VOL = 5.0        # 放量比
W_HOT = 10.0       # 属热行业
EXTREME_PROFIT = 1000.0  # 增速超过此值截断并标记 extreme
ROE_TARGET = 17.0

# ── 缓存策略(API配额友好) ──
DATA_DIR = os.path.join(BASE_DIR, "data")
FIN_CACHE = os.path.join(DATA_DIR, f"fin_{REPORT_MAIN}.json")   # 财务快照(跨日复用, 随仓库提交)
FIN_TTL_DAYS = 7           # 财务缓存有效期(天); 财报季可调为1或使用 --refresh-fin
IND_CACHE = os.path.join(DATA_DIR, "industry_members.json")     # 行业成分(跨日复用)
IND_TTL_DAYS = 7

# ── 其他 ──
ENRICH_PDF = True        # 为入选标的补充巨潮 财报/招股书 PDF 链接(便于投研)
FETCH_WORKERS_FIN = 25
FETCH_WORKERS_BARS = 30
FETCH_WORKERS_IND = 15
API_TIMEOUT = 20
RETRY_TIMES = 2

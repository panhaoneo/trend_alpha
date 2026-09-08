# 景气趋势每日选股（trend_alpha）

A股「景气趋势」每日自动选股器 —— 方法学蒸馏自 **知乎静水2008 投资问答** × **欧奈尔《笑傲股市》CANSLIM**，
数据来自同花顺 hithink 金融 API（fuyao 代理）。每个交易日自动运行，并把报告发布到 GitHub Pages。

## 方法学一句话

> 盯住当下景气度最高行业中业绩集体超预期、股价创一年新高的核心受益公司（核心α），
> 财报期用「利润+营收双高增」过滤全市场，只留强者；入场等回调分仓，错了止损，对了持盈。

完整框架（规则 → 量化字段 → 人工核验清单）见 [docs/trend_alpha_framework.md](docs/trend_alpha_framework.md)。

## 每日报告

GitHub Actions 每个交易日 **16:30（北京时间，收盘后）** 自动运行：

1. 全 A 财务筛选（**三率门槛**）：主报告期营收(销售)同比≥30% 且 归母净利同比≥40% 且 EPS同比≥30%（API暂无EPS字段，以归母净利代理），前一报告期净利≥40% 双期确认（排除 ST/北交所/科创板）
2. 质量指标量化：毛利率同比Δ、净现比(经营现金流/净利)、现金质量评级（优/良/一般/差）
3. 技术面：距 52 周高点、MA50/150/200、RS 代理（120日池内百分位）、放量比
4. 行业热度：同花顺一级行业(881xxx)+二级(884xxx)回退补全，「未分类」不计热行业
5. 大盘方向（M）：上证/沪深300/创业板指 vs MA50/MA200
6. 输出分层清单：**A 景气核心α / B 接近一年新高 / C 回调观察 / 待观察**
7. 每只入选标的附 **财报 PDF + 招股书 PDF** 链接（巨潮资讯网，便于投研）

- 报告 Markdown/JSON：`output/trend_alpha/trend_alpha_YYYY-MM-DD.md/.json`
- 网页浏览（GitHub Pages）：`https://panhaoneo.github.io/trend_alpha/`
- JSON 内含全量结构化记录（292+ 只），MD 为人类可读版本

## 本地运行

```bash
pip install requests          # 仅依赖 requests
# 环境变量提供 API Key（或放 data/THS_API_KEY）
export FUYAO_API_KEY=sk-...
python3 projects/trend_alpha/run.py            # 每日运行（缓存优先）
python3 projects/trend_alpha/run.py --refresh-fin   # 强制重拉财务（新报告期）
python3 projects/trend_alpha/run.py --sample 60     # 冒烟测试
python3 scripts/build_site.py                  # 渲染 docs/ 静态站点
```

当日重跑依赖缓存（财务/行业成分/技术K线），通常 <1 分钟；换交易日全量约 6-8 分钟。
指标真实 id 每次运行自动探测并 dump 至 `projects/trend_alpha/cache/probe_dump.json`。

## 目录结构

```
tools/                    # 共享 API 客户端(同花顺/巨潮)
projects/trend_alpha/     # 选股器(config/fetch/metrics/enricher/report/run)
docs/trend_alpha_framework.md  # 框架蒸馏文档
data/cninfo_pdf_cache.json     # 巨潮 PDF 链接缓存(每日增量自愈)
scripts/build_site.py     # md → GitHub Pages 静态站渲染器
.github/workflows/daily.yml    # 每日 16:30 定时任务
output/trend_alpha/       # 每日报告(自动提交)
```

## 重要口径与局限

- 净利为归母净利润同比（同花顺指标）；EPS同比: API 无每股收益增速字段, 以归母净利同比为代理（已预留 eps id 自动探测, 接入真实EPS后自动生效）；ROE 默认仅计分不做硬门槛（可配）
- 净现比/现金质量为利润质量提示, 不参与综合分
- RS 无官方源：以「候选池内 120 日收益百分位」近似
- 机构持仓（CANSLIM I 要素）无数据接口：以流通市值/成交额近似，其余见人工核验清单
- 前复权日K口径；中报披露季(7-8月)数据逐日补齐，早期家数偏少属正常
- 「新产品/供不应求/量价齐升/管理层增持/调研纪要」无法纯量化 → 报告附人工核验清单

## 免责声明

本仓库为投资方法论蒸馏与自动化选股辅助工具，报告不构成任何投资建议；
买卖决策、仓位管理与风险控制由使用者自行负责。

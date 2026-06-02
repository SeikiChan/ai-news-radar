# AI News Radar — 变更日志 & 工程交接说明

> 本文件给**其他对话 / AI agent / 接手工程师**快速理解这个项目当前状态用。
> 既是 changelog，也是一份精简的架构交接。读完这一篇就能上手。
> 最近更新：2026-05-31。

---

## 0. 这是什么（30 秒版）

一个**本地运行、零付费订阅**的美股研究雷达。用免费公开信息（press wire、SEC EDGAR、公司 IR、技术博客/论文、宏观数据）自动发现"从故事变成硬证据"的早期机会，并对每个标的做多维尽调（价量确认 / SEC 财务 / 财务体检 / 空头轧空 / 13F 机构流向 / 财报全文拆解 / 反向 13F 持仓）。

定位：**分析师的晨间分流台 + 选题/尽调加速器**，不是自动下单、不出投资结论。

---

## 1. 关键事实（给 agent 的速查）

- **语言/运行时**：Python ≥ 3.10。运行时只依赖 `tzdata`（zoneinfo 在 Windows 需要）和 `pypdf`（PDF 全文解析）。其余全部标准库。开发期另需 `pytest`、`ruff`（`pip install -e ".[dev]"`）。
- **包布局**：源码在 `src/abnormal_news_radar/`，经 `src` 包导入（如 `from src.abnormal_news_radar.x import y`）。测试在 `tests/`。
- **跑测试 / lint**（务必在改动后跑）：
  ```
  .venv/Scripts/python.exe -m pytest        # 当前 156 passed
  .venv/Scripts/ruff.exe check src tests    # 必须 clean
  node --check src/abnormal_news_radar/web_static/app.js  # 前端语法
  ```
- **启动终端**：双击 `AI News Radar.cmd`（会先杀掉已有实例再起，避免多开污染），或
  `python -m src.abnormal_news_radar web --port 8765`，浏览器开 `http://127.0.0.1:8765`。
- **CLI**：`scan`（扫描打印信号）、`web`（终端）、`report`（信号→前瞻收益回测）、`daily`（机构级一页纸 Markdown）。
- **数据是运行时缓存**：`data/*.jsonl`、`data/market_regime.json` 是产物，不是源（`.jsonl` 已 gitignore）。

### ⚠️ 给 agent 的关键运维提醒
1. **改了代码必须重启 web 服务器才生效**——运行中的进程加载的是启动时的代码，不会热加载。静态文件（app.js/css/html）浏览器刷新即可，但**新增/修改 Python 端点必须重启**。
2. **不要多开服务器**——多个进程会同时写 `data/*.jsonl` 互相污染。`.cmd` 已内置"先杀后起"。
3. **联网富化会被限流**：Yahoo（crumb 接口）、SEC、arXiv、Nasdaq 都可能 429/超时。所有联网模块都**优雅降级**（标 `unavailable`，不伪造、不中断扫描）。验证时遇到限流是正常的。
4. **诚实优先**：本项目反复贯彻"宁可显示‘数据不可用’也不伪造"。新增功能请保持这个纪律。

---

## 2. 架构与数据流

```
公开源采集(feeds, 并发+重试+1年时效过滤)
  → 硬证据分层打分(scoring: tier1硬证据/tier2实质/tier3主题 + 置信度)
  → 发现候选公司(discovery, 含 watchlist 之外的反推)
  → 多维富化(每个候选)：
       ticker_resolver → price_volume(价量确认) → impact(一阶影响)
       → financials(SEC companyfacts: 营收/毛利/TTM/现金/现金流/资金投向)
       → quality(财务体检: 营收弹性/毛利趋势/生存跑道 → 否决归零股)
       → short_interest(空头轧空, Yahoo) → institutional_flow(13F派生流向, Yahoo)
       → quick_model → earnings_analysis → technology_intel → pdf_intel(PDF全文)
       → readthrough → options_flow/options_chain → expectations
  → 合成(analyst.build_daily_brief: 姿态/TOP CALL/机会队列/动态观察池/数据缺口)
  → 反馈(performance: 信号→前瞻收益回测，校准阈值)
  按需(UI 点击)：filing_teardown(财报全文拆解) / reverse_13f(谁在持有)
```

阈值集中处：`scoring.py`（`HARD_BAND=35/WATCH_BAND=20/WEAK_BAND=10/DISCOVERY_MIN_RAW=16`）、`timeliness.MAX_FRESH_DAYS=365`、`quality.py`（弹性/跑道阈值）、`short_interest.py`（轧空阈值）。

---

## 3. 模块地图（src/abnormal_news_radar/）

| 模块 | 职责 |
|---|---|
| `net.py` | 共享 HTTP：统一 User-Agent、URL 日期模板(`{yyyy}`等)、重试退避、`max_bytes` 上限、`configure_logging` |
| `feeds.py` | 并发采集 RSS/Atom/HTML，源健康，**1 年时效硬过滤**（`is_within_max_age`）|
| `timeliness.py` | 发布时间解析、新鲜度评分、`MAX_FRESH_DAYS` 时效判定 |
| `scoring.py` | 证据分层打分、置信度、量化经济识别、**保守公司匹配**（短 ticker 防误配）|
| `discovery.py` | 从硬证据文章反推候选公司 |
| `model.py` | 数据类（Article/Signal/Candidate/Source…）|
| `ticker_resolver.py` | 发现型公司名 → ticker（SEC）|
| `price_volume.py` | Yahoo 价量确认 |
| `impact.py` | 新闻一阶财务影响初判 + 金额抽取 |
| `financials.py` | SEC companyfacts：营收/毛利/TTM/现金/经营现金流/**资金投向**；`fetch_recent_filings`(10-Q/10-K/8-K 直链, 1年内)；`load_default_cik_map` |
| `quality.py` | **财务体检/防诈骗**：营收弹性、毛利趋势、生存跑道 → `[高风险归零股]`一票否决等 |
| `short_interest.py` | **空头轧空**：Yahoo `shortPercentOfFloat`，硬证据≥35 且空头>15% → 爆破警报 |
| `institutional_flow.py` | **13F 派生机构流向**（Yahoo）：机构持股%/家数/增减仓 → 吸筹/派发 |
| `reverse_13f.py` | **真·EDGAR 反向 13F**：efts 全文搜索 + 20 家精选知名机构 → 解析信息表拿精确持股 |
| `filing_teardown.py` | **财报全文拆解**：下载 10-Q/10-K HTML → 资金去向(用途分类)/关联公司(→ticker)/客户集中度 |
| `pdf_intel.py` | **PDF 全文**（pypdf）：下载 arXiv/.pdf → 抽正文 → 重打分找标题外硬证据 |
| `earnings_analysis.py` | 财报 release 原文解析（指标/资金投向/点名公司）|
| `earnings_calendar.py` | Nasdaq 财报日历；`collect_earnings_month`(按月，供日历视图)|
| `technology_intel.py` | 技术博客/论文路线图 + 供应链 read-through |
| `readthrough.py` | 二阶受益公司 |
| `options_flow.py` / `options_chain.py` | 期权流证据（未接数据源时不伪造）|
| `expectations.py` | 预期差 / price-in 判断 |
| `market.py` | 宏观 regime（利率/VIX/SPY/QQQ/美元/CPI/PPI/失业率 + 政策事件）→ risk-on/off |
| `analyst.py` | 合成每日 brief（含各因子的否决/信念联动）|
| `performance.py` | **信号→前瞻收益回测**（+1/+5/+20 交易日对 SPY 超额，按分档校准）|
| `daily_report.py` | 机构级一页纸 Markdown 日报 |
| `web.py` | 本地 HTTP 终端 + 调度器 + 全部 API 端点 |
| `storage.py` | JSONL 持久化 + review 状态 |
| `yahoo.py` | 共享 Yahoo cookie+crumb 握手（short_interest 与 institutional_flow 共用）|

前端：`web_static/{index.html, app.css, app.js}`（现代研究终端：状态条 + TOP CALL + 红绿灯密集表格 + 详情抽屉 + 财报月历）。

---

## 4. HTTP 端点（web.py）

| 端点 | 用途 |
|---|---|
| `GET /api/signals?limit=` | 存量信号+候选+last_scan |
| `GET /api/sources` | 配置的源/市场源/种子名单 |
| `GET /api/brief` | 合成每日 brief（驱动简报驾驶舱）|
| `GET /api/daily_report` | 机构级一页纸 Markdown |
| `GET /api/earnings?month=YYYY-MM` | 某月观察标的财报（日历网格，按月缓存）|
| `GET /api/financials?ticker=` | SEC 财务快照 + 近 1 年文件 + 财报全文拆解（缓存 6h）|
| `GET /api/holders?ticker=` | **反向 13F**：谁持有该标的（缓存 24h，较慢）|
| `POST /api/scan` | 触发一次扫描 |
| `POST /api/review_status` | 标记候选 reviewed/dismissed/promoted |

---

## 5. 变更历史（按主题，最新在前）

> 注：仓库以 `V0.1…V0.8` 递增提交。以下按**功能主题**归纳本轮大修内容（跨多个 commit）。

### 数据时效与正确性
- **1 年时效硬过滤**：`feeds.fetch_feed` 丢弃发布超 365 天的文章（无日期保留）；SEC 文件、反向 13F、财报新闻映射同样按 1 年过滤。超期消息（过气炒作/已落地技术）不再展示。`timeliness.MAX_FRESH_DAYS`。
- **修复短 ticker 误配**：`scoring._match_companies` 重写——英文词型 ticker（ON/CAT/ARM）需 ticker 上下文；英文词开头的公司名（"On Semiconductor"）需首词大写，避免地区"Taiwan"误配 TSM、"on"误配 onsemi。
- **修复 Treasury 写死日期**：收益率曲线 URL 改用 `{yyyy}` 动态模板。
- **修复 TTM 取值 bug**：`financials._quarterly_series` 选**最新数据的 XBRL 概念**（公司换标签导致取到陈旧数据，NVDA TTM $10.9B→$229.4B）。

### 量化因子（富化层）
- **财务体检 `quality.py`**：营收弹性（订单/TTM营收）、毛利趋势、生存跑道（现金/烧钱）→ `[高风险归零股]`一票否决、`[流血中标]`、`[基数惊天逆转]`；联动 analyst 降级动作 + 清零观察池信念。
- **空头轧空 `short_interest.py`**：Yahoo shortPercentOfFloat；硬证据≥35 且空头>15% → 红色爆破警报；被体检否决时抑制。
- **13F 派生机构流向 `institutional_flow.py`**：Yahoo 机构持股 → 吸筹/派发，联动信念分。
- **真·EDGAR 反向 13F `reverse_13f.py`**：efts 全文搜索 + 20 家精选知名机构（CIK 已核验）→ 解析信息表 XML 拿精确持股（机构名+股数+市值+申报日），知名机构置顶⭐。

### 财报工作台
- **主动拉 SEC 实际财务**：选任意公司展示 companyfacts 真实营收/毛利/TTM/现金/现金流（大号 stat 卡片）。
- **真实 SEC 文件链接**：`fetch_recent_filings` 给 10-Q/10-K/8-K 的 EDGAR 原文直链（修复"导向无关新闻"）。
- **财报全文拆解 `filing_teardown.py`**：下载 10-Q/10-K → **大额资金去向**（金额+中文用途分类：收购/采购承诺/资本开支/回购/分红/债务…，按可操作性排序）、**关联公司→ticker**（仅高置信、过滤地理表格噪音）、**客户集中度**（展示财报原文句，不合成误导单一%）。
- **财报月历视图**：月历网格，◀▶ 翻月浏览整季观察标的财报。

### 信号质量与基础设施
- **打分模型升级**：证据分层 + 主题词递减封顶 + 量化经济识别 + 置信度（`docs/signal_model.md`）。
- **信号→前瞻收益反馈闭环 `performance.py`** + CLI `report`：判断系统有没有 alpha（需积累数周成熟）。
- **PDF 全文 `pdf_intel.py`**（pypdf）：下载 arXiv/.pdf 抽正文重打分。
- **机构级一页纸日报 `daily_report.py`** + CLI `daily` + `/api/daily_report` + UI 导出按钮。
- **UI 重做**：现代研究终端（状态条姿态 + TOP CALL + 红绿灯密集表格 + 详情抽屉）。
- **工程地基**：pyproject 规范化、`net.py` 硬化 HTTP（重试/退避/UA/模板/日志）、feeds 并发+源健康、CI（Linux+Win×3.10/3.12）、`.env.example`、启动器"先杀后起"。

---

## 6. 跨领域约定（新增功能请遵守）

1. **联网模块必须可注入 fetcher/extractor**，便于离线确定性单测；默认走真实网络。
2. **失败优雅降级**：返回 `{"status": "unavailable"/...}`，绝不抛出中断扫描，绝不伪造数据。
3. **中文优先展示 + 英文原文备查**：标签/分类用确定性中文；无法忠实翻译的长句保留英文（悬停/小字），不做机器直译。
4. **重数据缓存**：慢端点（financials 6h、holders 24h、earnings 月 30min）按 key 缓存。
5. **改动后跑 `pytest` + `ruff check src tests` + `node --check app.js`**，全绿才算完成。

---

## 7. 诚实的能力边界

- **alpha 未验证**：`performance` 闭环已建，但 +5d/+20d 窗口需运行数周才成熟；当前阈值仍是受过教育的猜测。
- **不出估值/目标价/仓位/成稿论点**——到"证据密度变化"为止，判断仍需人。
- **实体/关系抽取是规则式**（无 LLM）：主流公司解析准，长尾/复杂句可能漏或误，已标"需人工复核"。
- **13F 有 45 天滞后 + 季度披露**；机构流向(Yahoo)是派生聚合，反向 13F 是精确但非全市场穷尽。
- **期权流未接真实数据源**（占位，不伪造）。EIA 能源源需 key（跳过）。

---

## 8. 剩余 backlog

- SQLite 持久化（替代 JSONL，支持信号绩效跨时间累积）。
- 源健康前端面板（后端 `source_health` 已就绪）。
- 条件 GET(ETag/304) 缓存。
- 离题财报相关性门槛（通用"reports financial results"会把离题公司捞进来）。
- 临近催化剂"热名单"快轮询（而非整体提频）。

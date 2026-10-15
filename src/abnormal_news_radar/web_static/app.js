const state = {
  candidates: [],
  articles: [],
  brief: null,
  sources: [],
  marketSources: [],
  watchlist: [],
  sourceCounts: {},
  query: "",
  view: initialView(),
  selectedEarningsTicker: initialSelectedEarningsTicker(),
  openRows: new Set(),
  stale: false,
  calendar: { month: currentMonthIso(), items: [], summary: "", loaded: false, loading: false },
  financials: {},
  holders: {},
  holdersProgress: {},
  optionsStructure: {},
  marketStructure: null,
  gammaChart: { index: "SPY", metric: "net_gex" },
  diagnose: { ticker: "", loading: false, result: null, error: "" },
};

const LANGUAGE_STORAGE_KEY = "ai-news-radar-language";
let locale = "zh-CN";
try {
  locale = window.localStorage.getItem(LANGUAGE_STORAGE_KEY) === "en" ? "en" : "zh-CN";
} catch {
  // A restricted browser storage context should not prevent the app from loading.
}

// Localize interface labels and known templates. Article titles, source names,
// and free-form analyst narratives stay in their collected language.
const UI_TRANSLATIONS = [
  ["AI News Radar | 研究终端", "AI News Radar | Research Terminal"],
  ["切换显示语言", "Switch interface language"], ["切换到 English", "Switch to 中文"],
  ["POSTURE 宏观", "POSTURE"], ["URGENT 立即研究", "URGENT"], ["CANDIDATES 候选", "CANDIDATES"], ["ARTICLES 文章", "ARTICLES"], ["NEXT SCAN 下次", "NEXT SCAN"],
  ["简报 Brief", "Brief"], ["机会 Ideas", "Ideas"], ["Alpha 猎手", "Alpha"], ["诊断 Diagnose", "Diagnose"], ["观察池", "Watchlist"], ["财报", "Earnings"], ["技术", "Technology"], ["宏观", "Market"], ["过程", "Process"], ["来源", "Sources"],
  ["每日简报", "Daily Brief"], ["机会清单", "Opportunity List"], ["Serenity Alpha · 小而纯受益者", "Serenity Alpha · Focused Beneficiaries"], ["个股诊断 · 错杀分析", "Stock Diagnosis · Mispricing"], ["动态观察池", "Watchlist"], ["财报工作台", "Earnings Workspace"], ["技术前沿", "Technology Frontier"], ["宏观状态", "Market Regime"], ["扫描过程", "Scan Process"], ["来源与种子名单", "Sources & Seed List"], ["研究终端", "Research Terminal"],
  ["待命", "Ready"], ["加载中", "Loading"], ["加载失败", "Load failed"], ["连接中断，等待自动重连", "Connection interrupted; waiting to reconnect"], ["等待排程", "Waiting for schedule"],
  ["导出日报", "Export Daily Report"], ["⤓ 导出日报", "⤓ Export Daily Report"], ["生成机构级一页纸日报 (Markdown)", "Export a one-page institutional brief (Markdown)"], ["筛选 ticker / 公司 / 来源 / 关键词", "Filter ticker / company / source / keyword"], ["筛选当前视图", "Filter current view"],
  ["RISK-ON 偏进攻", "RISK-ON · Risk seeking"], ["RISK-OFF 防守", "RISK-OFF · Defensive"], ["NEUTRAL 中性", "NEUTRAL"], ["未连接", "Disconnected"], ["OFFLINE", "OFFLINE"], ["LIVE", "LIVE"],
  ["简报还没有加载。", "The brief has not loaded yet."], ["今日宏观结论", "Today's Market Take"], ["系统暂未形成明确宏观结论。", "No clear market conclusion is available yet."], ["TOP CALL · 今日最该看", "TOP CALL · Highest-priority idea today"], ["重点机会", "Key Opportunities"], ["按动作优先级 + 分数排序。绿=已被证据/市场确认，红=负向或需先解释，灰=暂无数据。点行展开详情。", "Sorted by action priority and score. Green = confirmed by evidence or market action; red = negative or needs explanation; gray = no data. Select a row for details."], ["查看全部 →", "View all →"], ["财报重点", "Earnings Focus"], ["未来窗口暂无重点财报。", "No notable earnings in the upcoming window."], ["财报工作台 →", "Earnings workspace →"], ["近 14 天技术路线与供应链信号，按发布时间倒序", "Technology and supply-chain signals from the past 14 days, newest first"], ["技术工作台 →", "Technology workspace →"], ["近 14 天暂无有明确发布时间的技术路线文章；历史线索仍可在机会页查看。", "No recent technology articles with a clear publication date. Older items remain searchable on the Ideas page."], ["证据缺口", "Evidence Gaps"], ["系统下一轮要补的证据，不是交给你的待办。", "Evidence the system will seek in its next scan."], ["当前没有关键缺口。", "No critical gaps at this time."],
  ["本轮自动报告暂无达到阈值的机会。", "No opportunities met the threshold in this scan."], ["机会清单 · ", "Opportunity List · "], [" 项", " items"], ["点任意行展开完整证据、分析判断与缺口。", "Select a row to review the evidence, analysis, and gaps."], ["暂无达到阈值的机会。", "No opportunities met the threshold."], ["动作", "Action"], ["公司", "Company"], ["分数", "Score"], ["置信", "Confidence"], ["市场", "Market"], ["影响", "Impact"], ["期权", "Options"], ["预期", "Expectations"], ["催化剂", "Catalyst"], ["市场确认", "Market confirmation"], ["财务影响", "Financial impact"], ["SEC 财务", "SEC financials"], ["期权流", "Options flow"], ["预期差", "Expectations gap"], ["证据层 ", "Evidence tier "], ["还缺", "Missing"], ["错杀诊断 →", "Mispricing diagnosis →"], ["立即研究", "Research now"], ["跟踪", "Track"], ["待识别", "Identify"], ["观察", "Watch"],
  ["动态观察池还没有足够证据。", "The watchlist does not have enough evidence yet."], ["信念", "Conviction"], ["ticker待确认", "ticker pending"],
  ["财报日历 · 被选中公司", "Earnings Calendar · Selected Company"], ["财报详情", "Earnings Details"], ["核心财务指标、资金投向、提到的公司/产业链对象，以及二阶 read-through。", "Key financials, capital allocation, named companies and supply-chain references, plus second-order read-through."], ["本月", "This month"], ["个观察标的财报", " tracked earnings events"], ["加载中…", "Loading…"], ["点公司查看详情；用 ◀ ▶ 翻月浏览整个季度。", "Select a company for details. Use ◀ ▶ to browse the quarter."], ["上个月", "Previous month"], ["下个月", "Next month"], ["盘前", "Pre-market"], ["盘后", "After-hours"], ["盘中", "During market"], ["未来窗口内暂无重点财报。", "No notable earnings in the upcoming window."], ["已有原文拆解", "Source analysis available"], ["等待财报原文", "Waiting for earnings release"], ["没有可展示的财报事件。", "No earnings events to display."], ["数据不足", "Insufficient data"], ["查看期权结构（CBOE 全链 · GEX / IV / P-C）", "View options structure (CBOE chain · GEX / IV / P-C)"], ["Gamma 翻转位", "Gamma flip level"], ["期权怎么看这只股（CBOE 延迟全链）", "Options view (delayed CBOE chain)"], ["查看 13F 机构持仓（联网检索 SEC，较慢）", "View institutional 13F holdings (SEC lookup; slower)"],
  ["技术前沿任务", "Technology Frontier"], ["近 14 天文章按发布时间倒序；无发布时间的来源只保留最近 3 天首次抓取的条目。", "Articles from the past 14 days, newest first. Undated sources show only items first collected in the past 3 days."], ["近 14 天暂无明确技术路线文章。", "No clear technology-route articles from the past 14 days."], ["查看下游公司验证状态", "View downstream company validation"], ["查看技术证据与验证要点", "View technology evidence and validation"], ["技术路线", "Technology route"], ["关联公司", "Related companies"], ["技术来源命中", "Technology source match"],
  ["输入 ticker，回答一个问题：这只股是被错杀，还是真的坏了？", "Enter a ticker: is the stock mispriced, or are its fundamentals deteriorating?"], ["例如 CRDO / SMCI / MU", "e.g. CRDO / SMCI / MU"], ["诊断", "Diagnose"], ["数据源：FINRA 日度卖空、CBOE 延迟期权链（含希腊值）、Yahoo 价格、本地雷达新闻命中。全部免费公开数据，缺数据时明示，不伪造。", "Sources: FINRA daily short-sale data, delayed CBOE options chain (including Greeks), Yahoo prices, and local news matches. Public data only; missing data is disclosed."], ["诊断失败：", "Diagnosis failed: "], ["数据不足，无法诊断。", "Insufficient data for a diagnosis."], ["先诊断一只你怀疑被错杀的股票。诊断结论会自动存档，未来用 report 机制回测命中率。", "Diagnose a stock you suspect is mispriced. Results are saved for future evaluation."], ["大盘环境", "Market Context"], ["行动剧本", "Action Plan"], ["期权未平仓分布", "Open Interest Distribution"], ["call 未平仓", "Call open interest"], ["put 未平仓", "Put open interest"], ["各维度读数", "Factor Readings"], ["评分构成", "Score Breakdown"], ["触发条件", "Triggers"], ["宏观状态还没有加载。", "Market data has not loaded yet."],
  ["结构读数", "Structure Readings"], ["暂无结构读数。", "No structure readings."], ["来源与假设", "Sources & Assumptions"], ["本次结构快照：", "Structure snapshot: "], ["大盘 Gamma 分布（按 strike）", "Market Gamma by Strike"], ["未平仓 OI", "Open Interest (OI)"], ["现价", "Spot"], ["净 GEX 估算", "Estimated net GEX"], ["Call GEX 峰值", "Call GEX peak"], ["Put GEX 峰值", "Put GEX peak"], ["源时间", "Source time"], ["源时间不可用", "Source time unavailable"], ["宏观状态还没有加载。", "Market data has not loaded yet."], ["暂无宏观指标。", "No macro indicators."], ["政策/宏观事件", "Policy / Macro Events"], ["用于解释市场背景，不直接替代个股研究。", "Provides market context; does not replace company research."], ["暂无宏观事件。", "No macro events."],
  ["净 GEX 估算 −", "Estimated net GEX −"], ["净 GEX 估算 +", "Estimated net GEX +"], ["Call GEX 峰", "Call GEX peak"], ["Put GEX 峰", "Put GEX peak"], ["服务端未提供快照时间，当前数值的新鲜度无法确认", "The server did not provide a snapshot timestamp, so data freshness cannot be confirmed"], ["CBOE 源时间见下方图表", "CBOE source time is shown in the chart below"], ["条形显示现价下的净 GEX 估算：calls 正、puts 负是模型假设，不是真实做市商仓位。 CBOE 报价有延迟；上方源时间不代表 OI 的更新时间。翻转位需要按假设价格重新估算整条期权链，本页暂不显示。", "Bars show estimated net GEX at spot. Positive calls and negative puts are model assumptions, not actual dealer positions. CBOE quotes are delayed, and the source timestamp does not indicate when OI was updated. A gamma flip requires repricing the full chain at assumed spot prices, so it is not shown here."], ["CBOE 提供延迟期权链。未平仓量（OI）不显示买卖方；这里用 calls 正、puts 负估算 GEX，只是结构代理，不代表真实做市商仓位。Call/put GEX 峰值不是支撑或阻力。FINRA 卖空成交占比也不代表暗池净买卖方向。", "CBOE provides a delayed options chain. Open interest (OI) does not identify buyers or sellers. This page estimates GEX with positive calls and negative puts as a structural proxy, not actual dealer positioning. Call/put GEX peaks are not support or resistance. FINRA short-sale volume is not dark-pool net buying or selling."], ["能源政策会影响通胀、工业成本和电力基础设施。", "Energy policy can affect inflation, industrial costs, and power infrastructure."], ["AI 政策会影响算力、云、软件、监管和能源需求。", "AI policy can affect compute, cloud, software, regulation, and energy demand."], ["政策源事件：保留原文链接，等待主题匹配。", "Policy source event; awaiting a matching research theme. See the original source."],
  ["扫描过程", "Scan Process"], ["本轮来源分布", "Source Mix · Current Scan"], ["本服务会话还没有完成扫描。", "No scan has completed in this session."], ["暂无扫描过程。", "No scan activity to show."], ["来源=", "Source: "], ["信任权重=", "Trust: "], ["新鲜度=", "Freshness: "], ["时间权重=", "Time weight: "], ["发布时间=", "Published: "],
  ["没有配置来源。", "No sources configured."], ["种子关键词库", "Seed Keyword Library"], ["不是最终观察池", "Not the final watchlist"], ["查看", "View"], ["个种子标的", " seed tickers"], ["没有配置种子标的。", "No seed tickers configured."], ["本轮暂无候选可做 Serenity Alpha 评估（需先完成一次扫描）。", "No candidates are available for Serenity Alpha yet. Run a scan first."], ["个候选", " candidates"], ["新闻 → 小而纯、被错误分类、对该需求高弹性的受益者。五维乘法分（任一维近 0 即归零），外加排除规则与 1–4 季验证链。这是只读第二视角，不改主排序。", "Find focused, under-recognized beneficiaries with high demand sensitivity. A five-factor multiplicative score, exclusion rules, and a 1–4 quarter validation chain provide a read-only second view."], ["通过筛", "Qualified"], ["探索级", "Exploratory"], ["被排除", "Excluded"], ["仓位姿态：", "Positioning: "], ["验证链（1–4 季内证实 / 证伪）", "Validation Chain (confirm or reject within 1–4 quarters)"], ["利润表", "Income Statement"], ["需求 / 现金流", "Demand / Cash Flow"], ["经营杠杆", "Operating Leverage"], ["市场侧印证", "Market Validation"], ["通过 Serenity 筛", "Passed Serenity screen"], ["仅探索级", "Exploratory only"], ["分 ", "Score "],
  ["来源未标注", "Source not labeled"], ["标题未标注", "Title not labeled"], ["待确认", "Pending"], ["可能是不同事件，请分别核实", "May be separate events; verify individually"], ["较标题新增硬证据：", "New hard evidence beyond the headline: "], ["摘录：", "Excerpt: "], ["打开 PDF ↗", "Open PDF ↗"], ["机构持仓流向（13F 派生 · 聪明钱）", "Institutional Positioning (13F-derived)"], ["空头轧空潜力（美股制度型筹码因子）", "Short Squeeze Potential"], ["财务体检（防诈骗 / 防基数幻觉）", "Financial Health Check"], ["全文解析（PDF · pypdf）", "Full-text Analysis (PDF · pypdf)"], ["全文证据层", "Full-text evidence tier"], ["全文分", "Full-text score"], ["高风险", "High risk"], ["需谨慎", "Caution"], ["通过", "Pass"], ["数据不足", "Insufficient data"], ["未体检", "Not checked"], ["市场 ", "Market "], ["影响 ", "Impact "], ["SEC ", "SEC "], ["期权 ", "Options "], ["预期 ", "Expectations "],
  ["来源：", "Source: "], ["日期=", "Date: "], ["时间=", "Time: "], ["季度=", "Quarter: "], ["原文：", "Source text: "], ["核心财务（SEC 实际披露）", "Key Financials (SEC filings)"], ["最新 SEC 文件（EDGAR 实际申报 · 权威原文）", "Latest SEC Filings (EDGAR · Primary Source)"], ["打开 ↗", "Open ↗"], ["年度报告", "Annual Report"], ["季度报告", "Quarterly Report"], ["重大事件 / 业绩公告", "Current Report / Earnings Release"], ["外国公司年报", "Foreign Issuer Annual Report"], ["外国公司中期报告", "Foreign Issuer Interim Report"], ["最新 SEC 文件", "Latest SEC Filing"], ["钱花在哪里", "Capital Allocation"], ["研发投入", "R&D"], ["资本开支", "CapEx"], ["销售/管理费用", "SG&A"], ["股票回购", "Share Buybacks"], ["现金分红", "Dividends"], ["并购支出", "Acquisitions"],
  ["证据", "Evidence"], ["未知", "Unknown"], ["无", "None"], ["部分", "Partial"], ["缺失", "Missing"], ["早期", "Early"], ["仅价", "Price only"], ["已延伸", "Extended"], ["未确认", "Unconfirmed"], ["负向", "Negative"], ["无数据", "No data"], ["未验", "Unverified"], ["同向", "Supportive"], ["反向", "Bearish"], ["冲突", "Conflicting"], ["混合", "Mixed"], ["未计价", "Not priced in"], ["待查", "Needs review"], ["已计价", "Priced in"], ["负背离", "Negative divergence"], ["确认", "Confirmed"], ["净加仓（吸筹）", "Net accumulation"], ["净减仓（派发）", "Net distribution"], ["增减分化", "Mixed flows"], ["基本稳定", "Stable"], ["风险偏好", "Risk-on"], ["风险防御", "Risk-off"], ["中性", "Neutral"], ["无tkr", "No ticker"], ["宏观结论", "Macro Conclusion"], ["平静", "Calm"],
];

const UI_TRANSLATION_LOOKUP = new Map(UI_TRANSLATIONS.flatMap(([zh, en]) => [[zh, { "zh-CN": zh, en }], [en, { "zh-CN": zh, en }]]));
const UI_TRANSLATION_FRAGMENTS = [
  ["净 GEX 估算 −", "Estimated net GEX −"], ["净 GEX 估算 +", "Estimated net GEX +"],
  ["净 GEX 估算为正", "Estimated net GEX is positive"], ["净 GEX 估算为负", "Estimated net GEX is negative"],
  ["OI 模型净 GEX 为正", "OI-model net GEX is positive"], ["OI 模型净 GEX 为负", "OI-model net GEX is negative"],
  ["本次结构快照：", "Structure snapshot: "], ["服务端未提供快照时间，当前数值的新鲜度无法确认", "The server did not provide a snapshot timestamp, so data freshness cannot be confirmed"], ["CBOE 源时间见下方图表", "CBOE source time is shown in the chart below"],
  [" / 标的变动 1%", " / per 1% underlying move"], ["标的变动 1%", "underlying move 1%"], ["期权 Gamma 暴露（按 strike）", "Options Gamma Exposure by Strike"], ["Call GEX 峰", "Call GEX peak"], ["Put GEX 峰", "Put GEX peak"],
  ["空压↑", "Short pressure ↑"], ["空压↓", "Short pressure ↓"], ["空压平", "Short pressure flat"], ["全市场卖空", "Market-wide short volume"], ["大盘环境中性：", "Market regime: neutral: "], ["信号混杂，按标准触发条件执行。", "Mixed signals. Follow standard trigger criteria."], ["平静。", "Calm."],
  ["回撤前提成立", "Drawdown premise met"], ["无明显回撤", "No material drawdown"], ["缺失:", "Missing:"], ["时间待确认", "Time pending"], ["今日重点", "Today's focus"], ["检测到财报/指引相关语言，但 RSS 摘要中缺少足够数字，需打开原文或 8-K。", "Earnings or guidance language detected, but the RSS summary lacks enough figures. Open the original release or 8-K."],
  ["识别到技术路线图/研究信号：", "Technology route or research signal detected: "], ["技术来源命中，但暂未识别明确技术主题；强度=", "Technology source matched, but no specific theme was identified; strength: "], ["强度=", "Strength: "], ["二阶公司=", "Second-order companies: "], ["AI 工厂/机柜级架构", "AI factory / rack-scale architecture"], ["供电/散热", "Power / thermal management"], ["光互连", "Optical interconnect"], ["推理优化", "Inference optimization"], ["定制芯片", "Custom silicon"], ["机器人/边缘 AI", "Robotics / edge AI"], ["800V HVDC 供电", "800V HVDC power"],
  ["还没有候选标的获得正向价格/成交量确认。", "No candidates have positive price/volume confirmation."], ["目前没有候选标的强到进入快速建模队列。", "No candidates are strong enough for the fast modeling queue."], ["目前没有候选标的进入 Quick Model 工作流。", "No candidates entered the Quick Model workflow."], ["目前没有候选标的通过“早期预期差”筛选。", "No candidates passed the early expectations-gap screen."], ["部分新闻发现的公司在 SEC 名称匹配后仍未确认 ticker/交易所。", "Some companies found in news still lack a confirmed ticker or exchange after SEC name matching."], ["宏观状态源当前降级或不可用，市场背景评分可能不完整。", "Macro data sources are degraded or unavailable; market context scores may be incomplete."],
  ["部分降级", "Partially degraded"], ["宏观环境中性", "Macro regime: Neutral"], ["维持默认证据门槛，重点看公司新闻是否足够硬、是否被市场确认。", "Keep the default evidence threshold. Prioritize strong company news confirmed by market action."],
  ["📄 全文已读", "📄 Full text reviewed"], ["来源未提供摘要，点击原文。", "No summary was provided; open the original source."], ["重要性", "Importance"],
];

function localizedText(value) {
  const trimmed = value.trim();
  if (!trimmed) return value;
  const entry = UI_TRANSLATION_LOOKUP.get(trimmed);
  if (entry) return value.replace(trimmed, entry[locale]);

  const evidenceChip = trimmed.match(/^(市场|影响|SEC|期权|预期)\s+(.+)$/);
  if (evidenceChip) {
    const label = { 市场: "Market", 影响: "Impact", SEC: "SEC", 期权: "Options", 预期: "Expectations" }[evidenceChip[1]];
    const valueEntry = UI_TRANSLATION_LOOKUP.get(evidenceChip[2]);
    return value.replace(trimmed, `${label} ${valueEntry ? valueEntry[locale] : evidenceChip[2]}`);
  }

  const patterns = locale === "en" ? [
    [/^已加载 (\d+) 候选，正在生成简报…$/, "$1 candidates loaded · building brief…"],
    [/^已加载 (\d+) 个机会 · (\d+) 候选$/, "$1 opportunities · $2 candidates loaded"],
    [/^已加载 (\d+) 候选$/, "$1 candidates loaded"],
    [/^机会清单 · (\d+) 项$/, "Opportunity List · $1 items"],
    [/^查看 (\d+) 个种子标的$/, "View $1 seed tickers"],
    [/^(.+) 年 (\d+) 月$/, "$1 / $2"],
    [/^未来窗口内有 (\d+) 个主流观察标的财报；今日 (\d+) 个，后续 (\d+) 个。$/, "$1 tracked earnings events in the upcoming window; $2 today and $3 later."],
    [/^识别到 (\d+) 个二阶 read-through 公司；财报线索 (\d+)，技术线索 (\d+)，其中 (\d+) 个需要优先检查。$/, "$1 second-order read-through companies detected; $2 earnings signals and $3 technology signals, with $4 to review first."],
    [/^当前分数 (\d+)，宏观本身不给明显方向。$/, "Current score $1; macro conditions provide no clear directional signal."],
    [/^SCORE · 置信 (.+)$/, "SCORE · Confidence $1"],
    [/^同公司另有 (\d+) 条更新$/, "$1 more updates for this company"],
    [/^发布 (.+)$/, "Published $1"],
    [/^抓取 (.+)$/, "Fetched $1"],
    [/^— 现价 \$(.+) —$/, "— Spot $$$1 —"],
    [/^RISK-ON 偏进攻(?: \((.+)\))?$/, (_match, score) => `RISK-ON · Risk seeking${score ? ` (${score})` : ""}`],
    [/^RISK-OFF 防守(?: \((.+)\))?$/, (_match, score) => `RISK-OFF · Defensive${score ? ` (${score})` : ""}`],
    [/^NEUTRAL 中性(?: \((.+)\))?$/, (_match, score) => `NEUTRAL${score ? ` (${score})` : ""}`],
    [/^来源=(.+)$/, "Source: $1"],
    [/^截至=(.+)$/, "As of: $1"],
    [/^值=(.+)$/, "Value: $1"],
    [/^分数=(.+)$/, "Score: $1"],
    [/^([A-Z]+)：OI 符号假设下净 GEX 估算为(正|负|不可用)(?:（约 \$([^/]+)B \/ 标的变动 1%）)?(?:，现价 \$([\d.]+))?。$/, (_match, ticker, sign, billions, spot) => `${ticker}: estimated net GEX is ${{ "正": "positive", "负": "negative", "不可用": "unavailable" }[sign]} under the OI sign assumption${billions ? ` (about $${billions}B per 1% underlying move)` : ""}${spot ? `; spot $${spot}` : ""}.`],
    [/^SPX call\/put GEX 峰值：\$(.+) \/ \$(.+)；表示该符号模型的集中 strike，不是已确认的支撑或阻力。$/, (_match, call, put) => `SPX call/put GEX peaks: $${call} / $${put}. These are concentrations under the sign model, not confirmed support or resistance.`],
    [/^全市场卖空成交占比 ([\d.]+)%（20日均值 ([\d.]+)%）且基本持平。$/, "Market-wide short-sale volume is $1% (20-day average $2%), broadly flat."],
    [/^VIX=([\d.]+)（3个月均值 ([\d.]+)），市场恐惧状态：(.+)。$/, (_match, value, average, fear) => `VIX=${value} (3-month average ${average}); market fear: ${UI_TRANSLATION_LOOKUP.get(fear)?.en || fear}.`],
  ] : [
    [/^(\d+) candidates loaded · building brief…$/, "已加载 $1 候选，正在生成简报…"],
    [/^(\d+) opportunities · (\d+) candidates loaded$/, "已加载 $1 个机会 · $2 候选"],
    [/^(\d+) candidates loaded$/, "已加载 $1 候选"],
    [/^Opportunity List · (\d+) items$/, "机会清单 · $1 项"],
    [/^View (\d+) seed tickers$/, "查看 $1 个种子标的"],
    [/^(.+) \/ (\d+)$/, "$1 年 $2 月"],
    [/^(\d+) tracked earnings events in the upcoming window; (\d+) today and (\d+) later\.$/, "未来窗口内有 $1 个主流观察标的财报；今日 $2 个，后续 $3 个。"],
    [/^(\d+) second-order read-through companies detected; (\d+) earnings signals and (\d+) technology signals, with (\d+) to review first\.$/, "识别到 $1 个二阶 read-through 公司；财报线索 $2，技术线索 $3，其中 $4 个需要优先检查。"],
    [/^Current score (\d+); macro conditions provide no clear directional signal\.$/, "当前分数 $1，宏观本身不给明显方向。"],
    [/^SCORE · Confidence (.+)$/, "SCORE · 置信 $1"],
    [/^(\d+) more updates for this company$/, "同公司另有 $1 条更新"],
    [/^Published (.+)$/, "发布 $1"],
    [/^Fetched (.+)$/, "抓取 $1"],
    [/^— Spot \$(.+) —$/, "— 现价 $$$1 —"],
    [/^RISK-ON · Risk seeking(?: \((.+)\))?$/, (_match, score) => `RISK-ON 偏进攻${score ? ` (${score})` : ""}`],
    [/^RISK-OFF · Defensive(?: \((.+)\))?$/, (_match, score) => `RISK-OFF 防守${score ? ` (${score})` : ""}`],
    [/^NEUTRAL(?: \((.+)\))?$/, (_match, score) => `NEUTRAL 中性${score ? ` (${score})` : ""}`],
    [/^Source: (.+)$/, "来源=$1"],
    [/^As of: (.+)$/, "截至=$1"],
    [/^Value: (.+)$/, "值=$1"],
    [/^Score: (.+)$/, "分数=$1"],
    [/^([A-Z]+): estimated net GEX is (positive|negative|unavailable) under the OI sign assumption(?: \(about \$([^/]+)B per 1% underlying move\))?(?:; spot \$([\d.]+))?\.$/, (_match, ticker, sign, billions, spot) => `${ticker}：OI 符号假设下净 GEX 估算为${{ positive: "正", negative: "负", unavailable: "不可用" }[sign]}${billions ? `（约 $${billions}B / 标的变动 1%）` : ""}${spot ? `，现价 $${spot}` : ""}。`],
    [/^SPX call\/put GEX peaks: \$(.+) \/ \$(.+)\. These are concentrations under the sign model, not confirmed support or resistance\.$/, (_match, call, put) => `SPX call/put GEX 峰值：$${call} / $${put}；表示该符号模型的集中 strike，不是已确认的支撑或阻力。`],
    [/^Market-wide short-sale volume is ([\d.]+)% \(20-day average ([\d.]+)%\), broadly flat\.$/, "全市场卖空成交占比 $1%（20日均值 $2%）且基本持平。"],
    [/^VIX=([\d.]+) \(3-month average ([\d.]+)\); market fear: (.+)\.$/, (_match, value, average, fear) => `VIX=${value}（3个月均值 ${average}），市场恐惧状态：${UI_TRANSLATION_LOOKUP.get(fear)?.["zh-CN"] || fear}。`],
  ];
  for (const [pattern, replacement] of patterns) {
    if (pattern.test(trimmed)) return value.replace(trimmed, trimmed.replace(pattern, replacement));
  }

  const fragments = locale === "en" ? UI_TRANSLATION_FRAGMENTS : UI_TRANSLATION_FRAGMENTS.map(([zh, en]) => [en, zh]);
  let translatedText = trimmed;
  for (const [from, to] of fragments) translatedText = translatedText.replaceAll(from, to);
  if (translatedText !== trimmed) return value.replace(trimmed, translatedText);

  return value;
}

function localizeSubtree(root = document.body) {
  if (root.nodeType === Node.TEXT_NODE) {
    if (!root.parentElement?.closest("#languageToggle")) {
      const translated = localizedText(root.nodeValue || "");
      if (translated !== root.nodeValue) root.nodeValue = translated;
    }
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE && root !== document) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (!node.parentElement?.closest("#languageToggle")) {
      const translated = localizedText(node.nodeValue || "");
      if (translated !== node.nodeValue) node.nodeValue = translated;
    }
  }
  if (root instanceof Element) {
    for (const attribute of ["placeholder", "title", "aria-label"]) {
      if (root.hasAttribute(attribute)) {
        const original = root.getAttribute(attribute) || "";
        const translated = localizedText(original);
        if (translated !== original) root.setAttribute(attribute, translated);
      }
    }
    root.querySelectorAll("[placeholder], [title], [aria-label]").forEach((element) => {
      for (const attribute of ["placeholder", "title", "aria-label"]) {
        if (element.hasAttribute(attribute)) {
          const original = element.getAttribute(attribute) || "";
          const translated = localizedText(original);
          if (translated !== original) element.setAttribute(attribute, translated);
        }
      }
    });
  }
}

function applyLocale() {
  document.documentElement.lang = locale;
  document.title = locale === "en" ? "AI News Radar | Research Terminal" : "AI News Radar | 研究终端";
  const button = document.querySelector("#languageToggle");
  if (button) {
    button.querySelector("span").textContent = locale === "en" ? "English" : "中文";
    button.title = locale === "en" ? "Switch to 中文" : "切换到 English";
    button.setAttribute("aria-label", locale === "en" ? "Switch interface language" : "切换显示语言");
  }
  localizeSubtree(document.body);
}

function currentMonthIso() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

const AUTO_REFRESH_MS = 60000;

const elements = {
  postureVal: document.querySelector("#postureVal"),
  urgentVal: document.querySelector("#urgentVal"),
  urgentStat: document.querySelector("#urgentStat"),
  candVal: document.querySelector("#candVal"),
  artVal: document.querySelector("#artVal"),
  nextRun: document.querySelector("#nextRun"),
  liveDot: document.querySelector("#liveDot"),
  liveText: document.querySelector("#liveText"),
  oppBadge: document.querySelector("#oppBadge"),
  serenityBadge: document.querySelector("#serenityBadge"),
  statusLine: document.querySelector("#statusLine"),
  errorBox: document.querySelector("#errorBox"),
  scanProgress: document.querySelector("#scanProgress"),
  progressText: document.querySelector("#progressText"),
  contentArea: document.querySelector("#contentArea"),
  searchBox: document.querySelector("#searchBox"),
  viewTitle: document.querySelector("#viewTitle"),
  tabs: Array.from(document.querySelectorAll(".tab")),
};

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeArticleHref(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? escapeHtml(url.href) : "";
  } catch {
    return "";
  }
}

function articleOf(row) {
  return row?.article && typeof row.article === "object" ? row.article : {};
}

function objectValue(value) {
  return value && typeof value === "object" ? value : {};
}

function textOf(values) {
  return values.filter(Boolean).join(" ").toLowerCase();
}

function candidateTickers(candidate) {
  return (candidate.tickers || []).map((ticker) => String(ticker).toUpperCase().trim()).filter(Boolean);
}

function groupRows(rows, keyFn) {
  return rows.reduce((groups, row) => {
    const key = keyFn(row);
    if (!groups[key]) groups[key] = [];
    groups[key].push(row);
    return groups;
  }, {});
}

/* The analyst report is the ranked, action-tagged view. Fall back to raw
   candidates (with a score-derived action) before the first brief loads. */
function reportRows() {
  const rows = state.brief?.analyst_report;
  if (Array.isArray(rows)) return rows;
  return state.candidates.map((candidate) => ({
    ...candidate,
    action: candidate.action || actionFromScore(candidate.score),
    decision: candidate.decision || "",
  }));
}

function matchQuery(row) {
  const query = state.query.trim().toLowerCase();
  if (!query) return true;
  return textOf([
    row.company_name,
    row.decision,
    row.analyst_take,
    ...(row.tickers || []),
    ...(row.matched_terms || []),
    articleOf(row).title,
    articleOf(row).source,
  ]).includes(query);
}

function visibleOpportunities() {
  return reportRows().filter(matchQuery);
}

function visibleCandidates() {
  const query = state.query.trim().toLowerCase();
  if (!query) return state.candidates;
  return state.candidates.filter((candidate) => textOf([
    candidate.company_name,
    candidate.decision,
    candidate.analyst_take,
    ...(candidate.tickers || []),
    ...(candidate.matched_terms || []),
    articleOf(candidate).title,
    articleOf(candidate).source,
  ]).includes(query));
}

function visibleArticles() {
  const query = state.query.trim().toLowerCase();
  if (!query) return state.articles;
  return state.articles.filter((article) => textOf([article.title, article.source, article.summary, article.published]).includes(query));
}

function visibleSources() {
  const query = state.query.trim().toLowerCase();
  const rows = [...state.sources, ...state.marketSources];
  if (!query) return rows;
  return rows.filter((source) => textOf([source.name, source.group, source.type, source.url, source.purpose]).includes(query));
}

function rowKey(row) {
  return `${candidateTickers(row).join(",")}|${articleOf(row).link || articleOf(row).title || row.company_name || ""}`;
}

/* ------------------------------------------------------------------ */
/* traffic-light evidence mapping                                     */
/* ------------------------------------------------------------------ */
function evChip(label, cls, text) {
  return `<span class="ev ${cls}" title="${escapeHtml(label)}">${escapeHtml(text)}</span>`;
}

function evMarket(row) {
  const s = objectValue(row.market_confirmation).status || "";
  const map = {
    confirmed: ["ok", "确认"],
    early_confirmation: ["ok", "早期"],
    price_only_confirmation: ["warn", "仅价"],
    already_extended: ["warn", "已延伸"],
    unconfirmed: ["warn", "未确认"],
    negative_reaction: ["bad", "负向"],
    no_ticker: ["na", "无tkr"],
    unavailable: ["na", "无数据"],
  };
  const [cls, text] = map[s] || ["na", "—"];
  return { cls, text };
}

function evImpact(row) {
  const impact = objectValue(row.impact_assessment);
  const score = impact.impact_score;
  if (score === undefined || score === null || score === "") return { cls: "na", text: "—" };
  const n = Number(score);
  const cls = n >= 4 ? "ok" : n >= 2 ? "warn" : "na";
  return { cls, text: `${n}/5` };
}

function evSec(row) {
  const s = objectValue(row.financial_snapshot).status || "";
  const map = {
    ok: ["ok", "OK"],
    partial: ["warn", "部分"],
    missing: ["warn", "缺失"],
    unavailable: ["na", "无"],
    no_ticker: ["na", "无tkr"],
  };
  const [cls, text] = map[s] || ["na", "—"];
  return { cls, text };
}

function evFlow(row) {
  const s = objectValue(row.options_flow).status || "";
  const map = {
    supportive_flow: ["ok", "同向"],
    bearish_flow: ["bad", "反向"],
    conflicting_flow: ["bad", "冲突"],
    mixed_flow: ["warn", "混合"],
    unverified_bullish_flow: ["na", "未验"],
    unverified_flow: ["na", "未验"],
    no_flow_evidence: ["na", "无"],
  };
  const [cls, text] = map[s] || ["na", "—"];
  return { cls, text };
}

function evExp(row) {
  const s = objectValue(row.expectation_check).status || "";
  const map = {
    variant_not_fully_priced: ["ok", "未计价"],
    needs_price_in_check: ["warn", "待查"],
    likely_already_priced_in: ["bad", "已计价"],
    negative_divergence: ["bad", "负背离"],
    watch_only: ["na", "观察"],
    no_market_data: ["na", "无"],
  };
  const [cls, text] = map[s] || ["na", "—"];
  return { cls, text };
}

function confClass(conf) {
  const n = Number(conf);
  if (!Number.isFinite(n)) return "lo";
  if (n >= 0.7) return "hi";
  if (n >= 0.4) return "mid";
  return "lo";
}

/* ------------------------------------------------------------------ */
/* view routing                                                       */
/* ------------------------------------------------------------------ */
function setView(view) {
  state.view = view;
  const nextHash = view === "earnings" && state.selectedEarningsTicker ? `#earnings:${state.selectedEarningsTicker}` : `#${view}`;
  if (window.location.hash !== nextHash) {
    window.history.replaceState(null, "", nextHash);
  }
  elements.tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.view === view));
  const titles = {
    brief: "每日简报",
    opportunities: "机会清单",
    serenity: "Serenity Alpha · 小而纯受益者",
    diagnose: "个股诊断 · 错杀分析",
    watchlist: "动态观察池",
    earnings: "财报工作台",
    technology: "技术前沿",
    market: "宏观状态",
    process: "扫描过程",
    sources: "来源与种子名单",
  };
  elements.viewTitle.textContent = titles[view] || "研究终端";
  render();
}

function initialView() {
  const view = window.location.hash.replace("#", "").split(":")[0];
  return ["brief", "opportunities", "serenity", "diagnose", "watchlist", "earnings", "technology", "market", "process", "sources"].includes(view) ? view : "brief";
}

function initialSelectedEarningsTicker() {
  const [view, ticker] = window.location.hash.replace("#", "").split(":");
  return view === "earnings" && ticker ? ticker.toUpperCase() : null;
}

function render() {
  updateStatusStrip();
  if (state.view === "brief") renderBrief();
  if (state.view === "opportunities") renderOpportunities();
  if (state.view === "serenity") renderSerenity();
  if (state.view === "diagnose") renderDiagnose();
  if (state.view === "watchlist") renderWatchlist();
  if (state.view === "earnings") renderEarnings();
  if (state.view === "technology") renderTechnology();
  if (state.view === "market") renderMarket();
  if (state.view === "process") renderProcess();
  if (state.view === "sources") renderSources();
  localizeSubtree(document.body);
}

/* ------------------------------------------------------------------ */
/* status strip                                                       */
/* ------------------------------------------------------------------ */
function updateStatusStrip() {
  const brief = state.brief || {};
  const counts = brief.counts || {};
  const regime = brief.market_regime || {};
  const conclusion = brief.market_conclusion_zh || {};
  const automation = brief.automation || {};

  const regimeName = regime.regime || "unknown";
  const postureMap = {
    risk_on: ["posture-on", "RISK-ON 偏进攻"],
    risk_off: ["posture-off", "RISK-OFF 防守"],
    neutral: ["posture-neutral", "NEUTRAL 中性"],
  };
  const [postureCls, postureText] = postureMap[regimeName] || ["posture-na", "未连接"];
  elements.postureVal.className = `stat-v ${postureCls}`;
  const score = regime.score;
  elements.postureVal.textContent = score !== undefined && score !== null && regimeName !== "unknown"
    ? `${postureText} (${score})`
    : postureText;
  elements.postureVal.title = conclusion.action || conclusion.summary || "";

  const urgent = counts.urgent_items ?? reportRows().filter((row) => row.action === "research_now").length;
  elements.urgentVal.textContent = String(urgent);
  elements.urgentStat.classList.toggle("has-urgent", Number(urgent) > 0);

  elements.candVal.textContent = String(counts.report_items ?? reportRows().length);
  elements.artVal.textContent = String(counts.articles_reviewed ?? state.articles.length ?? 0);
  elements.nextRun.textContent = automation.next_run ? shortTime(automation.next_run) : "等待排程";

  const oppCount = reportRows().filter((row) => row.action === "research_now").length;
  elements.oppBadge.textContent = oppCount > 0 ? String(oppCount) : "";

  const serenityCount = reportRows().filter((row) => objectValue(row.serenity_alpha).verdict === "qualified").length;
  if (elements.serenityBadge) elements.serenityBadge.textContent = serenityCount > 0 ? String(serenityCount) : "";

  elements.liveDot.classList.toggle("stale", state.stale);
  elements.liveText.textContent = state.stale ? "OFFLINE" : "LIVE";
}

function updateScanProgress(lastScan) {
  // Hide the "first scan" banner once the in-session scan has completed OR we
  // already have stored data to show. Otherwise it would linger forever, since
  // the periodic refresh — not just initial load — now keeps it in sync.
  const completed = Boolean(lastScan && lastScan.completed_at);
  const hasData = (state.candidates && state.candidates.length > 0) || reportRows().length > 0;
  elements.scanProgress.hidden = completed || hasData;
  if (!elements.scanProgress.hidden) {
    elements.progressText.textContent = "首次自动分析进行中…（含全文/机构/空头富化，约 1–2 分钟）";
  }
}

function shortTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const TECH_MAX_PUBLISHED_AGE_DAYS = 14;
const TECH_MAX_UNDATED_AGE_DAYS = 3;

function parsedTime(value) {
  if (!value) return null;
  const timestamp = Date.parse(String(value));
  return Number.isFinite(timestamp) ? timestamp : null;
}

function technologyTimes(candidate) {
  const article = articleOf(candidate);
  const publishedAt = parsedTime(article.published);
  const observedAt = parsedTime(candidate.first_seen_at || article.fetched_at);
  return { publishedAt, observedAt, sortAt: publishedAt ?? observedAt };
}

function recentTechnologyCandidates(rows = visibleCandidates()) {
  const now = Date.now();
  return rows
    .filter(hasTechnologyIntel)
    .filter((candidate) => {
      const { publishedAt, observedAt } = technologyTimes(candidate);
      const timestamp = publishedAt ?? observedAt;
      if (timestamp === null) return false;
      const ageDays = (now - timestamp) / 86_400_000;
      const maxAge = publishedAt === null ? TECH_MAX_UNDATED_AGE_DAYS : TECH_MAX_PUBLISHED_AGE_DAYS;
      return ageDays >= -1 && ageDays <= maxAge;
    })
    .sort((a, b) => technologyTimes(b).sortAt - technologyTimes(a).sortAt);
}

function technologyDateMeta(candidate) {
  const { publishedAt, observedAt } = technologyTimes(candidate);
  const dateLabel = (timestamp, withTime = false) => {
    if (timestamp === null) return "";
    const date = new Date(timestamp);
    return withTime
      ? date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
      : date.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  };
  const published = publishedAt === null
    ? '<span class="tech-date-unknown">未提供发布时间</span>'
    : `<span>发布 ${escapeHtml(dateLabel(publishedAt))}</span>`;
  const observed = observedAt === null ? "" : `<span>抓取 ${escapeHtml(dateLabel(observedAt, true))}</span>`;
  return `<div class="technology-card-meta">${published}${observed}</div>`;
}

/* ------------------------------------------------------------------ */
/* BRIEF cockpit                                                      */
/* ------------------------------------------------------------------ */
function renderBrief() {
  const brief = state.brief;
  if (!brief) {
    elements.contentArea.innerHTML = '<div class="empty">简报还没有加载。</div>';
    return;
  }
  const conclusion = brief.market_conclusion_zh || {};
  const calendar = brief.earnings_calendar || {};
  const rows = state.query.trim()
    ? visibleOpportunities()
    : Array.isArray(brief.digest_items) ? brief.digest_items : visibleOpportunities();
  const top = rows[0];
  const tableRows = rows.slice(0, 12);
  const allTechnologyCandidates = visibleCandidates().filter(hasTechnologyIntel);
  const technologyCandidates = recentTechnologyCandidates(allTechnologyCandidates).slice(0, 3);
  const hiddenHistoricalTechnologyCount = Math.max(0, allTechnologyCandidates.length - recentTechnologyCandidates(allTechnologyCandidates).length);
  const earningsDetails = earningsDetailsByTicker(calendar.items || []);
  const gaps = (brief.data_gaps_zh || brief.data_gaps || [])
    .slice(0, 6)
    .map((gap) => `<span class="pill">${escapeHtml(gap)}</span>`)
    .join("");

  elements.contentArea.innerHTML = `
    <section class="section-head">
      <div>
        <h3>今日宏观结论</h3>
        <p>${escapeHtml(conclusion.summary || brief.headline_zh || "系统暂未形成明确宏观结论。")}</p>
      </div>
    </section>

    ${top ? `<section class="section-head"><div><h3>TOP CALL · 今日最该看</h3></div></section>${renderTopCall(top)}` : ""}

    <section class="section-head">
      <div>
        <h3>重点机会</h3>
        <p>按动作优先级 + 分数排序。绿=已被证据/市场确认，红=负向或需先解释，灰=暂无数据。点行展开详情。</p>
      </div>
      <button class="small-action" type="button" data-inline-view="opportunities">查看全部 →</button>
    </section>
    ${renderOppTable(tableRows)}

    <section class="section-head">
      <div>
        <h3>财报重点</h3>
        <p>${escapeHtml(calendar.summary_zh || "未来窗口暂无重点财报。")}</p>
      </div>
      <button class="small-action" type="button" data-inline-view="earnings">财报工作台 →</button>
    </section>
    <div class="content-grid">${renderTodayEarningsBrief(calendar.items || [], earningsDetails)}</div>

    <section class="section-head">
      <div>
        <h3>技术前沿</h3>
        <p>近 14 天技术路线与供应链信号，按发布时间倒序${hiddenHistoricalTechnologyCount ? ` · ${hiddenHistoricalTechnologyCount} 条旧线索已从首页收起` : ""}。</p>
      </div>
      <button class="small-action" type="button" data-inline-view="technology">技术工作台 →</button>
    </section>
    <div class="content-grid">${technologyCandidates.map(renderTechnologyCard).join("") || '<div class="empty">近 14 天暂无有明确发布时间的技术路线文章；历史线索仍可在机会页查看。</div>'}</div>

    <section class="section-head"><div><h3>证据缺口</h3><p>系统下一轮要补的证据，不是交给你的待办。</p></div></section>
    <section class="row"><div class="row-meta">${gaps || "<span>当前没有关键缺口。</span>"}</div></section>
  `;
  bindInlineViewButtons();
  bindOppRows();
  bindCrossLinks();
}

function renderTopCall(row) {
  const article = articleOf(row);
  const action = row.action || actionFromScore(row.score);
  const tickers = candidateTickers(row);
  const mainHref = safeArticleHref(article.link);
  const related = Array.isArray(row.related_updates) ? row.related_updates : [];
  const relatedLinks = related.map((update) => {
    const href = safeArticleHref(update.link);
    const label = `${update.source || "来源未标注"} · ${update.title || "标题未标注"}`;
    return href ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : `<span>${escapeHtml(label)}</span>`;
  }).join("");
  return `
    <article class="topcall act-${escapeHtml(action)}">
      <div class="topcall-head">
        <span class="act act-${escapeHtml(action)}">${escapeHtml(actionLabelZh(action))}</span>
        ${qualityChip(row)}${squeezeChip(row)}${flowChip(row)}${pdfChip(row)}
        <span class="topcall-ticker">${escapeHtml(tickers.join(", ") || "待确认")}</span>
        <span class="topcall-name">${escapeHtml(row.company_name || "Unknown")}</span>
        <span class="topcall-score"><b>${Number(row.score || 0).toFixed(1)}</b><span>SCORE · 置信 ${fmtConf(row.confidence)}</span></span>
      </div>
      <div class="topcall-decision">${escapeHtml(row.decision || row.analyst_take || "")}</div>
      <div class="row-meta">${evidenceChips(row)}</div>
      <div class="topcall-catalyst">${mainHref ? `<a href="${mainHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(article.source || "")} · ${escapeHtml(article.title || "")}</a>` : escapeHtml(`${article.source || ""} · ${article.title || ""}`)}</div>
      ${row.related_update_count ? `<div class="topcall-related"><b>同公司另有 ${Number(row.related_update_count)} 条更新</b><span>可能是不同事件，请分别核实</span>${relatedLinks}</div>` : ""}
    </article>
  `;
}

function qualityChip(row) {
  const q = objectValue(row.quality_screen);
  const labels = q.labels || [];
  if (q.veto) {
    return `<span class="risk risk-veto" title="${escapeHtml(q.summary_zh || "")}">${escapeHtml(labels[0] || "[高风险归零股]")}</span>`;
  }
  if (labels.length) {
    return `<span class="risk risk-warn" title="${escapeHtml(q.summary_zh || "")}">${escapeHtml(labels[0])}</span>`;
  }
  return "";
}

function squeezeChip(row) {
  const sq = objectValue(row.short_squeeze);
  // Suppress the "chase the squeeze" amplifier on a vetoed going-concern name.
  if (!sq.alert || objectValue(row.quality_screen).veto) return "";
  return `<span class="risk risk-squeeze" title="${escapeHtml(sq.summary_zh || "")}">🚀 ${escapeHtml(sq.label || "[空头轧空潜力]")}</span>`;
}

function pdfChip(row) {
  const p = objectValue(row.pdf_intel);
  if (p.status !== "ok") return "";
  return `<span class="risk risk-pdf" title="${escapeHtml(p.summary_zh || "")}">📄 全文已读</span>`;
}

function renderPdfDim(row) {
  const p = objectValue(row.pdf_intel);
  if (p.status !== "ok") return "";
  const extra = (p.extra_terms || []).slice(0, 10).map((t) => `<span class="ev ok">${escapeHtml(t)}</span>`).join(" ");
  return `
    <div class="dim" style="grid-column:1/-1;border-left:3px solid var(--blue)">
      <span class="dim-k">全文解析（PDF · pypdf）</span>
      <span class="dim-v"><span class="ev na">${escapeHtml(String(p.page_count ?? "?"))} 页</span> <span class="ev na">全文证据层 ${escapeHtml(p.evidence_tier || "n/a")}</span> <span class="ev na">全文分 ${escapeHtml(String(p.full_text_score ?? 0))}</span></span>
      ${extra ? `<span class="dim-v">较标题新增硬证据：</span><span class="dim-v">${extra}</span>` : ""}
      ${p.excerpt ? `<span class="dim-v" style="color:var(--muted)">摘录：${escapeHtml(p.excerpt)}</span>` : ""}
      ${safeArticleHref(p.source_url) ? `<span class="dim-v"><a href="${safeArticleHref(p.source_url)}" target="_blank" rel="noopener noreferrer">打开 PDF ↗</a></span>` : ""}
    </div>
  `;
}

function flowChip(row) {
  const f = objectValue(row.institutional_flow);
  if (f.flow === "accumulation") {
    return `<span class="risk risk-accum" title="${escapeHtml(f.summary_zh || "")}">🏦 机构吸筹</span>`;
  }
  if (f.flow === "distribution") {
    return `<span class="risk risk-distrib" title="${escapeHtml(f.summary_zh || "")}">🏦 机构派发</span>`;
  }
  return "";
}

function renderFlowDim(row) {
  const f = objectValue(row.institutional_flow);
  if (!f.status || f.status === "no_ticker" || f.status === "unavailable") return "";
  const cls = f.flow === "accumulation" ? "ok" : f.flow === "distribution" ? "bad" : f.flow === "mixed" ? "warn" : "na";
  const flowZh = { accumulation: "净加仓（吸筹）", distribution: "净减仓（派发）", mixed: "增减分化", stable: "基本稳定" }[f.flow] || "—";
  return `
    <div class="dim" style="grid-column:1/-1;border-left:3px solid var(--${cls === "bad" ? "red" : cls === "ok" ? "green" : cls === "warn" ? "amber" : "border"})">
      <span class="dim-k">机构持仓流向（13F 派生 · 聪明钱）</span>
      <span class="dim-v"><span class="ev ${cls}">${escapeHtml(flowZh)}</span> <span class="ev na">机构持股 ${escapeHtml(f.institutions_pct_display || "n/a")}</span> <span class="ev na">加仓 ${escapeHtml(String(f.accumulators ?? 0))} / 减仓 ${escapeHtml(String(f.reducers ?? 0))}</span></span>
      <span class="dim-v">${escapeHtml(f.summary_zh || "")}</span>
    </div>
  `;
}

function renderSqueezeDim(row) {
  const sq = objectValue(row.short_squeeze);
  if (!sq.status || sq.status === "no_ticker" || sq.status === "unavailable") return "";
  const cls = sq.alert ? "bad" : sq.potential === "high" || sq.potential === "elevated" ? "warn" : "na";
  return `
    <div class="dim" style="grid-column:1/-1;border-left:3px solid var(--${sq.alert ? "red" : "amber"})">
      <span class="dim-k">空头轧空潜力（美股制度型筹码因子）</span>
      <span class="dim-v"><span class="ev ${cls}">空头占流通盘 ${escapeHtml(sq.short_percent_display || "n/a")}</span> ${sq.short_ratio_days ? `<span class="ev na">回补天数 ${escapeHtml(Number(sq.short_ratio_days).toFixed(1))}</span>` : ""}</span>
      <span class="dim-v">${escapeHtml(sq.summary_zh || "")}</span>
    </div>
  `;
}

function renderQualityDim(row) {
  const q = objectValue(row.quality_screen);
  if (!q.status || q.status === "no_ticker") return "";
  const el = objectValue(q.revenue_elasticity);
  const rw = objectValue(q.runway);
  const mg = objectValue(q.margin);
  const cls = q.veto ? "bad" : q.grade === "caution" ? "warn" : q.grade === "ok" ? "ok" : "na";
  const labels = (q.labels || []).map((l) => `<span class="ev ${q.veto ? "bad" : "warn"}">${escapeHtml(l)}</span>`).join(" ");
  return `
    <div class="dim" style="grid-column:1/-1;border-left:3px solid var(--${cls === "bad" ? "red" : cls === "warn" ? "amber" : cls === "ok" ? "green" : "border"})">
      <span class="dim-k">财务体检（防诈骗 / 防基数幻觉）</span>
      <span class="dim-v"><span class="ev ${cls}">${escapeHtml(gradeZh(q.grade))}</span> ${labels}</span>
      <span class="dim-v">${escapeHtml(el.zh || "")}</span>
      <span class="dim-v">${escapeHtml(mg.zh || "")}</span>
      <span class="dim-v">${escapeHtml(rw.zh || "")}</span>
    </div>
  `;
}

function gradeZh(grade) {
  return { high_risk: "高风险", caution: "需谨慎", ok: "通过", unknown: "数据不足" }[grade] || "未体检";
}

function evidenceChips(row) {
  const m = evMarket(row), i = evImpact(row), s = evSec(row), f = evFlow(row), e = evExp(row);
  return [
    evChip("市场确认", m.cls, `市场 ${m.text}`),
    evChip("财务影响", i.cls, `影响 ${i.text}`),
    evChip("SEC 财务", s.cls, `SEC ${s.text}`),
    evChip("期权流", f.cls, `期权 ${f.text}`),
    evChip("预期差", e.cls, `预期 ${e.text}`),
  ].join(" ");
}

/* ------------------------------------------------------------------ */
/* OPPORTUNITIES table                                                */
/* ------------------------------------------------------------------ */
function renderOpportunities() {
  const rows = visibleOpportunities();
  if (!rows.length) {
    elements.contentArea.innerHTML = '<div class="empty">本轮自动报告暂无达到阈值的机会。</div>';
    return;
  }
  elements.contentArea.innerHTML = `
    <section class="section-head"><div><h3>机会清单 · ${rows.length} 项</h3><p>点任意行展开完整证据、分析判断与缺口。</p></div></section>
    ${renderOppTable(rows)}
  `;
  bindOppRows();
  bindCrossLinks();
}

function renderOppTable(rows) {
  if (!rows.length) return '<div class="empty">暂无达到阈值的机会。</div>';
  const body = rows.map(renderOppRow).join("");
  return `
    <div class="opp-wrap">
      <table class="opp">
        <thead>
          <tr>
            <th>动作</th>
            <th>Ticker</th>
            <th class="col-hide-md">公司</th>
            <th class="col-num">分数</th>
            <th class="col-num col-hide-sm">置信</th>
            <th>市场</th>
            <th class="col-hide-md">影响</th>
            <th class="col-hide-md">SEC</th>
            <th class="col-hide-sm">期权</th>
            <th class="col-hide-sm">预期</th>
            <th>催化剂</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function renderOppRow(row) {
  const article = articleOf(row);
  const action = row.action || actionFromScore(row.score);
  const key = rowKey(row);
  const open = state.openRows.has(key);
  const m = evMarket(row), i = evImpact(row), s = evSec(row), f = evFlow(row), e = evExp(row);
  const tickers = candidateTickers(row);
  return `
    <tr class="opp-row ${open ? "open" : ""}" data-key="${escapeHtml(key)}">
      <td><span class="act act-${escapeHtml(action)}">${escapeHtml(actionLabelZh(action))}</span>${qualityChip(row)}${squeezeChip(row)}${flowChip(row)}${pdfChip(row)}</td>
      <td class="col-ticker">${escapeHtml(tickers.join(", ") || "—")}</td>
      <td class="col-name col-hide-md">${escapeHtml(row.company_name || "Unknown")}</td>
      <td class="col-num">${Number(row.score || 0).toFixed(1)}</td>
      <td class="col-num col-hide-sm"><span class="conf ${confClass(row.confidence)}">${fmtConf(row.confidence)}</span></td>
      <td>${evChip("市场确认", m.cls, m.text)}</td>
      <td class="col-hide-md">${evChip("财务影响", i.cls, i.text)}</td>
      <td class="col-hide-md">${evChip("SEC 财务", s.cls, s.text)}</td>
      <td class="col-hide-sm">${evChip("期权流", f.cls, f.text)}</td>
      <td class="col-hide-sm">${evChip("预期差", e.cls, e.text)}</td>
      <td class="col-cat">${escapeHtml(article.title || "")}</td>
      <td class="caret">${open ? "▾" : "▸"}</td>
    </tr>
    ${open ? `<tr class="detail-row" data-detail="${escapeHtml(key)}"><td colspan="12">${renderDetail(row)}</td></tr>` : ""}
  `;
}

function renderDetail(row) {
  const article = articleOf(row);
  const action = row.action || actionFromScore(row.score);
  const market = objectValue(row.market_confirmation);
  const impact = objectValue(row.impact_assessment);
  const fin = objectValue(row.financial_snapshot);
  const model = objectValue(row.quick_model);
  const flow = objectValue(row.options_flow);
  const exp = objectValue(row.expectation_check);
  const dims = [
    ["市场确认", market.summary_zh],
    ["财务影响", impact.summary_zh ? `${impact.summary_zh} (${impact.impact_score ?? "n/a"}/5)` : ""],
    ["SEC 财务", fin.summary_zh],
    ["Quick Model", model.summary_zh],
    ["期权流", flow.summary_zh],
    ["预期差", exp.setup_zh || exp.summary_zh],
  ].filter(([, v]) => v);
  const dimCards = dims.map(([k, v]) => `<div class="dim"><span class="dim-k">${escapeHtml(k)}</span><span class="dim-v">${escapeHtml(v)}</span></div>`).join("");
  const missing = (row.missing_confirmations || []).slice(0, 6).map((item) => `<span class="ev warn">${escapeHtml(item)}</span>`).join(" ");
  const terms = (row.matched_terms || []).slice(0, 10).map((term) => `<span class="pill">${escapeHtml(term)}</span>`).join(" ");
  return `
    <div class="detail act-${escapeHtml(action)}">
      <div class="detail-decision">${escapeHtml(row.decision || "")}</div>
      ${row.analyst_take ? `<div class="detail-take">${escapeHtml(row.analyst_take)}</div>` : ""}
      <div class="row-meta"><span class="pill">证据层 ${escapeHtml(row.evidence_tier || "n/a")}</span><span class="pill">置信 ${fmtConf(row.confidence)}</span>${terms}</div>
      ${dimCards || renderQualityDim(row) || renderSqueezeDim(row) || renderFlowDim(row) || renderPdfDim(row) ? `<div class="detail-grid">${renderFlowDim(row)}${renderSqueezeDim(row)}${renderQualityDim(row)}${renderPdfDim(row)}${dimCards}</div>` : ""}
      ${missing ? `<div><span class="dim-k">还缺</span><div class="missing-list" style="margin-top:6px">${missing}</div></div>` : ""}
      ${renderTechnologyIntel(row)}
      ${renderEarningsAnalysis(row)}
      ${renderReadthroughAnalysis(row)}
      <div class="topcall-catalyst">
        ${safeArticleHref(article.link) ? `<a href="${safeArticleHref(article.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(article.source || "")} · 打开原文 ↗</a>` : ""}
        ${candidateTickers(row).slice(0, 1).map((t) => `<button class="small-action" type="button" data-diagnose-ticker="${escapeHtml(t)}">⚕ ${escapeHtml(t)} 错杀诊断 →</button>`).join("")}
        ${candidateTickers(row).slice(0, 1).map((t) => `<button class="small-action" type="button" data-earnings-jump="${escapeHtml(t)}">📊 财报工作台 →</button>`).join("")}
      </div>
    </div>
  `;
}

function jumpToDiagnose(ticker) {
  setView("diagnose");
  runDiagnose(ticker);
}

function jumpToEarnings(ticker) {
  state.selectedEarningsTicker = String(ticker || "").toUpperCase();
  setView("earnings");
}

function bindCrossLinks() {
  document.querySelectorAll("[data-diagnose-ticker]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      jumpToDiagnose(button.dataset.diagnoseTicker);
    });
  });
  document.querySelectorAll("[data-earnings-jump]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      jumpToEarnings(button.dataset.earningsJump);
    });
  });
}

function bindOppRows() {
  document.querySelectorAll(".opp-row").forEach((tr) => {
    tr.addEventListener("click", () => {
      const key = tr.dataset.key;
      if (state.openRows.has(key)) state.openRows.delete(key);
      else state.openRows.add(key);
      if (state.view === "brief") renderBrief();
      else renderOpportunities();
    });
  });
}

function fmtConf(conf) {
  const n = Number(conf);
  return Number.isFinite(n) && n > 0 ? n.toFixed(2) : "—";
}

function actionLabelZh(action) {
  const map = {
    research_now: "立即研究",
    track: "跟踪",
    identify_then_monitor: "待识别",
    monitor: "观察",
  };
  return map[action] || action || "观察";
}

/* ------------------------------------------------------------------ */
/* WATCHLIST                                                          */
/* ------------------------------------------------------------------ */
function renderWatchlist() {
  const rows = state.brief?.dynamic_watchlist || [];
  const query = state.query.trim().toLowerCase();
  const visible = query
    ? rows.filter((row) => textOf([row.company_name, row.decision_zh, ...(row.tickers || []), ...(row.sources || [])]).includes(query))
    : rows;
  elements.contentArea.innerHTML = visible.map(renderWatchlistItem).join("") || '<div class="empty">动态观察池还没有足够证据。</div>';
}

function renderWatchlistItem(row) {
  const article = row.latest_article || {};
  return `
    <article class="signal watchlist-item">
      <div>
        <div class="signal-title">
          <span class="band ${Number(row.conviction || 0) >= 4 ? "hard" : "watch"}">信念 ${escapeHtml(row.conviction || 0)}/5</span>
          <a href="${safeArticleHref(article.link) || "#"}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.company_name || "Unknown")}</a>
          <span class="pill">${escapeHtml(candidateTickers(row).join(", ") || "ticker待确认")}</span>
          ${qualityChip(row)}${squeezeChip(row)}${flowChip(row)}${pdfChip(row)}
        </div>
        <div class="terms">${escapeHtml(row.decision_zh || "")}</div>
        ${renderQualityDim(row) || renderSqueezeDim(row) || renderFlowDim(row) || renderPdfDim(row) ? `<div class="detail-grid">${renderFlowDim(row)}${renderSqueezeDim(row)}${renderQualityDim(row)}${renderPdfDim(row)}</div>` : ""}
        <div class="row-meta">${evidenceChips(row)}</div>
        ${renderTechnologyIntel(row)}
        ${renderEarningsAnalysis(row)}
        ${renderReadthroughAnalysis(row)}
        <div class="terms">${escapeHtml(row.why_zh || "")}</div>
      </div>
      <div class="score"><strong>${Number(row.max_score || 0).toFixed(1)}</strong><span>max</span></div>
    </article>
  `;
}

/* ------------------------------------------------------------------ */
/* EARNINGS                                                           */
/* ------------------------------------------------------------------ */
function renderEarnings() {
  const cal = state.calendar;
  if (!cal.loaded && !cal.loading) {
    loadEarningsMonth(cal.month);
  }
  const [year, month] = cal.month.split("-").map(Number);
  const items = cal.items || [];
  const detailsByTicker = earningsDetailsByTicker(items);
  const selectedTicker = selectedCalendarTicker(items, detailsByTicker);
  const selectedItem = items.find((item) => tickerOf(item) === selectedTicker) || null;
  const selectedDetail = selectedTicker ? detailsByTicker.get(selectedTicker) : null;
  if (selectedTicker) loadFinancials(selectedTicker);
  const note = cal.loading ? "加载中…" : `本月 ${items.length} 个观察标的财报`;

  elements.contentArea.innerHTML = `
    <section class="section-head">
      <div><h3>财报日历 · 被选中公司</h3><p>${escapeHtml(note)}。点公司查看详情；用 ◀ ▶ 翻月浏览整个季度。</p></div>
    </section>
    ${renderCalendarGrid(year, month, items, selectedTicker)}

    <section class="section-head">
      <div><h3>${selectedTicker ? `${escapeHtml(selectedTicker)} 财报详情` : "财报详情"}</h3><p>核心财务指标、资金投向、提到的公司/产业链对象，以及二阶 read-through。</p></div>
    </section>
    ${renderSelectedEarningsDetail(selectedItem, selectedDetail)}
  `;
  bindCalendarNav();
  bindEarningsButtons();
}

function renderCalendarGrid(year, month, items, selectedTicker) {
  const byDay = {};
  items.forEach((item) => {
    const iso = String(item.date || "");
    if (!iso) return;
    const day = Number(iso.split("-")[2]);
    (byDay[day] = byDay[day] || []).push(item);
  });
  const startIdx = (new Date(year, month - 1, 1).getDay() + 6) % 7; // Monday-first
  const daysInMonth = new Date(year, month, 0).getDate();
  const todayIso = todayLocalIso();

  const cells = [];
  for (let i = 0; i < startIdx; i++) cells.push('<div class="cal-cell cal-empty"></div>');
  for (let day = 1; day <= daysInMonth; day++) {
    const iso = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const evs = byDay[day] || [];
    const chips = evs
      .map((item) => {
        const ticker = tickerOf(item);
        const active = ticker === selectedTicker ? "active" : "";
        return `<button class="cal-ev ${active}" type="button" data-earnings-ticker="${escapeHtml(ticker)}" title="${escapeHtml((item.name || "") + " · " + timeZh(item.time || ""))}">${escapeHtml(ticker)}<span class="cal-ev-t">${escapeHtml(timeShort(item.time || ""))}</span></button>`;
      })
      .join("");
    cells.push(`<div class="cal-cell ${iso === todayIso ? "cal-today" : ""}"><div class="cal-daynum">${day}</div><div class="cal-evs">${chips}</div></div>`);
  }
  while (cells.length % 7 !== 0) cells.push('<div class="cal-cell cal-empty"></div>');

  const weekdays = ["一", "二", "三", "四", "五", "六", "日"].map((d) => `<div class="cal-wd">${d}</div>`).join("");
  return `
    <div class="calendar">
      <div class="cal-head">
        <button class="cal-nav" type="button" data-cal-nav="prev" aria-label="上个月">◀</button>
        <strong>${year} 年 ${month} 月</strong>
        <button class="cal-nav" type="button" data-cal-nav="next" aria-label="下个月">▶</button>
      </div>
      <div class="cal-grid">${weekdays}${cells.join("")}</div>
    </div>
  `;
}

function timeShort(value) {
  const low = String(value || "").toLowerCase();
  if (low.includes("before")) return "盘前";
  if (low.includes("after")) return "盘后";
  if (low.includes("during")) return "盘中";
  return "";
}

async function loadEarningsMonth(monthStr) {
  state.calendar.loading = true;
  state.calendar.loaded = true;
  try {
    const response = await fetch(`/api/earnings?month=${encodeURIComponent(monthStr)}`);
    const payload = await response.json();
    if (payload.ok) {
      state.calendar.month = monthStr;
      state.calendar.items = (payload.calendar && payload.calendar.items) || [];
      state.calendar.summary = (payload.calendar && payload.calendar.summary_zh) || "";
    }
  } catch (error) {
    showErrors([userFacingError(error)]);
  } finally {
    state.calendar.loading = false;
    if (state.view === "earnings") renderEarnings();
  }
}

function bindCalendarNav() {
  document.querySelectorAll("[data-cal-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      const [year, month] = state.calendar.month.split("-").map(Number);
      const shifted = new Date(year, month - 1 + (button.dataset.calNav === "next" ? 1 : -1), 1);
      state.selectedEarningsTicker = null;
      loadEarningsMonth(`${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, "0")}`);
    });
  });
}

function renderTodayEarningsBrief(items, detailsByTicker) {
  if (!items.length) return '<div class="empty">未来窗口内暂无重点财报。</div>';
  const today = todayLocalIso();
  let focus = items.filter((item) => item.date === today);
  if (!focus.length) {
    const upcoming = items.find((item) => String(item.date || "") > today);
    focus = upcoming ? [upcoming] : [items[0]];
  }
  return focus.map((item) => {
    const ticker = tickerOf(item);
    const detail = detailsByTicker.get(ticker);
    const analysis = objectValue(detail?.earnings_analysis);
    const metrics = (analysis.metrics || []).slice(0, 4).map((metric) => `${metric.metric}=${metric.value} ${metric.unit || ""}`).join("；");
    const readthrough = objectValue(detail?.readthrough_analysis);
    const readthroughCount = (readthrough.items || []).length;
    return `
      <article class="row">
        <div class="row-title">
          ${escapeHtml(ticker)} ${escapeHtml(item.name || "")}
          <span class="pill">${escapeHtml(item.status_zh || "")}</span>
          <span class="pill">${escapeHtml(timeZh(item.time || ""))}</span>
          ${detail ? '<span class="pill">已有原文拆解</span>' : '<span class="pill">等待财报原文</span>'}
        </div>
        <div class="row-meta">
          <span>日期=${escapeHtml(item.date || "")}</span>
          <span>EPS预期=${escapeHtml(item.eps_forecast || "n/a")}</span>
          <span>季度=${escapeHtml(item.fiscal_quarter_ending || "n/a")}</span>
          ${readthroughCount ? `<span>二阶对象=${readthroughCount}</span>` : ""}
        </div>
        <div class="terms">${escapeHtml(metrics || analysis.summary_zh || "尚未抓到可解析的财报正文；发布后下一轮会补核心指标、资金投向和二阶影响。")}</div>
      </article>
    `;
  }).join("");
}

function renderSelectedEarningsDetail(item, detail) {
  if (!item) return '<div class="empty">没有可展示的财报事件。</div>';
  const finState = state.financials[tickerOf(item)];
  return `
    <div class="content-grid">
      ${renderFinancialTiles(finState, item)}
      ${renderRevenueTrend(finState)}
      ${renderCapitalAllocation(finState)}
      ${renderTeardown(finState)}
      ${renderHolders(tickerOf(item))}
      ${renderOptionsStructureCard(tickerOf(item))}
      ${renderFilings(finState)}
      ${detail ? renderEarningsCard(detail) : renderNoReleaseCard(item)}
    </div>
  `;
}

function renderRevenueTrend(finState) {
  const snap = finState && typeof finState === "object" ? finState.snapshot : null;
  const trend = snap && typeof snap.revenue_trend === "object" ? snap.revenue_trend : null;
  if (!trend || trend.status !== "ok" || !(trend.quarters || []).length) return "";
  const quarters = trend.quarters || [];
  const maxRev = Math.max(...quarters.map((q) => Number(q.revenue_musd) || 0), 1);
  const bars = quarters.map((q) => {
    const h = Math.max(8, Math.round((Number(q.revenue_musd) || 0) / maxRev * 56));
    const yoy = q.yoy_pct == null ? "n/a" : `${Number(q.yoy_pct) >= 0 ? "+" : ""}${Number(q.yoy_pct).toFixed(0)}%`;
    const cls = q.yoy_pct == null ? "" : Number(q.yoy_pct) >= 0 ? "rev-up" : "rev-down";
    return `<div class="rev-q" title="${escapeHtml(q.end)} · ${escapeHtml(formatMusd(q.revenue_musd))} · YoY ${escapeHtml(yoy)}">
        <span class="rev-yoy ${cls}">${escapeHtml(yoy)}</span>
        <span class="rev-bar" style="height:${h}px"></span>
        <span class="rev-end">${escapeHtml(String(q.end).slice(2, 7))}</span>
      </div>`;
  }).join("");
  const verdictCls = { accelerating: "ok", stable: "warn", decelerating: "bad", declining: "bad" }[trend.verdict] || "na";
  return `
    <article class="row">
      <div class="row-title">本季判读 · 营收增速 <span class="ev ${verdictCls}">${escapeHtml(trendVerdictZh(trend.verdict))}</span></div>
      <div class="rev-trend">${bars}</div>
      <div class="terms">${escapeHtml(trend.verdict_zh || "")}</div>
      <div class="terms">来源：SEC companyfacts 单季营收（XBRL），同比按相隔一年的季度计算，不受财年错位影响。</div>
    </article>
  `;
}

function trendVerdictZh(verdict) {
  return { accelerating: "加速", decelerating: "减速", stable: "平稳", declining: "同比转负" }[verdict] || "数据不足";
}

function renderOptionsStructureCard(ticker) {
  const o = state.optionsStructure[ticker];
  let body;
  if (o === undefined) {
    body = `<button class="small-action" type="button" data-options="${escapeHtml(ticker)}">📈 查看期权结构（CBOE 全链 · GEX / IV / P-C）</button>`;
  } else if (o === "loading") {
    body = `<div class="terms">正在拉取 CBOE 全链并聚合 GEX…（约 3–10 秒）</div>`;
  } else if (!o || o.status !== "ok") {
    body = `<div class="terms">${escapeHtml((o && o.summary_zh) || "期权链不可用（可能无期权或 CBOE 限流）。")}</div>`;
  } else {
    const gex = objectValue(o.gex);
    const term = objectValue(o.iv_term);
    const pc = objectValue(o.put_call);
    const tiles = [
      statTile("GEX 代理", gex.regime === "positive_gamma" ? "净值估算 +" : gex.regime === "negative_gamma" ? "净值估算 −" : "n/a"),
      statTile("Gamma 翻转位", "未估算"),
      statTile("Call GEX 峰", gex.call_wall != null ? `$${gex.call_wall}` : "n/a"),
      statTile("Put GEX 峰", gex.put_wall != null ? `$${gex.put_wall}` : "n/a"),
      statTile("P/C OI", pc.oi_ratio != null ? String(pc.oi_ratio) : "n/a"),
      statTile("IV30", o.iv30 != null ? `${Number(o.iv30).toFixed(1)}%` : "n/a", term.inverted ? "accent" : ""),
    ].join("");
    const ivNote = term.inverted && term.front
      ? `近月 ATM IV ${(Number(term.front.atm_iv) * 100).toFixed(0)}% 高于远月——期权市场在为财报/短期事件定价大幅波动。`
      : "IV 期限结构正常，期权市场未对近期事件定价异常波动。";
    const strikeMap = objectValue(o.strike_map);
    body = `
      <div class="stat-tiles">${tiles}</div>
      <div class="terms">${escapeHtml(ivNote)}</div>
      ${strikeMap.status === "ok" ? `<div class="terms">📍 ${escapeHtml(strikeMap.summary_zh || "")}</div>` : ""}
      <div class="terms">${escapeHtml(o.summary_zh || "")}</div>
      <div class="terms">${escapeHtml(gex.flip_reason_zh || "OI 符号模型不等于实际做市商持仓；OI 本身不显示买卖方向。")}</div>
      <div class="terms">${escapeHtml(o.source_policy_zh || "")}</div>
    `;
  }
  return `
    <article class="row">
      <div class="row-title">📈 期权怎么看这只股（CBOE 延迟全链）</div>
      ${body}
    </article>
  `;
}

async function loadOptionsStructure(ticker) {
  if (!ticker || state.optionsStructure[ticker] === "loading") return;
  state.optionsStructure[ticker] = "loading";
  if (state.view === "earnings") renderEarnings();
  try {
    const response = await fetch(`/api/options_structure?ticker=${encodeURIComponent(ticker)}`);
    const payload = await response.json();
    state.optionsStructure[ticker] = payload.ok ? payload : null;
  } catch (error) {
    state.optionsStructure[ticker] = null;
  }
  if (state.view === "earnings") renderEarnings();
}

function renderHolders(ticker) {
  const h = state.holders[ticker];
  let body;
  if (h === undefined) {
    body = `<button class="small-action" type="button" data-holders="${escapeHtml(ticker)}">🏛️ 查看 13F 机构持仓（联网检索 SEC，较慢）</button>`;
  } else if (h === "loading") {
    const p = state.holdersProgress[ticker] || { stage_zh: "排队中", done: 0, total: 0 };
    const pct = p.total > 0 ? Math.round((p.done / p.total) * 100) : 0;
    body = `
      <div class="holders-progress">
        <div class="hp-bar"><span style="width:${pct}%"></span></div>
        <div class="terms">${escapeHtml(p.stage_zh)}${p.total > 0 ? ` ${p.done}/${p.total}` : ""}…（全文搜索 + 双季信息表对比，约 30–60 秒）</div>
      </div>`;
  } else if (!h || h.status !== "ok" || !(h.holders || []).length) {
    body = `<div class="terms">${escapeHtml((h && h.summary_zh) || "近一季 13F 申报中未检索到机构持仓（或 SEC 限流）。")}</div>`;
  } else {
    const rows = (h.holders || []).slice(0, 14).map((m) => {
      const changeCls = { increased: "ok", new: "ok", reduced: "bad", unchanged: "na" }[m.change_label] || "na";
      const changeChip = m.change_zh && m.change_label !== "unknown"
        ? `<span class="ev ${changeCls}" title="对比该机构上一份 13F（${escapeHtml(m.prev_filed || "上一季")}）">${escapeHtml(m.change_zh)}</span>`
        : "";
      return `
      <div class="holder-row${m.notable ? " holder-notable" : ""}">
        <span class="holder-val">${escapeHtml(fmtUsd(m.value_usd))}</span>
        <span class="holder-name">${m.notable ? "⭐ " : ""}${escapeHtml(m.manager || "")} ${changeChip}</span>
        <span class="holder-sh">${escapeHtml(fmtShares(m.shares))} 股 · ${escapeHtml(m.filed || "")}</span>
      </div>
    `;
    }).join("");
    body = `<div class="holder-list">${rows}</div><div class="terms">${escapeHtml(h.summary_zh || "")}</div>`;
  }
  return `
    <article class="row">
      <div class="row-title">🏛️ 谁在持有 · 13F 机构持仓（SEC 实际申报，反向检索）</div>
      ${body}
    </article>
  `;
}

async function loadHolders(ticker) {
  if (!ticker || state.holders[ticker] === "loading") return;
  state.holders[ticker] = "loading";
  if (state.view === "earnings") renderEarnings();
  const poll = setInterval(async () => {
    if (state.holders[ticker] !== "loading") { clearInterval(poll); return; }
    try {
      const r = await fetch(`/api/holders_progress?ticker=${encodeURIComponent(ticker)}`);
      state.holdersProgress[ticker] = await r.json();
      if (state.view === "earnings" && state.holders[ticker] === "loading") renderEarnings();
    } catch (e) { /* progress is cosmetic */ }
  }, 1500);
  try {
    const response = await fetch(`/api/holders?ticker=${encodeURIComponent(ticker)}`);
    const payload = await response.json();
    state.holders[ticker] = payload.ok ? payload : null;
  } catch (error) {
    state.holders[ticker] = null;
  }
  clearInterval(poll);
  delete state.holdersProgress[ticker];
  if (state.view === "earnings") renderEarnings();
}

function fmtUsd(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "n/a";
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toFixed(0)}`;
}

function fmtShares(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "n/a";
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return `${v}`;
}

function renderCapitalAllocation(finState) {
  const snap = finState && typeof finState === "object" ? finState.snapshot : null;
  const cap = snap && typeof snap.capital_allocation_musd === "object" ? snap.capital_allocation_musd : null;
  if (!cap) return "";
  const labels = { rd: "研发投入", capex: "资本开支", sga: "销售/管理费用", buyback: "股票回购", dividends: "现金分红", acquisitions: "并购支出" };
  const tiles = Object.keys(labels)
    .filter((k) => cap[k] != null)
    .map((k) => statTile(labels[k], formatMusd(cap[k]), k === "acquisitions" && cap[k] ? "accent" : ""))
    .join("");
  if (!tiles) return "";
  return `
    <article class="row">
      <div class="row-title">钱花在哪里（TTM · SEC 结构化）</div>
      <div class="stat-tiles">${tiles}</div>
      <div class="terms">来源：SEC companyfacts 现金流量表/利润表标签（研发、资本开支、回购、分红、并购）。</div>
    </article>
  `;
}

function renderTeardown(finState) {
  const t = finState && typeof finState === "object" ? finState.teardown : null;
  if (!t || t.status !== "ok") return "";
  const flows = (t.money_flows || []).slice(0, 8).map((m) => {
    const target = m.target_ticker ? `<span class="flow-target">${escapeHtml(m.target_ticker)}</span> ${escapeHtml(m.target_name || "")}` : "";
    return `<div class="flow-row" title="${escapeHtml(m.context || "")}">
        <span class="flow-amt">${escapeHtml(formatMusd(m.amount_musd))}</span>
        <span class="flow-use">${escapeHtml(m.purpose_zh || "")}</span>
        <span class="flow-to">${target}</span>
      </div>`;
  }).join("");
  const companies = (t.named_companies || []).map((c) => `
    <div class="named-co" title="${escapeHtml(c.context || "")}">
      <span class="named-tk">${escapeHtml(c.ticker)}</span>
      <span class="named-nm">${escapeHtml(c.name)}</span>
      <span class="named-ctx">原文：${escapeHtml(c.context || "")}</span>
    </div>
  `).join("");
  const conc = (t.customer_concentration || []).slice(0, 4).map((c) =>
    `<div class="terms">• ${escapeHtml(c.context || "")}</div>`
  ).join("");
  return `
    <article class="row">
      <div class="row-title">财报全文拆解 <span class="pill">${escapeHtml(t.form || "")} ${escapeHtml(t.filed || "")}</span></div>
      <div class="terms">来自 SEC 财报正文的规则化抽取：<strong>金额与用途较可靠</strong>；公司与集中度为<strong>线索</strong>，关系请对照原文判断（悬停看英文原文）。</div>
      ${flows ? `<div class="teardown-h">💰 大额资金去向（金额 → 用途 → 对象公司）</div><div class="flow-list">${flows}</div>` : ""}
      ${companies ? `<div class="teardown-h">🏢 正文点名、已对应美股代码的公司（线索）</div><div class="named-list">${companies}</div>` : ""}
      ${conc ? `<div class="teardown-h">📊 客户集中度（仅在正文明确披露时）</div>${conc}` : ""}
    </article>
  `;
}

function renderFinancialTiles(finState, item) {
  const snap = finState && typeof finState === "object" ? finState.snapshot : null;
  const tiles = [statTile("EPS 预期（一致）", escapeHtml(item.eps_forecast || "n/a"), "blue")];
  let note = "";
  const ready = snap && (snap.status === "ok" || snap.status === "partial" || snap.revenue_musd != null);
  if (ready) {
    tiles.push(statTile("TTM 营收", formatMusd(snap.ttm_revenue_musd != null ? snap.ttm_revenue_musd : snap.revenue_musd), "accent"));
    tiles.push(statTile("毛利率", snap.gross_margin_pct != null ? `${Number(snap.gross_margin_pct).toFixed(1)}%` : "n/a", "accent"));
    tiles.push(statTile("最新年度营收", formatMusd(snap.revenue_musd)));
    tiles.push(statTile("现金及等价物", formatMusd(snap.cash_musd)));
    tiles.push(statTile("季度经营现金流", formatMusd(snap.quarterly_operating_cash_flow_musd)));
    note = `来源：SEC companyfacts（XBRL 实际披露）${snap.period_end ? ` · 截至 ${escapeHtml(snap.period_end)}` : ""}${snap.fiscal_year ? ` · FY${escapeHtml(String(snap.fiscal_year))}` : ""}`;
  } else if (finState === "loading" || finState === undefined) {
    note = "正在从 SEC 拉取实际财务…";
  } else {
    note = "SEC 实际财务暂不可用（该标的可能不是美国注册申报人，或暂无标准 XBRL 标签）。";
  }
  return `
    <article class="row fin-panel">
      <div class="row-title">${escapeHtml(tickerOf(item))} ${escapeHtml(item.name || "")} · 核心财务（SEC 实际披露）</div>
      <div class="stat-tiles">${tiles.join("")}</div>
      <div class="terms">${note}</div>
    </article>
  `;
}

function renderFilings(finState) {
  const filings = finState && typeof finState === "object" && Array.isArray(finState.filings) ? finState.filings : [];
  if (!filings.length) {
    if (finState === "loading" || finState === undefined) return "";
    return "";
  }
  const rows = filings.slice(0, 8).map((f) => {
    const itemChips = (f.items_zh || [])
      .map((it) => `<span class="ev ${it.notable ? "warn" : "na"}" title="8-K Item ${escapeHtml(it.code)}">${escapeHtml(it.label_zh)}</span>`)
      .join(" ");
    return `
    <a class="filing-row" href="${safeArticleHref(f.doc_url) || "#"}" target="_blank" rel="noopener noreferrer">
      <span class="filing-form">${escapeHtml(f.form || "")}</span>
      <span class="filing-date">${escapeHtml(f.filed || "")}</span>
      <span class="filing-desc">${itemChips || escapeHtml(f.description || _filingFormZh(f.form))}</span>
      <span class="filing-open">打开 ↗</span>
    </a>
  `;
  }).join("");
  return `
    <article class="row">
      <div class="row-title">最新 SEC 文件（EDGAR 实际申报 · 权威原文）</div>
      <div class="filing-list">${rows}</div>
      <div class="terms">10-Q/10-K 为季度/年度财报全文，8-K 为重大事件（含业绩 release）。点击直达 SEC EDGAR 原文。</div>
    </article>
  `;
}

function _filingFormZh(form) {
  const map = { "10-K": "年度报告", "10-Q": "季度报告", "8-K": "重大事件 / 业绩公告", "20-F": "外国公司年报", "6-K": "外国公司中期报告" };
  return map[form] || "SEC 文件";
}

function renderNoReleaseCard(item) {
  return `
    <article class="row">
      <div class="row-title">本次财报 release 拆解 <span class="pill">${escapeHtml(item.status_zh || "")}</span></div>
      <div class="row-meta"><span>日期=${escapeHtml(item.date || "")}</span><span>时间=${escapeHtml(timeZh(item.time || ""))}</span><span>来源=Nasdaq 日历</span></div>
      <div class="terms">尚未在新闻流抓到该公司的财报 release 原文。上方为 SEC 实际披露财务；待公司发布 release/10-Q/call transcript 后，这里会补充本季的 beat/miss、资金投向与二阶 read-through（系统不会用模板伪造）。</div>
    </article>
  `;
}

function statTile(label, value, variant) {
  return `<div class="stat-tile ${variant || ""}"><span class="st-v">${value}</span><span class="st-k">${label}</span></div>`;
}

function formatMusd(musd) {
  const v = Number(musd);
  if (musd == null || !Number.isFinite(v)) return "n/a";
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(2)}B`;
  return `$${v.toFixed(0)}M`;
}

async function loadFinancials(ticker) {
  if (!ticker || state.financials[ticker] !== undefined) return;
  state.financials[ticker] = "loading";
  try {
    const response = await fetch(`/api/financials?ticker=${encodeURIComponent(ticker)}`);
    const payload = await response.json();
    state.financials[ticker] = payload.ok ? { snapshot: payload.snapshot, filings: payload.filings || [], teardown: payload.teardown || {} } : null;
  } catch (error) {
    state.financials[ticker] = null;
  }
  if (state.view === "earnings") renderEarnings();
}

function earningsDetailsByTicker(calendarItems) {
  const nameByTicker = new Map((calendarItems || []).map((i) => [tickerOf(i), String(i.name || "")]));
  const details = new Map();
  visibleCandidates().forEach((candidate) => {
    const analysis = objectValue(candidate.earnings_analysis);
    // Only a genuinely parsed earnings release counts — not any article that
    // merely mentions the ticker (that caused e.g. NVDA -> an IREN story).
    if (analysis.status !== "earnings_release_detected") return;
    if (isStale(articleOf(candidate).published)) return; // drop >1y-old releases
    const title = String(articleOf(candidate).title || "");
    candidateTickers(candidate).forEach((ticker) => {
      if (!nameByTicker.has(ticker)) return;
      if (!isEarningsSubject(title, candidate.company_name, nameByTicker.get(ticker))) return;
      const current = details.get(ticker);
      if (!current || earningsQualityScore(candidate) > earningsQualityScore(current)) {
        details.set(ticker, candidate);
      }
    });
  });
  return details;
}

function isStale(published, maxDays = 365) {
  if (!published) return false; // undated -> keep
  const t = Date.parse(published);
  if (Number.isNaN(t)) return false;
  return (Date.now() - t) / 86400000 > maxDays;
}

function isEarningsSubject(title, companyName, calendarName) {
  // The company must be the article's subject (its name at the head of the
  // title, or the discovered company_name), not just a mention deeper in.
  const firstWord = String(calendarName || "").toLowerCase().split(/[\s,.]+/)[0];
  if (!firstWord || firstWord.length < 3) return false;
  const head = title.toLowerCase().slice(0, 45);
  return head.includes(firstWord) || String(companyName || "").toLowerCase().includes(firstWord);
}

function earningsQualityScore(candidate) {
  const analysis = objectValue(candidate.earnings_analysis);
  const readthrough = objectValue(candidate.readthrough_analysis);
  let score = Number(candidate.score || 0) / 10;
  if (analysis.read_depth === "full_release_html") score += 25;
  score += (analysis.metrics || []).length * 8;
  score += (analysis.spend_allocation || []).length * 4;
  score += (analysis.mentioned_companies || []).length * 4;
  score += (readthrough.items || []).length * 6;
  if (String(articleOf(candidate).title || "").toLowerCase().includes("financial results")) score += 8;
  return score;
}

function selectedCalendarTicker(items, detailsByTicker) {
  const calendarTickers = new Set(items.map(tickerOf).filter(Boolean));
  if (state.selectedEarningsTicker && calendarTickers.has(state.selectedEarningsTicker)) return state.selectedEarningsTicker;
  const today = todayLocalIso();
  const todayWithDetail = items.find((item) => item.date === today && detailsByTicker.has(tickerOf(item)));
  if (todayWithDetail) return tickerOf(todayWithDetail);
  const todayItem = items.find((item) => item.date === today);
  if (todayItem) return tickerOf(todayItem);
  const firstWithDetail = items.find((item) => detailsByTicker.has(tickerOf(item)));
  if (firstWithDetail) return tickerOf(firstWithDetail);
  return items.length ? tickerOf(items[0]) : null;
}

function bindEarningsButtons() {
  document.querySelectorAll("[data-earnings-ticker]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedEarningsTicker = button.dataset.earningsTicker;
      window.history.replaceState(null, "", `#earnings:${state.selectedEarningsTicker}`);
      renderEarnings();
    });
  });
  document.querySelectorAll("[data-holders]").forEach((button) => {
    button.addEventListener("click", () => loadHolders(button.dataset.holders));
  });
  document.querySelectorAll("[data-options]").forEach((button) => {
    button.addEventListener("click", () => loadOptionsStructure(button.dataset.options));
  });
}

function renderEarningsCard(candidate) {
  const article = articleOf(candidate);
  return `
    <article class="signal earnings-card">
      <div>
        <div class="signal-title">
          <span class="band hard">财报</span>
          <a href="${safeArticleHref(article.link) || "#"}" target="_blank" rel="noopener noreferrer">${escapeHtml(candidate.company_name || "Unknown")}</a>
          <span class="pill">${escapeHtml(candidateTickers(candidate).join(", ") || "ticker待确认")}</span>
        </div>
        <div class="meta">${escapeHtml(article.source || "unknown")} · ${escapeHtml(article.title || "")}</div>
        ${renderEarningsAnalysis(candidate)}
        ${renderReadthroughAnalysis(candidate)}
      </div>
      <div class="score"><strong>${Number(candidate.score || 0).toFixed(1)}</strong><span>score</span></div>
    </article>
  `;
}

/* ------------------------------------------------------------------ */
/* TECHNOLOGY                                                         */
/* ------------------------------------------------------------------ */
function renderTechnology() {
  const allCandidates = visibleCandidates().filter(hasTechnologyIntel);
  const candidates = recentTechnologyCandidates(allCandidates);
  const historicalCount = allCandidates.length - candidates.length;
  elements.contentArea.innerHTML = `
    <section class="section-head">
      <div><h3>技术前沿任务</h3><p>近 14 天文章按发布时间倒序；无发布时间的来源只保留最近 3 天首次抓取的条目。${historicalCount ? `另有 ${historicalCount} 条旧线索，可在机会页搜索。` : ""}</p></div>
    </section>
    <div class="content-grid technology-results">${candidates.map(renderTechnologyCard).join("") || '<div class="empty">近 14 天暂无明确技术路线文章。</div>'}</div>
  `;
}

function renderTechnologyCard(candidate) {
  const article = articleOf(candidate);
  return `
    <article class="signal technology-card">
      <div>
        <div class="signal-title">
          <span class="band watch">技术</span>
          <a href="${safeArticleHref(article.link) || "#"}" target="_blank" rel="noopener noreferrer">${escapeHtml(candidate.company_name || "Unknown")}</a>
          <span class="pill">${escapeHtml(candidateTickers(candidate).join(", ") || "ticker待确认")}</span>
        </div>
        <div class="meta">${escapeHtml(article.source || "unknown")} · ${escapeHtml(article.title || "")}</div>
        ${technologyDateMeta(candidate)}
        ${renderTechnologyCardIntel(candidate)}
      </div>
      <div class="score"><strong>${Number(candidate.score || 0).toFixed(1)}</strong><span>score</span></div>
    </article>
  `;
}

function renderTechnologyCardIntel(candidate) {
  const intel = objectValue(candidate.technology_intel);
  if (!intel.status || intel.status === "not_technology_signal") return "";
  const analysis = objectValue(candidate.readthrough_analysis);
  const themes = (intel.themes || []).slice(0, 4)
    .map((item) => `<span class="pill">${escapeHtml(techThemeZh(item.theme))}</span>`).join("");
  const companies = intel.mentioned_companies || [];
  const companyTags = companies.slice(0, 5)
    .map((item) => `<span class="pill">${escapeHtml(item.ticker)} ${escapeHtml(item.name || "")}</span>`).join("");
  const extraCompanies = companies.length > 5 ? `<span class="tech-more">+${companies.length - 5}</span>` : "";
  const watchPoints = (intel.watch_points_zh || []).slice(0, 5)
    .map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const readthroughSummary = analysis.status && analysis.status !== "no_readthrough"
    ? analysis.summary_zh || "查看下游公司验证状态"
    : "查看技术证据与验证要点";
  const details = [
    intel.read_through_zh ? `<p>${escapeHtml(intel.read_through_zh)}</p>` : "",
    watchPoints ? `<ul class="technology-checklist">${watchPoints}</ul>` : "",
    intel.limitations_zh ? `<p class="technology-limitation">${escapeHtml(intel.limitations_zh)}</p>` : "",
    renderReadthroughAnalysis(candidate),
  ].filter(Boolean).join("");
  return `
    <div class="technology-card-insights">
      <div class="technology-route-line"><span class="band watch">技术路线</span><span>${escapeHtml(intel.summary_zh || "技术来源命中")}</span></div>
      ${themes ? `<div class="technology-card-tags">${themes}</div>` : ""}
      ${companyTags ? `<div class="technology-company-map"><span>关联公司</span><div>${companyTags}${extraCompanies}</div></div>` : ""}
      ${details ? `<details class="technology-details"><summary>${escapeHtml(readthroughSummary)}</summary><div class="technology-details-body">${details}</div></details>` : ""}
    </div>
  `;
}

/* ------------------------------------------------------------------ */
/* MARKET                                                             */
/* ------------------------------------------------------------------ */
/* ------------------------------------------------------------------ */
/* DIAGNOSE — ticker mispricing workbench                              */
/* ------------------------------------------------------------------ */
async function runDiagnose(ticker) {
  const symbol = String(ticker || "").toUpperCase().trim();
  if (!symbol) return;
  state.diagnose = { ticker: symbol, loading: true, result: null, error: "" };
  renderDiagnose();
  try {
    const response = await fetch(`/api/diagnose?ticker=${encodeURIComponent(symbol)}`);
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "诊断失败");
    state.diagnose = { ticker: symbol, loading: false, result: payload, error: "" };
  } catch (error) {
    state.diagnose = { ticker: symbol, loading: false, result: null, error: String(error.message || error) };
  }
  if (state.view === "diagnose") renderDiagnose();
}

function diagnoseVerdictClass(verdict) {
  if (verdict === "mispriced_candidate") return "risk_on";
  if (verdict === "watchlist") return "neutral";
  return "risk_off";
}

function renderDiagnose() {
  const diag = state.diagnose || {};
  const result = diag.result;
  const form = `
    <section class="row">
      <div class="row-title">输入 ticker，回答一个问题：这只股是被错杀，还是真的坏了？</div>
      <div class="row-meta diagnose-form">
        <input id="diagTicker" type="text" placeholder="例如 CRDO / SMCI / MU" value="${escapeHtml(diag.ticker || "")}"
               style="text-transform:uppercase" maxlength="6" aria-label="Ticker">
        <button id="diagRun" class="small-action" type="button">诊断</button>
        ${diag.loading ? "<span>正在拉取 FINRA 卖空 / CBOE 期权链 / 价格序列…（首次约 10-30 秒）</span>" : ""}
      </div>
      <div class="terms">数据源：FINRA 日度卖空、CBOE 延迟期权链（含希腊值）、Yahoo 价格、本地雷达新闻命中。全部免费公开数据，缺数据时明示，不伪造。</div>
    </section>
  `;
  let body = "";
  if (diag.error) {
    body = `<div class="errors">诊断失败：${escapeHtml(diag.error)}</div>`;
  } else if (result && result.status === "insufficient_data") {
    body = `<div class="empty">${escapeHtml(result.summary_zh || "数据不足，无法诊断。")}</div>`;
  } else if (result && result.status === "ok") {
    body = renderDiagnoseResult(result);
  } else if (!diag.loading) {
    body = '<div class="empty">先诊断一只你怀疑被错杀的股票。诊断结论会自动存档，未来用 report 机制回测命中率。</div>';
  }
  elements.contentArea.innerHTML = form + body;
  const input = document.querySelector("#diagTicker");
  const button = document.querySelector("#diagRun");
  if (button && input) {
    button.addEventListener("click", () => runDiagnose(input.value));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") runDiagnose(input.value);
    });
    if (!diag.loading && !result) input.focus();
  }
}

function renderMarketStrip(market) {
  if (!market || market.status !== "ok") return "";
  const postureCls = { friendly: "ok", neutral: "warn", hostile: "bad" }[market.posture] || "na";
  const chips = [];
  [market.spy, market.qqq, market.spx].forEach((idx) => {
    if (idx && idx.status === "ok") {
      const regimeZh = idx.regime === "positive_gamma" ? "净 GEX 估算 +" : "净 GEX 估算 −";
      chips.push(`<span class="ev warn" title="CBOE 延迟期权链的 OI 符号模型，不代表实际做市商持仓">${escapeHtml(idx.ticker)} ${regimeZh}</span>`);
    }
  });
  const dp = objectValue(market.dark_pool);
  if (dp.status === "ok") {
    const trendZh = { rising: "空压↑", falling: "空压↓", flat: "空压平" }[dp.trend] || "";
    chips.push(`<span class="ev ${dp.trend === "falling" ? "ok" : dp.trend === "rising" ? "bad" : "na"}">全市场卖空 ${(Number(dp.latest_ratio) * 100).toFixed(0)}% ${trendZh}</span>`);
  }
  const vix = objectValue(market.vix);
  if (vix.status === "ok") {
    chips.push(`<span class="ev ${vix.regime === "calm" ? "ok" : vix.regime === "fear" ? "bad" : "warn"}">VIX ${escapeHtml(vix.vix)}</span>`);
  }
  return `
    <section class="row market-strip">
      <div class="row-title">大盘环境 <span class="ev ${postureCls}">${escapeHtml({ friendly: "友好", neutral: "中性", hostile: "不友好" }[market.posture] || "未知")}</span> ${chips.join(" ")}</div>
      <div class="terms">${escapeHtml(market.posture_zh || "")}</div>
    </section>
  `;
}

function renderActionPlan(plan) {
  if (!plan || !plan.stance_zh) return "";
  const stanceCls = { plan_entry: "ok", watch: "warn", stand_aside: "bad" }[plan.stance] || "na";
  const levels = (plan.levels || []).map((level) => `
    <div class="level-row">
      <span class="level-price">$${escapeHtml(level.price)}</span>
      <span class="terms">${escapeHtml(level.label_zh)}</span>
    </div>
  `).join("");
  const lines = (plan.playbook_zh || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");
  return `
    <section class="row">
      <div class="row-title">行动剧本 <span class="ev ${stanceCls}">${escapeHtml(plan.stance_zh)}</span></div>
      ${levels ? `<div class="level-list">${levels}</div>` : ""}
      <ul class="terms">${lines}<li>${escapeHtml(plan.market_adjustment_zh || "")}</li></ul>
      <div class="terms">${escapeHtml(plan.disclaimer_zh || "")}</div>
    </section>
  `;
}

function renderStrikeLadder(options) {
  const map = options && typeof options.strike_map === "object" ? options.strike_map : null;
  if (!map || map.status !== "ok" || !(map.top_oi || []).length) return "";
  const spot = Number(options.spot);
  const rows = [...map.top_oi].sort((a, b) => b.strike - a.strike);
  const maxOi = Math.max(...rows.map((r) => Number(r.call_oi) + Number(r.put_oi)), 1);
  let spotInserted = false;
  const html = [];
  rows.forEach((r) => {
    if (!spotInserted && Number.isFinite(spot) && spot > Number(r.strike)) {
      html.push(`<div class="ladder-spot">— 现价 $${spot} —</div>`);
      spotInserted = true;
    }
    const callW = Math.round((Number(r.call_oi) / maxOi) * 100);
    const putW = Math.round((Number(r.put_oi) / maxOi) * 100);
    const marks = [];
    if (Number(r.strike) === Number(map.max_call_oi_strike)) marks.push("Call OI 峰");
    if (Number(r.strike) === Number(map.max_put_oi_strike)) marks.push("Put OI 峰");
    if (Number(r.strike) === Number(map.max_volume_strike)) marks.push("成交量峰");
    html.push(`
      <div class="ladder-row" title="call OI=${escapeHtml(fmtShares(r.call_oi))} / put OI=${escapeHtml(fmtShares(r.put_oi))} / 今日成交 ${escapeHtml(fmtShares(Number(r.call_volume) + Number(r.put_volume)))}">
        <span class="ladder-strike">$${escapeHtml(r.strike)}${marks.length ? ` <span class="pill">${marks.join("·")}</span>` : ""}</span>
        <span class="ladder-bars"><span class="lb-call" style="width:${callW}%"></span><span class="lb-put" style="width:${putW}%"></span></span>
      </div>`);
  });
  if (!spotInserted && Number.isFinite(spot)) html.push(`<div class="ladder-spot">— 现价 $${spot} —</div>`);
  return `
    <section class="row">
      <div class="row-title">期权未平仓分布</div>
      <div class="ladder-legend"><span class="lb-call-dot"></span>call 未平仓 <span class="lb-put-dot"></span>put 未平仓</div>
      ${html.join("")}
      <div class="terms">${escapeHtml(map.summary_zh || "")} 未平仓量与成交量都不显示主动买方/卖方，不能单独作为支撑或阻力判断。</div>
    </section>
  `;
}

function renderDiagnoseResult(result) {
  const premise = objectValue(result.premise);
  const componentsBlock = (result.score_components || []).map((component) => `
    <article class="row metric-row">
      <div class="row-title">${escapeHtml(component.name)} <span class="pill">${escapeHtml(component.points)}/${escapeHtml(component.max)}</span></div>
      <div class="terms">${escapeHtml(component.reason_zh || "")}</div>
    </article>
  `).join("");
  const triggers = (result.triggers_zh || []).map((trigger) => `<li>${escapeHtml(trigger)}</li>`).join("");
  const parts = objectValue(result.components);
  const sectionSummaries = [
    ["跌幅归因 / 动量", objectValue(parts.relative_strength).summary_zh],
    ["空头行为（FINRA 日度）", objectValue(parts.positioning).summary_zh],
    ["期权结构（GEX / IV / P-C）", objectValue(parts.options_structure).summary_zh],
    ["市场恐惧（VIX）", objectValue(parts.vix).summary_zh],
  ].filter(([, text]) => Boolean(text)).map(([label, text]) => `
    <article class="row">
      <div class="row-title">${escapeHtml(label)}</div>
      <div class="terms">${escapeHtml(text)}</div>
    </article>
  `).join("");
  const news = objectValue(parts.radar_news);
  const newsRows = (news.recent || []).slice(0, 6).map((hit) => `
    <article class="row">
      <a href="${safeArticleHref(hit.link) || "#"}" target="_blank" rel="noopener noreferrer">${escapeHtml(hit.title || "Untitled")}</a>
      <div class="row-meta">
        <span class="pill">${escapeHtml(hit.evidence_tier || "signal")}</span>
        <span>${escapeHtml(hit.published || "")}</span>
      </div>
    </article>
  `).join("");
  const gaps = (result.data_gaps || []).join("、");
  const optionsPolicy = objectValue(parts.options_structure).source_policy_zh || "";
  return `
    <section class="macro-hero ${diagnoseVerdictClass(result.verdict)}">
      <div>
        <div class="row-title">
          ${escapeHtml(result.ticker)} 错杀分 ${escapeHtml(result.score)}/100
          <span class="pill">${escapeHtml(premise.in_drawdown ? "回撤前提成立" : "无明显回撤")}</span>
          ${gaps ? `<span class="pill">缺失: ${escapeHtml(gaps)}</span>` : ""}
        </div>
        <p>${escapeHtml(result.verdict_zh || "")}</p>
        <div class="terms">${escapeHtml(result.method_zh || "")}</div>
      </div>
    </section>
    ${renderMarketStrip(objectValue(parts.market_structure))}
    ${renderActionPlan(objectValue(result.action_plan))}
    ${renderStrikeLadder(objectValue(parts.options_structure))}
    <section class="section-head"><div><h3>评分构成</h3><p>每一项都附理由；分数回答「结构是否支持错杀假设」，不直接构成买入指令。</p></div></section>
    <section class="source-grid">${componentsBlock}</section>
    <section class="section-head"><div><h3>触发条件</h3><p>出现以下任一信号，才把「观察」升级为「行动」。</p></div></section>
    <section class="row"><ul class="terms">${triggers}</ul></section>
    <section class="section-head"><div><h3>各维度读数</h3></div></section>
    <section class="source-grid">${sectionSummaries}</section>
    ${newsRows ? `<section class="section-head"><div><h3>雷达新闻命中（近${escapeHtml(news.lookback_days || 90)}天，硬证据 ${escapeHtml(news.hard_evidence_hits || 0)} 条）</h3></div></section><section class="source-grid">${newsRows}</section>` : ""}
    ${optionsPolicy ? `<section class="row"><div class="terms">${escapeHtml(optionsPolicy)}</div></section>` : ""}
  `;
}

async function loadMarketStructure() {
  if (state.marketStructure === "loading") return;
  state.marketStructure = "loading";
  try {
    const response = await fetch("/api/market_structure");
    const payload = await response.json();
    state.marketStructure = payload.ok ? payload : { status: "unavailable" };
  } catch (error) {
    state.marketStructure = { status: "unavailable" };
  }
  if (state.view === "market" || state.view === "diagnose") render();
}

function marketStructureSection() {
  const market = state.marketStructure;
  if (market === null) loadMarketStructure();
  if (market === null || market === "loading") {
    return '<section class="row"><div class="row-title">大盘结构（gamma / 暗盘 / VIX）</div><div class="terms">正在拉取 SPY/QQQ 期权链与 FINRA 全市场卖空…</div></section>';
  }
  if (!market || market.status !== "ok") {
    return '<section class="row"><div class="row-title">大盘结构（gamma / 暗盘 / VIX）</div><div class="terms">大盘结构数据暂不可用。</div></section>';
  }
  const indexLine = (index) => {
    if (!index || index.status !== "ok") return "";
    const sign = index.regime === "positive_gamma" ? "正" : index.regime === "negative_gamma" ? "负" : "不可用";
    const net = index.net_gex_usd == null ? "" : `（约 $${(Number(index.net_gex_usd) / 1e9).toFixed(2)}B / 标的变动 1%）`;
    const spot = index.spot == null ? "" : `，现价 $${index.spot}`;
    return `${index.ticker}：OI 符号假设下净 GEX 估算为${sign}${net}${spot}。`;
  };
  const spx = market.spx;
  const spxLine = spx && spx.status === "ok" && (spx.call_wall != null || spx.put_wall != null)
    ? `SPX call/put GEX 峰值：$${spx.call_wall ?? "n/a"} / $${spx.put_wall ?? "n/a"}；表示该符号模型的集中 strike，不是已确认的支撑或阻力。`
    : "";
  const summaryLines = [indexLine(market.spy), indexLine(market.qqq), spxLine,
    market.dark_pool?.summary_zh, market.vix?.summary_zh].filter(Boolean);
  const snapshotTime = market.fetched_at
    ? shortTime(market.fetched_at)
    : "服务端未提供快照时间，当前数值的新鲜度无法确认";
  return `
    ${renderMarketStrip(market)}
    <section class="row market-summary">
      <div class="market-summary-grid">
        <div class="market-summary-main">
          <div class="market-summary-label">结构读数</div>
          <div class="market-summary-lines">${summaryLines.map((line) => `<p>${escapeHtml(line)}</p>`).join("") || "<p>暂无结构读数。</p>"}</div>
        </div>
        <aside class="market-method">
          <div class="market-summary-label">来源与假设</div>
          <p>CBOE 提供延迟期权链。未平仓量（OI）不显示买卖方；这里用 calls 正、puts 负估算 GEX，只是结构代理，不代表真实做市商仓位。Call/put GEX 峰值不是支撑或阻力。FINRA 卖空成交占比也不代表暗池净买卖方向。</p>
        </aside>
      </div>
      <div class="market-data-time">本次结构快照：${escapeHtml(snapshotTime)} · CBOE 源时间见下方图表</div>
    </section>
  `;
}

function renderGammaByStrike() {
  const market = state.marketStructure;
  if (!market || market.status !== "ok") return "";
  const which = state.gammaChart.index;
  const metric = state.gammaChart.metric;
  const idx = which === "QQQ" ? objectValue(market.qqq) : which === "SPX" ? objectValue(market.spx) : objectValue(market.spy);
  const chart = objectValue(idx.strike_chart);
  const indexBtn = (key) => `<button class="small-action ${which === key ? "active" : ""}" type="button" data-gamma-index="${key}">${key}</button>`;
  const metricBtn = (key, label) => `<button class="small-action ${metric === key ? "active" : ""}" type="button" data-gamma-metric="${key}">${label}</button>`;
  const controls = `
    <div class="gamma-controls">
      <span class="gamma-toggle">${indexBtn("SPY")}${indexBtn("QQQ")}${indexBtn("SPX")}</span>
      <span class="gamma-toggle">${metricBtn("net_gex", "Net GEX")}${metricBtn("oi", "未平仓 OI")}</span>
    </div>`;
  if (chart.status !== "ok" || !(chart.bars || []).length) {
    return `<section class="row"><div class="row-title">大盘 Gamma 分布（按 strike）</div>${controls}<div class="terms">${escapeHtml(which)} 期权链数据暂不可用。</div></section>`;
  }
  const spot = Number(chart.spot);
  const bars = [...chart.bars].sort((a, b) => b.strike - a.strike);
  let maxAbs = 1;
  bars.forEach((b) => {
    const right = metric === "oi" ? Number(b.call_oi) : Math.max(0, Number(b.net_gex_usd));
    const left = metric === "oi" ? Number(b.put_oi) : Math.max(0, -Number(b.net_gex_usd));
    maxAbs = Math.max(maxAbs, right, left);
  });
  let spotInserted = false;
  const rowsHtml = [];
  bars.forEach((b) => {
    if (!spotInserted && Number.isFinite(spot) && spot > Number(b.strike)) {
      rowsHtml.push(`<div class="gx-spot">— 现价 $${spot} —</div>`);
      spotInserted = true;
    }
    let rightVal, leftVal;
    if (metric === "oi") { rightVal = Number(b.call_oi); leftVal = Number(b.put_oi); }
    else { const n = Number(b.net_gex_usd); rightVal = Math.max(0, n); leftVal = Math.max(0, -n); }
    const rightW = Math.round((rightVal / maxAbs) * 48);
    const leftW = Math.round((leftVal / maxAbs) * 48);
    const marks = [];
    if (Number(b.strike) === Number(chart.call_wall)) marks.push("Call GEX 峰");
    if (Number(b.strike) === Number(chart.put_wall)) marks.push("Put GEX 峰");
    const tip = `strike $${b.strike} | netGEX $${(Number(b.net_gex_usd) / 1e6).toFixed(1)}M | callGEX $${(Number(b.call_gex_usd) / 1e6).toFixed(1)}M | putGEX $${(Number(b.put_gex_usd) / 1e6).toFixed(1)}M | callOI ${fmtShares(b.call_oi)} | putOI ${fmtShares(b.put_oi)}`;
    rowsHtml.push(`
      <div class="gx-row" title="${escapeHtml(tip)}">
        <span class="gx-strike">$${escapeHtml(b.strike)}${marks.length ? ` <span class="pill">${marks.join("·")}</span>` : ""}</span>
        <span class="gx-track">
          <span class="gx-left"><span class="gx-bar gx-put" style="width:${leftW}%"></span></span>
          <span class="gx-center"></span>
          <span class="gx-right"><span class="gx-bar gx-call" style="width:${rightW}%"></span></span>
        </span>
      </div>`);
  });
  if (!spotInserted && Number.isFinite(spot)) rowsHtml.push(`<div class="gx-spot">— 现价 $${spot} —</div>`);
  const legend = metric === "oi"
    ? '<span class="lb-call-dot"></span>call OI <span class="lb-put-dot"></span>put OI'
    : '<span class="lb-call-dot"></span>净 GEX 估算为正<span class="lb-put-dot"></span>净 GEX 估算为负';
  const regimeZh = idx.regime === "positive_gamma" ? "OI 模型净 GEX 为正" : idx.regime === "negative_gamma" ? "OI 模型净 GEX 为负" : "—";
  const netTotal = idx.net_gex_usd != null ? `$${(Number(idx.net_gex_usd) / 1e9).toFixed(2)}B` : "n/a";
  const quoteTime = idx.as_of ? String(idx.as_of).replace("T", " ") : "源时间不可用";
  const callPeak = idx.call_wall != null ? `$${idx.call_wall}` : "n/a";
  const putPeak = idx.put_wall != null ? `$${idx.put_wall}` : "n/a";
  return `
    <section class="row gamma-panel">
      <div class="gamma-heading">
        <div class="row-title">${escapeHtml(which)} · 期权 Gamma 暴露（按 strike）</div>
        <span class="ev warn">${escapeHtml(regimeZh)}</span>
      </div>
      ${controls}
      <div class="gamma-meta">
        <span>现价 <b>$${escapeHtml(chart.spot)}</b></span>
        <span>净 GEX 估算 <b>${escapeHtml(netTotal)}</b><small>/ 标的变动 1%</small></span>
        <span>Call GEX 峰值 <b>${escapeHtml(callPeak)}</b></span>
        <span>Put GEX 峰值 <b>${escapeHtml(putPeak)}</b></span>
        <span>源时间 <b>${escapeHtml(quoteTime)}</b></span>
      </div>
      <div class="gamma-legend">${legend}</div>
      <div class="gamma-chart">${rowsHtml.join("")}</div>
      <div class="gamma-note">${metric === "oi" ? "条形显示 call/put 未平仓合约数，不显示买卖方向。" : "条形显示现价下的净 GEX 估算：calls 正、puts 负是模型假设，不是真实做市商仓位。"} CBOE 报价有延迟；上方源时间不代表 OI 的更新时间。翻转位需要按假设价格重新估算整条期权链，本页暂不显示。</div>
    </section>
  `;
}

function bindGammaChart() {
  document.querySelectorAll("[data-gamma-index]").forEach((btn) => {
    btn.addEventListener("click", () => { state.gammaChart.index = btn.dataset.gammaIndex; renderMarket(); });
  });
  document.querySelectorAll("[data-gamma-metric]").forEach((btn) => {
    btn.addEventListener("click", () => { state.gammaChart.metric = btn.dataset.gammaMetric; renderMarket(); });
  });
}

function renderMarket() {
  const regime = state.brief?.market_regime;
  const conclusion = state.brief?.market_conclusion_zh || {};
  if (!regime) {
    elements.contentArea.innerHTML = `${marketStructureSection()}${renderGammaByStrike()}<div class="empty">宏观状态还没有加载。</div>`;
    bindGammaChart();
    return;
  }
  const metrics = (regime.metrics || []).map((metric) => `
    <article class="row metric-row">
      <div class="row-title">${escapeHtml(metric.label || metric.key)} <span class="pill">${escapeHtml(metric.category || "")}</span></div>
      <div class="row-meta">
        <span>值=${escapeHtml(formatMetricValue(metric))}</span>
        <span>截至=${escapeHtml(metric.as_of || "n/a")}</span>
        ${metric.change_5obs_pct !== undefined ? `<span>5obs=${Number(metric.change_5obs_pct).toFixed(2)}%</span>` : ""}
        ${metric.change_20obs_pct !== undefined ? `<span>20obs=${Number(metric.change_20obs_pct).toFixed(2)}%</span>` : ""}
      </div>
      <div class="terms">来源=${escapeHtml(metric.source || "")}</div>
    </article>
  `).join("");
  const events = (regime.events || []).slice(0, 8).map((event) => `
    <article class="row">
      <a href="${safeArticleHref(event.link) || "#"}" target="_blank" rel="noopener noreferrer">${escapeHtml(event.title || "Untitled")}</a>
      <div class="row-meta">
        <span>${escapeHtml(event.source || "unknown")}</span>
        ${event.policy_importance ? `<span>importance=${escapeHtml(event.policy_importance)}/3</span>` : ""}
      </div>
      <div class="terms">${escapeHtml(event.market_read || event.summary || "来源未提供摘要，点击原文。")}</div>
    </article>
  `).join("");
  elements.contentArea.innerHTML = `
    ${marketStructureSection()}
    ${renderGammaByStrike()}
    <section class="macro-hero ${escapeHtml(regime.regime || "neutral")}">
      <div>
        <div class="row-title">
          ${escapeHtml(conclusion.title || "宏观结论")}
          <span class="pill">${escapeHtml(statusZh(regime.status))}</span>
          <span class="pill">${escapeHtml(regimeZh(regime.regime))}</span>
          <span class="pill">分数=${escapeHtml(regime.score ?? 0)}</span>
        </div>
        <p>${escapeHtml(conclusion.summary || regime.summary || "")}</p>
        <div class="terms">${escapeHtml(conclusion.action || "")}</div>
      </div>
      <div class="regime-meter">
        <div class="meter-track"><span></span><span></span><span></span><span></span><span></span></div>
        <strong>${escapeHtml(regimeZh(regime.regime))}</strong>
        <small>${escapeHtml(regime.generated_at || "")}</small>
      </div>
    </section>
    <section class="source-grid">${metrics || '<div class="empty">暂无宏观指标。</div>'}</section>
    <section class="section-head"><div><h3>政策/宏观事件</h3><p>用于解释市场背景，不直接替代个股研究。</p></div></section>
    <section class="source-grid">${events || '<div class="empty">暂无宏观事件。</div>'}</section>
  `;
  bindGammaChart();
}

/* ------------------------------------------------------------------ */
/* PROCESS                                                            */
/* ------------------------------------------------------------------ */
function renderProcess() {
  const sourceRows = Object.entries(state.sourceCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([source, count]) => `<span class="pill">${escapeHtml(source)}: ${count}</span>`)
    .join("");
  const articleRows = visibleArticles().slice(0, 150).map((article) => {
    const timing = article.timeliness || {};
    return `
      <article class="row">
        <a href="${safeArticleHref(article.link) || "#"}" target="_blank" rel="noopener noreferrer">${escapeHtml(article.title || "Untitled")}</a>
        <div class="row-meta">
          <span>来源=${escapeHtml(article.source || "unknown")}</span>
          <span>信任权重=${Number(article.source_trust || 0).toFixed(2)}</span>
          <span>新鲜度=${escapeHtml(timing.status || "unknown")}</span>
          <span>时间权重=${Number(timing.score_multiplier || 1).toFixed(2)}</span>
          <span>发布时间=${escapeHtml(article.published || "n/a")}</span>
        </div>
      </article>
    `;
  }).join("");
  elements.contentArea.innerHTML = `
    <section class="row"><div class="row-title">本轮来源分布</div><div class="row-meta">${sourceRows || "<span>本服务会话还没有完成扫描。</span>"}</div></section>
    ${articleRows || '<div class="empty">暂无扫描过程。</div>'}
  `;
}

/* ------------------------------------------------------------------ */
/* SOURCES                                                            */
/* ------------------------------------------------------------------ */
function renderSources() {
  const grouped = groupRows(visibleSources(), (row) => row.group || "ungrouped");
  const sourceRows = Object.entries(grouped).map(([group, rows]) => `
    <section class="row">
      <div class="row-title">${escapeHtml(group)} <span class="pill">${rows.length}</span></div>
      <div class="source-grid">
        ${rows.map((source) => `
          <article class="row source-row">
            <a href="${safeArticleHref(source.url) || "#"}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.name)}</a>
            <div class="row-meta">
              <span>type=${escapeHtml(source.type)}</span>
              ${source.trust !== undefined ? `<span>trust=${Number(source.trust || 0).toFixed(2)}</span>` : ""}
              ${source.status ? `<span>status=${escapeHtml(source.status)}</span>` : ""}
            </div>
            ${source.purpose ? `<div class="terms">${escapeHtml(source.purpose)}</div>` : ""}
            <code>${escapeHtml(source.url)}</code>
          </article>
        `).join("")}
      </div>
    </section>
  `).join("");
  const seeds = state.watchlist.map((company) => `<span class="pill">${escapeHtml(company.ticker)} ${escapeHtml(company.name)}</span>`).join("");
  elements.contentArea.innerHTML = `
    ${sourceRows || '<div class="empty">没有配置来源。</div>'}
    <section class="row">
      <div class="row-title">种子关键词库 <span class="pill">不是最终观察池</span></div>
      <details class="seed-details">
        <summary>查看 ${state.watchlist.length} 个种子标的</summary>
        <div class="row-meta">${seeds || "<span>没有配置种子标的。</span>"}</div>
      </details>
    </section>
  `;
}

/* ------------------------------------------------------------------ */
/* shared evidence sub-renderers                                      */
/* ------------------------------------------------------------------ */
function renderEarningsAnalysis(candidate) {
  const analysis = objectValue(candidate.earnings_analysis);
  if (!analysis.status || analysis.status === "not_earnings") return "";
  const metricTiles = (analysis.metrics || []).slice(0, 8)
    .map((metric) => statTile(metricLabelZh(metric.metric), `${escapeHtml(String(metric.value))}${metric.unit ? " " + escapeHtml(String(metric.unit)) : ""}`, "accent"))
    .join("");
  const spend = (analysis.spend_allocation || []).slice(0, 8).map((item) => `<span class="pill">${escapeHtml(spendCategoryZh(item.category))}</span>`).join("");
  const mentions = (analysis.mentioned_companies || []).slice(0, 8).map((item) => `<span class="pill">${escapeHtml(item.ticker)} ${escapeHtml(item.name || "")}</span>`).join("");
  const points = (analysis.watch_points_zh || []).slice(0, 5).map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("");
  return `
    <div class="earnings-analysis">
      <div><span class="band ${analysis.status === "earnings_release_detected" ? "hard" : "watch"}">本次 release 关键指标</span> ${escapeHtml(analysis.summary_zh || "")}</div>
      ${metricTiles ? `<div class="stat-tiles">${metricTiles}</div>` : '<div class="terms">未抽取到明确财务数字</div>'}
      <div class="row-title">钱花在哪里</div>
      <div class="row-meta">${spend || "<span>财报原文暂未识别明确资金投向</span>"}</div>
      <div class="row-title">提到的公司/产业链对象</div>
      <div class="row-meta">${mentions || "<span>暂未识别 watchlist 内二阶公司</span>"}</div>
      <div class="terms">${escapeHtml(analysis.read_through_zh || "")}</div>
      <div class="row-meta">${points}</div>
      <div class="terms">${escapeHtml(analysis.limitations_zh || "")}</div>
    </div>
  `;
}

/* ------------------------------------------------------------------ */
/* SERENITY ALPHA (dedicated section)                                  */
/* ------------------------------------------------------------------ */
function renderSerenity() {
  const rows = reportRows().filter((row) => objectValue(row.serenity_alpha).status && matchQuery(row));
  if (!rows.length) {
    elements.contentArea.innerHTML = '<div class="empty">本轮暂无候选可做 Serenity Alpha 评估（需先完成一次扫描）。</div>';
    return;
  }
  const order = { qualified: 0, exploratory: 1, excluded: 2 };
  rows.sort((a, b) => {
    const sa = objectValue(a.serenity_alpha);
    const sb = objectValue(b.serenity_alpha);
    const oa = order[sa.verdict] ?? 3;
    const ob = order[sb.verdict] ?? 3;
    if (oa !== ob) return oa - ob;
    return (Number(sb.alpha_score) || 0) - (Number(sa.alpha_score) || 0);
  });
  const counts = rows.reduce((acc, row) => {
    const v = objectValue(row.serenity_alpha).verdict;
    acc[v] = (acc[v] || 0) + 1;
    return acc;
  }, {});
  const cards = rows.map(renderSerenityCard).join("");
  elements.contentArea.innerHTML = `
    <section class="section-head">
      <div>
        <h3>Serenity Alpha · ${rows.length} 个候选</h3>
        <p>新闻 → 小而纯、被错误分类、对该需求高弹性的受益者。五维乘法分（任一维近 0 即归零），外加排除规则与 1–4 季验证链。这是只读第二视角，不改主排序。</p>
        <div class="row-meta">
          <span class="band weak">通过筛 ${counts.qualified || 0}</span>
          <span class="band watch">探索级 ${counts.exploratory || 0}</span>
          <span class="band monitor">被排除 ${counts.excluded || 0}</span>
        </div>
      </div>
    </section>
    <div class="serenity-grid">${cards}</div>
  `;
}

function renderSerenityCard(row) {
  const article = articleOf(row);
  const tickers = candidateTickers(row);
  return `
    <article class="serenity-card">
      <header class="sc-head">
        <span class="sc-tkr">${escapeHtml(tickers.join(", ") || "—")}</span>
        <span class="sc-name">${escapeHtml(row.company_name || "Unknown")}</span>
        <span class="sc-score-num">分 ${Number(row.score || 0).toFixed(1)}</span>
      </header>
      <div class="sc-cat">${escapeHtml(article.title || "")}</div>
      ${renderSerenityAlpha(row)}
      <div class="topcall-catalyst">${safeArticleHref(article.link) ? `<a href="${safeArticleHref(article.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(article.source || "")} · 打开原文 ↗</a>` : ""}</div>
    </article>
  `;
}

function renderSerenityAlpha(candidate) {
  const sa = objectValue(candidate.serenity_alpha);
  if (!sa.status || !Array.isArray(sa.dimensions) || !sa.dimensions.length) return "";
  const verdictMap = {
    qualified: ["weak", "通过 Serenity 筛"],
    exploratory: ["watch", "仅探索级"],
    excluded: ["monitor", "被排除"],
  };
  const [bandCls, verdictZh] = verdictMap[sa.verdict] || ["monitor", sa.verdict || ""];
  const bars = sa.dimensions.map((d) => {
    const value = Number(d.value) || 0;
    const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
    const weak = d.label_zh === sa.weakest_zh;
    return `<div class="sa-dim${weak ? " weak-link" : ""}">
        <span class="sa-dim-k">${escapeHtml(d.label_zh)}</span>
        <span class="sa-bar"><span style="width:${pct}%"></span></span>
        <span class="sa-dim-v">${value.toFixed(2)}</span>
      </div>`;
  }).join("");
  const filters = (sa.excluded_filters || []).map((f) => `<span class="ev warn">${escapeHtml(f.reason_zh)}</span>`).join(" ");
  const vc = objectValue(sa.verification_chain);
  const chainGroup = (title, items) => (Array.isArray(items) && items.length)
    ? `<div class="row-title">${escapeHtml(title)}</div><div class="row-meta">${items.map((i) => `<span class="pill">${escapeHtml(i)}</span>`).join("")}</div>`
    : "";
  const meta = [
    sa.market_cap_display && sa.market_cap_display !== "n/a" ? `市值 ${sa.market_cap_display}` : "",
    sa.analyst_count != null ? `覆盖 ${sa.analyst_count} 家` : "",
  ].filter(Boolean).map((m) => ` · ${escapeHtml(m)}`).join("");
  return `
    <div class="serenity">
      <div><span class="band ${bandCls}">Serenity Alpha · ${escapeHtml(verdictZh)}</span> <strong class="sa-score">${escapeHtml(String(sa.alpha_score))}</strong>/100${meta}</div>
      <div class="terms">${escapeHtml(sa.relabel_zh || "")}</div>
      <div class="sa-dims">${bars}</div>
      ${filters ? `<div class="missing-list" style="margin-top:6px">${filters}</div>` : ""}
      <div class="terms" style="margin-top:6px"><strong>仓位姿态：</strong>${escapeHtml(sa.posture_zh || "")}</div>
      <div class="row-title">验证链（1–4 季内证实 / 证伪）</div>
      ${chainGroup("利润表", vc.income_statement)}
      ${chainGroup("需求 / 现金流", vc.cashflow_demand)}
      ${chainGroup("经营杠杆", vc.operating_leverage)}
      ${chainGroup("市场侧印证", vc.market_validation)}
      <div class="terms">${escapeHtml(vc.timeline_zh || "")}</div>
    </div>
  `;
}

function renderTechnologyIntel(candidate) {
  const intel = objectValue(candidate.technology_intel);
  if (!intel.status || intel.status === "not_technology_signal") return "";
  const themes = (intel.themes || []).slice(0, 8).map((item) => `<span class="pill">${escapeHtml(techThemeZh(item.theme))}</span>`).join("");
  const mentions = (intel.mentioned_companies || []).slice(0, 10).map((item) => `<span class="pill">${escapeHtml(item.ticker)} ${escapeHtml(item.name || "")}</span>`).join("");
  const points = (intel.watch_points_zh || []).slice(0, 5).map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("");
  return `
    <div class="technology-intel">
      <div><span class="band watch">技术路线</span> ${escapeHtml(intel.summary_zh || "")}</div>
      <div class="row-meta">${themes || "<span>未识别明确主题</span>"}</div>
      <div class="row-title">被点名公司/供应链对象</div>
      <div class="row-meta">${mentions || "<span>暂未识别 watchlist 内二阶公司</span>"}</div>
      <div class="terms">${escapeHtml(intel.read_through_zh || "")}</div>
      <div class="row-meta">${points}</div>
      <div class="terms">${escapeHtml(intel.limitations_zh || "")}</div>
    </div>
  `;
}

function renderReadthroughAnalysis(candidate) {
  const analysis = objectValue(candidate.readthrough_analysis);
  if (!analysis.status || analysis.status === "no_readthrough") return "";
  const rows = (analysis.items || []).slice(0, 8).map((item) => `
    <article class="readthrough-row">
      <div class="row-title">${escapeHtml(item.ticker)} ${escapeHtml(item.name || "")}<span class="pill">${escapeHtml(item.status || "")}</span></div>
      <div class="terms">${escapeHtml(item.decision_zh || "")}</div>
      <div class="row-meta">
        <span>market=${escapeHtml(item.market_confirmation?.status || "n/a")}</span>
        <span>financial=${escapeHtml(item.financial_snapshot?.status || "n/a")}</span>
      </div>
    </article>
  `).join("");
  return `
    <div class="readthrough-analysis">
      <div><span class="band ${analysis.status === "active" ? "hard" : "watch"}">二阶 read-through</span> ${escapeHtml(analysis.summary_zh || "")}</div>
      <div class="readthrough-list">${rows}</div>
    </div>
  `;
}

/* ------------------------------------------------------------------ */
/* small helpers                                                      */
/* ------------------------------------------------------------------ */
function hasTechnologyIntel(candidate) {
  const intel = objectValue(candidate.technology_intel);
  return Boolean(intel.status && intel.status !== "not_technology_signal");
}

function actionFromScore(score) {
  const value = Number(score || 0);
  if (value >= 35) return "research_now";
  if (value >= 20) return "track";
  return "monitor";
}

function tickerOf(item) {
  return String(item?.ticker || "").toUpperCase().trim();
}

function todayLocalIso() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function timeZh(value) {
  const lower = String(value || "").toLowerCase();
  if (lower.includes("before")) return "盘前";
  if (lower.includes("after")) return "盘后";
  if (lower.includes("during")) return "盘中";
  return "时间待确认";
}

function spendCategoryZh(category) {
  const map = { rd: "研发", sales_marketing: "销售/市场", capex: "资本开支", buyback: "回购", mna: "并购/战略投资" };
  return map[category] || category || "未分类";
}

function metricLabelZh(metric) {
  const map = {
    revenue: "营收",
    product_revenue: "产品营收",
    eps: "EPS",
    rpo: "RPO 剩余履约义务",
    net_revenue_retention: "净收入留存 NRR",
    capex: "资本开支",
    research_development: "研发支出",
    free_cash_flow: "自由现金流",
  };
  return map[metric] || metric || "指标";
}

function techThemeZh(theme) {
  const map = {
    ai_factory_rackscale: "AI 工厂/机柜级架构",
    power_thermal: "供电/散热",
    optical_interconnect: "光互连",
    inference_optimization: "推理优化",
    custom_silicon: "定制芯片",
    robotics_edge_ai: "机器人/边缘 AI",
    "800v_hvdc_power": "800V HVDC 供电",
  };
  return map[theme] || theme || "未分类";
}

function statusZh(status) {
  if (status === "connected") return "已连接";
  if (status === "degraded") return "部分降级";
  if (status === "not_connected") return "未连接";
  return status || "未知";
}

function regimeZh(regime) {
  if (regime === "risk_on") return "风险偏好";
  if (regime === "risk_off") return "风险防御";
  if (regime === "neutral") return "中性";
  return regime || "未知";
}

function formatMetricValue(metric) {
  const value = Number(metric.value);
  if (!Number.isFinite(value)) return "n/a";
  const unit = metric.unit || "";
  if (unit === "pct") return `${value.toFixed(2)}%`;
  if (unit === "bp") return `${value.toFixed(1)}bp`;
  return value.toFixed(2);
}

function bindInlineViewButtons() {
  document.querySelectorAll("[data-inline-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.inlineView));
  });
}

function showErrors(errors) {
  if (!errors || !errors.length) {
    elements.errorBox.hidden = true;
    elements.errorBox.innerHTML = "";
    return;
  }
  elements.errorBox.hidden = false;
  elements.errorBox.innerHTML = errors.map((error) => `<div>${escapeHtml(error)}</div>`).join("");
}

function userFacingError(error) {
  const message = error?.message || String(error);
  if (message === "Failed to fetch" || message.includes("NetworkError")) {
    return "本地服务短暂中断，正在等待自动重连。";
  }
  return message;
}

/* ------------------------------------------------------------------ */
/* data loading                                                       */
/* ------------------------------------------------------------------ */
async function loadInitialState() {
  elements.statusLine.textContent = "加载中";
  const [signalsResponse, sourcesResponse] = await Promise.all([
    fetch("/api/signals?limit=200"),
    fetch("/api/sources"),
  ]);
  const signalsPayload = await signalsResponse.json();
  const sourcesPayload = await sourcesResponse.json();
  if (!signalsPayload.ok) throw new Error(signalsPayload.error || "Failed to load signals");
  if (!sourcesPayload.ok) throw new Error(sourcesPayload.error || "Failed to load sources");

  state.candidates = signalsPayload.candidates || [];
  state.articles = signalsPayload.last_scan?.articles || [];
  state.sourceCounts = signalsPayload.last_scan?.source_counts || {};
  state.sources = sourcesPayload.sources || [];
  state.marketSources = sourcesPayload.market_sources || [];
  state.watchlist = sourcesPayload.watchlist || [];
  state.stale = false;

  // Paint immediately with stored signals, then upgrade once the (sometimes
  // slow, network-backed) brief resolves, so first paint is never blank.
  updateScanProgress(signalsPayload.last_scan);
  showErrors([]);
  elements.statusLine.textContent = `已加载 ${state.candidates.length} 候选，正在生成简报…`;
  setView(state.view);

  await refreshBrief();
  elements.statusLine.textContent = `已加载 ${reportRows().length} 个机会 · ${state.candidates.length} 候选`;
  render();
}

async function refreshDashboard() {
  try {
    const response = await fetch("/api/signals?limit=200");
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "Failed to refresh dashboard");
    state.candidates = payload.candidates || [];
    state.articles = payload.last_scan?.articles || [];
    state.sourceCounts = payload.last_scan?.source_counts || {};
    state.stale = false;
    updateScanProgress(payload.last_scan);
    await refreshBrief();
    elements.statusLine.textContent = `已加载 ${reportRows().length} 个机会 · ${state.candidates.length} 候选`;
    showErrors([]);
    render();
  } catch (error) {
    state.stale = true;
    elements.statusLine.textContent = "连接中断，等待自动重连";
    showErrors([userFacingError(error)]);
    updateStatusStrip();
  }
}

async function refreshBrief() {
  const response = await fetch("/api/brief");
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error || "Failed to load brief");
  state.brief = payload.brief;
}

/* ------------------------------------------------------------------ */
/* events                                                             */
/* ------------------------------------------------------------------ */
elements.searchBox.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

const exportButton = document.querySelector("#exportReport");
if (exportButton) {
  exportButton.addEventListener("click", async () => {
    exportButton.disabled = true;
    try {
      const response = await fetch("/api/daily_report");
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.error || "导出失败");
      const blob = new Blob([payload.markdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `ai-news-radar-daily-${todayLocalIso()}.md`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      showErrors([userFacingError(error)]);
    } finally {
      exportButton.disabled = false;
    }
  });
}

elements.tabs.forEach((tab) => {
  tab.addEventListener("click", () => setView(tab.dataset.view));
});

document.querySelector("#languageToggle").addEventListener("click", () => {
  locale = locale === "en" ? "zh-CN" : "en";
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, locale === "en" ? "en" : "zh-CN");
  } catch {
    // The switch still works for this page when browser storage is restricted.
  }
  applyLocale();
});

const localeObserver = new MutationObserver((mutations) => {
  const roots = new Set();
  for (const mutation of mutations) {
    if (mutation.type === "characterData") roots.add(mutation.target);
    else if (mutation.target instanceof Element) roots.add(mutation.target);
  }
  roots.forEach((root) => localizeSubtree(root));
});
localeObserver.observe(document.body, { childList: true, characterData: true, subtree: true });
applyLocale();

window.addEventListener("hashchange", () => {
  const nextView = initialView();
  state.selectedEarningsTicker = initialSelectedEarningsTicker();
  if (nextView !== state.view) setView(nextView);
  else render();
});

loadInitialState().catch((error) => {
  state.stale = true;
  elements.statusLine.textContent = "加载失败";
  showErrors([userFacingError(error)]);
  updateStatusStrip();
});

setInterval(refreshDashboard, AUTO_REFRESH_MS);

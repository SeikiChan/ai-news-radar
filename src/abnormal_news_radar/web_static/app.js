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
};

const AUTO_REFRESH_MS = 60000;

const elements = {
  nextRun: document.querySelector("#nextRun"),
  sourceCount: document.querySelector("#sourceCount"),
  watchlistCount: document.querySelector("#watchlistCount"),
  fetchedCount: document.querySelector("#fetchedCount"),
  signalCount: document.querySelector("#signalCount"),
  statusLine: document.querySelector("#statusLine"),
  errorBox: document.querySelector("#errorBox"),
  scanProgress: document.querySelector("#scanProgress"),
  progressText: document.querySelector("#progressText"),
  contentArea: document.querySelector("#contentArea"),
  searchBox: document.querySelector("#searchBox"),
  viewTitle: document.querySelector("#viewTitle"),
  tabs: Array.from(document.querySelectorAll(".tab")),
  metricButtons: Array.from(document.querySelectorAll("[data-view-jump]")),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function groupRows(rows, keyFn) {
  return rows.reduce((groups, row) => {
    const key = keyFn(row);
    if (!groups[key]) groups[key] = [];
    groups[key].push(row);
    return groups;
  }, {});
}

function setView(view) {
  state.view = view;
  const nextHash = view === "earnings" && state.selectedEarningsTicker ? `#earnings:${state.selectedEarningsTicker}` : `#${view}`;
  if (window.location.hash !== nextHash) {
    window.history.replaceState(null, "", nextHash);
  }
  elements.tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.view === view));
  const titles = {
    brief: "每日投研简报",
    earnings: "财报工作台",
    technology: "技术前沿",
    market: "宏观状态",
    opportunities: "机会报告",
    watchlist: "动态观察池",
    process: "扫描过程",
    sources: "来源与种子名单",
  };
  elements.viewTitle.textContent = titles[view] || "市场终端";
  render();
}

function initialView() {
  const view = window.location.hash.replace("#", "").split(":")[0];
  return ["brief", "earnings", "technology", "market", "opportunities", "watchlist", "process", "sources"].includes(view) ? view : "brief";
}

function initialSelectedEarningsTicker() {
  const [view, ticker] = window.location.hash.replace("#", "").split(":");
  return view === "earnings" && ticker ? ticker.toUpperCase() : null;
}

function render() {
  elements.signalCount.textContent = String(state.candidates.length);
  if (state.view === "brief") renderBrief();
  if (state.view === "earnings") renderEarnings();
  if (state.view === "technology") renderTechnology();
  if (state.view === "market") renderMarket();
  if (state.view === "opportunities") renderOpportunities();
  if (state.view === "watchlist") renderWatchlist();
  if (state.view === "process") renderProcess();
  if (state.view === "sources") renderSources();
}

function renderBrief() {
  const brief = state.brief;
  if (!brief) {
    elements.contentArea.innerHTML = '<div class="empty">简报还没有加载。</div>';
    return;
  }

  const counts = brief.counts || {};
  const automation = brief.automation || {};
  const conclusion = brief.market_conclusion_zh || {};
  const calendar = brief.earnings_calendar || {};
  const topCandidates = visibleCandidates().slice(0, 4);
  const technologyCandidates = visibleCandidates().filter(hasTechnologyIntel).slice(0, 3);
  const earningsDetails = earningsDetailsByTicker(calendar.items || []);
  const gaps = (brief.data_gaps_zh || brief.data_gaps || [])
    .slice(0, 6)
    .map((gap) => `<span class="pill">${escapeHtml(gap)}</span>`)
    .join("");

  elements.nextRun.textContent = automation.next_run ? `下次 ${automation.next_run}` : "等待排程";

  elements.contentArea.innerHTML = `
    <section class="brief-hero">
      <div>
        <div class="row-title">${escapeHtml(brief.headline_zh || brief.headline || "暂无简报")}</div>
        <div class="row-meta">
          <span>文章 ${counts.articles_reviewed || 0}</span>
          <span>候选 ${counts.discoveries || 0}</span>
          <span>观察池 ${counts.dynamic_watchlist || 0}</span>
          <span>重点 ${counts.report_items || 0}</span>
        </div>
      </div>
      <div class="brief-verdict">
        <strong>${escapeHtml(conclusion.title || "宏观状态")}</strong>
        <span>${escapeHtml(conclusion.action || "")}</span>
      </div>
    </section>

    <section class="section-head">
      <div>
        <h3>今日结论</h3>
        <p>${escapeHtml(conclusion.summary || "系统暂未形成明确宏观结论。")}</p>
      </div>
    </section>

    <section class="section-head">
      <div>
        <h3>重点机会</h3>
        <p>按新闻证据、价格确认、财务影响、期权链/flow、预期差排序。</p>
      </div>
    </section>
    <section class="content-area">${topCandidates.map(renderCompactCandidate).join("") || '<div class="empty">暂无达到阈值的机会。</div>'}</section>

    <section class="section-head">
      <div>
        <h3>财报重点</h3>
        <p>${escapeHtml(calendar.summary_zh || "未来窗口暂无重点财报。")}</p>
      </div>
      <button class="small-action" type="button" data-inline-view="earnings">打开财报工作台</button>
    </section>
    <section class="content-area">${renderTodayEarningsBrief(calendar.items || [], earningsDetails)}</section>

    <section class="section-head">
      <div>
        <h3>技术前沿</h3>
        <p>技术博客、论文和研究报告里的路线图/供应链早期信号。</p>
      </div>
      <button class="small-action" type="button" data-inline-view="technology">打开技术工作台</button>
    </section>
    <section class="content-area">${technologyCandidates.map(renderTechnologyCard).join("") || '<div class="empty">本轮暂无明确技术路线图信号。</div>'}</section>

    <section class="section-head">
      <div>
        <h3>证据缺口</h3>
        <p>这是系统下一轮要补的证据，不是交给用户处理的待办。</p>
      </div>
    </section>
    <section class="row"><div class="row-meta">${gaps || "<span>当前没有关键缺口。</span>"}</div></section>
  `;
  bindInlineViewButtons();
}

function renderEarnings() {
  const calendar = state.brief?.earnings_calendar || {};
  const items = calendar.items || [];
  const detailsByTicker = earningsDetailsByTicker(items);
  const selectedTicker = selectedCalendarTicker(items, detailsByTicker);
  const selectedItem = items.find((item) => tickerOf(item) === selectedTicker) || null;
  const selectedDetail = selectedTicker ? detailsByTicker.get(selectedTicker) : null;

  elements.contentArea.innerHTML = `
    <section class="section-head">
      <div>
        <h3>财报日历</h3>
        <p>${escapeHtml(calendar.summary_zh || "未来窗口暂无重点财报。")} 一级入口只显示日历事件；新闻拆解只作为对应公司的详情证据。</p>
      </div>
    </section>
    ${renderEarningsCalendar(items, detailsByTicker, selectedTicker)}

    <section class="section-head">
      <div>
        <h3>${todayLocalIso()} 财报简报</h3>
        <p>当天若没有重点公司，则显示最近一个待跟踪财报。</p>
      </div>
    </section>
    <section class="content-area">${renderTodayEarningsBrief(items, detailsByTicker)}</section>

    <section class="section-head">
      <div>
        <h3>${selectedTicker ? `${escapeHtml(selectedTicker)} 财报详情` : "财报详情"}</h3>
        <p>核心财务指标、钱花在哪里、提到的公司/产业链对象，以及二阶 read-through。</p>
      </div>
    </section>
    ${renderSelectedEarningsDetail(selectedItem, selectedDetail)}
  `;
  bindEarningsButtons();
}

function renderEarningsCalendar(items, detailsByTicker, selectedTicker) {
  if (!items.length) return '<div class="empty">未来窗口内暂无主流观察标的财报。</div>';
  const grouped = groupRows(items, (item) => item.date || "unknown");
  const days = Object.entries(grouped)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, rows]) => `
      <article class="earnings-day ${date === todayLocalIso() ? "today" : ""}">
        <div class="row-title">
          ${escapeHtml(formatDateLabel(date))}
          ${date === todayLocalIso() ? '<span class="pill">今天</span>' : ""}
        </div>
        <div class="earnings-company-list">
          ${rows.map((item) => renderEarningsCompanyButton(item, detailsByTicker, selectedTicker)).join("")}
        </div>
      </article>
    `)
    .join("");
  return `<section class="earnings-calendar">${days}</section>`;
}

function renderEarningsCompanyButton(item, detailsByTicker, selectedTicker) {
  const ticker = tickerOf(item);
  const hasDetail = detailsByTicker.has(ticker);
  const active = ticker === selectedTicker ? "active" : "";
  return `
    <button class="earnings-company ${active}" type="button" data-earnings-ticker="${escapeHtml(ticker)}">
      <strong>${escapeHtml(ticker)}</strong>
      <span>${escapeHtml(item.name || "")}</span>
      <small>${escapeHtml(timeZh(item.time || ""))} · EPS ${escapeHtml(item.eps_forecast || "n/a")}</small>
      <em>${hasDetail ? "已拆解" : "待发布/待抓取"}</em>
    </button>
  `;
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
  if (detail) {
    return `<section class="content-area">${renderEarningsCard(detail)}</section>`;
  }
  return `
    <section class="content-area">
      <article class="row">
        <div class="row-title">${escapeHtml(tickerOf(item))} ${escapeHtml(item.name || "")}<span class="pill">${escapeHtml(item.status_zh || "")}</span></div>
        <div class="row-meta">
          <span>日期=${escapeHtml(item.date || "")}</span>
          <span>时间=${escapeHtml(timeZh(item.time || ""))}</span>
          <span>EPS预期=${escapeHtml(item.eps_forecast || "n/a")}</span>
          <span>来源=Nasdaq public earnings calendar API</span>
        </div>
        <div class="terms">还没有抓到可拆解的财报原文。系统不会用模板伪造“钱花在哪里”或 read-through；等公司发布 release/10-Q/call transcript 后再解析。</div>
      </article>
    </section>
  `;
}

function earningsDetailsByTicker(calendarItems) {
  const calendarTickers = new Set((calendarItems || []).map(tickerOf).filter(Boolean));
  const details = new Map();
  visibleCandidates()
    .filter(hasEarningsAnalysis)
    .forEach((candidate) => {
      const ticker = candidateTickers(candidate).find((value) => calendarTickers.has(value));
      if (!ticker) return;
      const current = details.get(ticker);
      if (!current || earningsQualityScore(candidate) > earningsQualityScore(current)) {
        details.set(ticker, candidate);
      }
    });
  return details;
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
}

function tickerOf(item) {
  return String(item?.ticker || "").toUpperCase().trim();
}

function candidateTickers(candidate) {
  return (candidate.tickers || []).map((ticker) => String(ticker).toUpperCase().trim()).filter(Boolean);
}

function todayLocalIso() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateLabel(dateText) {
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateText || "unknown";
  return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit", weekday: "short" });
}

function timeZh(value) {
  const lower = String(value || "").toLowerCase();
  if (lower.includes("before")) return "盘前";
  if (lower.includes("after")) return "盘后";
  if (lower.includes("during")) return "盘中";
  return "时间待确认";
}

function renderTechnology() {
  const candidates = visibleCandidates().filter(hasTechnologyIntel);
  elements.contentArea.innerHTML = `
    <section class="section-head">
      <div>
        <h3>技术前沿任务</h3>
        <p>读取技术博客、论文和研究报告，提取技术路线、被点名公司和供应链 read-through。</p>
      </div>
    </section>
    <section class="content-area">${candidates.map(renderTechnologyCard).join("") || '<div class="empty">本轮扫描暂未抓到明确技术路线图信号。</div>'}</section>
  `;
}

function renderMarket() {
  const regime = state.brief?.market_regime;
  const conclusion = state.brief?.market_conclusion_zh || {};
  if (!regime) {
    elements.contentArea.innerHTML = '<div class="empty">宏观状态还没有加载。</div>';
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
      <a href="${escapeHtml(event.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(event.title || "Untitled")}</a>
      <div class="row-meta">
        <span>${escapeHtml(event.source || "unknown")}</span>
        ${event.policy_importance ? `<span>importance=${escapeHtml(event.policy_importance)}/3</span>` : ""}
      </div>
      <div class="terms">${escapeHtml(event.market_read || event.summary || "来源未提供摘要，点击原文。")}</div>
    </article>
  `).join("");
  elements.contentArea.innerHTML = `
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
}

function renderOpportunities() {
  const candidates = visibleCandidates();
  if (!candidates.length) {
    elements.contentArea.innerHTML = '<div class="empty">本轮自动报告暂无机会。</div>';
    return;
  }
  elements.contentArea.innerHTML = candidates.map(renderCandidate).join("");
}

function renderWatchlist() {
  const rows = state.brief?.dynamic_watchlist || [];
  const query = state.query.trim().toLowerCase();
  const visible = query
    ? rows.filter((row) => textOf([row.company_name, row.decision_zh, ...(row.tickers || []), ...(row.sources || [])]).includes(query))
    : rows;
  elements.contentArea.innerHTML = visible.map(renderWatchlistItem).join("") || '<div class="empty">动态观察池还没有足够证据。</div>';
}

function renderProcess() {
  const sourceRows = Object.entries(state.sourceCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([source, count]) => `<span class="pill">${escapeHtml(source)}: ${count}</span>`)
    .join("");
  const articleRows = visibleArticles().slice(0, 150).map((article) => {
    const timing = article.timeliness || {};
    return `
      <article class="row">
        <a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(article.title || "Untitled")}</a>
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

function renderSources() {
  const grouped = groupRows(visibleSources(), (row) => row.group || "ungrouped");
  const sourceRows = Object.entries(grouped).map(([group, rows]) => `
    <section class="row">
      <div class="row-title">${escapeHtml(group)} <span class="pill">${rows.length}</span></div>
      <div class="source-grid">
        ${rows.map((source) => `
          <article class="row source-row">
            <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.name)}</a>
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

function renderCompactCandidate(candidate) {
  const article = articleOf(candidate);
  return `
    <article class="signal">
      <div>
        <div class="signal-title">
          <span class="band ${actionClass(candidate.action)}">${escapeHtml(candidate.action || actionFromScore(candidate.score))}</span>
          <a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(candidate.company_name || "Unknown")}</a>
          <span class="pill">${escapeHtml(candidateTickers(candidate).join(", ") || "ticker待确认")}</span>
        </div>
        <div class="terms">${escapeHtml(candidate.decision || "Monitor only")}</div>
        <div class="meta">${escapeHtml(article.title || "")}</div>
        ${renderEvidenceStrip(candidate)}
      </div>
      <div class="score"><strong>${Number(candidate.score || 0).toFixed(1)}</strong><span>score</span></div>
    </article>
  `;
}

function renderCandidate(candidate) {
  const article = articleOf(candidate);
  return `
    <article class="signal">
      <div>
        <div class="signal-title">
          <span class="band ${actionClass(candidate.action)}">${escapeHtml(candidate.action || actionFromScore(candidate.score))}</span>
          <a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(candidate.company_name || "Unknown")}</a>
          <span class="pill">${escapeHtml(candidateTickers(candidate).join(", ") || "ticker待确认")}</span>
        </div>
        <div class="meta">${escapeHtml(article.source || "unknown")} · ${escapeHtml(article.title || "")}</div>
        <div class="terms">${escapeHtml(candidate.decision || "")}</div>
        ${renderEvidenceStrip(candidate)}
        ${renderTechnologyIntel(candidate)}
        ${renderEarningsAnalysis(candidate)}
        ${renderReadthroughAnalysis(candidate)}
        <div class="terms">${escapeHtml(candidate.analyst_take || "")}</div>
      </div>
      <div class="score"><strong>${Number(candidate.score || 0).toFixed(1)}</strong><span>candidate</span></div>
    </article>
  `;
}

function renderWatchlistItem(row) {
  const article = row.latest_article || {};
  return `
    <article class="signal watchlist-item">
      <div>
        <div class="signal-title">
          <span class="band ${Number(row.conviction || 0) >= 4 ? "hard" : "watch"}">信念 ${escapeHtml(row.conviction || 0)}/5</span>
          <a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(row.company_name || "Unknown")}</a>
          <span class="pill">${escapeHtml(candidateTickers(row).join(", ") || "ticker待确认")}</span>
        </div>
        <div class="terms">${escapeHtml(row.decision_zh || "")}</div>
        ${renderEvidenceStrip(row)}
        ${renderTechnologyIntel(row)}
        ${renderEarningsAnalysis(row)}
        ${renderReadthroughAnalysis(row)}
        <div class="terms">${escapeHtml(row.why_zh || "")}</div>
      </div>
      <div class="score"><strong>${Number(row.max_score || 0).toFixed(1)}</strong><span>max</span></div>
    </article>
  `;
}

function renderTechnologyCard(candidate) {
  const article = articleOf(candidate);
  return `
    <article class="signal technology-card">
      <div>
        <div class="signal-title">
          <span class="band watch">技术</span>
          <a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(candidate.company_name || "Unknown")}</a>
          <span class="pill">${escapeHtml(candidateTickers(candidate).join(", ") || "ticker待确认")}</span>
        </div>
        <div class="meta">${escapeHtml(article.source || "unknown")} · ${escapeHtml(article.title || "")}</div>
        ${renderTechnologyIntel(candidate)}
        ${renderReadthroughAnalysis(candidate)}
      </div>
      <div class="score"><strong>${Number(candidate.score || 0).toFixed(1)}</strong><span>score</span></div>
    </article>
  `;
}

function renderEarningsCard(candidate) {
  const article = articleOf(candidate);
  return `
    <article class="signal earnings-card">
      <div>
        <div class="signal-title">
          <span class="band hard">财报</span>
          <a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(candidate.company_name || "Unknown")}</a>
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

function renderEvidenceStrip(candidate) {
  const market = objectValue(candidate.market_confirmation);
  const impact = objectValue(candidate.impact_assessment);
  const financial = objectValue(candidate.financial_snapshot);
  const model = objectValue(candidate.quick_model);
  const flow = objectValue(candidate.options_flow);
  const expectation = objectValue(candidate.expectation_check);
  return `
    <div class="row-meta">
      <span class="pill">市场=${escapeHtml(statusLabel(market.status))}</span>
      <span class="pill">影响=${escapeHtml(impact.impact_score ?? "n/a")}/5</span>
      <span class="pill">SEC=${escapeHtml(financial.status || "n/a")}</span>
      <span class="pill">模型=${escapeHtml(model.status || "n/a")}</span>
      <span class="pill">期权=${escapeHtml(optionsFlowStatusZh(flow.status))}</span>
      <span class="pill">预期差=${escapeHtml(expectationStatusZh(expectation.status))}</span>
    </div>
  `;
}

function renderEarningsAnalysis(candidate) {
  const analysis = objectValue(candidate.earnings_analysis);
  if (!analysis.status || analysis.status === "not_earnings") return "";
  const metrics = (analysis.metrics || []).slice(0, 8).map((metric) => `<span class="pill">${escapeHtml(metric.metric)}=${escapeHtml(metric.value)} ${escapeHtml(metric.unit)}</span>`).join("");
  const spend = (analysis.spend_allocation || []).slice(0, 8).map((item) => `<span class="pill">${escapeHtml(spendCategoryZh(item.category))}</span>`).join("");
  const mentions = (analysis.mentioned_companies || []).slice(0, 8).map((item) => `<span class="pill">${escapeHtml(item.ticker)} ${escapeHtml(item.name || "")}</span>`).join("");
  const points = (analysis.watch_points_zh || []).slice(0, 5).map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("");
  return `
    <div class="earnings-analysis">
      <div><span class="band ${analysis.status === "earnings_release_detected" ? "hard" : "watch"}">${escapeHtml(analysis.status)}</span> ${escapeHtml(analysis.summary_zh || "")}</div>
      <div class="row-meta">${metrics || "<span>未抽取到明确财务数字</span>"}</div>
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

function hasEarningsAnalysis(candidate) {
  const analysis = objectValue(candidate.earnings_analysis);
  return Boolean(analysis.status && analysis.status !== "not_earnings");
}

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

function actionClass(action) {
  if (action === "research_now") return "hard";
  if (action === "track") return "watch";
  return "monitor";
}

function statusLabel(status) {
  if (status === "confirmed") return "confirmed";
  if (status === "price_only_confirmation") return "price only";
  if (status === "unconfirmed") return "unconfirmed";
  if (status === "insufficient_data") return "no data";
  return status || "n/a";
}

function optionsFlowStatusZh(status) {
  if (status === "confirmed") return "confirmed";
  if (status === "degraded") return "部分降级";
  if (status === "not_connected") return "未连接";
  if (status === "no_flow_confirmation") return "未确认";
  return status || "n/a";
}

function expectationStatusZh(status) {
  if (status === "early_variant") return "早期变异";
  if (status === "partly_priced") return "部分计价";
  if (status === "priced_in") return "已计价";
  if (status === "unconfirmed") return "未确认";
  return status || "n/a";
}

function spendCategoryZh(category) {
  const map = {
    rd: "研发",
    sales_marketing: "销售/市场",
    capex: "资本开支",
    buyback: "回购",
    mna: "并购/战略投资",
  };
  return map[category] || category || "未分类";
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
  await refreshBrief();

  elements.sourceCount.textContent = String(state.sources.length);
  elements.watchlistCount.textContent = String(state.brief?.counts?.dynamic_watchlist || 0);
  elements.fetchedCount.textContent = String(signalsPayload.last_scan?.fetched_count || 0);
  elements.statusLine.textContent = `已加载 ${state.candidates.length} 个机会`;
  elements.scanProgress.hidden = Boolean(signalsPayload.last_scan?.completed_at);
  if (!signalsPayload.last_scan?.completed_at) elements.progressText.textContent = "等待第一次自动分析";
  showErrors([]);
  setView(state.view);
}

async function refreshDashboard() {
  try {
    const response = await fetch("/api/signals?limit=200");
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "Failed to refresh dashboard");
    state.candidates = payload.candidates || [];
    state.articles = payload.last_scan?.articles || [];
    state.sourceCounts = payload.last_scan?.source_counts || {};
    elements.fetchedCount.textContent = String(payload.last_scan?.fetched_count || 0);
    await refreshBrief();
    elements.watchlistCount.textContent = String(state.brief?.counts?.dynamic_watchlist || 0);
    elements.statusLine.textContent = `已加载 ${state.candidates.length} 个机会`;
    showErrors([]);
    render();
  } catch (error) {
    elements.statusLine.textContent = "连接中断，等待自动重连";
    showErrors([userFacingError(error)]);
  }
}

async function refreshBrief() {
  const response = await fetch("/api/brief");
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error || "Failed to load brief");
  state.brief = payload.brief;
}

elements.searchBox.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

elements.tabs.forEach((tab) => {
  tab.addEventListener("click", () => setView(tab.dataset.view));
});

elements.metricButtons.forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.viewJump));
});

window.addEventListener("hashchange", () => {
  const nextView = initialView();
  state.selectedEarningsTicker = initialSelectedEarningsTicker();
  if (nextView !== state.view) setView(nextView);
  else render();
});

loadInitialState().catch((error) => {
  elements.statusLine.textContent = "加载失败";
  showErrors([userFacingError(error)]);
});

setInterval(refreshDashboard, AUTO_REFRESH_MS);

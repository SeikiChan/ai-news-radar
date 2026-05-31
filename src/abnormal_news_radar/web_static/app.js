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
};

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
  if (Array.isArray(rows) && rows.length) return rows;
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
  return ["brief", "opportunities", "watchlist", "earnings", "technology", "market", "process", "sources"].includes(view) ? view : "brief";
}

function initialSelectedEarningsTicker() {
  const [view, ticker] = window.location.hash.replace("#", "").split(":");
  return view === "earnings" && ticker ? ticker.toUpperCase() : null;
}

function render() {
  updateStatusStrip();
  if (state.view === "brief") renderBrief();
  if (state.view === "opportunities") renderOpportunities();
  if (state.view === "watchlist") renderWatchlist();
  if (state.view === "earnings") renderEarnings();
  if (state.view === "technology") renderTechnology();
  if (state.view === "market") renderMarket();
  if (state.view === "process") renderProcess();
  if (state.view === "sources") renderSources();
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

  elements.liveDot.classList.toggle("stale", state.stale);
  elements.liveText.textContent = state.stale ? "OFFLINE" : "LIVE";
}

function shortTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
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
  const rows = visibleOpportunities();
  const top = rows[0];
  const tableRows = rows.slice(0, 12);
  const technologyCandidates = visibleCandidates().filter(hasTechnologyIntel).slice(0, 3);
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
        <p>技术博客/论文里的路线图与供应链早期信号。</p>
      </div>
      <button class="small-action" type="button" data-inline-view="technology">技术工作台 →</button>
    </section>
    <div class="content-grid">${technologyCandidates.map(renderTechnologyCard).join("") || '<div class="empty">本轮暂无明确技术路线图信号。</div>'}</div>

    <section class="section-head"><div><h3>证据缺口</h3><p>系统下一轮要补的证据，不是交给你的待办。</p></div></section>
    <section class="row"><div class="row-meta">${gaps || "<span>当前没有关键缺口。</span>"}</div></section>
  `;
  bindInlineViewButtons();
  bindOppRows();
}

function renderTopCall(row) {
  const article = articleOf(row);
  const action = row.action || actionFromScore(row.score);
  const tickers = candidateTickers(row);
  return `
    <article class="topcall act-${escapeHtml(action)}">
      <div class="topcall-head">
        <span class="act act-${escapeHtml(action)}">${escapeHtml(actionLabelZh(action))}</span>
        ${qualityChip(row)}${squeezeChip(row)}
        <span class="topcall-ticker">${escapeHtml(tickers.join(", ") || "待确认")}</span>
        <span class="topcall-name">${escapeHtml(row.company_name || "Unknown")}</span>
        <span class="topcall-score"><b>${Number(row.score || 0).toFixed(1)}</b><span>SCORE · 置信 ${fmtConf(row.confidence)}</span></span>
      </div>
      <div class="topcall-decision">${escapeHtml(row.decision || row.analyst_take || "")}</div>
      <div class="row-meta">${evidenceChips(row)}</div>
      <div class="topcall-catalyst"><a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(article.source || "")} · ${escapeHtml(article.title || "")}</a></div>
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
      <td><span class="act act-${escapeHtml(action)}">${escapeHtml(actionLabelZh(action))}</span>${qualityChip(row)}${squeezeChip(row)}</td>
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
      ${dimCards || renderQualityDim(row) || renderSqueezeDim(row) ? `<div class="detail-grid">${renderSqueezeDim(row)}${renderQualityDim(row)}${dimCards}</div>` : ""}
      ${missing ? `<div><span class="dim-k">还缺</span><div class="missing-list" style="margin-top:6px">${missing}</div></div>` : ""}
      ${renderTechnologyIntel(row)}
      ${renderEarningsAnalysis(row)}
      ${renderReadthroughAnalysis(row)}
      <div class="topcall-catalyst"><a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(article.source || "")} · 打开原文 ↗</a></div>
    </div>
  `;
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
          <a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(row.company_name || "Unknown")}</a>
          <span class="pill">${escapeHtml(candidateTickers(row).join(", ") || "ticker待确认")}</span>
          ${qualityChip(row)}${squeezeChip(row)}
        </div>
        <div class="terms">${escapeHtml(row.decision_zh || "")}</div>
        ${renderQualityDim(row) || renderSqueezeDim(row) ? `<div class="detail-grid">${renderSqueezeDim(row)}${renderQualityDim(row)}</div>` : ""}
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
  if (detail) return `<div class="content-grid">${renderEarningsCard(detail)}</div>`;
  return `
    <div class="content-grid">
      <article class="row">
        <div class="row-title">${escapeHtml(tickerOf(item))} ${escapeHtml(item.name || "")}<span class="pill">${escapeHtml(item.status_zh || "")}</span></div>
        <div class="row-meta">
          <span>日期=${escapeHtml(item.date || "")}</span>
          <span>时间=${escapeHtml(timeZh(item.time || ""))}</span>
          <span>EPS预期=${escapeHtml(item.eps_forecast || "n/a")}</span>
          <span>来源=Nasdaq public earnings calendar API</span>
        </div>
        <div class="terms">还没有抓到可拆解的财报原文。系统不会用模板伪造结论；等公司发布 release/10-Q/call transcript 后再解析。</div>
      </article>
    </div>
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

/* ------------------------------------------------------------------ */
/* TECHNOLOGY                                                         */
/* ------------------------------------------------------------------ */
function renderTechnology() {
  const candidates = visibleCandidates().filter(hasTechnologyIntel);
  elements.contentArea.innerHTML = `
    <section class="section-head">
      <div><h3>技术前沿任务</h3><p>读取技术博客、论文和研究报告，提取技术路线、被点名公司和供应链 read-through。</p></div>
    </section>
    <div class="content-grid">${candidates.map(renderTechnologyCard).join("") || '<div class="empty">本轮扫描暂未抓到明确技术路线图信号。</div>'}</div>
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

/* ------------------------------------------------------------------ */
/* MARKET                                                             */
/* ------------------------------------------------------------------ */
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

/* ------------------------------------------------------------------ */
/* shared evidence sub-renderers                                      */
/* ------------------------------------------------------------------ */
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

/* ------------------------------------------------------------------ */
/* small helpers                                                      */
/* ------------------------------------------------------------------ */
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

function spendCategoryZh(category) {
  const map = { rd: "研发", sales_marketing: "销售/市场", capex: "资本开支", buyback: "回购", mna: "并购/战略投资" };
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
  elements.scanProgress.hidden = Boolean(signalsPayload.last_scan?.completed_at);
  if (!signalsPayload.last_scan?.completed_at) elements.progressText.textContent = "等待第一次自动分析";
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

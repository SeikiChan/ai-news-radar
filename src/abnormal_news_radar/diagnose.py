"""Ticker-centric mispricing (错杀) diagnosis — the terminal's decision page.

Composes the positioning (FINRA short volume), options structure (CBOE GEX /
IV / P-C), relative-strength attribution, Yahoo short interest, VIX context,
and the radar's own stored news hits into one verdict:

* a transparent 0-100 mispricing score built from rule-based components,
* an explicit verdict band, and
* concrete *upgrade triggers* — the observable events that would turn
  "watch" into "actionable" — because a score without a trigger is decoration.

Every component degrades independently; missing data lowers confidence and is
listed in ``data_gaps`` instead of being papered over.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .gamma import assess_options_structure
from .market_structure import assess_market_structure, vix_context
from .positioning import assess_positioning
from .relative_strength import assess_relative_strength
from .short_interest import fetch_short_percent_of_float
from .storage import load_candidate_rows, load_signal_rows
from .yahoo import make_yahoo_fetcher

logger = logging.getLogger("ai_news_radar")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: A mispricing thesis needs an actual drawdown first.
MIN_DRAWDOWN_52W_PCT = -15.0
MIN_DROP_20D_PCT = -8.0
#: Radar news hits within this window count as fundamental-thesis evidence.
NEWS_LOOKBACK_DAYS = 90

VERDICT_BANDS = (
    (70, "mispriced_candidate", "错杀候选：结构支持，等待触发条件确认后可行动"),
    (50, "watchlist", "观察名单：部分证据支持，但关键确认缺失"),
    (0, "high_risk_or_unproven", "风险偏高或证据不足：不满足错杀假设，先证伪「真实恶化」"),
)


def diagnose_ticker(
    ticker: str,
    chart_fetcher: object | None = None,
    finra_fetcher: object | None = None,
    cboe_fetcher: object | None = None,
    yahoo_fetcher: object | None = None,
    data_dir: Path | None = None,
    now: datetime | None = None,
    market_context: dict[str, object] | None = None,
) -> dict[str, object]:
    symbol = ticker.strip().upper()
    if not symbol:
        return {"status": "error", "reason": "missing ticker"}
    data = Path(data_dir) if data_dir else PROJECT_ROOT / "data"

    relative = assess_relative_strength(symbol, fetcher=chart_fetcher, profile_fetcher=yahoo_fetcher)
    positioning = assess_positioning(symbol, fetcher=finra_fetcher, cache_dir=data / "finra_short_volume", now=now)
    options = assess_options_structure(
        symbol, fetcher=cboe_fetcher, history_path=data / "options_structure_history.jsonl", now=now
    )
    short_interest = _short_interest(symbol, yahoo_fetcher)
    market = market_context if market_context is not None else assess_market_structure(
        cboe_fetcher=cboe_fetcher,
        finra_fetcher=finra_fetcher,
        chart_fetcher=chart_fetcher,
        data_dir=data,
        now=now,
    )
    vix = market.get("vix") if isinstance(market.get("vix"), dict) else vix_context(chart_fetcher)
    news = _radar_news_hits(symbol, data, now=now)

    if relative.get("status") != "ok":
        reason = str(relative.get("reason") or "")
        retryable = "限流" in reason or "网络" in reason or "不可用" in reason
        return {
            "status": "insufficient_data",
            "ticker": symbol,
            "reason": reason,
            "retryable": retryable,
            "summary_zh": f"{symbol} 暂时无法诊断：{reason}。" + ("点「诊断」重试即可。" if retryable else ""),
            "components": _components(relative, positioning, options, short_interest, vix, news, market),
        }

    trend = relative.get("trend") if isinstance(relative.get("trend"), dict) else {}
    premise = _drawdown_premise(trend)
    scored = _score(relative, positioning, options, short_interest, news, premise)
    if premise.get("in_drawdown"):
        triggers = _triggers(symbol, relative, positioning, options, news)
    else:
        triggers = [f"等待错杀前提出现（距52周高点 ≤ {MIN_DRAWDOWN_52W_PCT}% 或 20日跌幅 ≤ {MIN_DROP_20D_PCT}%）后再诊断"]
    verdict_key, verdict_zh = _verdict(scored["total"], premise)
    gaps = _data_gaps(positioning, options, short_interest, vix, news)
    action_plan = _action_plan(symbol, premise, verdict_key, relative, positioning, options, market)

    result = {
        "status": "ok",
        "ticker": symbol,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "premise": premise,
        "score": scored["total"],
        "score_components": scored["components"],
        "verdict": verdict_key,
        "verdict_zh": verdict_zh,
        "triggers_zh": triggers,
        "action_plan": action_plan,
        "data_gaps": gaps,
        "summary_zh": _summary_zh(symbol, scored["total"], verdict_zh, premise, gaps),
        "components": _components(relative, positioning, options, short_interest, vix, news, market),
        "method_zh": (
            "错杀分为透明规则打分：跌幅归因(25) + 卖压衰竭(20) + 空头行为(20) + 期权结构(20) + 基本面证据(15)。"
            "分数只回答「结构是否支持错杀假设」，行动必须等触发条件出现。每次诊断会存档，用 report 机制回测命中率。"
        ),
    }
    _archive_diagnosis(result, data / "diagnoses.jsonl")
    return result


def _archive_diagnosis(result: dict[str, object], path: Path) -> None:
    """One archived verdict per ticker per day, so hit rates are backtestable."""
    day = str(result.get("generated_at") or "")[:10]
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ticker") == result.get("ticker") and str(row.get("generated_at") or "")[:10] == day:
                    return
        row = {
            "ticker": result.get("ticker"),
            "generated_at": result.get("generated_at"),
            "score": result.get("score"),
            "verdict": result.get("verdict"),
            "in_drawdown": (result.get("premise") or {}).get("in_drawdown"),
            "data_gaps": result.get("data_gaps"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("diagnosis archive write failed: %s", exc)


def _drawdown_premise(trend: dict[str, object]) -> dict[str, object]:
    off_high = _to_float(trend.get("pct_off_52w_high"))
    drop_20d = _to_float(trend.get("return_20d_pct"))
    in_drawdown = bool(
        (off_high is not None and off_high <= MIN_DRAWDOWN_52W_PCT)
        or (drop_20d is not None and drop_20d <= MIN_DROP_20D_PCT)
    )
    return {
        "in_drawdown": in_drawdown,
        "pct_off_52w_high": off_high,
        "return_20d_pct": drop_20d,
        "rule_zh": f"前提：距52周高点 ≤ {MIN_DRAWDOWN_52W_PCT}% 或 20日跌幅 ≤ {MIN_DROP_20D_PCT}%。",
    }


def _score(
    relative: dict[str, object],
    positioning: dict[str, object],
    options: dict[str, object],
    short_interest: dict[str, object],
    news: dict[str, object],
    premise: dict[str, object],
) -> dict[str, object]:
    components = [
        _attribution_points(relative),
        _exhaustion_points(relative),
        _positioning_points(positioning, short_interest),
        _options_points(options),
        _evidence_points(news),
    ]
    total = sum(int(c["points"]) for c in components)
    if not premise.get("in_drawdown"):
        total = min(total, 30)
    return {"total": max(0, min(100, total)), "components": components}


def _attribution_points(relative: dict[str, object]) -> dict[str, object]:
    attribution = relative.get("attribution") if isinstance(relative.get("attribution"), dict) else {}
    verdict = str(attribution.get("verdict") or "")
    points, reason = {
        "sector_driven": (25, "下跌主要由板块解释，个股残差小——典型陪葬式错杀形态"),
        "mixed": (13, "板块与个股因素混合，需要进一步拆分"),
        "idiosyncratic": (5, "下跌以个股自身为主——必须先排除真实基本面恶化"),
        "not_in_drawdown_20d": (5, "近20日未下跌"),
    }.get(verdict, (8, "归因数据不足"))
    return {"name": "跌幅归因", "max": 25, "points": points, "reason_zh": reason}


def _exhaustion_points(relative: dict[str, object]) -> dict[str, object]:
    trend = relative.get("trend") if isinstance(relative.get("trend"), dict) else {}
    exhaustion = str(trend.get("selling_exhaustion") or "unknown")
    rsi = _to_float(trend.get("rsi_14"))
    points, reason = {
        "exhausting": (16, "下跌缩量，卖压衰竭中"),
        "steady": (8, "卖压平稳，未见衰竭也未加速"),
        "not_applicable": (8, "近5日未明显下跌"),
        "active_selling": (0, "仍在放量下跌，接刀风险高"),
    }.get(exhaustion, (6, "卖压状态未知"))
    if rsi is not None and rsi <= 30:
        points = min(20, points + 4)
        reason += f"；RSI={rsi} 已超卖"
    return {"name": "卖压衰竭", "max": 20, "points": points, "reason_zh": reason}


def _positioning_points(positioning: dict[str, object], short_interest: dict[str, object]) -> dict[str, object]:
    if positioning.get("status") != "ok":
        return {"name": "空头行为", "max": 20, "points": 6, "reason_zh": "FINRA 卖空占比不可用，给中性偏低分"}
    trend = str(positioning.get("trend") or "")
    level = str(positioning.get("level") or "")
    points, reason = {
        "falling": (15, "卖空占比回落——空头开始回补"),
        "flat": (8, "卖空占比持平"),
        "rising": (2, "卖空占比仍在上升——空头继续施压"),
    }.get(trend, (6, "卖空占比趋势历史不足"))
    if trend == "falling" and level in {"high", "elevated"}:
        points += 5
        reason += "，且从高位回落（轧空弹性大）"
    spf = _to_float(short_interest.get("short_percent_of_float"))
    if spf is not None:
        reason += f"；空头占流通盘 {spf * 100:.1f}%"
    return {"name": "空头行为", "max": 20, "points": min(20, points), "reason_zh": reason}


def _options_points(options: dict[str, object]) -> dict[str, object]:
    if options.get("status") != "ok":
        return {"name": "期权结构", "max": 20, "points": 6, "reason_zh": "期权链不可用，给中性偏低分"}
    gex = options.get("gex") if isinstance(options.get("gex"), dict) else {}
    term = options.get("iv_term") if isinstance(options.get("iv_term"), dict) else {}
    pc = options.get("put_call") if isinstance(options.get("put_call"), dict) else {}
    points = 0
    reasons = []
    if str(gex.get("regime") or "") == "positive_gamma":
        reasons.append("OI 符号模型估算净 GEX 为正；未观测实际做市商方向，不计入方向分")
    else:
        reasons.append("OI 符号模型估算净 GEX 为负；未观测实际做市商方向，不计入方向分")
    if term.get("status") == "ok" and term.get("inverted"):
        points += 7
        reasons.append("近月 ATM IV 高于远月，短期期权隐含波动率较高；需结合事件日历解释")
    oi_ratio = _to_float(pc.get("oi_ratio"))
    if oi_ratio is not None:
        reasons.append(f"P/C OI={oi_ratio} 仅表示未平仓合约数量比例；不能推断多空方向，不计分")
    return {"name": "期权结构", "max": 20, "points": min(20, points), "reason_zh": "；".join(reasons)}


def _evidence_points(news: dict[str, object]) -> dict[str, object]:
    hard = int(news.get("hard_evidence_hits") or 0)
    total = int(news.get("total_hits") or 0)
    if hard > 0:
        return {
            "name": "基本面证据",
            "max": 15,
            "points": 15,
            "reason_zh": f"雷达近{NEWS_LOOKBACK_DAYS}天有 {hard} 条硬证据命中——基本面论点仍然成立",
        }
    if total > 0:
        return {"name": "基本面证据", "max": 15, "points": 10, "reason_zh": f"雷达有 {total} 条一般信号，但缺硬证据"}
    return {"name": "基本面证据", "max": 15, "points": 7, "reason_zh": "雷达近期无该标的新闻命中：错杀假设缺少正面证据，也无新利空"}


def _triggers(
    symbol: str,
    relative: dict[str, object],
    positioning: dict[str, object],
    options: dict[str, object],
    news: dict[str, object],
) -> list[str]:
    triggers = []
    trend = relative.get("trend") if isinstance(relative.get("trend"), dict) else {}
    attribution = relative.get("attribution") if isinstance(relative.get("attribution"), dict) else {}
    if str(positioning.get("trend") or "") == "rising":
        triggers.append("FINRA 卖空成交占比连续 3 日回落（空头停止施压）")
    if str(trend.get("selling_exhaustion") or "") == "active_selling":
        triggers.append("出现缩量企稳日或放量长下影线（卖压衰竭信号）")
    if str(attribution.get("verdict") or "") == "idiosyncratic":
        triggers.append("核对最近 8-K/新闻确认无基本面恶化（个股残差过大，先证伪利空）")
    if int(news.get("hard_evidence_hits") or 0) == 0:
        triggers.append("雷达扫到该标的新的硬证据（订单/产能/具名客户）")
    sma20 = _to_float(trend.get("sma20"))
    if sma20 is not None and _to_float(trend.get("price")) is not None and float(trend["price"]) < sma20:
        triggers.append(f"站回 20 日均线 ${sma20}")
    return triggers or ["无单一缺失项；以错杀分是否达到 70（错杀候选线）和仓位纪律决定是否分批行动"]


def _action_plan(
    symbol: str,
    premise: dict[str, object],
    verdict: str,
    relative: dict[str, object],
    positioning: dict[str, object],
    options: dict[str, object],
    market: dict[str, object],
) -> dict[str, object]:
    """Concrete levels and condition->action lines — the "now what" layer.

    The 20DMA is a trend reference. Option-chain concentration levels are
    displayed as context only; OI does not reveal direction and is not used as
    support, resistance, entry, target, or invalidation. This is a research
    framework, not a trade instruction.
    """
    trend = relative.get("trend") if isinstance(relative.get("trend"), dict) else {}
    gex = options.get("gex") if isinstance(options.get("gex"), dict) else {}
    strike_map = options.get("strike_map") if isinstance(options.get("strike_map"), dict) else {}
    put_wall = _to_float(gex.get("put_wall"))
    call_wall = _to_float(gex.get("call_wall"))
    sma20 = _to_float(trend.get("sma20"))
    max_volume_strike = _to_float(strike_map.get("max_volume_strike"))

    stance, stance_zh = {
        "mispriced_candidate": ("plan_entry", "结构支持错杀假设：可以制定分批买入计划，按下方触发执行"),
        "watchlist": ("watch", "挂入观察池：结构部分支持，出现触发信号前不动手"),
        "high_risk_or_unproven": ("stand_aside", "暂不参与：先证伪「真实恶化」，证据改善前只跟踪"),
        "no_mispricing_premise": ("stand_aside", "不参与：没有明显回撤，错杀前提不成立"),
    }.get(verdict, ("stand_aside", "暂不参与"))

    levels = []
    if put_wall is not None:
        levels.append({"price": put_wall, "label_zh": "Put-side GEX 峰值：OI 符号模型参考，不代表支撑位"})
    if sma20 is not None:
        levels.append({"price": sma20, "label_zh": "20 日均线：短期趋势分界"})
    if call_wall is not None:
        levels.append({"price": call_wall, "label_zh": "Call-side GEX 峰值：OI 符号模型参考，不代表阻力位"})
    if max_volume_strike is not None and all(abs(max_volume_strike - float(level["price"])) > 0.01 for level in levels):
        levels.append({"price": max_volume_strike, "label_zh": "当日期权成交量集中位：成交量不区分买卖方向"})
    levels.sort(key=lambda level: float(level["price"]))

    playbook = []
    if stance == "stand_aside":
        playbook.append("当前不满足买入研究条件；只跟踪触发条件变化，不做价格预设。")
    else:
        entry_conditions = []
        if str(positioning.get("trend") or "") == "rising":
            entry_conditions.append("FINRA 卖空占比连续 3 日回落")
        if str(trend.get("selling_exhaustion") or "") == "active_selling":
            entry_conditions.append("出现缩量企稳日")
        if entry_conditions:
            playbook.append(f"买入触发：{'，且'.join(entry_conditions)} → 首仓不超过计划仓位的 1/3，留出加仓空间。")
        else:
            playbook.append("买入触发已基本满足 → 分批建仓（首仓 ≤ 1/3），不追单日大阳线。")

    posture = str(market.get("posture") or "unknown")
    market_adjustment_zh = {
        "hostile": "大盘调整：OI 符号模型的净 GEX 估算偏负或卖空成交占比上升；环境标签只是结构代理，买入触发需连续 2 个收盘确认。",
        "friendly": "大盘调整：结构代理指标偏友好（OI 符号模型净 GEX 偏正且卖空占比回落）；仍按标准纪律执行。",
        "neutral": "大盘调整：大盘环境中性——按标准触发条件执行。",
        "unknown": "大盘调整：大盘数据不可用——按保守（hostile）标准执行。",
    }[posture if posture in {"hostile", "friendly", "neutral"} else "unknown"]

    return {
        "stance": stance,
        "stance_zh": stance_zh,
        "levels": levels,
        "playbook_zh": playbook,
        "market_adjustment_zh": market_adjustment_zh,
        "disclaimer_zh": (
            "本剧本是基于公开数据结构的研究框架，不是投资指令；"
            "点位来自期权未平仓分布与均线，会随持仓变化每日移动，执行前需重新诊断确认。"
        ),
    }


def _verdict(total: int, premise: dict[str, object]) -> tuple[str, str]:
    if not premise.get("in_drawdown"):
        return "no_mispricing_premise", "无错杀前提：该标的当前不处于明显回撤中"
    for threshold, key, text in VERDICT_BANDS:
        if total >= threshold:
            return key, text
    return "high_risk_or_unproven", VERDICT_BANDS[-1][2]


def _summary_zh(symbol: str, total: int, verdict_zh: str, premise: dict[str, object], gaps: list[str]) -> str:
    base = f"{symbol} 错杀分 {total}/100 —— {verdict_zh}。"
    if not premise.get("in_drawdown"):
        return f"{symbol}：{verdict_zh}（距52周高点 {premise.get('pct_off_52w_high')}%）。"
    if gaps:
        base += f" 缺失数据：{('、'.join(gaps))}。"
    return base


def _data_gaps(
    positioning: dict[str, object],
    options: dict[str, object],
    short_interest: dict[str, object],
    vix: dict[str, object],
    news: dict[str, object],
) -> list[str]:
    gaps = []
    if positioning.get("status") != "ok":
        gaps.append("FINRA 卖空占比")
    if options.get("status") != "ok":
        gaps.append("CBOE 期权链")
    if short_interest.get("status") != "ok":
        gaps.append("空头持仓(SI)")
    if vix.get("status") != "ok":
        gaps.append("VIX")
    if int(news.get("total_hits") or 0) == 0:
        gaps.append("雷达新闻命中")
    return gaps


def _short_interest(symbol: str, yahoo_fetcher: object | None) -> dict[str, object]:
    try:
        fetch = yahoo_fetcher or make_yahoo_fetcher()
        return fetch_short_percent_of_float(symbol, fetch)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "ticker": symbol, "reason": str(exc)[:160]}


def _radar_news_hits(symbol: str, data_dir: Path, now: datetime | None = None) -> dict[str, object]:
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(days=NEWS_LOOKBACK_DAYS)
    rows = load_signal_rows(data_dir / "signals.jsonl", limit=2000)
    rows += load_candidate_rows(data_dir / "candidates.jsonl", limit=2000)
    hits = []
    seen_links = set()
    for row in rows:
        tickers = {str(t).upper() for t in (row.get("tickers") or [])}
        if symbol not in tickers:
            continue
        article = row.get("article") if isinstance(row.get("article"), dict) else {}
        stamp = _row_time(article)
        if stamp is not None and stamp < cutoff:
            continue
        link = str(article.get("link") or "")
        if link and link in seen_links:
            continue
        seen_links.add(link)
        hits.append(
            {
                "title": str(article.get("title") or ""),
                "link": link,
                "published": str(article.get("published") or ""),
                "evidence_tier": str(row.get("evidence_tier") or ""),
                "score": row.get("score"),
                "matched_terms": (row.get("matched_terms") or [])[:6],
            }
        )
    hits.sort(key=lambda h: str(h.get("published") or ""), reverse=True)
    hard = sum(1 for h in hits if h.get("evidence_tier") == "hard_evidence")
    return {
        "status": "ok",
        "total_hits": len(hits),
        "hard_evidence_hits": hard,
        "recent": hits[:8],
        "lookback_days": NEWS_LOOKBACK_DAYS,
    }


def _row_time(article: dict[str, object]) -> datetime | None:
    fetched = str(article.get("fetched_at") or "")
    if fetched:
        try:
            return datetime.fromisoformat(fetched)
        except ValueError:
            pass
    published = str(article.get("published") or "")
    if published:
        try:
            stamp = parsedate_to_datetime(published)
            return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    return None


def _components(
    relative: dict[str, object],
    positioning: dict[str, object],
    options: dict[str, object],
    short_interest: dict[str, object],
    vix: dict[str, object],
    news: dict[str, object],
    market: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "relative_strength": relative,
        "positioning": positioning,
        "options_structure": options,
        "short_interest": short_interest,
        "vix": vix,
        "radar_news": news,
        "market_structure": market or {"status": "unavailable"},
    }


def _to_float(value: object) -> float | None:
    try:
        if value in {None, "", ".", "-"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

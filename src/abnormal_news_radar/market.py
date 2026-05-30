from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from io import StringIO
from urllib.request import Request, urlopen

from .model import MarketSource

USER_AGENT = "AI-News-Radar/0.1 (+local-market-regime)"
FETCH_TIMEOUT_SECONDS = 6

POLICY_EVENT_TOPICS: dict[str, tuple[str, int, str]] = {
    "tariff": ("tariffs", 3, "关税/贸易摩擦可能改变进口成本、供应链和风险偏好。"),
    "tariffs": ("tariffs", 3, "关税/贸易摩擦可能改变进口成本、供应链和风险偏好。"),
    "export control": ("export_controls", 3, "出口管制会直接影响半导体、AI、先进制造和中国暴露。"),
    "export controls": ("export_controls", 3, "出口管制会直接影响半导体、AI、先进制造和中国暴露。"),
    "sanction": ("sanctions", 3, "制裁会改变国家/行业风险溢价，并可能影响能源、金融和供应链。"),
    "sanctions": ("sanctions", 3, "制裁会改变国家/行业风险溢价，并可能影响能源、金融和供应链。"),
    "china": ("china_policy", 3, "中国相关政策会影响半导体、工业、材料、消费和跨国供应链。"),
    "taiwan": ("taiwan_policy", 3, "台湾相关消息是半导体供应链和地缘风险核心变量。"),
    "semiconductor": ("semiconductors", 3, "半导体政策直接影响 AI、设备、EDA、代工和封测链。"),
    "semiconductors": ("semiconductors", 3, "半导体政策直接影响 AI、设备、EDA、代工和封测链。"),
    "chips": ("semiconductors", 3, "芯片政策直接影响 AI、设备、EDA、代工和封测链。"),
    "artificial intelligence": ("ai", 2, "AI 政策会影响算力、云、软件、监管和能源需求。"),
    "data center": ("data_centers", 2, "数据中心政策会影响电力、制冷、地产、服务器和网络设备。"),
    "energy": ("energy", 2, "能源政策会影响通胀、工业成本和电力基础设施。"),
    "nuclear": ("nuclear_power", 2, "核电政策会影响数据中心电力、铀、设备和公用事业。"),
    "critical minerals": ("critical_minerals", 2, "关键矿产政策会影响电池、军工、半导体材料和供应安全。"),
    "rare earth": ("critical_minerals", 2, "稀土政策会影响国防、电动车、工业电机和供应链安全。"),
    "defense": ("defense", 2, "国防政策会影响主承包商、无人系统、电子战和通信链。"),
    "procurement": ("federal_procurement", 2, "联邦采购政策会影响政府承包商订单节奏。"),
    "federal contracting": ("federal_procurement", 2, "联邦合同政策会影响政府承包商订单节奏。"),
}


class SourceLimitedError(RuntimeError):
    pass


def collect_market_regime(
    sources: list[MarketSource],
    fetcher: object | None = None,
) -> dict[str, object]:
    fetch = fetcher or _fetch_text
    metrics: dict[str, dict[str, object]] = {}
    events: list[dict[str, object]] = []
    health: list[dict[str, object]] = []

    for source in sources:
        if source.status == "requires_key":
            health.append(_health(source, "skipped", "requires key"))
            continue
        try:
            raw = fetch(source.url)
            parsed = _parse_source(source, raw)
        except SourceLimitedError as exc:
            health.append(_health(source, "limited", str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 - market source failures must be reported, not fatal.
            health.append(_health(source, "error", str(exc)))
            continue

        metrics.update(parsed.get("metrics", {}))
        events.extend(parsed.get("events", []))
        health.append(_health(source, "ok", parsed.get("message", "")))

    events = _enrich_event_summaries(events, fetch)
    return assess_market_regime(metrics, health, events)


def assess_market_regime(
    metrics: dict[str, dict[str, object]],
    source_health: list[dict[str, object]],
    events: list[dict[str, object]],
) -> dict[str, object]:
    score = 0
    drivers: list[str] = []

    spy_20d = _metric_number(metrics, "spy", "change_20d_pct")
    qqq_20d = _metric_number(metrics, "qqq", "change_20d_pct")
    vix = _metric_number(metrics, "vix", "value")
    vix_5d = _metric_number(metrics, "vix", "change_5d")
    ten_year = _metric_number(metrics, "us10y", "value")
    two_year = _metric_number(metrics, "us2y", "value")
    ten_year_20d = _metric_number(metrics, "us10y", "change_20d_bp")
    dollar_20d = _metric_number(metrics, "broad_dollar", "change_20d_pct")
    cpi_yoy = _metric_number(metrics, "cpi", "yoy_pct")
    ppi_yoy = _metric_number(metrics, "ppi", "yoy_pct")
    unemployment = _metric_number(metrics, "unemployment_rate", "value")

    score += _momentum_points("SPY", spy_20d, drivers)
    score += _momentum_points("QQQ", qqq_20d, drivers)

    if vix is not None:
        if vix >= 25:
            score -= 2
            drivers.append(f"VIX 升至 {vix:.1f}，波动率偏高，市场风险承受力下降")
        elif vix >= 20:
            score -= 1
            drivers.append(f"VIX 为 {vix:.1f}，高于舒适区")
        elif vix < 16:
            score += 1
            drivers.append(f"VIX 为 {vix:.1f}，波动率环境温和")
    if vix_5d is not None and vix_5d >= 4:
        score -= 1
        drivers.append(f"VIX 近 5 个观察日上升 {vix_5d:.1f} 点，风险偏好转弱")

    if ten_year_20d is not None:
        if ten_year_20d >= 25:
            score -= 1
            drivers.append(f"10 年期美债收益率近 20 个观察日上升 {ten_year_20d:.0f}bp，估值压力上升")
        elif ten_year_20d <= -25:
            score += 1
            drivers.append(f"10 年期美债收益率近 20 个观察日下降 {abs(ten_year_20d):.0f}bp，成长股估值压力缓和")

    if ten_year is not None and two_year is not None:
        curve_bp = (ten_year - two_year) * 100
        metrics["yield_curve_2s10s"] = {
            "label": "2s10s Treasury curve",
            "value": round(curve_bp, 1),
            "unit": "bp",
            "source": "FRED/Treasury",
            "interpretation": _curve_interpretation(curve_bp),
            "status": "ok",
        }
        if curve_bp < -50:
            score -= 1
            drivers.append(f"2s10s 曲线深度倒挂 {curve_bp:.0f}bp，经济周期信号偏谨慎")

    if dollar_20d is not None:
        if dollar_20d >= 2:
            score -= 1
            drivers.append(f"美元指数近 20 个观察日上涨 {dollar_20d:.1f}%，全球流动性压力上升")
        elif dollar_20d <= -2:
            score += 1
            drivers.append(f"美元指数近 20 个观察日下跌 {abs(dollar_20d):.1f}%，全球风险资产压力缓和")

    if cpi_yoy is not None and cpi_yoy >= 4:
        score -= 1
        drivers.append(f"CPI 同比 {cpi_yoy:.1f}%，通胀仍偏高")
    if ppi_yoy is not None and ppi_yoy >= 4:
        score -= 1
        drivers.append(f"PPI 同比 {ppi_yoy:.1f}%，成本压力仍需关注")
    if unemployment is not None and unemployment >= 5:
        score -= 1
        drivers.append(f"失业率 {unemployment:.1f}%，劳动力市场压力上升")

    core_keys = ["us10y", "us2y", "vix", "spy", "qqq"]
    connected_core = sum(1 for key in core_keys if key in metrics)
    error_count = sum(1 for item in source_health if item.get("status") == "error")
    if connected_core >= 4:
        status = "connected" if error_count == 0 else "degraded"
    elif metrics:
        status = "degraded"
    else:
        status = "not_connected"

    regime = _regime_label(score)
    summary = _summary(regime, score, drivers, connected_core, error_count)
    generated_at = datetime.now(timezone.utc).isoformat()
    prioritized_events = _prioritize_events(events)

    return {
        "status": status,
        "regime": regime,
        "score": score,
        "summary": summary,
        "generated_at": generated_at,
        "drivers": drivers[:8],
        "calculation_notes": _calculation_notes(),
        "methodology": _methodology(),
        "metrics": _ordered_metrics(metrics),
        "source_health": source_health,
        "events": prioritized_events[:12],
        "implications": _implications(regime),
        "needed_feeds": _needed_feeds(metrics),
    }


def _parse_source(source: MarketSource, raw: str) -> dict[str, object]:
    name = source.name
    if name == "U.S. Treasury Daily Yield Curve XML":
        return _parse_treasury_curve(source, raw)
    if name.startswith("FRED DGS10"):
        return {"metrics": {"us10y": _csv_series_metric(source, raw, "10Y Treasury yield", "yield", "pct", bp_changes=True)}}
    if name.startswith("FRED DGS2"):
        return {"metrics": {"us2y": _csv_series_metric(source, raw, "2Y Treasury yield", "yield", "pct", bp_changes=True)}}
    if name.startswith("FRED DXY"):
        return {"metrics": {"broad_dollar": _csv_series_metric(source, raw, "Broad dollar index", "index", "index")}}
    if name.startswith("Yahoo U.S. Dollar Index"):
        return {"metrics": {"broad_dollar": _yahoo_chart_metric(source, raw, "DX-Y.NYB", "U.S. Dollar Index")}}
    if name.startswith("Cboe VIX"):
        return {"metrics": {"vix": _csv_series_metric(source, raw, "VIX", "volatility", "index", date_field="DATE", value_field="CLOSE", absolute_changes=True)}}
    if name.startswith("Yahoo SPY"):
        return {"metrics": {"spy": _yahoo_chart_metric(source, raw, "SPY", "S&P 500 ETF")}}
    if name.startswith("Yahoo QQQ"):
        return {"metrics": {"qqq": _yahoo_chart_metric(source, raw, "QQQ", "Nasdaq 100 ETF")}}
    if name.startswith("BLS CPI"):
        return {"metrics": {"cpi": _bls_metric(source, raw, "CPI", "inflation")}}
    if name.startswith("BLS PPI"):
        return {"metrics": {"ppi": _bls_metric(source, raw, "PPI final demand", "inflation")}}
    if name.startswith("BLS Unemployment"):
        return {"metrics": {"unemployment_rate": _bls_metric(source, raw, "Unemployment rate", "labor")}}
    if source.type == "rss":
        return {"metrics": {}, "events": _rss_events(source, raw)}
    return {"metrics": {}, "events": [], "message": "source type not used in regime score"}


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        raw = response.read()
    return raw.decode("utf-8-sig", errors="replace")


def _csv_series_metric(
    source: MarketSource,
    raw: str,
    label: str,
    category: str,
    unit: str,
    date_field: str = "observation_date",
    value_field: str | None = None,
    bp_changes: bool = False,
    absolute_changes: bool = False,
) -> dict[str, object]:
    rows = list(csv.DictReader(StringIO(raw)))
    if not rows:
        raise ValueError("empty csv")
    if value_field is None:
        value_field = next((field for field in rows[0] if field != date_field), "")
    series = []
    for row in rows:
        value = _to_float(row.get(value_field))
        date = row.get(date_field, "")
        if value is not None and date:
            series.append((date, value))
    if not series:
        raise ValueError("csv contains no numeric observations")
    latest_date, latest_value = series[-1]
    metric = _base_metric(source, label, category, latest_value, unit, latest_date)
    _add_series_changes(metric, series, bp_changes=bp_changes, absolute_changes=absolute_changes)
    return metric


def _yahoo_chart_metric(source: MarketSource, raw: str, symbol: str, label: str) -> dict[str, object]:
    payload = json.loads(raw)
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        raise ValueError("missing yahoo chart result")
    timestamps = result.get("timestamp") or []
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    series = []
    for ts, close in zip(timestamps, closes):
        value = _to_float(close)
        if value is not None:
            date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
            series.append((date, value))
    if not series:
        raise ValueError(f"{symbol} chart contains no closes")
    latest_date, latest_value = series[-1]
    metric = _base_metric(source, label, "equity", latest_value, "price", latest_date)
    _add_series_changes(metric, series)
    return metric


def _bls_metric(source: MarketSource, raw: str, label: str, category: str) -> dict[str, object]:
    payload = json.loads(raw)
    if payload.get("status") != "REQUEST_SUCCEEDED":
        message = "; ".join(str(item) for item in payload.get("message", []))
        if "threshold" in message.lower() or "allocated" in message.lower():
            raise SourceLimitedError(message or "BLS request limit reached")
        raise ValueError(message or "BLS request was not processed")
    series = payload.get("Results", {}).get("series", [])
    if not series:
        raise ValueError("missing BLS series")
    rows = series[0].get("data", [])
    observations = []
    for row in rows:
        period = str(row.get("period", ""))
        if not period.startswith("M"):
            continue
        month = int(period[1:])
        value = _to_float(row.get("value"))
        if value is None:
            continue
        date = f"{int(row['year']):04d}-{month:02d}"
        observations.append((date, value))
    if not observations:
        raise ValueError("BLS series contains no numeric observations")
    observations.sort(key=lambda item: item[0])
    latest_date, latest_value = observations[-1]
    metric = _base_metric(source, label, category, latest_value, "index" if category == "inflation" else "pct", latest_date)
    prior_year = _same_month_prior_year(observations, latest_date)
    if prior_year is not None and prior_year != 0:
        metric["yoy_pct"] = round((latest_value / prior_year - 1) * 100, 2)
    return metric


def _parse_treasury_curve(source: MarketSource, raw: str) -> dict[str, object]:
    root = ET.fromstring(raw)
    ns = {
        "a": "http://www.w3.org/2005/Atom",
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
        "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
    }
    entries = root.findall("a:entry", ns)
    observations = []
    for entry in entries:
        props = entry.find("a:content/m:properties", ns)
        if props is None:
            continue
        data = {child.tag.split("}")[-1]: child.text for child in list(props)}
        date = str(data.get("NEW_DATE") or "")[:10]
        two = _to_float(data.get("BC_2YEAR"))
        ten = _to_float(data.get("BC_10YEAR"))
        if date and two is not None and ten is not None:
            observations.append((date, two, ten))
    if not observations:
        raise ValueError("Treasury XML contains no 2Y/10Y observations")
    observations.sort(key=lambda item: item[0])
    latest_date, two, ten = observations[-1]
    two_metric = _base_metric(source, "Treasury 2Y yield", "yield", two, "pct", latest_date)
    ten_metric = _base_metric(source, "Treasury 10Y yield", "yield", ten, "pct", latest_date)
    _add_series_changes(two_metric, [(date, value) for date, value, _ten in observations], bp_changes=True)
    _add_series_changes(ten_metric, [(date, value) for date, _two, value in observations], bp_changes=True)
    return {
        "metrics": {
            "us2y": two_metric,
            "us10y": ten_metric,
        }
    }


def _rss_events(source: MarketSource, raw: str) -> list[dict[str, object]]:
    root = ET.fromstring(raw)
    events = []
    for item in root.findall("./channel/item")[:3]:
        event = {
                "source": source.name,
                "title": _child_text(item, "title"),
                "link": _child_text(item, "link"),
                "published": _child_text(item, "pubDate"),
                "summary": _clean_summary(_child_text(item, "description")),
            }
        event.update(_policy_event_fields(event, source))
        events.append(event)
    if not events:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns)[:3]:
            link = entry.find("a:link", ns)
            event = {
                    "source": source.name,
                    "title": _child_text(entry, "a:title", ns),
                    "link": link.attrib.get("href", "") if link is not None else "",
                    "published": _child_text(entry, "a:updated", ns),
                    "summary": _clean_summary(_child_text(entry, "a:summary", ns)),
                }
            event.update(_policy_event_fields(event, source))
            events.append(event)
    return [event for event in events if event.get("title")]


def _policy_event_fields(event: dict[str, object], source: MarketSource) -> dict[str, object]:
    if "policy" not in source.group and "white house" not in source.name.lower() and "trump" not in source.name.lower():
        return {}
    text = f"{event.get('title', '')} {event.get('summary', '')}".lower()
    topics: list[str] = []
    reads: list[str] = []
    importance = 0
    for term, (topic, points, read) in POLICY_EVENT_TOPICS.items():
        if term in text and topic not in topics:
            topics.append(topic)
            reads.append(read)
            importance = max(importance, points)
    if not topics:
        return {"policy_importance": 1, "policy_topics": [], "market_read": "政策源事件：保留原文链接，等待主题匹配。"}
    return {
        "policy_importance": importance,
        "policy_topics": topics,
        "market_read": " ".join(reads[:2]),
    }


def _prioritize_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    def key(index_event: tuple[int, dict[str, object]]) -> tuple[int, int, int]:
        index, event = index_event
        importance = int(event.get("policy_importance") or 0)
        source = str(event.get("source") or "").lower()
        policy_source = 1 if "white house" in source or "trump" in source else 0
        return (importance, policy_source, -index)

    return [event for _index, event in sorted(enumerate(events), key=key, reverse=True)]


def _enrich_event_summaries(events: list[dict[str, object]], fetch: object) -> list[dict[str, object]]:
    enriched = []
    for index, event in enumerate(events):
        item = dict(event)
        summary = str(item.get("summary") or "")
        title = str(item.get("title") or "")
        link = str(item.get("link") or "")
        if index < 6 and link and (not summary or summary.strip().lower() == title.strip().lower()):
            try:
                item["summary"] = _page_summary(fetch(link), title)
            except Exception:  # noqa: BLE001 - article summary enrichment is optional.
                item["summary"] = summary
        enriched.append(item)
    return enriched


def _page_summary(raw: str, title: str, max_len: int = 360) -> str:
    paragraphs = []
    for paragraph in re.findall(r"(?is)<p[^>]*>(.*?)</p>", raw):
        cleaned = _clean_summary(paragraph, max_len=800)
        cleaned = re.sub(r"^For release at .*? Share\s+", "", cleaned)
        if _useful_summary_chunk(cleaned, title):
            paragraphs.append(cleaned)
        if len(" ".join(paragraphs)) >= max_len:
            break
    if paragraphs:
        summary = " ".join(paragraphs).strip()
        if len(summary) <= max_len:
            return summary
        return summary[: max_len - 1].rstrip() + "..."

    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", text)
    text = _clean_summary(text, max_len=4000)
    candidates = []
    for chunk in re.split(r"(?<=[.!?])\s+|\n+", text):
        chunk = chunk.strip()
        if not _useful_summary_chunk(chunk, title):
            continue
        candidates.append(chunk)
        if len(" ".join(candidates)) >= max_len:
            break
    summary = " ".join(candidates).strip()
    if not summary:
        return ""
    if len(summary) <= max_len:
        return summary
    return summary[: max_len - 1].rstrip() + "..."


def _useful_summary_chunk(chunk: str, title: str) -> bool:
    if len(chunk) < 70:
        return False
    lowered = chunk.lower()
    blocked = (
        "an official website",
        "official websites use",
        "secure .gov",
        "skip to main content",
        "stay connected",
        "facebook",
        "instagram",
        "youtube",
        "flickr",
        "linkedin",
        "subscribe",
        "back to home",
        "lock locked padlock",
        "provides the nation with a safe, flexible, and stable monetary and financial system",
        "federal open market committee",
        "monetary policy principles and practice",
    )
    if any(term in lowered for term in blocked):
        return False
    return lowered != title.lower()


def _base_metric(
    source: MarketSource,
    label: str,
    category: str,
    value: float,
    unit: str,
    as_of: str,
) -> dict[str, object]:
    return {
        "label": label,
        "category": category,
        "value": round(value, 4),
        "unit": unit,
        "as_of": as_of,
        "source": source.name,
        "source_url": source.url,
        "status": "ok",
    }


def _add_series_changes(
    metric: dict[str, object],
    series: list[tuple[str, float]],
    bp_changes: bool = False,
    absolute_changes: bool = False,
) -> None:
    latest = series[-1][1]
    metric["sparkline"] = _sparkline(series[-30:])
    metric["calculation"] = "5obs/20obs compare the latest valid observation with the value 5/20 valid observations earlier."
    if len(series) > 5:
        change = latest - series[-6][1]
        if bp_changes:
            metric["change_5d_bp"] = round(change * 100, 1)
        elif absolute_changes:
            metric["change_5d"] = round(change, 2)
        else:
            metric["change_5d_pct"] = round((latest / series[-6][1] - 1) * 100, 2)
    if len(series) > 20:
        change = latest - series[-21][1]
        if bp_changes:
            metric["change_20d_bp"] = round(change * 100, 1)
        elif absolute_changes:
            metric["change_20d"] = round(change, 2)
        else:
            metric["change_20d_pct"] = round((latest / series[-21][1] - 1) * 100, 2)


def _same_month_prior_year(observations: list[tuple[str, float]], latest_date: str) -> float | None:
    year = int(latest_date[:4]) - 1
    month = latest_date[5:7]
    target = f"{year:04d}-{month}"
    for date, value in observations:
        if date == target:
            return value
    return None


def _momentum_points(label: str, change_20d: float | None, drivers: list[str]) -> int:
    if change_20d is None:
        return 0
    if change_20d >= 3:
        drivers.append(f"{_market_label_zh(label)} 近 20 个观察日上涨 {change_20d:.1f}%，风险偏好正在改善")
        return 2
    if change_20d >= 1:
        drivers.append(f"{_market_label_zh(label)} 近 20 个观察日小幅上涨")
        return 1
    if change_20d <= -3:
        drivers.append(f"{_market_label_zh(label)} 近 20 个观察日下跌 {abs(change_20d):.1f}%，风险偏好转弱")
        return -2
    if change_20d <= -1:
        drivers.append(f"{_market_label_zh(label)} 近 20 个观察日小幅下跌")
        return -1
    return 0


def _market_label_zh(label: str) -> str:
    return {"SPY": "标普 500 ETF", "QQQ": "纳斯达克 100 ETF"}.get(label, label)


def _metric_number(metrics: dict[str, dict[str, object]], key: str, field: str) -> float | None:
    metric = metrics.get(key)
    if not metric:
        return None
    return _to_float(metric.get(field))


def _to_float(value: object) -> float | None:
    try:
        if value in {None, "", ".", "-"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _child_text(node: ET.Element, tag: str, ns: dict[str, str] | None = None) -> str:
    child = node.find(tag, ns or {})
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _clean_summary(value: str, max_len: int = 280) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def _sparkline(series: list[tuple[str, float]]) -> list[float]:
    values = [value for _date, value in series if value is not None]
    if not values:
        return []
    low = min(values)
    high = max(values)
    if high == low:
        return [50.0 for _value in values]
    return [round(((value - low) / (high - low)) * 100, 2) for value in values]


def _health(source: MarketSource, status: str, message: object = "") -> dict[str, object]:
    return {
        "name": source.name,
        "group": source.group,
        "type": source.type,
        "url": source.url,
        "status": status,
        "message": str(message or ""),
    }


def _curve_interpretation(curve_bp: float) -> str:
    if curve_bp < -50:
        return "deep inversion; recession/tight-policy signal"
    if curve_bp < 0:
        return "inverted; late-cycle signal"
    if curve_bp > 125:
        return "steep; easier front-end policy or growth/inflation premium"
    return "normal"


def _regime_label(score: int) -> str:
    if score >= 3:
        return "risk_on"
    if score <= -3:
        return "risk_off"
    return "neutral"


def _summary(regime: str, score: int, drivers: list[str], connected_core: int, error_count: int) -> str:
    if not drivers:
        return "宏观数据已连接，但方向性证据还不够明确。"
    lead = {
        "risk_on": "宏观环境支持成长股和高 beta 标的",
        "neutral": "宏观环境方向混合，需要更强公司级证据",
        "risk_off": "宏观环境偏防守，需要提高投机性机会门槛",
    }[regime]
    error_note = f" 来源错误数：{error_count}。" if error_count else ""
    return f"{lead}。宏观分数={score}；核心数据连接={connected_core}/5。主因：{drivers[0]}。{error_note}"


def _implications(regime: str) -> list[str]:
    if regime == "risk_on":
        return [
            "可以更积极跟踪早期发现标的，但不能因为宏观偏暖就直接买入。",
            "AI、半导体、国防、机器人等成长主题更容易获得市场配合，前提是价格和成交量确认。",
            "宏观环境只影响跟踪力度，不替代公司证据、估值和流动性检查。",
        ]
    if regime == "risk_off":
        return [
            "提高机会晋级门槛，弱新闻直接过滤。",
            "优先选择资产负债表稳、合同明确、短期收入可转换的公司。",
            "对依赖融资的小盘股保持谨慎，除非新闻实质改变融资风险。",
        ]
    return [
        "维持默认新闻证据门槛，不追弱信号，也不忽视硬证据。",
        "只有来源可靠、证据重复、ticker 明确、价格成交量确认的标的才进入重点观察。",
        "宏观事件用于判断仓位和节奏，不单独生成股票结论。",
    ]


def _calculation_notes() -> list[str]:
    return [
        "这不是手写模板结论。SPY、QQQ、美元指数来自 Yahoo chart API；VIX 来自 Cboe；美债收益率来自 U.S. Treasury XML。",
        "20obs 涨跌幅 = 最新有效价格 / 20 个有效观察值前的价格 - 1。页面里的 5.0% 和 9.9% 是系统按该公式算出的结果。",
        "宏观分数是透明规则引擎，不是机器学习黑箱，也不是已完成回测的交易模型。它借鉴常见 cross-asset 框架，但阈值仍需要历史回测校准。",
        "公式：SPY/QQQ 20obs >= +3% 各 +2，>= +1% 各 +1，<= -3% 各 -2，<= -1% 各 -1；VIX >=25 扣2，>=20 扣1，<16 加1，5obs 上升 >=4 点再扣1。",
        "公式续：10Y 收益率 20obs 上升 >=25bp 扣1，下降 >=25bp 加1；2Y/10Y 曲线低于 -50bp 扣1；美元 20obs 上涨 >=2% 扣1，下降 >=2% 加1；CPI/PPI YoY >=4% 各扣1；失业率 >=5% 扣1。",
        "分类：总分 >=3 为 risk_on，<= -3 为 risk_off，其余为 neutral。中文句子是分析员表达模板，但触发它的方向、数值和分数来自数据计算。",
        "白宫/特朗普政策事件目前进入事件流和主题标记；除非规则明确识别为关税、出口管制、制裁、半导体、能源、国防等主题，否则不会直接改变股票结论。",
    ]


def _methodology() -> dict[str, object]:
    return {
        "type": "transparent_rules_engine",
        "not_claimed": "不是 Bloomberg/FactSet 模型，不是内幕公式，不是已完成回测的买卖信号。",
        "market_score_formula": [
            "SPY/QQQ 20obs momentum: >=+3% +2, >=+1% +1, <=-3% -2, <=-1% -1 each.",
            "VIX: >=25 -2, >=20 -1, <16 +1; 5obs rise >=4 points adds -1.",
            "10Y yield 20obs: >=+25bp -1, <=-25bp +1.",
            "2Y/10Y curve below -50bp: -1.",
            "Dollar index 20obs: >=+2% -1, <=-2% +1.",
            "CPI YoY >=4%, PPI YoY >=4%, unemployment >=5%: -1 each.",
            "Regime: score >=3 risk_on, score <=-3 risk_off, otherwise neutral.",
        ],
        "news_score_formula": [
            "raw_score = sum(hard evidence term weights) + penalties.",
            "adjusted_score = raw_score * source_trust.",
            "source_trust is a reliability multiplier from config, not proof the article is true.",
            "Dynamic watchlist conviction combines max adjusted score, repeated evidence count, and whether ticker was seed-confirmed.",
        ],
        "analyst_standard": "结论必须能追溯到来源、原文、关键词、分数和缺失确认；缺少价格/成交量、财务影响和估值检查时，只能是观察或研究，不是买入建议。",
    }


def _needed_feeds(metrics: dict[str, dict[str, object]]) -> list[str]:
    missing = []
    for key, label in [
        ("us10y", "10Y Treasury yield"),
        ("us2y", "2Y Treasury yield"),
        ("vix", "VIX"),
        ("spy", "SPY price"),
        ("qqq", "QQQ price"),
        ("cpi", "CPI"),
        ("unemployment_rate", "Unemployment rate"),
    ]:
        if key not in metrics:
            missing.append(label)
    return missing


def _ordered_metrics(metrics: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    order = [
        "us10y",
        "us2y",
        "yield_curve_2s10s",
        "vix",
        "spy",
        "qqq",
        "broad_dollar",
        "cpi",
        "ppi",
        "unemployment_rate",
    ]
    rows = []
    for key in order:
        if key in metrics:
            row = dict(metrics[key])
            row["key"] = key
            rows.append(row)
    for key, value in metrics.items():
        if key not in order:
            row = dict(value)
            row["key"] = key
            rows.append(row)
    return rows

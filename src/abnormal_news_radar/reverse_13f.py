"""Reverse 13F — *who holds this stock* from the actual SEC filings.

Regular 13F data is "what does manager X hold". The analyst question is the
reverse: "which institutions hold / are building TICKER?". SEC has no
per-issuer holder index, so this reconstructs it from primary filings:

1. EDGAR full-text search (efts.sec.gov) for the issuer name within recent
   ``13F-HR`` filings -> the managers that report holding it;
2. for each manager's filing, fetch the 13F information-table XML and read the
   exact position (shares + market value) for that issuer.

Result: a list of real institutional holders (manager name + shares + $ value +
as-of date), ranked by position size — sourced entirely from free SEC filings.
Network access is injected for deterministic tests; every failure degrades to a
status flag and never breaks the scan.
"""

from __future__ import annotations

import json
import re
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .net import fetch_text

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
LOOKBACK_DAYS = 200
MAX_MANAGERS = 14
MAX_TABLE_BYTES = 30_000_000
MAX_WORKERS = 6
_SUFFIX_RE = re.compile(r"\b(corp|corporation|inc|incorporated|co|company|ltd|limited|plc|holdings?|the|class [a-c])\b", re.IGNORECASE)

#: Curated well-known managers (CIKs verified against SEC submissions). Their
#: latest 13F-HR is always checked so recognizable "smart money" surfaces even
#: when full-text search ranks small filers first.
NOTABLE_MANAGERS: dict[int, str] = {
    1067983: "Berkshire Hathaway (Buffett)",
    102909: "Vanguard Group",
    1364742: "BlackRock",
    93751: "State Street",
    1037389: "Renaissance Technologies",
    1350694: "Bridgewater Associates",
    1336528: "Pershing Square (Ackman)",
    1135730: "Coatue Management",
    1167483: "Tiger Global Management",
    1423053: "Citadel Advisors",
    1179392: "Two Sigma",
    1273087: "Millennium Management",
    1603466: "Point72 (Cohen)",
    1697748: "ARK Investment Management",
    1649339: "Scion Asset (Burry)",
    1656456: "Appaloosa (Tepper)",
    1061768: "Baupost Group (Klarman)",
    1029160: "Soros Fund Management",
    1536411: "Duquesne Family Office (Druckenmiller)",
}


def find_institutional_holders(
    issuer_name: str,
    efts_fetcher: object | None = None,
    doc_fetcher: object | None = None,
    max_managers: int = MAX_MANAGERS,
    lookback_days: int = LOOKBACK_DAYS,
    today: date | None = None,
    include_notable: bool = True,
    progress: object | None = None,
) -> dict[str, object]:
    if not issuer_name:
        return {"status": "no_issuer", "holders": []}
    efts = efts_fetcher or _default_efts_fetch
    doc = doc_fetcher or fetch_text
    issuer_key = _normalize(issuer_name)
    report = progress if callable(progress) else (lambda *_args: None)

    report("全文检索 13F 申报", 0, 0)
    try:
        discovered = _search_managers(issuer_name, efts, lookback_days, today)
    except Exception as exc:  # noqa: BLE001 - degrade cleanly.
        discovered = []
        if not include_notable:
            return {"status": "unavailable", "holders": [], "reason": str(exc)[:160]}

    # Merge full-text-discovered managers with the curated notable list, deduped
    # by CIK (the curated label/flag wins).
    managers: dict[int, dict[str, object]] = {}
    for manager in discovered[:max_managers]:
        managers[int(manager["cik"])] = manager
    if include_notable:
        for location in _notable_locations(doc):
            managers[int(location["cik"])] = {**managers.get(int(location["cik"]), {}), **location}

    if not managers:
        return {"status": "no_holders", "issuer_name": issuer_name, "holders": []}

    counter = {"done": 0}
    counter_lock = threading.Lock()

    def resolve(manager: dict[str, object]) -> dict[str, object] | None:
        position = _holding_in_filing(manager, issuer_key, doc)
        with counter_lock:
            counter["done"] += 1
            report("解析各机构信息表", counter["done"], len(managers))
        return {**manager, **position} if position is not None else None

    report("解析各机构信息表", 0, len(managers))
    holders: list[dict[str, object]] = []
    workers = max(1, min(MAX_WORKERS, len(managers)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(resolve, list(managers.values())):
            if result is not None:
                holders.append(result)
    # Drop filings older than a year (e.g. a manager's stale last 13F under an
    # old CIK) — consistent with the system-wide freshness rule.
    cutoff = ((today or date.today()) - timedelta(days=365)).isoformat()
    holders = [h for h in holders if not str(h.get("filed") or "") or str(h.get("filed")) >= cutoff]
    holders.sort(key=lambda h: (bool(h.get("notable")), float(h.get("value_usd") or 0)), reverse=True)

    # Quarter-over-quarter change: parse each top holder's *previous* 13F and
    # diff the shares. Without this the panel only proves "they hold it" — the
    # decision-relevant fact is whether they added or trimmed last quarter.
    diff_targets = holders[:MAX_QOQ_DIFFS]
    if diff_targets:
        counter["done"] = 0
        report("对比各机构上一季持仓", 0, len(diff_targets))

        def diff(holder: dict[str, object]) -> None:
            _attach_qoq_change(holder, issuer_key, doc)
            with counter_lock:
                counter["done"] += 1
                report("对比各机构上一季持仓", counter["done"], len(diff_targets))

        with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(diff_targets)))) as pool:
            list(pool.map(diff, diff_targets))
    report("完成", 1, 1)
    return {
        "status": "ok" if holders else "no_holders",
        "issuer_name": issuer_name,
        "holders": holders,
        "summary_zh": _summary_zh(issuer_name, holders),
        "source": "SEC EDGAR 13F-HR (full-text search + curated managers + information table)",
    }


#: Holders that get the (expensive) previous-quarter diff: 3 extra requests
#: each (submissions JSON + index.json + information table XML).
MAX_QOQ_DIFFS = 12


def _attach_qoq_change(holder: dict[str, object], issuer_key: str, doc: object) -> None:
    """Mutate ``holder`` in place with shares change vs its previous 13F-HR."""
    try:
        previous = _previous_13f_location(int(holder["cik"]), str(holder["accession"]), doc)
    except Exception:  # noqa: BLE001 - the diff is best-effort.
        previous = None
    if previous is None:
        holder["change_label"] = "unknown"
        holder["change_zh"] = "上一季对比不可用"
        return
    prior = _holding_in_filing({**holder, **previous}, issuer_key, doc)
    shares = holder.get("shares")
    holder["prev_filed"] = previous.get("filed", "")
    if prior is None:
        holder["change_label"] = "new"
        holder["change_zh"] = "新建仓"
        holder["prev_shares"] = 0
        return
    prev_shares = prior.get("shares")
    holder["prev_shares"] = prev_shares
    if not isinstance(shares, int) or not isinstance(prev_shares, int) or prev_shares <= 0:
        holder["change_label"] = "unknown"
        holder["change_zh"] = "上一季对比不可用"
        return
    change_pct = (shares / prev_shares - 1) * 100
    holder["change_pct"] = round(change_pct, 1)
    if change_pct >= 2:
        holder["change_label"] = "increased"
        holder["change_zh"] = f"加仓 {change_pct:+.0f}%"
    elif change_pct <= -2:
        holder["change_label"] = "reduced"
        holder["change_zh"] = f"减仓 {change_pct:+.0f}%"
    else:
        holder["change_label"] = "unchanged"
        holder["change_zh"] = "持仓基本不变"


def _previous_13f_location(cik: int, current_accession: str, doc: object) -> dict[str, object] | None:
    """Locate the 13F-HR filed immediately before ``current_accession``."""
    subs = json.loads(doc(_submissions_url(cik), accept="application/json", timeout=20, max_bytes=8_000_000))  # type: ignore[operator]
    recent = (subs.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filed = recent.get("filingDate") or []
    thirteen_f = [
        (str(accessions[i]), str(filed[i]) if i < len(filed) else "")
        for i, form in enumerate(forms)
        if form == "13F-HR"
    ]
    index = next((i for i, (accession, _) in enumerate(thirteen_f) if accession == current_accession), None)
    if index is None or index + 1 >= len(thirteen_f):
        return None
    prev_accession, prev_filed = thirteen_f[index + 1]
    idx = json.loads(doc(_index_url(cik, prev_accession), accept="application/json", timeout=20, max_bytes=4_000_000))  # type: ignore[operator]
    files = [str(item.get("name") or "") for item in (idx.get("directory") or {}).get("item") or []]
    info = _pick_info_table(files)
    if not info:
        return None
    return {"accession": prev_accession, "filename": info, "filed": prev_filed}


def _notable_locations(doc: object) -> list[dict[str, object]]:
    """Resolve each curated manager's latest 13F-HR information-table location."""
    def locate(item: tuple[int, str]) -> dict[str, object] | None:
        cik, name = item
        return _latest_13f_location(cik, name, doc)

    out: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for location in pool.map(locate, list(NOTABLE_MANAGERS.items())):
            if location is not None:
                out.append(location)
    return out


def _latest_13f_location(cik: int, name: str, doc: object) -> dict[str, object] | None:
    try:
        subs = json.loads(doc(_submissions_url(cik), accept="application/json", timeout=20, max_bytes=8_000_000))  # type: ignore[operator]
        recent = (subs.get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        filed = recent.get("filingDate") or []
        index = next((i for i, form in enumerate(forms) if form == "13F-HR"), None)
        if index is None:
            return None
        accession = str(accessions[index])
        idx = json.loads(doc(_index_url(cik, accession), accept="application/json", timeout=20, max_bytes=4_000_000))  # type: ignore[operator]
        files = [str(item.get("name") or "") for item in (idx.get("directory") or {}).get("item") or []]
        info = _pick_info_table(files)
        if not info:
            return None
        return {"manager": name, "cik": cik, "accession": accession, "filename": info,
                "filed": str(filed[index]) if index < len(filed) else "", "notable": True}
    except Exception:  # noqa: BLE001 - a manager we cannot resolve is simply skipped.
        return None


def _pick_info_table(files: list[str]) -> str:
    xmls = [f for f in files if f.lower().endswith(".xml") and "primary_doc" not in f.lower()]
    for f in xmls:
        if "infotable" in f.lower() or "info_table" in f.lower() or "table" in f.lower():
            return f
    return xmls[0] if xmls else ""


def _submissions_url(cik: int) -> str:
    return f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"


def _index_url(cik: int, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/index.json"


def _search_managers(issuer_name: str, efts: object, lookback_days: int, today: date | None) -> list[dict[str, object]]:
    today = today or date.today()
    start = (today - timedelta(days=lookback_days)).isoformat()
    end = today.isoformat()
    latest_by_cik: dict[int, dict[str, object]] = {}
    for offset in (0, 10, 20, 30):
        payload = json.loads(efts(issuer_name, start, end, offset))  # type: ignore[operator]
        hits = (payload.get("hits") or {}).get("hits") or []
        if not hits:
            break
        for hit in hits:
            source = hit.get("_source") or {}
            ident = str(hit.get("_id") or "")
            if ":" not in ident:
                continue
            accession, filename = ident.split(":", 1)
            cik = _cik_from_accession(accession)
            if cik is None:
                continue
            filed = str(source.get("file_date") or "")
            manager = _display_name(source)
            previous = latest_by_cik.get(cik)
            if previous is None or filed > str(previous.get("filed") or ""):
                latest_by_cik[cik] = {
                    "manager": manager,
                    "cik": cik,
                    "accession": accession,
                    "filename": filename,
                    "filed": filed,
                }
    return sorted(latest_by_cik.values(), key=lambda m: str(m.get("filed") or ""), reverse=True)


def _holding_in_filing(manager: dict[str, object], issuer_key: str, doc: object) -> dict[str, object] | None:
    url = _info_table_url(int(manager["cik"]), str(manager["accession"]), str(manager["filename"]))
    try:
        raw = doc(url, accept="application/xml", timeout=25, max_bytes=MAX_TABLE_BYTES)  # type: ignore[operator]
        root = ET.fromstring(raw)
    except Exception:  # noqa: BLE001 - skip a filing we cannot read.
        return None
    best: dict[str, object] | None = None
    for info in root.iter():
        if _local(info.tag) != "infoTable":
            continue
        fields = {_local(child.tag): (child.text or "") for child in info.iter()}
        name = fields.get("nameOfIssuer", "")
        if not name or _normalize(name) != issuer_key:
            continue
        shares = _to_int(fields.get("sshPrnamt"))
        value = _to_int(fields.get("value"))
        if value is None:
            continue
        # 13F "value" is in whole dollars since 2023-Q3; older filings used
        # thousands. Detect the legacy unit via implied price-per-share.
        if shares and shares > 0 and value / shares < 1:
            value *= 1000
        if best is None or value > int(best.get("value_usd") or 0):
            best = {"shares": shares, "value_usd": value, "cusip": fields.get("cusip", "")}
    return best


def _summary_zh(issuer_name: str, holders: list[dict[str, object]]) -> str:
    if not holders:
        return f"近一季 13F 申报中未检索到持有 {issuer_name} 的机构。"
    top = holders[0]
    increased = sum(1 for h in holders if h.get("change_label") == "increased")
    reduced = sum(1 for h in holders if h.get("change_label") == "reduced")
    new = sum(1 for h in holders if h.get("change_label") == "new")
    flow_zh = ""
    if increased or reduced or new:
        parts = []
        if new:
            parts.append(f"{new} 家新建仓")
        if increased:
            parts.append(f"{increased} 家加仓")
        if reduced:
            parts.append(f"{reduced} 家减仓")
        flow_zh = f"对比各自上一季：{'、'.join(parts)}。"
    return (
        f"近一季 13F 申报中检索到 {len(holders)} 家机构持有 {issuer_name}；"
        f"最大持仓：{top.get('manager')}（{_fmt_usd(top.get('value_usd'))}）。{flow_zh}"
        "数据为各机构最近一份 13F-HR（滞后最多 45 天），非全市场穷尽，仅供线索。"
    )


# --------------------------------------------------------------------------- #
# defaults / helpers
# --------------------------------------------------------------------------- #
def _default_efts_fetch(issuer_name: str, start: str, end: str, offset: int) -> str:
    import urllib.parse

    query = urllib.parse.quote(f'"{issuer_name}"')
    url = f"{EFTS_URL}?q={query}&forms=13F-HR&startdt={start}&enddt={end}&from={offset}"
    return fetch_text(url, accept="application/json", timeout=25)


def _info_table_url(cik: int, accession: str, filename: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{filename}"


def _cik_from_accession(accession: str) -> int | None:
    head = accession.split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def _display_name(source: dict[str, object]) -> str:
    names = source.get("display_names")
    if isinstance(names, list) and names:
        return re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", str(names[0])).strip()
    return "Unknown manager"


def _normalize(name: str) -> str:
    lowered = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    without_suffix = _SUFFIX_RE.sub(" ", lowered)
    return re.sub(r"\s+", " ", without_suffix).strip()


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _to_int(value: object) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _fmt_usd(value: object) -> str:
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "n/a"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:.0f}"

# AI News Radar

Open-source financial news radar for finding early hard signals before a theme becomes consensus.

The project is intentionally not a Bloomberg clone. The first version focuses on one job:

> detect public news items that may indicate early order flow, supply-chain bottlenecks, capacity reservations, or new AI infrastructure demand before the market fully reprices a company.

## MVP

- Pull public RSS/Atom feeds.
- Monitor selected company IR / press-release pages that do not publish RSS.
- Match articles against a focused watchlist.
- Score hard signals such as:
  - `prepayment`
  - `capacity reservation`
  - `mass production`
  - `production qualification`
  - `manufacturing readiness`
  - `design win`
  - `lifecycle revenue`
  - `book-to-bill`
  - `hyperscale customer`
  - `qualification to production`
  - `supply constrained`
  - `multi-year agreement`
  - `data center demand`
  - `AI customer`
  - `new product ramp`
- Save scored events to `data/signals.jsonl`.
- Print a compact terminal report.

## Run

```powershell
cd C:\Users\Allen\ai-news-radar
python -m src.abnormal_news_radar scan --limit 40
```

## Local Web Terminal

Double-click `AI News Radar.cmd`, or run:

```powershell
cd C:\Users\Allen\ai-news-radar
python -m src.abnormal_news_radar web --port 8765
```

Open `http://127.0.0.1:8765`.

The web terminal runs an automatic scan at startup and refreshes the browser dashboard every 60 seconds.

The terminal is organized around the daily analyst workflow:

- `Brief`: morning-style summary, review count, active modules, and data gaps.
- `Market`: macro regime placeholder for public rates, inflation, growth, energy, and liquidity feeds.
- `Opportunities`: unified analyst output with candidates, action labels, evidence, state, and source links.
- `Process`: the exact articles reviewed in the latest scan, grouped by source.
- `Sources`: configured feeds, IR pages, and watchlist companies.

## Project Shape

```text
config/
  sources.json      Public feeds to scan.
  watchlist.json    Companies, tickers, aliases, themes.
docs/
  product_brief.md  Why this exists and what it should catch.
  signal_model.md   Scoring rules and false-positive rules.
src/
  abnormal_news_radar/
    cli.py
    feeds.py
    model.py
    scoring.py
    storage.py
    web.py
    web_static/
```

## Design Principle

The system should prefer a small number of high-signal discoveries over a large stream of generic market news.

The watchlist is not the discovery boundary. It is only a seed and validation layer. The primary flow is:

1. scan public evidence sources;
2. score hard business evidence;
3. infer candidate companies from high-evidence articles;
4. classify candidates into research actions: research now, track, identify then monitor, or monitor;
5. promote confirmed candidates into persistent watchlists after evidence and market confirmation.

Bad alert:

```text
Company says AI demand is strong.
```

Good alert:

```text
Company received $290M customer prepayment tied to silicon photonics capacity.
```

## Next Milestones

1. Add SEC 8-K and 10-Q item extraction.
2. Add price/volume confirmation after each signal.
3. Add durable SQLite storage for articles, source health, and signal history.
4. Add X/Reddit/Substack social confirmation as secondary evidence only.
5. Add weekly anomaly report and then a compact web terminal UI.

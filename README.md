# AI News Radar

AI-assisted research workflow for monitoring public news, filtering source relevance, and surfacing concise summaries for human review.

The project is designed around an analyst workflow rather than a generic news feed:

1. collect public evidence;
2. score hard business signals;
3. identify candidate companies;
4. present evidence and source links for human verification;
5. keep confirmed candidates in a persistent watchlist.

## What this demonstrates

- Structured output review for **factual consistency**, source quality, and relevance.
- Rule-based signal scoring for terms such as `prepayment`, `capacity reservation`, `design win`, `multi-year agreement`, and `data center demand`.
- Human-in-the-loop review: the system surfaces evidence and uncertainty instead of treating every alert as a conclusion.
- A compact terminal and local web workflow for reviewing the latest scan.

## MVP

- Pull public RSS/Atom feeds.
- Monitor selected company IR / press-release pages that do not publish RSS.
- Match articles against a focused watchlist.
- Score high-signal evidence and save events to `data/signals.jsonl`.
- Print a compact terminal report and a local analyst dashboard.

## Run

The runtime is standard-library only except for `tzdata` (required so the market-hours scheduler can resolve `America/New_York` on Windows).

```powershell
cd C:\Users\Allen\ai-news-radar
pip install -e .
ai-news-radar scan --limit 40
# or, without installing:
python -m src.abnormal_news_radar scan --limit 40
```

Date-scoped public feeds use `{yyyy}` / `{yyyymm}` / `{yyyymmdd}` templates in `config/sources.json`, resolved against the U.S. Eastern calendar at fetch time.

## Local Web Terminal

```powershell
python -m src.abnormal_news_radar web --port 8765
```

Open `http://127.0.0.1:8765`.

The dashboard is organized around the daily analyst workflow:

- **Brief** — summary, review count, active modules, and data gaps.
- **Market** — macro-regime placeholder for public rates, inflation, growth, energy, and liquidity feeds.
- **Opportunities** — candidates, action labels, evidence, state, and source links.
- **Process** — articles reviewed in the latest scan, grouped by source.
- **Sources** — configured feeds, IR pages, and watchlist companies.

## Validate the Signal Model

The `report` command backtests stored signals against forward price moves and excess over SPY:

```powershell
ai-news-radar report
ai-news-radar report --json
```

The report shows matured sample size, hit rate, mean excess return, and a calibration check for whether `hard >= watch >= weak` holds.

## Project Shape

```text
config/                 Public feeds, companies, aliases, and themes
docs/                   Product brief and signal-model notes
src/abnormal_news_radar/ CLI, feeds, model, scoring, storage, and web UI
tests/                  Automated tests
```

## Development

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
pytest
ruff check src tests
```

CI runs lint and tests on Linux and Windows for Python 3.10 and 3.12. Copy `.env.example` to `.env` to set a real `User-Agent` contact string before heavy use.

## Design Principle

Prefer a small number of high-signal discoveries over a large stream of generic market news. A useful alert includes concrete evidence and a source link; a vague claim such as “AI demand is strong” is not enough.

## Next Milestones

1. Add SEC 8-K and 10-Q item extraction.
2. Add price/volume confirmation after each signal.
3. Add durable SQLite storage for articles, source health, and signal history.
4. Add social confirmation as secondary evidence only.
5. Add weekly anomaly reporting.

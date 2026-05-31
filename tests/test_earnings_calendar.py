import json
import unittest
from datetime import date

from src.abnormal_news_radar.earnings_calendar import collect_earnings_calendar, collect_earnings_month
from src.abnormal_news_radar.model import Company


class EarningsCalendarTests(unittest.TestCase):
    def test_collects_only_focused_watchlist_companies(self):
        watchlist = [
            Company(ticker="SNOW", name="Snowflake", aliases=("SNOW", "Snowflake"), themes=("cloud", "ai_software")),
            Company(ticker="NVDA", name="NVIDIA", aliases=("NVDA",), themes=("ai_datacenter",)),
        ]

        def fetcher(_url):
            return json.dumps(
                {
                    "data": {
                        "rows": [
                            {"symbol": "SNOW", "name": "Snowflake Inc.", "time": "time-after-hours", "epsForecast": "$0.32"},
                            {"symbol": "WEN", "name": "Wendy's", "time": "time-before-hours", "epsForecast": "$0.20"},
                        ]
                    }
                }
            )

        calendar = collect_earnings_calendar(
            watchlist,
            fetcher=fetcher,
            today=date(2026, 5, 27),
            days_back=0,
            days_forward=0,
        )

        self.assertEqual(calendar["status"], "connected")
        self.assertEqual(calendar["local_trading_date"], "2026-05-27")
        self.assertEqual(len(calendar["items"]), 1)
        self.assertEqual(calendar["items"][0]["ticker"], "SNOW")

    def test_summary_uses_supplied_local_trading_date(self):
        watchlist = [Company(ticker="MRVL", name="Marvell", aliases=("MRVL",), themes=("ai_datacenter",))]

        def fetcher(_url):
            return json.dumps({"data": {"rows": [{"symbol": "MRVL", "time": "time-after-hours"}]}})

        calendar = collect_earnings_calendar(
            watchlist,
            fetcher=fetcher,
            today=date(2026, 5, 27),
            days_back=0,
            days_forward=0,
        )

        self.assertEqual(calendar["items"][0]["date"], "2026-05-27")
        self.assertIn("主流观察标的财报", calendar["summary_zh"])


    def test_collect_month_covers_full_calendar_month(self):
        watchlist = [Company(ticker="AVGO", name="Broadcom", aliases=("AVGO",), themes=("ai_datacenter",))]
        seen_dates = []

        def fetcher(url):
            seen_dates.append(url.split("date=")[1])
            return json.dumps({"data": {"rows": [{"symbol": "AVGO", "time": "time-after-hours"}]}})

        calendar = collect_earnings_month(watchlist, 2026, 6, fetcher=fetcher, today=date(2026, 6, 1))

        self.assertEqual(calendar["month"], "2026-06")
        self.assertEqual(calendar["window"], {"from": "2026-06-01", "to": "2026-06-30"})
        self.assertEqual(len(seen_dates), 30)  # one request per day of June
        self.assertEqual(len(calendar["items"]), 30)


if __name__ == "__main__":
    unittest.main()

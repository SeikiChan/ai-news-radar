import unittest

from src.abnormal_news_radar.earnings_analysis import analyze_earnings_candidate
from src.abnormal_news_radar.model import Company


class EarningsAnalysisTests(unittest.TestCase):
    def test_extracts_key_metrics_from_earnings_release_text(self):
        candidate = {
            "company_name": "Snowflake",
            "article": {
                "title": "Snowflake Reports Financial Results for the First Quarter",
                "summary": "Product revenue was $996.8 million. Remaining performance obligations were $6.7 billion. Net revenue retention was 125%.",
            },
        }

        analysis = analyze_earnings_candidate(candidate)

        self.assertEqual(analysis["status"], "earnings_release_detected")
        metric_names = {row["metric"] for row in analysis["metrics"]}
        self.assertIn("product_revenue", metric_names)
        self.assertIn("rpo", metric_names)
        self.assertIn("net_revenue_retention", metric_names)

    def test_reads_full_release_for_spend_and_mentioned_companies(self):
        candidate = {
            "company_name": "Snowflake",
            "tickers": ["SNOW"],
            "article": {
                "title": "Snowflake Reports Financial Results",
                "summary": "Financial results.",
                "link": "https://example.com/snow",
            },
        }
        watchlist = [
            Company(ticker="NVDA", name="NVIDIA", aliases=("NVIDIA", "NVDA", "GPU"), themes=("ai_datacenter",)),
            Company(ticker="AMZN", name="Amazon", aliases=("AWS", "Amazon"), themes=("cloud",)),
        ]

        analysis = analyze_earnings_candidate(
            candidate,
            watchlist=watchlist,
            fetcher=lambda _url: """
                <html><body>
                Snowflake reports financial results. Product revenue was $996.8 million.
                We continue investing in AI infrastructure, GPU capacity, research and development,
                and deeper collaboration with NVIDIA and AWS for enterprise AI workloads.
                </body></html>
            """,
        )

        self.assertEqual(analysis["read_depth"], "full_release_html")
        self.assertTrue(any(item["category"] == "ai_infrastructure" for item in analysis["spend_allocation"]))
        tickers = {item["ticker"] for item in analysis["mentioned_companies"]}
        self.assertIn("NVDA", tickers)
        self.assertIn("AMZN", tickers)

    def test_non_earnings_candidate_is_ignored(self):
        analysis = analyze_earnings_candidate({"article": {"title": "Company launches product"}})

        self.assertEqual(analysis["status"], "not_earnings")


if __name__ == "__main__":
    unittest.main()

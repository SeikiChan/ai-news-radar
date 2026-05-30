import unittest

from src.abnormal_news_radar.model import Company
from src.abnormal_news_radar.technology_intel import analyze_technology_candidate


class TechnologyIntelTests(unittest.TestCase):
    def test_reads_technical_blog_and_extracts_supply_chain_readthrough(self):
        candidate = {
            "company_name": "NVIDIA",
            "tickers": ["NVDA"],
            "article": {
                "source": "NVIDIA Developer Technical Blog",
                "title": "NVIDIA 800 VDC Architecture Will Power the Next Generation of AI Factories",
                "summary": "NVIDIA is leading the transition to 800 VDC data center power infrastructure.",
                "link": "https://example.com/nvidia-800v",
            },
        }
        watchlist = [
            Company(ticker="NVDA", name="NVIDIA", aliases=("NVIDIA", "NVDA"), themes=("ai_datacenter",)),
            Company(ticker="NVTS", name="Navitas Semiconductor", aliases=("Navitas", "GeneSiC"), themes=("ai_power",)),
            Company(ticker="TXN", name="Texas Instruments", aliases=("Texas Instruments", "TXN"), themes=("ai_power",)),
            Company(ticker="VRT", name="Vertiv", aliases=("Vertiv",), themes=("ai_power",)),
        ]

        analysis = analyze_technology_candidate(
            candidate,
            watchlist=watchlist,
            fetcher=lambda _url: """
                <html><body>
                NVIDIA is leading the transition to 800 VDC data center power infrastructure
                to support 1 MW racks and Kyber rack-scale systems. Featured companies include
                Navitas, Texas Instruments, and Vertiv.
                </body></html>
            """,
        )

        self.assertEqual(analysis["status"], "technology_signal_detected")
        self.assertEqual(analysis["read_depth"], "full_article_html")
        themes = {item["theme"] for item in analysis["themes"]}
        self.assertIn("800v_hvdc_power", themes)
        tickers = {item["ticker"] for item in analysis["mentioned_companies"]}
        self.assertEqual(tickers, {"NVTS", "TXN", "VRT"})

    def test_non_technical_article_is_ignored(self):
        analysis = analyze_technology_candidate({"article": {"title": "Company announces dividend"}})

        self.assertEqual(analysis["status"], "not_technology_signal")


if __name__ == "__main__":
    unittest.main()

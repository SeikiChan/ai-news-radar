import unittest

from src.abnormal_news_radar.readthrough import _candidate_readthrough


class ReadthroughTests(unittest.TestCase):
    def test_technology_intel_mentions_feed_readthrough_analysis(self):
        candidate = {
            "company_name": "NVIDIA",
            "tickers": ["NVDA"],
            "technology_intel": {
                "mentioned_companies": [
                    {
                        "ticker": "NVTS",
                        "name": "Navitas Semiconductor",
                        "matched_alias": "Navitas",
                        "source_context": "technology_intel",
                    }
                ]
            },
            "article": {"title": "NVIDIA 800 VDC architecture"},
        }

        analysis = _candidate_readthrough(candidate, by_ticker={})
        self.assertEqual(analysis["status"], "watching")
        self.assertEqual(analysis["items"][0]["ticker"], "NVTS")
        self.assertEqual(analysis["items"][0]["source_context"], "technology_intel")


if __name__ == "__main__":
    unittest.main()

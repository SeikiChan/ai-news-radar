import json
import tempfile
import unittest
from pathlib import Path

from src.abnormal_news_radar.config import load_market_sources, load_sources


class ConfigTests(unittest.TestCase):
    def test_load_sources_preserves_group_and_patterns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sources.json"
            path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "name": "Example Wire",
                                "group": "global_press_wires",
                                "type": "html",
                                "url": "https://example.com/news",
                                "trust": 0.7,
                                "include_patterns": ["contract"],
                                "exclude_patterns": ["privacy"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            sources = load_sources(path)

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].group, "global_press_wires")
        self.assertEqual(sources[0].include_patterns, ("contract",))
        self.assertEqual(sources[0].exclude_patterns, ("privacy",))

    def test_load_market_sources_preserves_purpose_and_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sources.json"
            path.write_text(
                json.dumps(
                    {
                        "market_sources": [
                            {
                                "name": "Example VIX",
                                "group": "volatility",
                                "type": "csv",
                                "url": "https://example.com/vix.csv",
                                "purpose": "Equity volatility regime.",
                                "status": "configured",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            sources = load_market_sources(path)

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].group, "volatility")
        self.assertEqual(sources[0].purpose, "Equity volatility regime.")
        self.assertEqual(sources[0].status, "configured")


if __name__ == "__main__":
    unittest.main()

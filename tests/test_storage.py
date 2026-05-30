import json
import tempfile
import unittest
from pathlib import Path

from src.abnormal_news_radar.model import Article, Candidate, Signal
from src.abnormal_news_radar.storage import append_candidates, append_signals, load_review_state, save_review_state


class StorageTests(unittest.TestCase):
    def test_append_signals_skips_existing_links(self):
        article = Article(
            source="Test",
            source_trust=1.0,
            title="Example announces production order",
            link="https://example.com/order",
        )
        signal = Signal(
            article=article,
            tickers=("EXM",),
            themes=("ai_datacenter",),
            score=35,
            raw_score=35,
            matched_terms=("production order",),
            band="hard alert",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "signals.jsonl"

            first_count = append_signals(path, [signal])
            second_count = append_signals(path, [signal])

            self.assertEqual(first_count, 1)
            self.assertEqual(second_count, 0)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)

    def test_review_state_round_trips_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review_state.json"
            save_review_state(path, {"abc": "reviewed"})

            self.assertEqual(load_review_state(path), {"abc": "reviewed"})

    def test_append_candidates_skips_same_company_article_pair(self):
        article = Article(
            source="Test",
            source_trust=1.0,
            title="Example announces production order",
            link="https://example.com/order",
        )
        candidate = Candidate(
            article=article,
            company_name="Example",
            tickers=(),
            score=22,
            raw_score=22,
            matched_terms=("production order",),
            status="discovered",
            reason="Company inferred from hard-evidence article.",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.jsonl"

            first_count = append_candidates(path, [candidate])
            second_count = append_candidates(path, [candidate])

            self.assertEqual(first_count, 1)
            self.assertEqual(second_count, 0)


if __name__ == "__main__":
    unittest.main()

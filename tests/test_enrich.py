"""Offline tests for the enrichment stage. A fake transport stands in for Jev: no network, no key, no cost.

    .venv/bin/python -m unittest discover tests -v
"""

import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import httpx

from pipeline.common import FIELDS
from pipeline.enrich import Enricher
from pipeline.extract import entities, load_lexicon, parts
from pipeline.ingest import ingest
from pipeline.labels import reconcile_severity

ROOT = Path(__file__).resolve().parent.parent
LONG = ("I have used this app for years and mostly liked it. Since the last update I cannot log in at all, it just says "
        "something went wrong. I reinstalled twice and reset my password. Please fix this soon because I pay for premium "
        "and right now I cannot listen to anything.")
REVIEWS = [("a", "Good"), ("b", "Too many ads"), ("c", "Good"), ("d", ""), ("e", LONG), ("f", "👍"), ("g", "Crashes on start")]


def answer(body, **overrides):
    values = {"topic": "other", "intent": "praise", "severity": "none", "sentiment": 3, "quote": "part_2", "model": body["model"]}
    values.update(overrides)
    answers = {name: {"type": "choice", "choice": values[name], "confidence": 0.9, "probabilities": {values[name]: 1.0}}
               for name in ("topic", "intent", "severity")}
    answers["sentiment"] = {"type": "score", "score": values["sentiment"], "confidence": 0.9,
                            "probabilities": {str(i): float(i == values["sentiment"]) for i in range(5)}}
    if "quote" in body["questions"]:
        answers["quote"] = {"type": "choice", "choice": values["quote"], "confidence": 0.9, "probabilities": {}}
    return httpx.Response(200, json={"model": values["model"], "answers": answers, "usage": {"input_tokens": 500, "output_tokens": 20}})


class EnrichTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        source = Path(self.tmp.name) / "reviews.csv"
        with source.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(FIELDS)
            for rid, text in REVIEWS:
                writer.writerow([rid, text, "3", "0", "", "2023-01-01 00:00:00"])
        ingest(source, self.run_dir)
        self.requests = []

    def tearDown(self):
        self.tmp.cleanup()

    def enricher(self, handler, cap=1.0, **options):
        def transport(request):
            body = json.loads(request.content)
            self.requests.append(body["state"])
            return handler(body)
        return Enricher(self.run_dir, prompt_path=ROOT / "prompts/enrich_jev_v1.json", lexicon_path=ROOT / "labels/entities.json",
                        rates_path=ROOT / "cost/rates.csv", model="jev-1.13.0", api_key="test-key", max_spend_usd=cap,
                        transport=httpx.MockTransport(transport), sleep=lambda seconds: None, **options)

    def query(self, sql):
        db = sqlite3.connect(self.run_dir / "state.db")
        try:
            return db.execute(sql).fetchall()
        finally:
            db.close()

    def statuses(self):
        return dict(self.query("SELECT status, COUNT(*) FROM reviews GROUP BY status"))

    def test_completes_every_text_once_and_reuses_exact_duplicates(self):
        summary = self.enricher(answer).run()
        self.assertEqual(summary["texts"]["completed"], 5)
        self.assertEqual(sorted(self.requests), sorted({text for _, text in REVIEWS if text}))  # "Good" sent once
        self.assertEqual(self.statuses(), {"completed": 6, "quarantined": 1})
        self.assertEqual(summary["calls"]["cost_usd"], round(5 * 500 * 0.042 / 1_000_000, 6))
        quote, review = self.query("SELECT evidence_quote, needs_review FROM enrichments WHERE source_review_id = 'e'")[0]
        self.assertIn(quote, LONG)
        self.assertLess(len(quote), len(LONG))
        self.assertEqual(self.query("SELECT needs_review FROM enrichments WHERE source_review_id = 'f'"), [(1,)])  # emoji only

    def test_warm_rerun_makes_no_calls(self):
        self.enricher(answer).run()
        first = len(self.requests)
        summary = self.enricher(answer).run()
        self.assertEqual((len(self.requests) - first, summary["calls"]["attempts"], summary["stop_reason"]), (0, 0, "queue_empty"))

    def test_rate_limit_is_retried_with_every_attempt_logged(self):
        seen = []
        def handler(body):
            seen.append(body["state"])
            return httpx.Response(429, headers={"retry-after": "1"}) if seen.count(body["state"]) == 1 else answer(body)
        summary = self.enricher(handler).run()
        self.assertEqual(summary["texts"]["completed"], 5)
        self.assertEqual((summary["calls"]["attempts"], summary["calls"]["failed"]), (10, 5))
        self.assertEqual(self.query("SELECT DISTINCT error FROM calls WHERE outcome = 'failed'"), [("http_429",)])

    def test_invalid_output_is_retried_once_then_quarantined(self):
        handler = lambda body: answer(body, topic="music") if body["state"] == "Too many ads" else answer(body)
        summary = self.enricher(handler).run()
        self.assertEqual((summary["texts"]["completed"], summary["texts"]["quarantined"]), (4, 1))
        self.assertEqual(self.requests.count("Too many ads"), 2)
        self.assertEqual(self.query("SELECT reason, attempts FROM reviews WHERE review_id = 'b'"), [("invalid_model_output", 2)])
        self.assertEqual(self.statuses(), {"completed": 5, "quarantined": 2})

    def test_persistent_outage_leaves_work_pending_not_quarantined(self):
        summary = self.enricher(lambda body: httpx.Response(529), max_attempts=3).run()
        self.assertEqual((summary["texts"]["transient"], summary["calls"]["attempts"]), (5, 15))
        self.assertEqual(self.statuses(), {"pending": 6, "quarantined": 1})

    def test_bad_key_stops_the_run_immediately(self):
        summary = self.enricher(lambda body: httpx.Response(401, json={"error": "bad key"})).run()
        self.assertEqual((summary["stop_reason"], summary["calls"]["attempts"]), ("fatal_http_401", 1))
        self.assertEqual(self.statuses(), {"pending": 6, "quarantined": 1})

    def test_spend_cap_stops_work_and_resume_finishes_without_repaying(self):
        # Each call reserves about $0.00009 worst case and settles at $0.000021 actual (500 tokens x $0.042/M),
        # so a $0.00012 cap admits two calls and refuses the reservation for the third.
        first = self.enricher(answer, cap=0.00012, save_every=1).run()
        self.assertEqual((first["stop_reason"], first["texts"]["completed"], first["phase"]), ("spend_cap", 2, "initial"))
        done_before = set(self.requests)
        second = self.enricher(answer).run()
        self.assertEqual((second["phase"], second["texts"]["completed"]), ("resume", 3))
        self.assertFalse(done_before & set(self.requests[len(done_before):]))
        before, after = sorted((self.run_dir / "checkpoints").glob("*.json"))
        before, after = (set(json.loads(p.read_text())["completed_ids"]) for p in (before, after))
        self.assertTrue(before and before < after)
        self.assertEqual(self.query("SELECT phase, COUNT(*) FROM calls GROUP BY phase"), [("initial", 2), ("resume", 3)])

    def test_changed_configuration_is_refused_for_the_same_run(self):
        self.enricher(answer).run()
        with self.assertRaises(SystemExit):
            Enricher(self.run_dir, prompt_path=ROOT / "prompts/enrich_jev_v1.json", lexicon_path=ROOT / "labels/entities.json",
                     rates_path=ROOT / "cost/rates.csv", model="jev-9.9.9", api_key="k", max_spend_usd=1).run()

    def test_praise_with_a_severe_answer_is_set_to_one_and_flagged(self):
        self.enricher(lambda body: answer(body, severity="blocked")).run()
        self.assertEqual(self.query("SELECT DISTINCT severity, needs_review FROM enrichments"), [(1, 1)])


class ExtractionTests(unittest.TestCase):
    def test_parts_are_exact_substrings_and_cover_long_text(self):
        pieces = parts(LONG)
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(piece in LONG and len(piece) >= 25 for piece in pieces))
        self.assertEqual(parts("Short one."), ["Short one."])

    def test_entities_come_only_from_the_text(self):
        lexicon = load_lexicon(ROOT / "labels/entities.json")
        self.assertEqual(entities("Too many adds, switching to YouTube Music unless Premium gets cheaper", lexicon),
                         ["ads", "youtube music", "premium"])
        self.assertEqual(entities("Good", lexicon), [])

    def test_severity_rules(self):
        self.assertEqual(reconcile_severity("praise", 4)[0], 1)
        self.assertEqual(reconcile_severity("complaint", 1)[0], 2)
        self.assertEqual(reconcile_severity("cancellation", 1), (1, None))
        self.assertEqual(reconcile_severity("complaint", 4), (4, None))


if __name__ == "__main__":
    unittest.main()

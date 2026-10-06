"""Stage 2, classify (role: enrich). Label every pending distinct review text and save validated results.

Code owns the queue, validation, retries, budgets, record accounting and the evidence quote and entity extraction.
The model (Jev) reads the review and answers four fixed-label questions, plus a quote-selection question for
long reviews. One review per request, which is within the limit of 50 reviews per enrichment request.

Results and the call log are saved in one transaction after each batch, so an interrupted run resumes from the
last saved batch and never pays again for a text that is already completed.
"""

import hashlib
import json
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import jev
from .common import append_jsonl, write_json, write_jsonl
from .extract import entities, has_ascii_letters, load_lexicon, parts
from .labels import SCHEMA_VERSION, reconcile_severity, record_problems
from .ledger import RateLimiter, SpendLedger, call_cost, load_rates
from .store import insert_call, new_call, next_session, open_db, utc_now

ROLE = "enrich"
RETRYABLE = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_BACKOFF_SECONDS = 30
TRANSIENT_STREAK_LIMIT = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS enrichments (
    text_sha256      TEXT PRIMARY KEY,
    source_review_id TEXT NOT NULL,
    label_config     TEXT NOT NULL,
    topic            TEXT NOT NULL,
    intent           TEXT NOT NULL,
    sentiment        REAL NOT NULL,
    severity         INTEGER NOT NULL,
    entities         TEXT NOT NULL,
    evidence_quote   TEXT NOT NULL,
    needs_review     INTEGER NOT NULL,
    review_reasons   TEXT NOT NULL,
    raw              TEXT NOT NULL,
    request_id       TEXT NOT NULL,
    completed_at     TEXT NOT NULL
);
"""


@dataclass
class Outcome:
    kind: str  # completed | quarantined | transient | skipped | fatal
    text_sha256: str
    review_id: str
    calls: list = field(default_factory=list)
    record: dict = None
    reason: str = None


class Enricher:
    def __init__(self, run_dir, *, prompt_path, lexicon_path, rates_path, model, api_key, max_spend_usd,
                 workers=1, max_rps=10.0, max_seconds=None, save_every=50, timeout=30.0, max_attempts=5,
                 transport=None, sleep=time.sleep, ledger=None):
        self.run_dir = Path(run_dir)
        self.prompt = json.loads(Path(prompt_path).read_text(encoding="utf-8"))
        self.lexicon = load_lexicon(lexicon_path)
        self.rates = load_rates(rates_path)
        self.model, self.workers, self.save_every = model, workers, save_every
        self.max_seconds, self.max_attempts, self.sleep = max_seconds, max_attempts, sleep
        # Any edit to the questions or the lexicon changes the label configuration, so stale results are never reused.
        digest = hashlib.sha256(Path(prompt_path).read_bytes() + Path(lexicon_path).read_bytes()).hexdigest()[:8]
        self.label_config = f"{model}+{self.prompt['version']}.{digest}+{SCHEMA_VERSION}"
        self.ledger = ledger or SpendLedger(max_spend_usd)
        self.limiter = RateLimiter(max_rps, sleep=sleep)
        self.http = httpx.Client(timeout=timeout, transport=transport,
                                 headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        self.stop_reason = None
        self.stop_flag = threading.Event()
        self.started = None

    # ---- worker side: no database access -------------------------------------------------------------------

    def stop(self, reason):
        if not self.stop_flag.is_set():
            self.stop_reason = reason
            self.stop_flag.set()

    def _send(self, body, review_id, calls):
        """Send one request with bounded retries. Returns (kind, answers); every attempt is appended to calls."""
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        # Worst case for the reservation: far more tokens than this text can produce at the input rate.
        reservation = call_cost(self.rates, jev.PROVIDER, self.model, len(payload) // 2, 0)
        for attempt in range(1, self.max_attempts + 1):
            if self.max_seconds and time.monotonic() - self.started > self.max_seconds:
                self.stop("time_cap")
            if self.stop_flag.is_set():
                return "skipped", None
            if not self.ledger.reserve(reservation):
                self.stop("spend_cap")
                return "skipped", None
            self.limiter.wait()
            call = new_call(ROLE, jev.PROVIDER, self.model, self.label_config, [review_id], attempt, f"jev-{uuid.uuid4().hex}")
            calls.append(call)
            clock = time.monotonic()
            retry_after = None
            try:
                response = self.http.post(jev.API_URL, content=payload)
            except httpx.TimeoutException:
                # The provider may have processed and billed this request; charge the reservation and flag it.
                call.update(error="timeout", usage_unknown=True, cost_usd=reservation)
                self.ledger.settle(reservation, reservation)
            except httpx.TransportError as e:
                call.update(error=f"connection: {type(e).__name__}")
                self.ledger.settle(reservation, 0.0)
            else:
                call["status_code"] = response.status_code
                call["provider_request_id"] = response.headers.get("x-request-id")
                if response.status_code == 200:
                    try:
                        data = response.json()
                        usage = data["usage"]
                        call.update(input_tokens=int(usage["input_tokens"]), output_tokens=int(usage["output_tokens"]))
                        call["cost_usd"] = call_cost(self.rates, jev.PROVIDER, self.model, call["input_tokens"], call["output_tokens"])
                        self.ledger.settle(reservation, call["cost_usd"])
                    except (ValueError, KeyError, TypeError):
                        call.update(error="invalid_output: unreadable response body", usage_unknown=True, cost_usd=reservation)
                        self.ledger.settle(reservation, reservation)
                        return "invalid", None
                    call.update(duration_ms=round((time.monotonic() - clock) * 1000), outcome="succeeded")
                    if data.get("model") != self.model:
                        call.update(outcome="failed", error=f"invalid_output: answered by {data.get('model')!r}, not the pinned model")
                        return "invalid", None
                    return "ok", data.get("answers")
                self.ledger.settle(reservation, 0.0)
                call["error"] = f"http_{response.status_code}"
                if response.status_code not in RETRYABLE:
                    call["duration_ms"] = round((time.monotonic() - clock) * 1000)
                    self.stop(f"fatal_http_{response.status_code}")
                    return "fatal", response.text[:300]
                try:
                    retry_after = float(response.headers.get("retry-after", ""))
                except ValueError:
                    pass
            call["duration_ms"] = round((time.monotonic() - clock) * 1000)
            if attempt < self.max_attempts:
                # Exponential backoff with jitter; a rate-limit response also slows every other worker.
                delay = min(MAX_BACKOFF_SECONDS, 2 ** (attempt - 1)) * random.uniform(0.5, 1.5)
                delay = max(delay, retry_after or 0)
                if call["status_code"] in (429, 529):
                    self.limiter.pause(delay)
                self.sleep(delay)
        return "transient", None

    def _record(self, text, parsed, quote_parts):
        reasons = []
        severity, adjusted = reconcile_severity(parsed["intent"], parsed["severity"])
        if adjusted and abs(severity - parsed["severity"]) >= 2:
            reasons.append(adjusted)
        threshold = self.prompt["needs_review_confidence"]
        reasons += [f"low_confidence_{name}" for name, value in parsed["confidence"].items()
                    if name != "sentiment" and value < threshold]
        if not has_ascii_letters(text):
            reasons.append("no_ascii_letters")  # emoji-only or non-Latin script; Jev is weaker outside English
        quote = quote_parts[parsed["quote_index"]] if quote_parts else text.strip()
        return {"topic": parsed["topic"], "intent": parsed["intent"], "sentiment": parsed["sentiment"], "severity": severity,
                "entities": entities(text, self.lexicon), "evidence_quote": quote, "needs_review": bool(reasons),
                "label_config": self.label_config, "review_reasons": reasons,
                "raw": {"model_severity": parsed["severity"], "severity_rule": adjusted, "confidence": parsed["confidence"]}}

    def _label_text(self, item):
        sha, review_id, text = item
        outcome = Outcome("skipped", sha, review_id)
        quote_parts = parts(text) if len(text) > self.prompt["short_text_chars"] else []
        if len(quote_parts) < 2:
            quote_parts = []
        body = jev.build_body(text, self.prompt, self.model, quote_parts)
        # Invalid output is retried once, then the text is quarantined with its reason.
        for _ in range(2):
            kind, answers = self._send(body, review_id, outcome.calls)
            if kind in ("skipped", "transient", "fatal"):
                outcome.kind, outcome.reason = kind, answers
                return outcome
            if kind == "ok":
                try:
                    record = self._record(text, jev.parse_answers(answers, self.prompt, quote_parts), quote_parts)
                    problems = record_problems(record, text)
                    if not problems:
                        record["request_id"] = outcome.calls[-1]["request_id"]
                        outcome.kind, outcome.record = "completed", record
                        return outcome
                    error = "invalid_record: " + ", ".join(problems)
                except jev.InvalidOutput as e:
                    error = f"invalid_output: {e}"
                outcome.calls[-1].update(outcome="failed", error=error)
        outcome.kind, outcome.reason = "quarantined", "invalid_model_output"
        return outcome

    # ---- orchestrator side ---------------------------------------------------------------------------------

    def _save(self, db, outcomes, session, phase):
        for o in outcomes:
            for c in o.calls:
                insert_call(db, c, session, phase)
            if o.kind == "completed":
                r = o.record
                db.execute(
                    "INSERT INTO enrichments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (o.text_sha256, o.review_id, r["label_config"], r["topic"], r["intent"], r["sentiment"], r["severity"],
                     json.dumps(r["entities"], ensure_ascii=False), r["evidence_quote"], int(r["needs_review"]),
                     json.dumps(r["review_reasons"]), json.dumps(r["raw"], sort_keys=True), r["request_id"], utc_now()))
                db.execute("UPDATE reviews SET status = 'completed' WHERE text_sha256 = ? AND status = 'pending'", (o.text_sha256,))
            elif o.kind == "quarantined":
                db.execute("UPDATE reviews SET status = 'quarantined', reason = ?, attempts = attempts + ? "
                           "WHERE text_sha256 = ? AND status = 'pending'", (o.reason, len(o.calls), o.text_sha256))
            elif o.calls:
                db.execute("UPDATE reviews SET attempts = attempts + ? WHERE text_sha256 = ?", (len(o.calls), o.text_sha256))
        db.commit()  # one transaction per batch: results, statuses and the call log move together

    def run(self, limit=None, session=None):
        self.started = time.monotonic()
        db = open_db(self.run_dir, SCHEMA)
        stored = db.execute("SELECT value FROM meta WHERE key = 'label_config'").fetchone()
        if stored and stored[0] != self.label_config:
            db.close()
            raise SystemExit(f"{self.run_dir} was enriched with {stored[0]}; the current configuration is "
                             f"{self.label_config}. Results are only reused under an unchanged configuration: use a new --run-id.")
        db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('label_config', ?)", (self.label_config,))
        db.commit()

        pending = db.execute(
            "SELECT t.text_sha256, t.first_review_id, r.review_text FROM texts t JOIN reviews r ON r.review_id = t.first_review_id "
            "WHERE r.status = 'pending' ORDER BY r.row_num" + (" LIMIT ?" if limit else ""), (limit,) if limit else ()).fetchall()
        session = session or next_session(db)
        # The first enrichment session is "initial"; any later one resumes from saved progress.
        earlier = db.execute("SELECT COUNT(*) FROM calls WHERE role = ? AND session < ?", (ROLE, session)).fetchone()[0]
        phase = "resume" if earlier else "initial"
        log = self.run_dir / "run_log.jsonl"
        append_jsonl(log, {"event": "enrich_start", "at": utc_now(), "session": session, "phase": phase, "pending_texts": len(pending),
                           "label_config": self.label_config, "workers": self.workers, "spend_cap_usd": self.ledger.cap})

        counts = {"completed": 0, "quarantined": 0, "transient": 0, "skipped": 0, "fatal": 0}
        transient_streak, fatal_detail = 0, None
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for start in range(0, len(pending), self.save_every):
                if self.stop_flag.is_set():
                    break
                futures = [pool.submit(self._label_text, item) for item in pending[start:start + self.save_every]]
                try:
                    outcomes = [f.result() for f in futures]
                except KeyboardInterrupt:
                    # Stop admitting work, let in-flight requests finish, and save what completed.
                    self.stop("interrupted")
                    for f in futures:
                        f.cancel()
                    outcomes = [f.result() for f in futures if not f.cancelled()]
                self._save(db, outcomes, session, phase)
                for o in outcomes:
                    counts[o.kind] += 1
                    transient_streak = transient_streak + 1 if o.kind == "transient" else 0
                    if o.kind == "fatal":
                        fatal_detail = o.reason
                if transient_streak >= TRANSIENT_STREAK_LIMIT:
                    self.stop("api_unavailable")
                append_jsonl(log, {"event": "batch_saved", "at": utc_now(), "session": session, **counts,
                                   "spent_usd": round(self.ledger.spent, 6)})

        wall = time.monotonic() - self.started
        totals = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(outcome = 'succeeded'), 0), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), "
            "COALESCE(SUM(cost_usd), 0), COALESCE(SUM(usage_unknown), 0) FROM calls WHERE role = ? AND session = ?", (ROLE, session)).fetchone()
        statuses = dict(db.execute("SELECT status, COUNT(*) FROM reviews GROUP BY status"))
        completed_ids = [row[0] for row in db.execute("SELECT review_id FROM reviews WHERE status = 'completed' ORDER BY row_num")]
        quarantined = [{"review_id": a, "source_sha256": b, "status": "quarantined", "reason": c, "attempts": d} for a, b, c, d in
                       db.execute("SELECT review_id, source_sha256, reason, attempts FROM reviews WHERE status = 'quarantined' ORDER BY row_num")]
        db.close()
        self.http.close()

        summary = {
            "session": session, "phase": phase, "label_config": self.label_config, "stop_reason": self.stop_reason or "queue_empty",
            "fatal_detail": fatal_detail, "texts_pending_at_start": len(pending), "texts": counts,
            "calls": {"attempts": totals[0], "succeeded": totals[1], "failed": totals[0] - totals[1], "input_tokens": totals[2],
                      "output_tokens": totals[3], "cost_usd": round(totals[4], 6), "usage_unknown": totals[5]},
            "wall_seconds": round(wall, 2), "texts_per_second": round(counts["completed"] / wall, 2) if wall else None,
            "workers": self.workers, "spend_cap_usd": self.ledger.cap, "review_status_counts": statuses,
        }
        if totals[0] or self.stop_reason:
            # A snapshot per session; the first and last become grading/checkpoint_before.json and checkpoint_after.json.
            write_json(self.run_dir / "checkpoints" / f"{session:03d}_{phase}_{summary['stop_reason']}.json",
                       {"session": session, "phase": phase, "stop_reason": summary["stop_reason"], "saved_at": utc_now(),
                        "completed_count": len(completed_ids), "completed_ids": completed_ids})
        write_jsonl(self.run_dir / "quarantine.jsonl", quarantined)
        write_json(self.run_dir / "enrich_last_session.json", summary)
        append_jsonl(log, {"event": "enrich_stop", "at": utc_now(), **{k: summary[k] for k in ("session", "stop_reason", "texts", "calls", "wall_seconds")}})
        return summary

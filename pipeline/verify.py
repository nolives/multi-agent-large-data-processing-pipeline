"""Stage 3, verify (role: verify). An independent model re-labels a declared random sample; code compares.

The verifier is given only review texts and the rubric. It never receives the enricher's predictions, and it is a
different model family from the enricher. Code then compares the two sets of labels, lists every disagreement,
scores needs_review as a predictor of disagreement, and runs a planted-error check on a separate copy.
"""

import csv
import hashlib
import io
import json

from .common import write_json, write_jsonl, write_text_atomic
from .labels import INTENTS, SCHEMA_VERSION, TOPICS
from .store import insert_call, phase_for, role_config, utc_now

ROLE = "verify"
SENTIMENTS = (-1, -0.5, 0, 0.5, 1)
SENTIMENT_TOLERANCE = 0.5
FIELDS = ("topic", "intent", "severity")
MAX_FAILED_BATCHES = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS verifications (
    text_sha256     TEXT PRIMARY KEY,
    review_id       TEXT NOT NULL,
    verifier_config TEXT NOT NULL,
    topic           TEXT NOT NULL,
    intent          TEXT NOT NULL,
    severity        INTEGER NOT NULL,
    sentiment       REAL NOT NULL,
    request_id      TEXT NOT NULL,
    verified_at     TEXT NOT NULL
);
"""

OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["labels"],
    "properties": {"labels": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "topic", "intent", "severity", "sentiment"],
        "properties": {"id": {"type": "string"}, "topic": {"type": "string", "enum": list(TOPICS)},
                       "intent": {"type": "string", "enum": list(INTENTS)}, "severity": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                       "sentiment": {"type": "number", "enum": list(SENTIMENTS)}}}}},
}


def sample(db, size, seed):
    """A declared, reproducible random sample of completed distinct texts: the lowest SHA-256(seed:text hash) values."""
    rows = db.execute("SELECT e.text_sha256, e.source_review_id, r.review_text FROM enrichments e "
                      "JOIN reviews r ON r.review_id = e.source_review_id").fetchall()
    rows.sort(key=lambda row: hashlib.sha256(f"{seed}:{row[0]}".encode()).hexdigest())
    return rows[:size]


def parse_labels(data, expected_ids):
    """Validate the verifier's output for one request. Returns {id: labels} or raises ValueError."""
    labels = data.get("labels") if isinstance(data, dict) else None
    if not isinstance(labels, list):
        raise ValueError("labels is not a list")
    result = {}
    for item in labels:
        if not isinstance(item, dict) or item.get("id") in result:
            raise ValueError("malformed or repeated entry")
        if (item.get("topic") not in TOPICS or item.get("intent") not in INTENTS or type(item.get("severity")) is not int
                or not 1 <= item["severity"] <= 5 or item.get("sentiment") not in SENTIMENTS):
            raise ValueError(f"disallowed label for {item.get('id')}")
        result[item["id"]] = item
    if set(result) != set(expected_ids):
        raise ValueError(f"returned IDs do not match the request: missing {sorted(set(expected_ids) - set(result))}, "
                         f"unexpected {sorted(set(result) - set(expected_ids))}")
    return result


def compare(pairs):
    """pairs: dicts with enricher labels (e_*), verifier labels (v_*), needs_review. Returns the agreement report body."""
    n = len(pairs)
    disagreements = []
    agree = dict.fromkeys((*FIELDS, "all_three", "sentiment_within_tolerance"), 0)
    severity_error = flagged = flagged_and_disagree = 0
    confusion = {field: {} for field in FIELDS}
    for p in pairs:
        differs = [f for f in FIELDS if p["e_" + f] != p["v_" + f]]
        for f in FIELDS:
            agree[f] += f not in differs
            if f in differs:
                key = f"{p['e_' + f]} -> {p['v_' + f]}"
                confusion[f][key] = confusion[f].get(key, 0) + 1
        agree["all_three"] += not differs
        agree["sentiment_within_tolerance"] += abs(p["e_sentiment"] - p["v_sentiment"]) <= SENTIMENT_TOLERANCE
        severity_error += abs(p["e_severity"] - p["v_severity"])
        flagged += p["needs_review"]
        flagged_and_disagree += p["needs_review"] and bool(differs)
        if differs:
            disagreements.append({**p, "fields": differs})
    rate = lambda a, b: round(a / b, 4) if b else None
    return {
        "compared": n,
        "agreement": {name: rate(count, n) for name, count in agree.items()},
        "agreement_counts": agree,
        "severity_mean_absolute_difference": rate(severity_error, n),
        "disagreeing_texts": len(disagreements),
        "confusion_enricher_to_verifier": {f: dict(sorted(c.items(), key=lambda kv: -kv[1])) for f, c in confusion.items()},
        # needs_review scored as a prediction that the two labelers will disagree.
        "needs_review_as_predictor": {"flagged": flagged, "flagged_and_disagree": flagged_and_disagree,
                                      "precision": rate(flagged_and_disagree, flagged),
                                      "recall": rate(flagged_and_disagree, len(disagreements))},
    }, disagreements


def planted_error_check(pairs, count, seed):
    """On a separate copy, change the enricher's topic for `count` agreeing texts and confirm the comparison catches each."""
    agreeing = sorted((p for p in pairs if all(p["e_" + f] == p["v_" + f] for f in FIELDS)),
                      key=lambda p: hashlib.sha256(f"planted:{seed}:{p['text_sha256']}".encode()).hexdigest())[:count]
    planted = {}
    for p in agreeing:
        planted[p["text_sha256"]] = TOPICS[(TOPICS.index(p["e_topic"]) + 1) % len(TOPICS)]
    copy = [{**p, "e_topic": planted.get(p["text_sha256"], p["e_topic"])} for p in pairs]
    caught = {d["text_sha256"] for d in compare(copy)[1] if "topic" in d["fields"]}
    return {"planted": len(planted), "detected": len(set(planted) & caught), "all_detected": set(planted) <= caught,
            "cases": [{"review_id": p["review_id"], "true_topic": p["e_topic"], "planted_topic": planted[p["text_sha256"]],
                       "detected": p["text_sha256"] in caught} for p in agreeing],
            "note": "Synthetic test on a copy of the predictions; the saved enrichment results are not modified."}


def verify(run_dir, db, caller, *, prompt_path, model, sample_size, seed, session, batch_size=10, planted=5, effort=None):
    system, config = role_config(prompt_path, model, SCHEMA_VERSION, effort)
    db.executescript(SCHEMA)
    chosen = sample(db, sample_size, seed)
    done = {row[0] for row in db.execute("SELECT text_sha256 FROM verifications WHERE verifier_config = ?", (config,))}
    todo = [row for row in chosen if row[0] not in done]
    phase = phase_for(db, ROLE, session)
    stop_reason, failed_texts, failed_batches = None, 0, 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        local = {f"r{i}": row for i, row in enumerate(batch, 1)}
        # The request holds review text only: no predictions, no metadata, no star ratings.
        user = "Label each of these reviews.\n\n" + json.dumps([{"id": k, "text": row[2]} for k, row in local.items()], ensure_ascii=False)
        labels = None
        for _ in range(2):  # invalid output is retried once
            kind, data, calls = caller.call(role=ROLE, model=model, label_config=config, system=system, user=user,
                                            schema=OUTPUT_SCHEMA, max_tokens=4000, review_ids=[row[1] for row in batch], effort=effort)
            if kind == "ok":
                try:
                    labels = parse_labels(data, local)
                except ValueError as e:
                    calls[-1].update(outcome="failed", error=f"invalid_output: {e}")
                    kind = "invalid"
            for call in calls:
                insert_call(db, call, session, phase)
            if kind not in ("invalid",):
                break
        if labels:
            for key, row in local.items():
                item = labels[key]
                db.execute("INSERT OR REPLACE INTO verifications VALUES (?,?,?,?,?,?,?,?,?)",
                           (row[0], row[1], config, item["topic"], item["intent"], item["severity"], item["sentiment"],
                            calls[-1]["request_id"], utc_now()))
            failed_batches = 0
        else:
            failed_texts += len(batch)
            failed_batches += 1
        db.commit()
        if kind in ("fatal", "spend_cap", "transient", "refusal"):
            stop_reason = kind if kind != "fatal" else f"fatal: {data}"
            break
        if failed_batches >= MAX_FAILED_BATCHES:
            # The same failure twice in a row is a systematic problem; stop paying for it and report.
            stop_reason = "repeated_invalid_output"
            break

    pairs = [dict(zip(("text_sha256", "review_id", "review_text", "needs_review", "e_topic", "e_intent", "e_severity", "e_sentiment",
                       "v_topic", "v_intent", "v_severity", "v_sentiment"), row)) for row in db.execute(
        "SELECT e.text_sha256, e.source_review_id, r.review_text, e.needs_review, e.topic, e.intent, e.severity, e.sentiment, "
        "v.topic, v.intent, v.severity, v.sentiment FROM verifications v JOIN enrichments e ON e.text_sha256 = v.text_sha256 "
        "JOIN reviews r ON r.review_id = e.source_review_id WHERE v.verifier_config = ? ORDER BY r.row_num", (config,))]
    wanted = {row[0] for row in chosen}
    pairs = [p for p in pairs if p["text_sha256"] in wanted]
    body, disagreements = compare(pairs)
    report = {"verifier_config": config, "enricher_config": db.execute("SELECT value FROM meta WHERE key = 'label_config'").fetchone()[0],
              "sample": {"unit": "distinct completed review texts", "requested": sample_size, "drawn": len(chosen), "seed": seed,
                         "method": "lowest SHA-256(seed:text_sha256) values", "verified": len(pairs), "new_this_session": len(todo) - failed_texts,
                         "failed_this_session": failed_texts},
              "independence": "The verifier receives review text and the rubric only; it is never shown the enricher's labels.",
              "sentiment_tolerance": SENTIMENT_TOLERANCE, "stop_reason": stop_reason, **body,
              "planted_error_test": planted_error_check(pairs, planted, seed)}
    write_json(run_dir / "verify_report.json", report)
    write_jsonl(run_dir / "verify_predictions.jsonl",
                [{"review_id": p["review_id"], "verifier_config": config, **{f: p["v_" + f] for f in (*FIELDS, "sentiment")}} for p in pairs])
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["review_id", "fields_that_differ", "enricher_topic", "verifier_topic", "enricher_intent", "verifier_intent",
                     "enricher_severity", "verifier_severity", "enricher_needs_review", "review_text"])
    for d in disagreements:
        writer.writerow([d["review_id"], "; ".join(d["fields"]), d["e_topic"], d["v_topic"], d["e_intent"], d["v_intent"],
                         d["e_severity"], d["v_severity"], bool(d["needs_review"]), d["review_text"]])
    write_text_atomic(run_dir / "verify_disagreements.csv", buffer.getvalue())
    return report

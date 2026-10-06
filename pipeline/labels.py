"""The shared label schema and the code-side checks every record must pass."""

import math

SCHEMA_VERSION = "schema-v1"
TOPICS = ("access", "usability", "playback", "downloads", "catalog", "billing", "support", "other")
INTENTS = ("cancellation", "complaint", "request", "praise", "unclear")  # precedence order
COMPLAINT_INTENTS = ("cancellation", "complaint")
LABEL_FIELDS = ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review", "label_config")


def record_problems(record, review_text):
    """Mirror the completed-record checks in data/check_submission.py; return a list of problems (empty if valid)."""
    problems = []
    if record.get("topic") not in TOPICS:
        problems.append("topic")
    if record.get("intent") not in INTENTS:
        problems.append("intent")
    if not (isinstance(record.get("label_config"), str) and record["label_config"].strip()):
        problems.append("label_config")
    if not (type(record.get("severity")) is int and 1 <= record["severity"] <= 5):
        problems.append("severity")
    sentiment = record.get("sentiment")
    if not (type(sentiment) in (int, float) and math.isfinite(sentiment) and -1 <= sentiment <= 1):
        problems.append("sentiment")
    if type(record.get("needs_review")) is not bool:
        problems.append("needs_review")
    entities = record.get("entities")
    if not (isinstance(entities, list) and all(isinstance(x, str) and x.strip() for x in entities)):
        problems.append("entities")
    quote = record.get("evidence_quote")
    if not (isinstance(quote, str) and quote.strip()):
        problems.append("evidence_quote")
    elif quote not in review_text:
        problems.append("evidence_quote_not_in_text")
    return problems


def reconcile_severity(intent, severity):
    """Make severity consistent with intent under the shared definitions. Returns (severity, reason or None).

    Severity 1 means no reported problem, so praise, a pure request and unclear content are 1 by definition,
    and a complaint is at least 2. The model's own answer is kept in the raw output; a change of two or more
    levels is flagged for review by the caller.
    """
    if intent in ("praise", "request", "unclear") and severity != 1:
        return 1, f"severity_{severity}_to_1_for_{intent}"
    if intent == "complaint" and severity == 1:
        return 2, "severity_1_to_2_for_complaint"
    return severity, None

"""Stage 6, recommend (role: memo). A model writes the decision memo from saved aggregates and a bounded evidence pack.

The model never types a number. Every figure in its text is a placeholder that code fills from the saved ranking
({{C001}}), run facts ({{F:name}}) or the evidence pack ({{R:review-id}}). Code rejects a memo that contains a raw
digit, an unknown placeholder, an unknown issue ID or a missing section, so a numerical claim cannot drift from the
saved calculation. A person still has to judge whether the argument is sound.
"""

import csv
import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .common import canonical, write_json, write_text_atomic
from .labels import SCHEMA_VERSION
from .rank import write_csv
from .store import insert_call, phase_for, role_config

ROLE = "memo"
METRICS = ("complaint_count", "severity_sum", "mean_severity", "priority_score")
PRIORITIES = {"access": ("access",), "usability": ("usability",), "playback": ("playback",), "billing_support": ("billing", "support")}
SECTIONS = ("## Recommendation", "## Evidence", "## Alternatives considered", "## Limitations")
PLACEHOLDER = re.compile(r"\{\{(C\d{3}|F:[A-Za-z0-9_.\-]+|R:[^{}]+)\}\}")
TOP_ISSUES = 10
EXAMPLES_PER_ISSUE = 3
QUOTE_MAX_CHARS = 200

OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["recommended_priority", "memo_markdown"],
    "properties": {"recommended_priority": {"type": "string", "enum": list(PRIORITIES)}, "memo_markdown": {"type": "string"}},
}


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def percent(part, whole):
    return f"{(Decimal(100 * part) / Decimal(whole)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%" if whole else "n/a"


def build_input(run_dir, db):
    """Everything the memo model may see: ranking rows, priority-area sums, run facts and a few examples per top issue."""
    run_dir = Path(run_dir)
    ranking = read_csv(run_dir / "ranking.csv")
    names = {i["issue_id"]: i for i in json.loads((run_dir / "issues.json").read_text(encoding="utf-8"))["issues"]}
    claims, rows = {}, []
    for row in ranking[:TOP_ISSUES]:
        ids = {}
        for metric in METRICS:
            cid = f"C{len(claims) + 1:03d}"
            claims[cid] = {"claim_id": cid, "issue_id": row["issue_id"], "metric": metric, "value": row[metric]}
            ids[metric] = {"value": row[metric], "cite_as": "{{" + cid + "}}"}
        rows.append({"rank": row["rank"], "issue_id": row["issue_id"], "title": names[row["issue_id"]]["title"],
                     "description": names[row["issue_id"]]["description"], "numbers": ids})

    facts = {}
    ingestion = json.loads((run_dir / "ingestion_report.json").read_text(encoding="utf-8"))
    status = dict(db.execute("SELECT status, COUNT(*) FROM reviews GROUP BY status"))
    total = sum(status.values())
    facts["source_reviews"] = f"{ingestion['accounting']['source_rows']:,}"
    facts["classified_reviews"] = f"{status.get('completed', 0):,}"
    facts["classified_share"] = percent(status.get("completed", 0), total)
    facts["quarantined_reviews"] = f"{status.get('quarantined', 0):,}"
    facts["unclassified_pending_reviews"] = f"{status.get('pending', 0):,}"
    facts["first_review_date"] = ingestion["profile"]["first_review"][:10]
    facts["last_review_date"] = ingestion["profile"]["last_review"][:10]
    total_complaints = sum(int(r["complaint_count"]) for r in ranking)
    facts["complaint_reviews"] = f"{total_complaints:,}"
    facts["issues_ranked"] = str(len(ranking))
    verify_path = run_dir / "verify_report.json"
    if verify_path.exists():
        v = json.loads(verify_path.read_text(encoding="utf-8"))
        facts["verification_sample_texts"] = f"{v['compared']:,}"
        for field in ("topic", "intent", "severity"):
            facts[f"verification_{field}_agreement"] = percent(v["agreement_counts"][field], v["compared"])

    by_topic = {r["topic"]: r for r in read_csv(run_dir / "topic_rollup.csv")}
    areas = []
    for area, topics in PRIORITIES.items():
        count = sum(int(by_topic[t]["complaint_count"]) for t in topics if t in by_topic)
        total_severity = sum(int(by_topic[t]["severity_sum"]) for t in topics if t in by_topic)
        values = {"complaint_count": f"{count:,}", "severity_sum": f"{total_severity:,}",
                  "mean_severity": str((Decimal(total_severity) / Decimal(count)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if count else "n/a",
                  "share_of_complaints": percent(count, total_complaints)}
        for name, value in values.items():
            facts[f"{area}.{name}"] = value
        areas.append({"priority": area, "topics": list(topics),
                      "numbers": {name: {"value": value, "cite_as": "{{F:" + f"{area}.{name}" + "}}"} for name, value in values.items()},
                      "issues": [r["issue_id"] for r in ranking if r["issue_id"].split(".")[0] in topics][:5]})

    evidence = []
    for row in ranking[:TOP_ISSUES]:
        # Representative, confident examples: distinct texts, most-liked first, short exact quotes.
        for rid, severity, quote, _ in db.execute(
                "SELECT r.review_id, e.severity, e.evidence_quote, MIN(r.row_num) AS first_row FROM memberships m "
                "JOIN reviews r ON r.review_id = m.review_id JOIN enrichments e ON e.text_sha256 = r.text_sha256 "
                "WHERE m.issue_id = ? AND e.needs_review = 0 AND LENGTH(e.evidence_quote) <= ? GROUP BY r.text_sha256 "
                "ORDER BY CAST(r.review_likes AS INTEGER) DESC, first_row LIMIT ?", (row["issue_id"], QUOTE_MAX_CHARS, EXAMPLES_PER_ISSUE)).fetchall():
            evidence.append({"cite_as": "{{R:" + rid + "}}", "review_id": rid, "issue_id": row["issue_id"], "severity": severity, "quote": quote})

    # The model sees each value so it can reason about it, but must write the placeholder, never the digits.
    model_input = {"ranking": rows, "priority_areas": areas,
                   "facts": {name: {"value": value, "cite_as": "{{F:" + name + "}}"} for name, value in facts.items()},
                   "fact_meanings": "Facts are named for what they hold; counts are reviews.", "evidence": evidence}
    return model_input, claims, facts, {e["review_id"]: e for e in evidence}, {r["issue_id"] for r in ranking}


def check(text, claims, facts, evidence, issue_ids):
    """Return (errors, cited claim IDs, cited review IDs) for the model's memo body."""
    errors, cited_claims, cited_reviews = [], [], []
    for token in PLACEHOLDER.findall(text):
        if token.startswith("C"):
            (cited_claims if token in claims else errors).append(token if token in claims else f"unknown claim placeholder {token}")
        elif token.startswith("F:"):
            if token[2:] not in facts:
                errors.append(f"unknown fact placeholder {token}")
        elif token[2:] in evidence:
            cited_reviews.append(token[2:])
        else:
            errors.append(f"review {token[2:]} is not in the evidence pack")
    stripped = PLACEHOLDER.sub("", text)
    # A quotation copied exactly from an evidence quote may contain digits the reviewer wrote.
    for quoted in re.findall(r'"([^"\n]+)"|\u201c([^\u201d\n]+)\u201d', stripped):
        words = (quoted[0] or quoted[1]).strip(" .,;:!?…")
        if words and any(words in e["quote"] for e in evidence.values()):
            stripped = stripped.replace(quoted[0] or quoted[1], "")
    if "{{" in stripped or "}}" in stripped:
        errors.append("malformed placeholder")
    digits = sorted(set(re.findall(r"\S*\d\S*", stripped)))
    if digits:
        errors.append("raw digits outside placeholders: " + ", ".join(digits[:8]))
    for issue in set(re.findall(r"`([a-z_]+\.[a-z\-]+)`", text)):
        if issue not in issue_ids:
            errors.append(f"unknown issue ID {issue}")
    errors += [f"missing section {s}" for s in SECTIONS if s not in text]
    if not cited_claims:
        errors.append("no issue-level claim is cited")
    if len(set(cited_reviews)) < 3:
        errors.append("fewer than three example reviews are cited")
    return errors, list(dict.fromkeys(cited_claims)), list(dict.fromkeys(cited_reviews))


def render(text, claims, facts):
    def fill(match):
        token = match.group(1)
        if token.startswith("C"):
            value = claims[token]["value"]
            return f"{int(value):,} [{token}]" if value.isdigit() else f"{value} [{token}]"
        if token.startswith("F:"):
            return facts[token[2:]]
        return f"review `{token[2:]}`"
    return PLACEHOLDER.sub(fill, text)


def memo(run_dir, db, caller, *, prompt_path, model, session, effort=None):
    run_dir = Path(run_dir)
    system, config = role_config(prompt_path, model, SCHEMA_VERSION)
    model_input, claims, facts, evidence, issue_ids = build_input(run_dir, db)
    if not model_input["ranking"]:
        write_json(run_dir / "memo_check.json", {"valid": False, "errors": ["no ranked issues: nothing to recommend"], "memo_config": config})
        return {"valid": False, "errors": ["no ranked issues"], "calls": 0}
    key = hashlib.sha256((config + canonical(model_input) + canonical(claims) + canonical(facts)).encode("utf-8")).hexdigest()
    previous = db.execute("SELECT value FROM meta WHERE key = 'memo_key'").fetchone()
    if previous and previous[0] == key and (run_dir / "memo.md").exists():
        return {"valid": True, "errors": [], "calls": 0, "reused": True}  # unchanged inputs and configuration: no new call

    write_json(run_dir / "memo_input.json", {"memo_config": config, "model_input": model_input, "claims": list(claims.values()), "facts": facts})
    phase = phase_for(db, ROLE, session)
    base = "Write the decision memo from this saved analysis.\n\n" + json.dumps(model_input, ensure_ascii=False, indent=1)
    user, errors, attempts, data = base, ["no attempt made"], 0, None
    for _ in range(2):  # a rejected memo is retried once, with the reasons it was rejected
        attempts += 1
        kind, data, calls = caller.call(role=ROLE, model=model, label_config=config, system=system, user=user,
                                        schema=OUTPUT_SCHEMA, max_tokens=16000, effort=effort)
        if kind == "ok":
            body = data.get("memo_markdown", "") if isinstance(data, dict) else ""
            errors, cited_claims, cited_reviews = check(body, claims, facts, evidence, issue_ids)
            if data.get("recommended_priority") not in PRIORITIES:
                errors.append("recommended_priority is not an allowed value")
            if errors:
                calls[-1].update(outcome="failed", error="invalid_output: " + "; ".join(errors)[:300])
        else:
            errors = [f"model call ended with {kind}" + (f": {data}" if kind == "fatal" else "")]
        for call in calls:
            insert_call(db, call, session, phase)
        db.commit()
        if not errors or kind != "ok":
            break
        user = base + "\n\nYour previous memo was rejected by the automatic check for these reasons. Fix every one:\n- " + "\n- ".join(errors)

    result = {"valid": not errors, "errors": errors, "memo_config": config, "attempts": attempts}
    if errors:
        write_json(run_dir / "memo_check.json", {**result, "rejected_output": data if isinstance(data, dict) else None})
        return {**result, "calls": attempts}
    cited = [claims[c] for c in cited_claims]
    write_csv(run_dir / "claims.csv", ("claim_id", "issue_id", "metric", "value"), ([c[k] for k in ("claim_id", "issue_id", "metric", "value")] for c in cited))
    appendix = ["", "---", "", "## Appendix: how to check this memo", "",
                f"- Recommended priority: **{data['recommended_priority']}**.",
                "- Issue-level numbers carry a claim ID in square brackets. Each is listed in `claims.csv` and equals the value in `ranking.csv`, "
                "which `python3 -m pipeline rank` recomputes from saved records and issue membership without any model call.",
                "- priority_score = complaint_count × mean_severity = severity_sum, over completed complaint and cancellation records.",
                "- Priority-area totals sum the topic rows in `topic_rollup.csv` (billing_support = billing + support); shares are of all grouped complaint records.",
                f"- Written by `{config}` from `memo_input.json`; numbers were inserted by code from saved calculations.", "",
                "| Claim | Issue | Metric | Value |", "|---|---|---|---|",
                *(f"| {c['claim_id']} | `{c['issue_id']}` | {c['metric']} | {c['value']} |" for c in cited), "",
                "| Cited review | Issue | Severity | Evidence quote |", "|---|---|---|---|",
                *(f"| `{r}` | `{evidence[r]['issue_id']}` | {evidence[r]['severity']} | {evidence[r]['quote'].replace('|', '/').replace(chr(10), ' ')} |" for r in cited_reviews)]
    write_text_atomic(run_dir / "memo.md", "# Where should Spotify's next quarter of product effort go?\n\n"
                      + render(data["memo_markdown"].strip(), claims, facts) + "\n" + "\n".join(appendix) + "\n")
    write_json(run_dir / "memo_check.json", {**result, "recommended_priority": data["recommended_priority"], "cited_claims": cited_claims,
                                             "cited_reviews": cited_reviews, "checks": ["every number is a placeholder filled by code",
                                             "every placeholder, review ID and issue ID exists in the saved input", "all four sections present"]})
    db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('memo_key', ?)", (key,))
    db.commit()
    return {**result, "calls": attempts, "recommended_priority": data["recommended_priority"]}

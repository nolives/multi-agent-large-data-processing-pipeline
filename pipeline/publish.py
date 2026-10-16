"""Publish one run's saved results to the dashboard database (Postgres). No model calls.

    python3 -m pipeline publish --run-id <run>

Loads the processed reviews, issue ranking, memo, claims and saved reports from the run directory into the tables
defined in dashboard/db/schema.sql, replacing what was there in a single transaction. Needs DATABASE_URL in .env.
Everything written here comes from files the pipeline already saved; nothing is recomputed by a model.
"""

import csv
import json
import os
from pathlib import Path

from .common import load_env, open_saved_state

SCHEMA = Path(__file__).resolve().parent.parent / "dashboard" / "db" / "schema.sql"
REVIEW_COLUMNS = ("review_id", "row_num", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp", "review_month",
                  "source_sha256", "status", "reason", "topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review",
                  "cache_source_id", "issue_id")


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def review_rows(db):
    """Every source review with its original values, status, labels and issue, in source order."""
    query = ("SELECT r.review_id, r.row_num, r.review_text, r.review_rating, r.review_likes, r.app_version, r.review_timestamp, "
             "r.source_sha256, r.status, r.reason, e.topic, e.intent, e.sentiment, e.severity, e.entities, e.evidence_quote, e.needs_review, "
             "e.source_review_id, m.issue_id FROM reviews r LEFT JOIN enrichments e ON e.text_sha256 = r.text_sha256 "
             "LEFT JOIN memberships m ON m.review_id = r.review_id ORDER BY r.row_num")
    for (rid, row_num, text, rating, likes, version, stamp, sha, status, reason, topic, intent, sentiment, severity, ents, quote, review,
         source, issue) in db.execute(query):
        done = status == "completed"
        yield (rid, row_num, text, rating, likes, version, stamp, stamp[:7], sha, status, reason,
               topic if done else None, intent if done else None, sentiment if done else None, severity if done else None,
               ents if done else None, quote if done else None, bool(review) if done else None,
               source if done and source != rid else None, issue if done else None)


def publish(run_dir, database_url, golden_report=None, full_corpus_run=None):
    import psycopg  # imported here so the rest of the pipeline does not need the Postgres driver

    run_dir = Path(run_dir)
    state = open_saved_state(run_dir)
    ingestion = read_json(run_dir / "ingestion_report.json")
    issues = {i["issue_id"]: i for i in read_json(run_dir / "issues.json")["issues"]}
    aggregates = read_csv(run_dir / "aggregates.csv")
    label_config = state.execute("SELECT value FROM meta WHERE key = 'label_config'").fetchone()[0]

    documents = {"ingestion_report": ingestion, "rank_report": read_json(run_dir / "rank_report.json"),
                 "run_summary": read_json(run_dir / "run_summary.json"), "topic_rollup": read_csv(run_dir / "topic_rollup.csv")}
    if (run_dir / "verify_report.json").exists():
        documents["verify_report"] = read_json(run_dir / "verify_report.json")
    if golden_report and Path(golden_report).exists():
        documents["golden_report"] = read_json(golden_report)
    if full_corpus_run and (Path(full_corpus_run) / "ingestion_report.json").exists():
        # The profile of the whole source file, which is ingested in full whatever subset this run classifies.
        documents["full_corpus_ingestion"] = read_json(Path(full_corpus_run) / "ingestion_report.json")
    calls = [dict(zip(("role", "model", "attempts", "failed", "input_tokens", "output_tokens", "cost_usd"), row)) for row in state.execute(
        "SELECT role, model, COUNT(*), SUM(outcome = 'failed'), SUM(input_tokens), SUM(output_tokens), ROUND(SUM(cost_usd), 6) "
        "FROM calls GROUP BY role, model ORDER BY role, model")]
    documents["model_calls"] = {"by_role": calls, "total_cost_usd": round(sum(c["cost_usd"] for c in calls), 6)}

    memo_ready = (run_dir / "memo.md").exists() and read_json(run_dir / "memo_check.json").get("valid")
    if memo_ready:
        memo_input, memo_check = read_json(run_dir / "memo_input.json"), read_json(run_dir / "memo_check.json")
        documents["priority_areas"] = memo_input["model_input"]["priority_areas"]
        documents["memo_facts"] = memo_input["facts"]
        evidence = {e["review_id"]: e for e in memo_input["model_input"]["evidence"]}

    with psycopg.connect(database_url) as pg, pg.cursor() as cur:  # one transaction: readers never see a half-loaded run
        cur.execute(SCHEMA.read_text(encoding="utf-8"))
        cur.execute("INSERT INTO published_run (run_id, label_config, source_file, source_sha256, source_rows) VALUES (%s, %s, %s, %s, %s)",
                    (run_dir.name, label_config, ingestion["input"]["file"], ingestion["input"]["sha256"], ingestion["accounting"]["source_rows"]))
        with cur.copy(f"COPY reviews ({', '.join(REVIEW_COLUMNS)}) FROM STDIN") as copy:
            count = 0
            for row in review_rows(state):
                copy.write_row(row)
                count += 1
        for a in aggregates:
            i = issues[a["issue_id"]]
            cur.execute("INSERT INTO issues VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (a["issue_id"], i["topic"], i["aspect"], i["title"], i["description"], i["named_by"], a["rank"], a["complaint_count"],
                         a["severity_sum"], a["mean_severity"], a["priority_score"], a["cancellation_count"], a["needs_review_count"],
                         *(a[f"severity_{k}"] for k in range(1, 6))))
        # Monthly complaint counts per issue are computed in the database from the rows just loaded.
        cur.execute("INSERT INTO issue_months SELECT issue_id, review_month, COUNT(*), SUM(severity) FROM reviews "
                    "WHERE issue_id IS NOT NULL GROUP BY issue_id, review_month")
        if memo_ready:
            cur.execute("INSERT INTO memo (recommended_priority, markdown, memo_config, checked) VALUES (%s, %s, %s, %s)",
                        (memo_check["recommended_priority"], (run_dir / "memo.md").read_text(encoding="utf-8"), memo_check["memo_config"],
                         json.dumps(memo_check)))
            for c in read_csv(run_dir / "claims.csv"):
                cur.execute("INSERT INTO claims VALUES (%s, %s, %s, %s)", (c["claim_id"], c["issue_id"], c["metric"], c["value"]))
            for rid in memo_check["cited_reviews"]:
                e = evidence[rid]
                cur.execute("INSERT INTO memo_citations VALUES (%s, %s, %s, %s)", (rid, e["issue_id"], e["severity"], e["quote"]))
        for key, body in documents.items():
            cur.execute("INSERT INTO documents VALUES (%s, %s)", (key, json.dumps(body, ensure_ascii=False)))
        # Read back what the dashboard will see, and compare with the saved files before committing.
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'completed'), COUNT(issue_id) FROM reviews")
        loaded, completed, grouped = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM issues i JOIN (SELECT issue_id, COUNT(*) n, SUM(severity) s FROM reviews WHERE issue_id IS NOT NULL "
                    "GROUP BY issue_id) r USING (issue_id) WHERE r.n = i.complaint_count AND r.s = i.severity_sum")
        consistent = cur.fetchone()[0]
        if loaded != count or consistent != len(aggregates):
            raise RuntimeError(f"Loaded data does not match the saved ranking ({consistent} of {len(aggregates)} issues agree); nothing was published.")
    state.close()
    return {"run": run_dir.name, "reviews": loaded, "completed": completed, "grouped_complaints": grouped, "issues": len(aggregates),
            "issues_matching_saved_ranking": consistent, "memo": bool(memo_ready), "documents": sorted(documents)}


def main_publish(args):
    load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set. Add your Postgres connection string to .env (see .env.example).")
    try:
        result = publish(args.runs_dir / args.run_id, url, args.golden_report, args.runs_dir / args.full_corpus_run)
    except Exception as e:  # never echo the connection string, which drivers sometimes include in messages
        raise SystemExit("Publish failed: " + str(e).replace(url, "<DATABASE_URL>")) from None
    print(json.dumps(result, indent=1))

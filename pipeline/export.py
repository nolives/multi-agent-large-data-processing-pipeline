"""Write the run's saved handoff files from the state store: one record per source review ID, and issue membership."""

import csv
import gzip
import io
import json

from .common import canonical, write_text_atomic

ENRICHED = "enriched.jsonl.gz"
MEMBERSHIP = "membership.csv"


def export_records(run_dir, db):
    """enriched.jsonl.gz: every source ID once, in source order, with its true status."""
    path = run_dir / ENRICHED
    tmp = path.with_name(path.name + ".tmp")
    counts = {}
    query = ("SELECT r.review_id, r.source_sha256, r.status, r.reason, e.source_review_id, e.topic, e.intent, e.sentiment, e.severity, "
             "e.entities, e.evidence_quote, e.needs_review, e.label_config FROM reviews r "
             "LEFT JOIN enrichments e ON e.text_sha256 = r.text_sha256 ORDER BY r.row_num")
    # mtime=0 keeps the compressed file byte-identical across reruns on unchanged results.
    with gzip.GzipFile(tmp, "wb", mtime=0) as f:
        for rid, sha, status, reason, source, topic, intent, sentiment, severity, ents, quote, review, config in db.execute(query):
            record = {"review_id": rid, "source_sha256": sha, "status": status}
            if status == "completed":
                record.update(topic=topic, intent=intent, sentiment=sentiment, severity=severity, entities=json.loads(ents),
                              evidence_quote=quote, needs_review=bool(review), label_config=config)
                if source != rid:
                    record["cache_source_id"] = source  # exact-text reuse of a result with its own model-call evidence
            elif status == "quarantined":
                record["reason"] = reason
            counts[status] = counts.get(status, 0) + 1
            f.write((canonical(record) + "\n").encode("utf-8"))
    tmp.replace(path)
    return counts


def export_membership(run_dir, db):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["issue_id", "review_id"])
    writer.writerows(db.execute("SELECT m.issue_id, m.review_id FROM memberships m JOIN reviews r ON r.review_id = m.review_id "
                                "ORDER BY m.issue_id, r.row_num"))
    write_text_atomic(run_dir / MEMBERSHIP, buffer.getvalue())

"""Stage 5, rank. Recompute the baseline ranking from saved files only: no model, no network, no state store.

    python3 -m pipeline rank --run-id <run>

priority(issue) = complaint_count x mean_severity, which is exactly severity_sum. Completed complaint and
cancellation records count once per issue. Order: descending score, then ascending issue ID.
"""

import csv
import gzip
import io
import json
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .common import write_json, write_text_atomic
from .export import ENRICHED, MEMBERSHIP
from .labels import COMPLAINT_INTENTS


def mean_string(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def read_records(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_csv(path, header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    write_text_atomic(path, buffer.getvalue())


def rank(records_path, membership_path, out_dir):
    out_dir = Path(out_dir)
    complaints = {r["review_id"]: r for r in read_records(records_path)
                  if r["status"] == "completed" and r["intent"] in COMPLAINT_INTENTS}
    members, seen, problems = defaultdict(list), set(), Counter()
    with Path(membership_path).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            pair = (row["issue_id"], row["review_id"])
            if pair in seen:
                problems["duplicate_membership"] += 1
            elif row["review_id"] not in complaints:
                problems["member_is_not_a_completed_complaint"] += 1
            else:
                seen.add(pair)
                members[row["issue_id"]].append(complaints[row["review_id"]])
    grouped = {rid for _, rid in seen}
    problems["ungrouped_complaints"] = len(set(complaints) - grouped)
    problems["reviews_in_several_issues"] = len(seen) - len(grouped)

    rows = []
    for issue_id, recs in members.items():
        total = sum(r["severity"] for r in recs)
        levels = Counter(r["severity"] for r in recs)
        rows.append({"issue_id": issue_id, "complaint_count": len(recs), "severity_sum": total, "mean_severity": mean_string(total, len(recs)),
                     "priority_score": total, "cancellation_count": sum(r["intent"] == "cancellation" for r in recs),
                     "needs_review_count": sum(r["needs_review"] for r in recs), **{f"severity_{k}": levels[k] for k in range(1, 6)}})
    rows.sort(key=lambda r: (-r["priority_score"], r["issue_id"]))
    for position, row in enumerate(rows, 1):
        row["rank"] = position

    base = ("rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score")
    extra = ("cancellation_count", "needs_review_count", *(f"severity_{k}" for k in range(1, 6)))
    write_csv(out_dir / "ranking.csv", base, ([r[c] for c in base] for r in rows))
    write_csv(out_dir / "aggregates.csv", (*base, *extra), ([r[c] for c in (*base, *extra)] for r in rows))

    topics = defaultdict(lambda: [0, 0])
    for r in complaints.values():
        if r["review_id"] in grouped:
            topics[r["topic"]][0] += 1
            topics[r["topic"]][1] += r["severity"]
    topic_rows = sorted(((t, n, s, mean_string(s, n), s) for t, (n, s) in topics.items()), key=lambda r: (-r[4], r[0]))
    write_csv(out_dir / "topic_rollup.csv", ("topic", "complaint_count", "severity_sum", "mean_severity", "priority_score"), topic_rows)

    report = {"issues": len(rows), "complaint_records": len(complaints), "grouped_complaint_records": len(grouped),
              "problems": {k: v for k, v in problems.items() if v}, "formula": "priority_score = complaint_count x mean_severity = severity_sum",
              "order": "descending priority_score, then ascending issue_id", "inputs": [Path(records_path).name, Path(membership_path).name]}
    write_json(out_dir / "rank_report.json", report)
    return report, rows


def rank_run(run_dir):
    return rank(Path(run_dir) / ENRICHED, Path(run_dir) / MEMBERSHIP, run_dir)

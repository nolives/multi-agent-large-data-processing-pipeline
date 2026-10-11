"""Write the standardized grading/ folder from a finished run's saved outputs. No model calls.

    python3 -m pipeline export-grading --run-id final_100k --analysis data/final_100k.csv

Follows data/GRADING_CONTRACT.md. Everything is copied or reformatted from files and state the run already saved.
The call log's enrichment phases are expressed relative to one chosen interruption (see grading/README.md).
"""

import csv
import gzip
import json
import shutil
import sqlite3
from pathlib import Path

from .common import canonical, file_sha, write_json, write_text_atomic
from .export import ENRICHED

VERSION = "a5-audit-v1"


def gz_lines(path, rows):
    tmp = path.with_name(path.name + ".tmp")
    count = 0
    with gzip.GzipFile(tmp, "wb", mtime=0) as f:  # mtime=0 keeps the file byte-identical across re-exports
        for row in rows:
            f.write((canonical(row) + "\n").encode("utf-8"))
            count += 1
    tmp.replace(path)
    return count


def export_grading(run_dir, analysis_csv, full_run_dir, out, before_checkpoint=None):
    run_dir, out = Path(run_dir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(run_dir / "state.db")
    label_config = db.execute("SELECT value FROM meta WHERE key = 'label_config'").fetchone()[0]
    with Path(analysis_csv).open(encoding="utf-8-sig", newline="") as f:
        analysis_count = sum(1 for _ in csv.DictReader(f, strict=True))
    full_profile = json.loads((Path(full_run_dir) / "ingestion_report.json").read_text(encoding="utf-8"))["profile"]

    write_json(out / "run.json", {
        "version": VERSION, "analysis_count": analysis_count, "analysis_sha256": file_sha(analysis_csv),
        "classification_input_fields": ["review_text"], "allow_multi_issue": False,
        # Extra context; the checker reads only the keys above.
        "run_id": run_dir.name, "analysis_file": Path(analysis_csv).name, "label_config": label_config,
        "full_corpus_rows": full_profile["counts"]["records"],
        "scope": "The full source file was ingested and profiled (ingestion.json). Classification covers the analysis file: "
                 "100,000 reviews chosen by the course's sampling rule plus the 13 empty-text reviews.",
    })
    write_json(out / "ingestion.json", full_profile)  # identical to `check_submission.py profile` on the full file

    # Final records: completed or quarantined, one per source ID. A row still pending would be exported as quarantined.
    pending = 0
    def records():
        nonlocal pending
        with gzip.open(run_dir / ENRICHED, "rt", encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                if record["status"] == "pending":
                    pending += 1
                    record.update(status="quarantined", reason="not_classified_pending")
                yield record
    record_count = gz_lines(out / "records.jsonl.gz", records())
    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        shutil.copyfile(run_dir / name, out / name)

    # The interruption used for the before/after evidence. Calls up to and including its session are "initial";
    # calls in later sessions are "resume".
    checkpoints = sorted((run_dir / "checkpoints").glob("*.json"))
    before_path = Path(before_checkpoint) if before_checkpoint else next(p for p in checkpoints if "interrupted" in p.name)
    before, after = json.loads(before_path.read_text(encoding="utf-8")), json.loads(checkpoints[-1].read_text(encoding="utf-8"))
    boundary = before["session"]
    write_json(out / "checkpoint_before.json", {"completed_ids": before["completed_ids"], "completed_count": before["completed_count"],
                                                "saved_at": before["saved_at"], "session": before["session"], "source_file": before_path.name})
    write_json(out / "checkpoint_after.json", {"completed_ids": after["completed_ids"], "completed_count": after["completed_count"],
                                               "saved_at": after["saved_at"], "session": after["session"], "source_file": checkpoints[-1].name})

    def calls():
        query = ("SELECT request_id, role, review_ids, model, phase, outcome, label_config, input_tokens, output_tokens, cache_read_tokens, "
                 "cache_write_tokens, session, provider, attempt, error, status_code, usage_unknown, cost_usd, started_at, duration_ms FROM calls "
                 "ORDER BY started_at, request_id")
        for (request_id, role, ids, model, phase, outcome, config, inp, outp, cache_read, cache_write, session, provider, attempt, error,
             status, unknown, cost, started, duration) in db.execute(query):
            yield {"request_id": request_id, "role": role, "review_ids": json.loads(ids), "model": model,
                   "phase": ("initial" if session <= boundary else "resume") if role == "enrich" else phase,
                   "outcome": outcome, "label_config": config,
                   # Billed input in all categories; the cache columns break it down (both are zero in this run).
                   "input_tokens": inp + cache_read + cache_write, "output_tokens": outp,
                   "session": session, "provider": provider, "attempt": attempt, "error": error, "status_code": status,
                   "usage_unknown": bool(unknown), "cost_usd": round(cost, 8), "started_at": started, "duration_ms": duration}
    call_count = gz_lines(out / "calls.jsonl.gz", calls())

    sessions = [dict(zip(("session", "role", "calls", "failed", "first_call", "last_call", "cost_usd"), row)) for row in db.execute(
        "SELECT session, role, COUNT(*), SUM(outcome = 'failed'), MIN(started_at), MAX(started_at), ROUND(SUM(cost_usd), 6) FROM calls GROUP BY 1, 2 ORDER BY 1, 2")]
    db.close()
    summary = {"records": record_count, "pending_exported_as_quarantined": pending, "calls": call_count, "interruption_session": boundary,
               "checkpoint_before": before["completed_count"], "checkpoint_after": after["completed_count"], "sessions": sessions}
    readme = f"""# Grading export

Written by `python3 -m pipeline export-grading` from the saved outputs of run `{run_dir.name}`. No model was called to produce it.
The format follows `data/GRADING_CONTRACT.md`.

| File | Contents |
|---|---|
| `run.json` | Version, the analysis file's row count ({analysis_count:,}) and SHA-256, and the declared scope |
| `ingestion.json` | Profile of the full {full_profile['counts']['records']:,}-row source file, identical to `check_submission.py profile` |
| `records.jsonl.gz` | One final record per analysis review ID: {record_count:,} records |
| `membership.csv` | `issue_id,review_id`, one issue per complaint or cancellation record |
| `ranking.csv` | The baseline ranking |
| `claims.csv` | Every issue-level number the memo cites |
| `calls.jsonl.gz` | Every attempted model call: {call_count:,} entries |
| `checkpoint_before.json`, `checkpoint_after.json` | Completed IDs before the interruption and at the end of the run |

## Scope

The full source file was ingested and profiled. Classification covers `{Path(analysis_csv).name}`: the 100,000 reviews with the lowest
SHA-256(seed:review_id) values, which is the course's own sampling rule and includes the golden 50 and all development files, plus the
13 empty-text reviews, which are quarantined as `empty_review_text`. Build the checker's reference with `--analysis {analysis_csv}`.

## Interruption and resume

Enrichment ran in {max(s['session'] for s in sessions)} sessions. The before-and-after evidence uses the interruption at the end of session {boundary}:
`checkpoint_before.json` is the checkpoint written when that session was stopped ({before['completed_count']:,} completed reviews), and
`checkpoint_after.json` is the checkpoint at the end of the run ({after['completed_count']:,}). In `calls.jsonl.gz`, enrichment calls made in
sessions 1 to {boundary} have phase `initial` and calls made after it have phase `resume`. Each call also carries its original `session` number.
No review completed before the interruption was sent again afterwards.

Earlier stops are part of the same record: see the `session` field, `runs/{run_dir.name}/run_log.jsonl` and the README's failure case.

## Self-check

```sh
python3 data/check_submission.py reference --full data/spotify_reviews_18months.csv --analysis {analysis_csv} --out local-reference.json
python3 data/check_submission.py check --reference local-reference.json --submission grading --out self-check.json
```
"""
    write_text_atomic(out / "README.md", readme)
    return summary

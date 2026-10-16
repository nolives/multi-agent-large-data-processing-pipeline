# Grading export

Written by `python3 -m pipeline export-grading` from the saved outputs of run `final_100k`. No model was called to produce it.
The format follows `data/GRADING_CONTRACT.md`.

| File | Contents |
|---|---|
| `run.json` | Version, the analysis file's row count (100,013) and SHA-256, and the declared scope |
| `ingestion.json` | Profile of the full 660,622-row source file, identical to `check_submission.py profile` |
| `records.jsonl.gz` | One final record per analysis review ID: 100,013 records |
| `membership.csv` | `issue_id,review_id`, one issue per complaint or cancellation record |
| `ranking.csv` | The baseline ranking |
| `claims.csv` | Every issue-level number the memo cites |
| `calls.jsonl.gz` | Every attempted model call: 78,302 entries |
| `checkpoint_before.json`, `checkpoint_after.json` | Completed IDs before the interruption and at the end of the run |

## Scope

The full source file was ingested and profiled. Classification covers `final_100k.csv`: the 100,000 reviews with the lowest
SHA-256(seed:review_id) values, which is the course's own sampling rule and includes the golden 50 and all development files, plus the
13 empty-text reviews, which are quarantined as `empty_review_text`. The updated assignment brief accepts a run of "at least 100,000"
reviews, and the instructor confirmed a 100,000-review run by email on October 11, 2026. Build the checker's reference with
`--analysis data/final_100k.csv`; a reference built from the full file expects 660,622 records and will report a mismatch.

## Interruption and resume

Enrichment ran in 4 sessions. The before-and-after evidence uses the interruption at the end of session 3:
`checkpoint_before.json` is the checkpoint written when that session was stopped (27,305 completed reviews), and
`checkpoint_after.json` is the checkpoint at the end of the run (100,000). In `calls.jsonl.gz`, enrichment calls made in
sessions 1 to 3 have phase `initial` and calls made after it have phase `resume`. Each call also carries its original `session` number.
No review completed before the interruption was sent again afterwards.

Earlier stops are part of the same record: see the `session` field, `runs/final_100k/run_log.jsonl` and the README's failure case.

## Self-check

```sh
python3 data/check_submission.py reference --full data/spotify_reviews_18months.csv --analysis data/final_100k.csv --out local-reference.json
python3 data/check_submission.py check --reference local-reference.json --submission grading --out self-check.json
```

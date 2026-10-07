"""Copy a pilot run's saved measurements into cost/ so the calculator can replay them offline. No model calls.

Writes pilot_records.jsonl (one status per pilot ID), pilot_calls.jsonl (every attempted call, with run and
request IDs) and pilot_measurements.json (clock times, counts and settings). Nothing here is estimated.
"""

import csv
import gzip
import json
import sqlite3
from pathlib import Path

from .common import file_sha, write_json, write_jsonl
from .export import ENRICHED

CALL_FIELDS = ("request_id", "session", "role", "phase", "provider", "model", "label_config", "review_ids", "attempt", "outcome",
               "error", "status_code", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "usage_unknown",
               "cost_usd", "started_at", "duration_ms", "provider_request_id")


def read_run(run_dir, run_type_for):
    run_dir = Path(run_dir)
    db = sqlite3.connect(run_dir / "state.db")
    if run_type_for is None:
        # A session that made model calls is part of the cold measurement; a session that made none is a warm rerun.
        active = {row[0] for row in db.execute("SELECT DISTINCT session FROM calls")}
        run_type_for = lambda session: "cold" if session in active else "warm"
    calls = []
    for row in db.execute(f"SELECT {', '.join(CALL_FIELDS)} FROM calls ORDER BY started_at, request_id"):
        call = dict(zip(CALL_FIELDS, row))
        call["review_ids"] = json.loads(call["review_ids"])
        call["usage_unknown"] = bool(call["usage_unknown"])
        call["logged_cost_usd"] = call.pop("cost_usd")
        calls.append({"run": run_dir.name, "run_type": run_type_for(call["session"]), **call})
    texts = db.execute("SELECT COUNT(DISTINCT text_sha256) FROM reviews WHERE text_sha256 IS NOT NULL").fetchone()[0]
    statuses = dict(db.execute("SELECT status, COUNT(*) FROM reviews GROUP BY status"))
    verified = db.execute("SELECT COUNT(*) FROM verifications").fetchone()[0] if db.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'verifications'").fetchone() else 0
    issues = db.execute("SELECT COUNT(*) FROM issue_names").fetchone()[0] if db.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'issue_names'").fetchone() else 0
    db.close()
    sessions = []
    for path in sorted(run_dir.glob("run_summary_session_*.json")):
        s = json.loads(path.read_text(encoding="utf-8"))
        mine = [c for c in calls if c["session"] == s["session"]]
        sessions.append({
            "run": run_dir.name, "session": s["session"], "run_type": run_type_for(s["session"]), "workers": s["workers"],
            "spend_cap_usd": s["spend_cap_usd"], "wall_seconds": s["wall_seconds"], "stage_seconds": s["stage_seconds"],
            "summed_call_seconds": round(sum(c["duration_ms"] for c in mine) / 1000, 3),
            "attempts": len(mine), "failed_attempts": sum(c["outcome"] == "failed" for c in mine),
            "rate_limited_attempts": sum(c["status_code"] in (429, 529) for c in mine),
            "texts_enriched": sum(c["role"] == "enrich" and c["outcome"] == "succeeded" for c in mine),
            "new_enrichment_calls": sum(c["role"] == "enrich" for c in mine),
            "downstream_calls": sum(c["role"] != "enrich" for c in mine),
            "records_at_end": statuses, "unique_texts": texts, "texts_verified_at_end": verified, "issues_named_at_end": issues,
            "settings": s.get("settings"), "models_configured": s["models"]})
    return calls, sessions


def export_pilot(run, failed_runs, input_csv, full_run, out, parser):
    out = Path(out)
    calls, sessions = read_run(run, None)
    for failed in failed_runs:
        more_calls, more_sessions = read_run(failed, lambda session: "cold_failed_attempt")
        calls += more_calls
        sessions += more_sessions
    with gzip.open(Path(run) / ENRICHED, "rt", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    with Path(input_csv).open(encoding="utf-8-sig", newline="") as f:
        input_ids = [row["review_id"] for row in csv.DictReader(f)]
    # Settings were not saved by the first pilot sessions; they ran with the command's defaults, read here from the parser.
    defaults = vars(parser.parse_args(["run", "--input", str(input_csv), "--max-spend-usd", "0"]))
    fallback = {k: defaults[k] for k in ("max_rps", "save_every", "verify_sample", "verify_batch", "seed", "memo_effort")}
    for s in sessions:
        s["settings"] = s["settings"] or {**fallback, "source": "command defaults (not overridden for this session)"}
    configs = {c["role"]: c["label_config"] for c in calls if c["run"] == Path(run).name}
    settings = sessions[0]["settings"]
    measurements = {
        "input": {"file": Path(input_csv).name, "sha256": file_sha(input_csv), "rows": len(input_ids),
                  "every_input_id_has_a_record": sorted(input_ids) == sorted(r["review_id"] for r in records)},
        "sessions": sessions,
        "stages": {
            "ingest": {"provider": "local", "model": "none (code)"},
            "enrich": {"provider": "typesafe", "effort": "not applicable: Jev has no effort or thinking setting", "label_config": configs.get("enrich"),
                       "reviews_per_request": 1, "saved_batch_texts": settings["save_every"], "max_requests_per_second": settings["max_rps"]},
            "verify": {"provider": "anthropic", "effort": "not applicable: Haiku 4.5 without extended thinking", "label_config": configs.get("verify"),
                       "reviews_per_request": settings["verify_batch"], "declared_sample_texts": settings["verify_sample"],
                       "sample_seed": settings["seed"], "output_token_cap": 4000},
            "group": {"provider": "anthropic", "effort": "not applicable: Haiku 4.5 without extended thinking", "label_config": configs.get("group"),
                      "issues_per_request": 20, "output_token_cap": 4000},
            "rank": {"provider": "local", "model": "none (code)"},
            "memo": {"provider": "anthropic", "effort": settings["memo_effort"], "label_config": configs.get("memo"),
                     "output_token_cap": 16000, "note": "Opus 5.5 always thinks; thinking tokens are billed inside output tokens"},
        },
        "provider_prompt_cache": "No cache reads or writes occurred: cache_read_tokens and cache_write_tokens are 0 on every call.",
    }
    if full_run:
        manifest = json.loads((Path(full_run) / "data_manifest.json").read_text(encoding="utf-8"))
        measurements["full_corpus_ingest"] = {"seconds": manifest["ingest_seconds"], "rows": 660622, "source": f"{Path(full_run).name}/data_manifest.json"}
    write_jsonl(out / "pilot_records.jsonl", records)
    write_jsonl(out / "pilot_calls.jsonl", calls)
    write_json(out / "pilot_measurements.json", measurements)
    return {"records": len(records), "calls": len(calls), "sessions": [(s["run"], s["session"], s["run_type"], s["attempts"]) for s in sessions]}

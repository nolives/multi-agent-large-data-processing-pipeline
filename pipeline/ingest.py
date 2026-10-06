"""Stage 1, prepare: read every row, preserve IDs and source values, profile quality,
find exact duplicate texts and queue pending work. No model calls.

Outputs in the run directory:
  state.db               SQLite store of every source row, its hashes and its status
  ingestion_report.json  deterministic full-file profile, accounting and expectation checks
  quarantine.jsonl       rows that will not be classified, with reasons
  data_manifest.json     input identity, code version and output checksums
"""

import hashlib
import platform
import sqlite3
import subprocess
import time
from array import array
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .common import FIELDS, csv_rows, file_sha, row_sha, text_sha, write_json, write_jsonl

EMPTY_REASON = "empty_review_text"
BATCH = 10_000

# Figures stated in the assignment brief that the course manifest.json does not carry.
BRIEF_EXPECTED = {
    "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6": {
        "nonempty_reviews": 660_609,
        "distinct_nonempty_texts": 484_189,
    }
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews (
    review_id        TEXT PRIMARY KEY,
    row_num          INTEGER NOT NULL,
    review_text      TEXT NOT NULL,
    review_rating    TEXT NOT NULL,
    review_likes     TEXT NOT NULL,
    app_version      TEXT NOT NULL,
    review_timestamp TEXT NOT NULL,
    source_sha256    TEXT NOT NULL,
    text_sha256      TEXT,
    status           TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'quarantined')),
    reason           TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS reviews_text ON reviews (text_sha256);
CREATE INDEX IF NOT EXISTS reviews_status ON reviews (status);
CREATE TABLE IF NOT EXISTS texts (
    text_sha256     TEXT PRIMARY KEY,
    first_review_id TEXT NOT NULL,
    n_reviews       INTEGER NOT NULL
);
"""


def open_state(run_dir):
    db = sqlite3.connect(Path(run_dir) / "state.db")
    db.executescript(SCHEMA)
    return db


def percentile(sorted_values, p):
    return sorted_values[min(len(sorted_values) - 1, int(p * len(sorted_values)))] if sorted_values else None


def code_version():
    def git(*args):
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                                  cwd=Path(__file__).parent).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    status = git("status", "--porcelain", "--", ".")
    return {"git_commit": git("rev-parse", "HEAD"), "uncommitted_changes": bool(status) if status is not None else None}


def expectation_checks(file_hash, size, profile, accounting, course_manifest):
    """Compare the measured profile with the course manifest and brief, when the input is a known file."""
    checks = []
    def check(name, expected, actual):
        checks.append({"check": name, "expected": expected, "actual": actual, "ok": expected == actual})
    known = None
    for name, entry in (course_manifest or {}).get("files", {}).items():
        if entry.get("sha256") == file_hash:
            known = name
            check("file_bytes", entry.get("bytes"), size)
    # Only the full extract has a published profile; the samples are identified by checksum alone.
    if known and known == (course_manifest.get("assignment_scope") or {}).get("final_input"):
        declared = course_manifest.get("profile", {})
        for key in ("records", "duplicate_review_ids", "empty_review_text", "missing_app_version"):
            check(key, declared.get(key), profile["counts"][key])
        check("reviews_by_month", course_manifest.get("reviews_by_month"), dict(sorted(profile["reviews_by_month"].items())))
        check("reviews_by_rating", course_manifest.get("reviews_by_rating"), dict(sorted(profile["reviews_by_rating"].items())))
        window = course_manifest.get("window", {})
        check("first_review", window.get("first_review"), profile["first_review"])
        check("last_review", window.get("last_review"), profile["last_review"])
    for key, expected in BRIEF_EXPECTED.get(file_hash, {}).items():
        check(key, expected, accounting[key])
    return known, checks


def ingest(input_path, run_dir, course_manifest=None, run_id=None):
    started = time.monotonic()
    input_path, run_dir = Path(input_path), Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or run_dir.name
    file_hash, size = file_sha(input_path), input_path.stat().st_size

    db = open_state(run_dir)
    stored = db.execute("SELECT value FROM meta WHERE key = 'input_sha256'").fetchone()
    if stored and stored[0] != file_hash:
        raise SystemExit(f"{run_dir} already holds a different input ({stored[0][:12]}…). Use a new --run-id.")

    ids, months, ratings = set(), Counter(), Counter()
    counts = Counter(records=0, duplicate_review_ids=0, empty_review_text=0, missing_app_version=0)
    content = hashlib.sha256()
    first = last = None

    texts = {}  # text_sha256 -> [first_review_id, n_reviews, first row_num]
    lengths = array("I")
    quality = Counter()
    versions = set()
    max_likes = 0
    rejected, batch = [], []
    insert = ("INSERT OR IGNORE INTO reviews (review_id, row_num, review_text, review_rating, review_likes, app_version,"
              " review_timestamp, source_sha256, text_sha256, status, reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)")

    for row_num, row in enumerate(csv_rows(input_path), 1):
        digest = row_sha(row)
        rid, text, stamp = row["review_id"], row["review_text"], row["review_timestamp"]

        # This block mirrors profile() in data/check_submission.py so grading/ingestion.json matches exactly.
        content.update(bytes.fromhex(digest))
        counts["records"] += 1
        duplicate = rid in ids
        counts["duplicate_review_ids"] += duplicate
        ids.add(rid)
        empty = not text.strip()
        counts["empty_review_text"] += empty
        counts["missing_app_version"] += not row["app_version"].strip()
        months[stamp[:7]] += 1
        ratings[row["review_rating"]] += 1
        first = min(first, stamp) if first else stamp
        last = max(last, stamp) if last else stamp

        quality["invalid_rating"] += row["review_rating"] not in ("1", "2", "3", "4", "5")
        try:
            datetime.fromisoformat(stamp)
        except ValueError:
            quality["unparseable_timestamp"] += 1
        try:
            likes = int(row["review_likes"])
            quality["reviews_with_likes"] += likes > 0
            max_likes = max(max_likes, likes)
        except ValueError:
            quality["invalid_likes"] += 1
        if row["app_version"].strip():
            versions.add(row["app_version"])

        if duplicate:
            # A repeated ID cannot be a second record; keep the first occurrence and report this one.
            rejected.append({"row_num": row_num, "review_id": rid, "source_sha256": digest, "reason": "duplicate_review_id"})
            continue

        text_hash = None
        if not empty:
            text_hash = text_sha(text)
            entry = texts.get(text_hash)
            if entry:
                entry[1] += 1
            else:
                texts[text_hash] = [rid, 1, row_num]
            lengths.append(len(text))
            quality["multiline_text"] += "\n" in text or "\r" in text
            quality["text_without_ascii_letters"] += not any("a" <= c <= "z" or "A" <= c <= "Z" for c in text)

        batch.append((rid, row_num, text, row["review_rating"], row["review_likes"], row["app_version"], stamp, digest,
                      text_hash, "quarantined" if empty else "pending", EMPTY_REASON if empty else None))
        if len(batch) >= BATCH:
            db.executemany(insert, batch)
            batch.clear()

    db.executemany(insert, batch)
    db.executemany("INSERT OR IGNORE INTO texts (text_sha256, first_review_id, n_reviews) VALUES (?,?,?)",
                   ((h, e[0], e[1]) for h, e in texts.items()))
    db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('input_sha256', ?)", (file_hash,))
    # One transaction: an interrupted ingest leaves no partial state, and a rerun never resets later statuses.
    db.commit()

    profile = {"file_sha256": file_hash, "parsed_rows_sha256": content.hexdigest(), "counts": dict(counts),
               "reviews_by_month": dict(months), "reviews_by_rating": dict(ratings), "first_review": first, "last_review": last}

    status_counts = dict(db.execute("SELECT status, COUNT(*) FROM reviews GROUP BY status"))
    quarantined = [{"review_id": rid, "source_sha256": digest, "status": "quarantined", "reason": reason, "attempts": attempts}
                   for rid, digest, reason, attempts in db.execute(
                       "SELECT review_id, source_sha256, reason, attempts FROM reviews WHERE status = 'quarantined' ORDER BY row_num")]
    pending_texts = db.execute("SELECT COUNT(DISTINCT text_sha256) FROM reviews WHERE status = 'pending'").fetchone()[0]
    db.close()

    nonempty = len(lengths)
    accounting = {
        "source_rows": counts["records"],
        "stored_review_ids": len(ids),
        "rejected_rows": len(rejected),
        "nonempty_reviews": nonempty,
        "distinct_nonempty_texts": len(texts),
        "texts_shared_by_several_reviews": sum(e[1] > 1 for e in texts.values()),
        "reviews_served_by_exact_text_reuse": nonempty - len(texts),
        "status_counts": status_counts,
        "quarantine_reasons": dict(Counter(q["reason"] for q in quarantined)),
        "pending_reviews": status_counts.get("pending", 0),
        "pending_distinct_texts": pending_texts,
        "accounted_for": sum(status_counts.values()) + len(rejected) == counts["records"],
    }
    ordered = sorted(lengths)
    most_repeated = sorted(texts.values(), key=lambda e: (-e[1], e[2]))[:10]
    quality_report = {
        **{key: quality[key] for key in ("invalid_rating", "unparseable_timestamp", "invalid_likes", "reviews_with_likes",
                                         "multiline_text", "text_without_ascii_letters")},
        "max_review_likes": max_likes,
        "distinct_app_versions": len(versions),
        "text_length_chars": {"total": sum(ordered), "min": ordered[0] if ordered else None,
                              "median": percentile(ordered, 0.5), "p90": percentile(ordered, 0.9),
                              "p99": percentile(ordered, 0.99), "max": ordered[-1] if ordered else None},
        "most_repeated_texts": [{"first_review_id": e[0], "n_reviews": e[1]} for e in most_repeated],
        "notes": ["text_without_ascii_letters is a rough signal for emoji-only or non-Latin-script text, not a language detector.",
                  "review_timestamp has no stated timezone; months are taken from the source string as written."],
    }
    known_file, checks = expectation_checks(file_hash, size, profile, accounting, course_manifest)

    report = {
        "run_id": run_id,
        "input": {"file": input_path.name, "bytes": size, "sha256": file_hash, "known_course_file": known_file},
        "profile": profile,  # identical to `check_submission.py profile`; exported unchanged as grading/ingestion.json
        "accounting": accounting,
        "quality": quality_report,
        "rejected_rows": rejected,
        "expectation_checks": checks,
        "all_expectations_met": all(c["ok"] for c in checks) if checks else None,
    }
    write_json(run_dir / "ingestion_report.json", report)
    write_jsonl(run_dir / "quarantine.jsonl", quarantined)
    write_json(run_dir / "data_manifest.json", {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": {"path": str(input_path), "bytes": size, "sha256": file_hash, "columns": list(FIELDS),
                  "known_course_file": known_file},
        "code": code_version(),
        "python": platform.python_version(),
        "outputs": {name: file_sha(run_dir / name) for name in ("ingestion_report.json", "quarantine.jsonl")},
        "state_store": "state.db (SQLite; tables reviews, texts, meta). Pending work: SELECT review_id FROM reviews WHERE status = 'pending'.",
        "ingest_seconds": round(time.monotonic() - started, 2),
    })
    return report

"""Shared helpers for every stage. Standard library only; no network or model calls."""

import csv
import hashlib
import json
import os
from pathlib import Path

FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def row_sha(row):
    # Must stay byte-identical to row_sha in data/check_submission.py: the six original
    # field strings, in order, with no trimming or Unicode normalization.
    return hashlib.sha256(canonical([row[k] for k in FIELDS]).encode("utf-8")).hexdigest()


def text_sha(text):
    # Exact-text identity for result reuse. Any difference, including whitespace, is a different text.
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def csv_rows(path):
    # Same parsing as the checker, so multiline review text and row hashes agree with it.
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("Missing or duplicate CSV headers")
        missing = [k for k in FIELDS if k not in reader.fieldnames]
        if missing:
            raise ValueError("Input CSV is missing required columns: " + ", ".join(missing))
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"Malformed CSV row near line {reader.line_num}")
            yield row


def write_text_atomic(path, text):
    # Write to a temporary file, then rename, so an interruption never leaves a half-written artifact.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_json(path, value):
    write_text_atomic(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")


def write_jsonl(path, rows):
    write_text_atomic(path, "".join(canonical(row) + "\n" for row in rows))


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(canonical(row) + "\n")


def load_env(path=".env"):
    # Minimal dotenv loader: KEY=value lines only. Existing environment variables win. Values are never logged.
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip())


def open_saved_state(run_dir):
    """Open a finished run's state.db for reading. It is not committed (it holds the whole run, over 100 MB), so a fresh
    checkout has none; stop with a clear message rather than let SQLite create an empty file."""
    import sqlite3
    path = Path(run_dir) / "state.db"
    if not path.exists():
        raise SystemExit(f"{path} is missing. This command reads the local state of the original run, which is not committed. "
                         "Its committed outputs are in the run directory and grading/; see the README's setup section.")
    return sqlite3.connect(path)

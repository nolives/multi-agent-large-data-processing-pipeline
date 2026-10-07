"""The run's SQLite state: one call log shared by every model role, and session numbering."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

CALL_COLUMNS = ("request_id", "session", "role", "phase", "provider", "model", "label_config", "review_ids", "attempt",
                "outcome", "error", "status_code", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
                "usage_unknown", "cost_usd", "started_at", "duration_ms", "provider_request_id")

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    request_id          TEXT PRIMARY KEY,
    session             INTEGER NOT NULL,
    role                TEXT NOT NULL,
    phase               TEXT NOT NULL,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    label_config        TEXT NOT NULL,
    review_ids          TEXT NOT NULL,
    attempt             INTEGER NOT NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('succeeded', 'failed')),
    error               TEXT,
    status_code         INTEGER,
    input_tokens        INTEGER NOT NULL,
    output_tokens       INTEGER NOT NULL,
    usage_unknown       INTEGER NOT NULL,
    cost_usd            REAL NOT NULL,
    started_at          TEXT NOT NULL,
    duration_ms         INTEGER NOT NULL,
    provider_request_id TEXT,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0
);
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def open_db(run_dir, extra_schema=""):
    db = sqlite3.connect(Path(run_dir) / "state.db")
    db.executescript(SCHEMA + extra_schema)
    return db


def next_session(db):
    """Sessions number each program invocation that made model calls; every stage of one invocation shares one."""
    return db.execute("SELECT COALESCE(MAX(session), 0) + 1 FROM calls").fetchone()[0]


def new_call(role, provider, model, label_config, review_ids, attempt, request_id):
    # input_tokens holds uncached input only; cache reads and writes are separate, mutually exclusive billing items.
    return {"request_id": request_id, "role": role, "provider": provider, "model": model, "label_config": label_config,
            "review_ids": list(review_ids), "attempt": attempt, "outcome": "failed", "error": None, "status_code": None,
            "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "usage_unknown": False,
            "cost_usd": 0.0, "started_at": utc_now(), "duration_ms": 0, "provider_request_id": None}


def insert_call(db, call, session, phase):
    row = {**call, "session": session, "phase": phase, "review_ids": json.dumps(call["review_ids"]),
           "usage_unknown": int(call["usage_unknown"])}
    db.execute(f"INSERT INTO calls ({', '.join(CALL_COLUMNS)}) VALUES ({', '.join('?' * len(CALL_COLUMNS))})",
               [row[c] for c in CALL_COLUMNS])


def phase_for(db, role, session):
    """A role's first session is "initial"; any later session of that role resumes from saved progress."""
    earlier = db.execute("SELECT COUNT(*) FROM calls WHERE role = ? AND session < ?", (role, session)).fetchone()[0]
    return "resume" if earlier else "initial"


def role_config(prompt_path, model, schema_version, effort=None):
    """Read a role prompt file ("version: <name>" on line one, instructions after) and derive its configuration ID.

    The ID names the model, its effort setting when one is sent, the prompt version with a content hash, and the schema.
    """
    import hashlib
    raw = Path(prompt_path).read_bytes()
    first, _, body = raw.decode("utf-8").partition("\n")
    if not first.startswith("version:"):
        raise ValueError(f"{prompt_path} must start with a 'version:' line")
    setting = f"@effort-{effort}" if effort else ""
    return body.strip(), f"{model}{setting}+{first.split(':', 1)[1].strip()}.{hashlib.sha256(raw).hexdigest()[:8]}+{schema_version}"

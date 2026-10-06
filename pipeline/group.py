"""Stage 4, group (role: group). Code assigns every complaint to one stable issue; a model only names the issues.

Issue membership is deterministic: issue_id = "<topic>.<aspect>", decided by the rules in labels/issues.json from the
record's topic and entity list. The naming model sees a bounded evidence pack (a few examples per issue), and its
accepted titles are saved so that ranking never needs a model.
"""

import json
from pathlib import Path

from .common import write_json
from .labels import COMPLAINT_INTENTS, SCHEMA_VERSION
from .store import insert_call, phase_for, role_config

ROLE = "group"
EXAMPLES_PER_ISSUE = 4
EXAMPLE_MAX_CHARS = 300
ISSUES_PER_REQUEST = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS memberships (review_id TEXT PRIMARY KEY, issue_id TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS memberships_issue ON memberships (issue_id);
CREATE TABLE IF NOT EXISTS issue_names (
    issue_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
    named_by TEXT NOT NULL, example_review_ids TEXT NOT NULL, request_id TEXT
);
"""

OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["issues"],
    "properties": {"issues": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["issue_id", "title", "description"],
        "properties": {"issue_id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}}}}},
}


def load_rules(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["version"], {topic: [(a["aspect"], set(a["entities"])) for a in aspects] for topic, aspects in data["topics"].items()}


def assign_issue(topic, entity_list, rules):
    found = set(entity_list)
    for aspect, names in rules.get(topic, ()):
        if found & names:
            return f"{topic}.{aspect}"
    return f"{topic}.general"


def build_membership(db, rules):
    """Rebuild issue membership for every completed complaint or cancellation record. No model involved."""
    db.executescript(SCHEMA)
    by_text = {sha: assign_issue(topic, json.loads(ents), rules) for sha, topic, ents in db.execute(
        f"SELECT text_sha256, topic, entities FROM enrichments WHERE intent IN ({','.join('?' * len(COMPLAINT_INTENTS))})", COMPLAINT_INTENTS)}
    db.execute("DELETE FROM memberships")
    db.executemany("INSERT INTO memberships (review_id, issue_id) VALUES (?, ?)",
                   ((rid, by_text[sha]) for rid, sha in db.execute("SELECT review_id, text_sha256 FROM reviews WHERE status = 'completed'")
                    if sha in by_text))
    db.commit()
    return dict(db.execute("SELECT issue_id, COUNT(*) FROM memberships GROUP BY issue_id"))


def evidence_pack(db, issue_ids):
    """A bounded set of example reviews per issue: distinct texts, most-liked first, each short enough to send whole."""
    pack = []
    for issue_id in issue_ids:
        rows = db.execute(
            "SELECT r.review_id, r.review_text, MIN(r.row_num) AS first_row FROM memberships m JOIN reviews r ON r.review_id = m.review_id "
            "WHERE m.issue_id = ? AND LENGTH(r.review_text) <= ? GROUP BY r.text_sha256 "
            "ORDER BY CAST(r.review_likes AS INTEGER) DESC, first_row LIMIT ?", (issue_id, EXAMPLE_MAX_CHARS, EXAMPLES_PER_ISSUE)).fetchall()
        topic, _, aspect = issue_id.partition(".")
        count = db.execute("SELECT COUNT(*) FROM memberships WHERE issue_id = ?", (issue_id,)).fetchone()[0]
        pack.append({"issue_id": issue_id, "topic": topic, "aspect": aspect, "complaint_reviews": count,
                     "examples": [{"review_id": rid, "text": text} for rid, text, _ in rows]})
    return pack


def group(run_dir, db, caller, *, rules_path, prompt_path, model, session):
    rules_version, rules = load_rules(rules_path)
    counts = build_membership(db, rules)
    system, config = role_config(prompt_path, model, f"{rules_version}+{SCHEMA_VERSION}")
    named = {row[0] for row in db.execute("SELECT issue_id FROM issue_names")}
    # An accepted name is kept: only issues seen for the first time are sent to the model.
    unnamed = sorted(set(counts) - named)
    phase = phase_for(db, ROLE, session)
    pack = evidence_pack(db, unnamed)
    stop_reason = None
    for start in range(0, len(pack), ISSUES_PER_REQUEST):
        batch = pack[start:start + ISSUES_PER_REQUEST]
        user = "Name each of these issue groups.\n\n" + json.dumps(batch, ensure_ascii=False)
        review_ids = [e["review_id"] for item in batch for e in item["examples"]]
        names = None
        for _ in range(2):
            kind, data, calls = caller.call(role=ROLE, model=model, label_config=config, system=system, user=user,
                                            schema=OUTPUT_SCHEMA, max_tokens=4000, review_ids=review_ids)
            if kind == "ok":
                got = {i.get("issue_id"): i for i in data.get("issues", []) if isinstance(i, dict)}
                if set(got) == {item["issue_id"] for item in batch} and all(
                        isinstance(i.get("title"), str) and i["title"].strip() and isinstance(i.get("description"), str) for i in got.values()):
                    names = got
                else:
                    calls[-1].update(outcome="failed", error="invalid_output: issue IDs do not match the request")
                    kind = "invalid"
            for call in calls:
                insert_call(db, call, session, phase)
            if kind != "invalid":
                break
        for item in batch:
            if names:
                db.execute("INSERT INTO issue_names VALUES (?,?,?,?,?,?)",
                           (item["issue_id"], names[item["issue_id"]]["title"].strip(), names[item["issue_id"]]["description"].strip(),
                            config, json.dumps([e["review_id"] for e in item["examples"]]), calls[-1]["request_id"]))
        db.commit()
        if kind in ("fatal", "spend_cap", "transient", "refusal"):
            stop_reason = kind if kind != "fatal" else f"fatal: {data}"
            break

    names = {row[0]: row[1:] for row in db.execute("SELECT issue_id, title, description, named_by, example_review_ids FROM issue_names")}
    issues = []
    for issue_id in sorted(counts):
        topic, _, aspect = issue_id.partition(".")
        # Without an accepted model name, the issue keeps a plain code-made title; ranking is unaffected.
        title, description, named_by, examples = names.get(issue_id, (f"{topic}: {aspect.replace('-', ' ')}", "", "code_fallback", "[]"))
        issues.append({"issue_id": issue_id, "topic": topic, "aspect": aspect, "title": title, "description": description,
                       "named_by": named_by, "complaint_count": counts[issue_id], "example_review_ids": json.loads(examples)})
    write_json(run_dir / "group_input.json", {"group_config": config, "rules": rules_version, "sent_this_session": pack})
    write_json(run_dir / "issues.json", {"rules": rules_version, "group_config": config, "stop_reason": stop_reason,
                                         "membership_rule": "issue_id = <topic>.<aspect>; see labels/issues.json", "issues": issues})
    return {"issues": len(issues), "members": sum(counts.values()), "named_this_session": len(pack) if not stop_reason else None,
            "unnamed": sum(i["named_by"] == "code_fallback" for i in issues), "stop_reason": stop_reason}

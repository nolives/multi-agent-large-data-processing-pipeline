"""Check how many `usability.ads` complaints are really the verb "adds", not the misspelling of "ads". No model calls.

    python3 tools/adds_check.py

The entity lexicon (labels/entities.json) counts "adds" as "ads", because reviewers often misspell it ("too many adds").
That also catches the verb: "it adds songs to my playlist". This script takes the final run's `usability.ads` members
(runs/final_100k/membership.csv), reads their texts from data/final_100k.csv (rebuilt by tools/build_final_subset.py),
and keeps those whose only ad word is "adds". A text pattern then picks out the ones that look like the verb, and each
of those has a verdict read by hand in evals/adds_check/verdicts.csv. The rest were not read individually.

Writes evals/adds_check/adds_only_members.csv (every such member, its pattern match and verdict) and report.json.
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

ISSUE = "usability.ads"
ADDS = r"\badds\b"
# "adds" followed by what is added (songs, music, it, them...), or preceded by what does the adding (it, Spotify, the app...).
VERB = re.compile(r"\badds\s+(in\s+|on\s+)?(a\s+|random\s+|the\s+|some\s+|other\s+|more\s+|new\s+|extra\s+|its\s+own\s+|recommended\s+"
                  r"|suggested\s+)*(songs?|tracks?|music|it|them|stuff)\b"
                  r"|\b(it|spotify|app|that|which|automatically|just|also|now|keeps|still|always|randomly)\s+adds\b", re.IGNORECASE)
VERDICTS = ("verb", "misspelling", "both")  # both: the verb and a misspelt ad complaint in one review


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, default=Path("runs/final_100k"))
    parser.add_argument("--input", type=Path, default=Path("data/final_100k.csv"))
    parser.add_argument("--lexicon", type=Path, default=Path("labels/entities.json"))
    parser.add_argument("--verdicts", type=Path, default=Path("evals/adds_check/verdicts.csv"))
    parser.add_argument("--out", type=Path, default=Path("evals/adds_check"))
    args = parser.parse_args()

    patterns = json.loads(args.lexicon.read_text(encoding="utf-8"))["entities"]["ads"]
    if ADDS not in patterns:
        raise SystemExit(f'The "ads" entity no longer contains {ADDS}; this check no longer applies.')
    other_ad_words = re.compile("|".join(p for p in patterns if p != ADDS), re.IGNORECASE)
    adds = re.compile(ADDS, re.IGNORECASE)

    with (args.run / "membership.csv").open(encoding="utf-8", newline="") as f:
        members = {row["review_id"] for row in csv.DictReader(f) if row["issue_id"] == ISSUE}
    with args.input.open(encoding="utf-8-sig", newline="") as f:
        texts = {row["review_id"]: row["review_text"] for row in csv.DictReader(f, strict=True) if row["review_id"] in members}
    if set(texts) != members:
        raise SystemExit(f"{len(members - set(texts))} {ISSUE} members are not in {args.input}; is it the final run's input?")

    verdicts = {}
    if args.verdicts.exists():
        with args.verdicts.open(encoding="utf-8", newline="") as f:
            verdicts = {row["review_id"]: row for row in csv.DictReader(f)}
    bad = [rid for rid, v in verdicts.items() if v["verdict"] not in VERDICTS]
    if bad:
        raise SystemExit(f"Verdicts must be one of {VERDICTS}: {bad[:5]}")

    rows = []
    for rid in sorted(texts):
        text = texts[rid]
        if not adds.search(text) or other_ad_words.search(text):
            continue
        matched = bool(VERB.search(text))
        v = verdicts.get(rid)
        rows.append({"review_id": rid, "matches_verb_pattern": matched,
                     "verdict": v["verdict"] if v else ("MISSING" if matched else "not_read"), "note": v["note"] if v else "",
                     "review_text": text})

    missing = [r["review_id"] for r in rows if r["verdict"] == "MISSING"]
    stray = sorted(set(verdicts) - {r["review_id"] for r in rows if r["matches_verb_pattern"]})
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "adds_only_members.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (not r["matches_verb_pattern"], r["verdict"], r["review_id"])))

    counts = Counter(r["verdict"] for r in rows)
    report = {
        "issue": ISSUE, "issue_members": len(members),
        "members_whose_only_ad_word_is_adds": len(rows),
        "matching_the_verb_pattern": sum(r["matches_verb_pattern"] for r in rows),
        "verdicts_for_pattern_matches": {k: counts[k] for k in VERDICTS},
        "verb_share_of_issue": round(counts["verb"] / len(members), 4),
        "not_read_individually": counts["not_read"],
        "verb_pattern": VERB.pattern,
        "method": "Pattern matches were each read by hand. The members that do not match the pattern were not read "
                  "individually, so a verb use phrased differently could remain among them: the verb count is a lower bound.",
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("verb_pattern", "method")}, indent=1))
    if missing or stray:
        raise SystemExit(f"{len(missing)} pattern matches have no verdict; {len(stray)} verdicts match no current pattern match.")


if __name__ == "__main__":
    main()

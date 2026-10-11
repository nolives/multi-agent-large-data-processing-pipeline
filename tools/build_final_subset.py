"""Build the input file for the final run: a reproducible 100,000-review subset of the full corpus. No model calls.

    python3 tools/build_final_subset.py

Selection rule: the course's own sampling rule from data/manifest.json. Among unique, nonempty reviews with a valid
rating, take the lowest SHA-256(seed + ':' + review_id) values. The first 50 by this rule are the golden set and the
next 10,000 are analysis_10000.csv, so the subset contains every course sample. The 13 empty-text reviews are then
added so that the run quarantines them explicitly. Rows are written in source order with their values unchanged.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", type=Path, default=Path("data/spotify_reviews_18months.csv"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    parser.add_argument("--size", type=int, default=100_000)
    parser.add_argument("--out", type=Path, default=Path("data/final_100k.csv"))
    args = parser.parse_args()

    seed = json.loads(args.manifest.read_text(encoding="utf-8"))["samples"]["seed"]
    with args.full.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, strict=True))
    seen, eligible, empty = set(), [], set()
    for row in rows:
        rid = row["review_id"]
        if not row["review_text"].strip():
            empty.add(rid)
        elif row["review_rating"] in ("1", "2", "3", "4", "5") and rid not in seen:
            eligible.append((hashlib.sha256((seed + ":" + rid).encode("utf-8")).hexdigest(), rid))
        seen.add(rid)
    eligible.sort()
    chosen = {rid for _, rid in eligible[:args.size]}
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        written = 0
        for row in rows:  # source order, values untouched
            if row["review_id"] in chosen or row["review_id"] in empty:
                writer.writerow({k: row[k] for k in FIELDS})
                written += 1
    order = [rid for _, rid in eligible]
    ids = lambda name: [r["review_id"] for r in csv.DictReader((args.full.parent / name).open(encoding="utf-8-sig", newline=""))]
    summary = {
        "output": str(args.out), "rows": written, "sampled_nonempty": len(chosen), "empty_text_rows_added": len(empty),
        "distinct_nonempty_texts": len({r["review_text"] for r in rows if r["review_id"] in chosen}),
        "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(), "seed": seed,
        "rule": "lowest SHA-256(seed + ':' + review_id) among unique nonempty reviews with a valid rating, plus every empty-text review",
        "contains_golden_50": set(ids("golden_50_to_label.csv")) <= chosen and order[:50] == ids("golden_50_to_label.csv"),
        "contains_analysis_10000": set(ids("analysis_10000.csv")) <= chosen,
        "months_covered": len({r["review_timestamp"][:7] for r in rows if r["review_id"] in chosen}),
    }
    args.out.with_suffix(".manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

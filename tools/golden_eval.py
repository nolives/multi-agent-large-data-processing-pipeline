"""Compare the pipeline's saved predictions with the hand-labeled golden set. No model calls.

    python3 tools/golden_eval.py --run runs/golden_50

Reads the human labels (evals/golden_50_labeled.csv), the enricher's records (enriched.jsonl.gz) and the independent
verifier's labels (verify_predictions.jsonl) from a run made on the unlabeled golden file. Writes per-case and
per-field results, a confusion table and every disagreement to evals/golden/. Human labels are never model inputs:
the run reads data/golden_50_to_label.csv, whose label columns are blank.
"""

import argparse
import csv
import gzip
import io
import json
from collections import Counter
from pathlib import Path

SENTIMENT_TOLERANCE = 0.5  # declared in labels/LABEL_GUIDE.md before the evaluation
FIELDS = ("topic", "intent", "severity")


def rate(a, b):
    return round(a / b, 4) if b else None


def score(cases, who):
    """Agreement of one labeler ('enricher' or 'verifier') with the human labels over the given cases."""
    n = len(cases)
    out = {"cases": n}
    for field in FIELDS:
        out[f"{field}_agreement"] = rate(sum(c["human"][field] == c[who][field] for c in cases), n)
    out["all_three_agreement"] = rate(sum(all(c["human"][f] == c[who][f] for f in FIELDS) for c in cases), n)
    out["severity_mean_absolute_error"] = rate(sum(abs(c["human"]["severity"] - c[who]["severity"]) for c in cases), n)
    out["severity_within_one"] = rate(sum(abs(c["human"]["severity"] - c[who]["severity"]) <= 1 for c in cases), n)
    out["sentiment_within_tolerance"] = rate(sum(abs(c["human"]["sentiment"] - c[who]["sentiment"]) <= SENTIMENT_TOLERANCE for c in cases), n)
    out["sentiment_mean_absolute_error"] = rate(sum(abs(c["human"]["sentiment"] - c[who]["sentiment"]) for c in cases), n)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=Path("evals/golden_50_labeled.csv"))
    parser.add_argument("--out", type=Path, default=Path("evals/golden"))
    args = parser.parse_args()

    with args.labels.open(encoding="utf-8-sig", newline="") as f:
        human_rows = list(csv.DictReader(f))
    with gzip.open(args.run / "enriched.jsonl.gz", "rt", encoding="utf-8") as f:
        enriched = {r["review_id"]: r for r in map(json.loads, f)}
    verified = {r["review_id"]: r for r in map(json.loads, (args.run / "verify_predictions.jsonl").read_text(encoding="utf-8").splitlines())}
    # A review whose text duplicates an earlier one reuses that text's verifier label, as it reuses the enricher's.
    for rid, record in enriched.items():
        if rid not in verified and record.get("cache_source_id") in verified:
            verified[rid] = verified[record["cache_source_id"]]

    cases, missing = [], []
    for h in human_rows:
        rid = h["review_id"]
        e, v = enriched.get(rid), verified.get(rid)
        if not e or e["status"] != "completed":
            missing.append({"review_id": rid, "status": (e or {}).get("status", "absent"), "reason": (e or {}).get("reason")})
            continue
        human = {"topic": h["topic"], "intent": h["intent"], "severity": int(h["severity"]), "sentiment": float(h["sentiment"]),
                 "needs_review": h["needs_review"] == "true", "evidence_quote": h["evidence_quote"],
                 "entities": [x.strip() for x in h["entities"].split(";") if x.strip()]}
        quote = e["evidence_quote"]
        cases.append({
            "review_id": rid, "review_text": h["review_text"], "ambiguous": h["ambiguous"] == "true", "notes": h["notes"], "human": human,
            "enricher": {k: e[k] for k in ("topic", "intent", "severity", "sentiment", "needs_review", "evidence_quote", "entities")},
            "verifier": {k: v[k] for k in ("topic", "intent", "severity", "sentiment")} if v else None,
            "reused_from": e.get("cache_source_id"),
            "quote_is_exact_substring": quote in h["review_text"],
            # The two quotes point at the same evidence if one contains the other.
            "quote_overlaps_human_quote": quote in human["evidence_quote"] or human["evidence_quote"] in quote,
            "enricher_entities_not_in_human": [x for x in e["entities"] if x not in human["entities"]],
            "human_entities_not_in_enricher": [x for x in human["entities"] if x not in e["entities"]],
        })

    clear = [c for c in cases if not c["ambiguous"]]
    wrong = lambda c, who="enricher": [f for f in FIELDS if c["human"][f] != c[who][f]]
    flagged = [c for c in cases if c["enricher"]["needs_review"]]
    human_flagged = [c for c in cases if c["human"]["needs_review"]]
    errors = [c for c in cases if wrong(c)]
    confusion = {f: dict(Counter(f"{c['human'][f]} -> {c['enricher'][f]}" for c in cases if c["human"][f] != c["enricher"][f]).most_common()) for f in FIELDS}
    by_topic = {}
    for topic in sorted({c["human"]["topic"] for c in cases}):
        mine = [c for c in cases if c["human"]["topic"] == topic]
        by_topic[topic] = {"human_count": len(mine), "enricher_same_topic": sum(c["enricher"]["topic"] == topic for c in mine),
                           "enricher_predicted_count": sum(c["enricher"]["topic"] == topic for c in cases)}
    with_verifier = [c for c in cases if c["verifier"]]

    report = {
        "note": "Fifty cases are a small diagnostic sample, not a precise estimate of accuracy on the whole corpus.",
        "run": args.run.name, "enricher_config": next(iter(enriched.values())).get("label_config"),
        "labels_file": str(args.labels), "golden_reviews": len(human_rows), "scored": len(cases), "missing_or_quarantined": missing,
        "ambiguous_cases": sum(c["ambiguous"] for c in cases), "sentiment_tolerance": SENTIMENT_TOLERANCE,
        "enricher_vs_human": {"all_cases": score(cases, "enricher"), "non_ambiguous_cases": score(clear, "enricher"),
                              "ambiguous_cases": score([c for c in cases if c["ambiguous"]], "enricher")},
        "verifier_vs_human": {"all_cases": score(with_verifier, "verifier"), "non_ambiguous_cases": score([c for c in with_verifier if not c["ambiguous"]], "verifier")},
        "per_topic": by_topic, "confusion_human_to_enricher": confusion,
        "evidence_quote": {"exact_substring_of_source": sum(c["quote_is_exact_substring"] for c in cases),
                           "overlaps_human_quote": sum(c["quote_overlaps_human_quote"] for c in cases), "of": len(cases)},
        "entities": {"cases_where_enricher_lists_an_entity_the_human_did_not": sum(bool(c["enricher_entities_not_in_human"]) for c in cases),
                     "cases_where_human_lists_an_entity_the_enricher_did_not": sum(bool(c["human_entities_not_in_enricher"]) for c in cases),
                     "note": "The enricher's entities come from a fixed lexicon matched against the text, so each one is present in the text; "
                             "differences are mostly naming and granularity. They are listed per case for inspection."},
        "needs_review_as_prediction": {
            "of_the_human_flag": {"enricher_flagged": len(flagged), "human_flagged": len(human_flagged),
                                  "both": sum(c["human"]["needs_review"] for c in flagged),
                                  "precision": rate(sum(c["human"]["needs_review"] for c in flagged), len(flagged)),
                                  "recall": rate(sum(c["enricher"]["needs_review"] for c in human_flagged), len(human_flagged))},
            "of_an_enricher_error": {"enricher_errors": len(errors), "flagged_errors": sum(c["enricher"]["needs_review"] for c in errors),
                                     "precision": rate(sum(bool(wrong(c)) for c in flagged), len(flagged)),
                                     "recall": rate(sum(c["enricher"]["needs_review"] for c in errors), len(errors))}},
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "golden_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out / "golden_cases.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["review_id", "ambiguous", "topic_human", "topic_enricher", "topic_verifier", "topic_pass", "intent_human", "intent_enricher",
                     "intent_verifier", "intent_pass", "severity_human", "severity_enricher", "severity_verifier", "severity_pass", "severity_abs_error",
                     "sentiment_human", "sentiment_enricher", "sentiment_pass", "needs_review_human", "needs_review_enricher", "quote_exact_substring",
                     "quote_overlaps_human", "human_notes", "review_text"])
    for c in cases:
        h, e, v = c["human"], c["enricher"], c["verifier"] or {}
        writer.writerow([c["review_id"], c["ambiguous"], h["topic"], e["topic"], v.get("topic"), h["topic"] == e["topic"], h["intent"], e["intent"],
                         v.get("intent"), h["intent"] == e["intent"], h["severity"], e["severity"], v.get("severity"), h["severity"] == e["severity"],
                         abs(h["severity"] - e["severity"]), h["sentiment"], e["sentiment"], abs(h["sentiment"] - e["sentiment"]) <= SENTIMENT_TOLERANCE,
                         h["needs_review"], e["needs_review"], c["quote_is_exact_substring"], c["quote_overlaps_human_quote"], c["notes"], c["review_text"]])
    (args.out / "golden_results.csv").write_text(buffer.getvalue(), encoding="utf-8")

    a, na, va = report["enricher_vs_human"]["all_cases"], report["enricher_vs_human"]["non_ambiguous_cases"], report["verifier_vs_human"]["all_cases"]
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"
    lines = ["# Golden-set evaluation", "", report["note"], "",
             f"- Run `{report['run']}`, enricher `{report['enricher_config']}`.",
             f"- {report['scored']} of {report['golden_reviews']} golden reviews scored; {len(missing)} missing or quarantined (these count as incorrect).",
             f"- {report['ambiguous_cases']} cases were marked ambiguous by the labeler.", "",
             "| Measure | Enricher, all cases | Enricher, non-ambiguous | Verifier, all cases |", "|---|---|---|---|",
             *(f"| {name} | {fmt(a[key])} | {fmt(na[key])} | {fmt(va[key])} |" for name, key, fmt in (
                 ("Cases", "cases", str), ("Topic agreement", "topic_agreement", pct), ("Intent agreement", "intent_agreement", pct),
                 ("Severity exact agreement", "severity_agreement", pct), ("Severity within one level", "severity_within_one", pct),
                 ("Severity mean absolute error", "severity_mean_absolute_error", str), ("Topic, intent and severity all agree", "all_three_agreement", pct),
                 (f"Sentiment within {SENTIMENT_TOLERANCE}", "sentiment_within_tolerance", pct), ("Sentiment mean absolute error", "sentiment_mean_absolute_error", str))),
             "", "## Per topic (human label)", "", "| Topic | Human count | Enricher chose the same | Enricher chose this topic in total |", "|---|---|---|---|",
             *(f"| {t} | {v['human_count']} | {v['enricher_same_topic']} | {v['enricher_predicted_count']} |" for t, v in by_topic.items()),
             "", "## Confusions (human label -> enricher label)", ""]
    for field in FIELDS:
        lines.append(f"- **{field}:** " + ("; ".join(f"{k} ({n})" for k, n in confusion[field].items()) or "none"))
    q, nr = report["evidence_quote"], report["needs_review_as_prediction"]
    lines += ["", "## Other fields", "",
              f"- **Evidence quote:** {q['exact_substring_of_source']} of {q['of']} are exact substrings of the source (checked in code); {q['overlaps_human_quote']} overlap the human's quote.",
              f"- **Entities:** the enricher listed an entity the human did not in {report['entities']['cases_where_enricher_lists_an_entity_the_human_did_not']} cases, "
              f"and missed one the human listed in {report['entities']['cases_where_human_lists_an_entity_the_enricher_did_not']}. {report['entities']['note']}",
              f"- **needs_review, as a prediction of the human flag:** the enricher flagged {nr['of_the_human_flag']['enricher_flagged']}, the human {nr['of_the_human_flag']['human_flagged']}, "
              f"both {nr['of_the_human_flag']['both']} (precision {pct(nr['of_the_human_flag']['precision'])}, recall {pct(nr['of_the_human_flag']['recall'])}).",
              f"- **needs_review, as a prediction of an enricher error:** {nr['of_an_enricher_error']['flagged_errors']} of {nr['of_an_enricher_error']['enricher_errors']} "
              f"wrong records were flagged (recall {pct(nr['of_an_enricher_error']['recall'])}); {pct(nr['of_an_enricher_error']['precision'])} of flagged records were wrong.",
              "", "## Every disagreement on topic, intent or severity", "",
              "| Review | Ambiguous | Fields | Human | Enricher | Verifier | Enricher flagged | Text |", "|---|---|---|---|---|---|---|---|"]
    show = lambda d: f"{d['topic']} / {d['intent']} / {d['severity']}" if d else "n/a"
    for c in errors:
        text = c["review_text"].replace("|", "/").replace("\n", " ")
        lines.append(f"| `{c['review_id'][:8]}` | {'yes' if c['ambiguous'] else ''} | {', '.join(wrong(c))} | {show(c['human'])} | {show(c['enricher'])} | "
                     f"{show(c['verifier'])} | {'yes' if c['enricher']['needs_review'] else ''} | {text[:240]} |")
    (args.out / "golden_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:22 + len(by_topic) + 12]))
    print(f"\n{len(errors)} disagreements listed in {args.out / 'golden_report.md'}")


if __name__ == "__main__":
    main()

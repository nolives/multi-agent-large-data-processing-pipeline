#!/usr/bin/env python3
"""100-review cost and runtime calculator. Standard library only; no network, no API key, no model calls.

    python3 cost/calculator.py                       # offline replay: recompute everything, write report.md and usage.csv
    python3 cost/calculator.py --rate-multiplier 2   # what-if: double every API rate (prints, does not overwrite the report)
    python3 cost/calculator.py --distinct-texts 250000 --budget 20
    python3 cost/calculator.py --self-test           # checks the arithmetic properties the grader tests

Measured results come only from the saved pilot files beside this script (pilot_calls.jsonl, pilot_records.jsonl,
pilot_measurements.json). Costs are recomputed as billed_units x price_per_unit from rates.csv, so editing a rate
changes the cost and nothing else. Projections use assumptions.json. Running the paid pilot is a separate,
explicit command described in README.md; this file never makes a call.
"""

import argparse
import csv
import io
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ITEMS = ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens")  # mutually exclusive billing items
STAGES = ("ingest", "enrich", "verify", "group", "rank", "memo")


def load_rates(path, multiplier=1.0):
    with Path(path).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        # Prices are quoted per million units; divide first, then multiply by billed units.
        row["unit_price"] = float(row["price_per_million_units"]) * multiplier / 1_000_000
    return rows


def unit_price(rates, provider, model, item):
    """The rate row for this model. A dated snapshot ID (model-YYYYMMDD) is billed at its base model's rate."""
    for row in rates:
        if row["provider"] == provider and row["billing_item"] == item and (model == row["model"] or model.startswith(row["model"] + "-")):
            return row["unit_price"]
    raise KeyError(f"No rate for {provider} / {model} / {item}. Add it to rates.csv.")


def call_cost(call, rates):
    return sum(call[item] * unit_price(rates, call["provider"], call["model"], item) for item in ITEMS if call[item])


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def money(value, places=4):
    return "unknown" if value is None else f"${value:,.{places}f}"


def duration(seconds):
    if seconds is None:
        return "unknown"
    return f"{seconds:,.1f} s" if seconds < 600 else f"{seconds / 3600:,.2f} h"


def measure(calls, records, measurements, rates):
    """Everything measured in the pilot, with cost recomputed from usage and rates."""
    usage = defaultdict(lambda: {"calls": 0, "units": 0})
    by_stage = defaultdict(lambda: defaultdict(lambda: {"attempts": 0, "failed": 0, "cost": 0.0, "unknown": 0, "call_seconds": 0.0,
                                                        "models": set(), **{i: 0 for i in ITEMS}}))
    for c in calls:
        key = (c["run"], c["session"])
        stage = by_stage[key][c["role"]]
        stage["attempts"] += 1
        stage["failed"] += c["outcome"] == "failed"
        stage["unknown"] += c["usage_unknown"]
        stage["cost"] += call_cost(c, rates)
        stage["call_seconds"] += c["duration_ms"] / 1000
        stage["models"].add(c["model"])
        for item in ITEMS:
            stage[item] += c[item]
            if c[item]:
                row = usage[(c["run"], c["session"], c["run_type"], c["role"], c["provider"], c["model"], item)]
                row["calls"] += 1
                row["units"] += c[item]
    sessions = []
    for s in measurements["sessions"]:
        stages = by_stage.get((s["run"], s["session"]), {})
        cost = sum(v["cost"] for v in stages.values())
        completed = s["records_at_end"].get("completed", 0)
        rows = measurements["input"]["rows"]
        sessions.append({**s, "stages": stages, "api_cost": cost, "completed": completed,
                         "failed_records": rows - completed - s["records_at_end"].get("quarantined", 0),
                         "cost_per_1000_rows": cost / rows * 1000, "cost_per_completed": cost / completed if completed else None,
                         "records_per_second": rows / s["wall_seconds"],
                         "result_cache_hits": s["unique_texts"] if s["run_type"] == "warm" else measurements["input"]["rows"] - s["unique_texts"]})
    logged = sum(c["logged_cost_usd"] for c in calls)
    recomputed = sum(call_cost(c, rates) for c in calls)
    return {"sessions": sessions, "usage": usage, "logged_total": logged, "recomputed_total": recomputed, "attempts": len(calls),
            "unknown_usage_calls": sum(c["usage_unknown"] for c in calls),
            "records": {"total": len(records), "completed": sum(r["status"] == "completed" for r in records),
                        "quarantined": sum(r["status"] == "quarantined" for r in records)}}


def per_unit(calls, rates, measurements):
    """Unit usage from the measured cold run: what one text, one issue or one memo cost and took."""
    cold = next(s for s in measurements["sessions"] if s["run_type"] == "cold")
    mine = [c for c in calls if c["run"] == cold["run"] and c["session"] == cold["session"]]
    def stage(role):
        ok = [c for c in mine if c["role"] == role and c["outcome"] == "succeeded"]
        return {"calls": len(ok), "cost": sum(call_cost(c, rates) for c in ok), "input": sum(c["input_tokens"] for c in ok),
                "provider": ok[0]["provider"], "model": ok[0]["model"], "seconds": cold["stage_seconds"][role]}
    e, v, g, m = stage("enrich"), stage("verify"), stage("group"), stage("memo")
    texts, verified, issues = cold["unique_texts"], cold["texts_verified_at_end"], cold["issues_named_at_end"]
    return {
        "enrich_input_tokens_per_text": e["input"] / texts, "enrich_cost_per_text": e["cost"] / texts,
        "enrich_texts_per_second_one_worker": texts / e["seconds"],
        "enrich_input_price": unit_price(rates, e["provider"], e["model"], "input_tokens"),
        "verify_cost_per_text": v["cost"] / verified, "verify_seconds_per_text": v["seconds"] / verified,
        "group_cost_per_issue": g["cost"] / issues, "group_seconds_per_call": g["seconds"] / g["calls"],
        "memo_cost": m["cost"], "memo_seconds": m["seconds"], "pilot_texts": texts, "pilot_verified": verified, "pilot_issues": issues,
    }


def project(unit, assumptions, measurements, name, reuse=True):
    """One full-run scenario. Each stage is scaled by its own work count; fixed overhead is added once."""
    a, sc, p, controls = assumptions, assumptions["scenarios"][name], assumptions["projection"], assumptions["controls"]
    texts = p["distinct_nonempty_texts"] if reuse else p["nonempty_reviews"]
    workers = min(sc["workers"], controls["max_workers"])
    fallback = min(sc["fallback_fraction"], controls["max_fallback_fraction"])
    rate = min(workers * unit["enrich_texts_per_second_one_worker"] * (sc["parallel_efficiency"] if workers > 1 else 1.0),
               controls["max_requests_per_second"], controls["provider_requests_per_second_limit"])
    enrich_requests = texts * (1 + sc["enrich_retry_fraction"])
    sample = a["verification"]["full_run_sample_texts"]
    issues = a["fixed_overhead"]["issues_to_name_max"]
    ingest = measurements.get("full_corpus_ingest", {}).get("seconds")
    stages = [
        {"stage": "ingest", "kind": "fixed, local", "work": f"{p['source_rows']:,} rows", "cost": 0.0, "seconds": ingest,
         "basis": "measured on the full file" if ingest else "not measured"},
        {"stage": "enrich", "kind": "variable", "work": f"{texts:,} texts x {1 + sc['enrich_retry_fraction']:.2f} attempts",
         "cost": enrich_requests * unit["enrich_input_tokens_per_text"] * (1 + sc["token_margin"]) * unit["enrich_input_price"],
         "seconds": enrich_requests / rate, "basis": f"{unit['enrich_input_tokens_per_text']:,.1f} input tokens per text; {rate:.1f} texts/s "
         + ("(measured, one worker)" if workers == 1 else f"(modeled: {workers} workers at {sc['parallel_efficiency']:.0%} of linear)")},
        {"stage": "fallback", "kind": "variable, capped", "work": f"{texts * fallback:,.0f} texts ({fallback:.1%} of texts)",
         "cost": texts * fallback * unit["verify_cost_per_text"], "seconds": texts * fallback * unit["verify_seconds_per_text"],
         "basis": "modeled at the verifier's measured per-text cost; no fallback role exists yet"},
        {"stage": "verify", "kind": "variable", "work": f"{sample:,} sampled texts ({sample / texts:.2%} of texts) x {1 + sc['verify_retry_fraction']:.1f}",
         "cost": sample * (1 + sc["verify_retry_fraction"]) * unit["verify_cost_per_text"],
         "seconds": sample * (1 + sc["verify_retry_fraction"]) * unit["verify_seconds_per_text"], "basis": "measured per-text cost and time"},
        {"stage": "group", "kind": "fixed, once", "work": f"up to {issues} issues named", "cost": issues * unit["group_cost_per_issue"],
         "seconds": math.ceil(issues / 20) * unit["group_seconds_per_call"], "basis": "measured per-issue cost"},
        {"stage": "rank", "kind": "fixed, local", "work": "export and arithmetic", "cost": 0.0, "seconds": None,
         "basis": "no API cost; time not yet measured at full scale"},
        {"stage": "memo", "kind": "fixed, once", "work": f"{a['fixed_overhead']['memos']} memo x {sc['memo_attempts']} attempt(s)",
         "cost": a["fixed_overhead"]["memos"] * sc["memo_attempts"] * sc["memo_size_multiplier"] * unit["memo_cost"],
         "seconds": a["fixed_overhead"]["memos"] * sc["memo_attempts"] * sc["memo_size_multiplier"] * unit["memo_seconds"],
         "basis": f"measured memo x {sc['memo_size_multiplier']} for a larger input"},
    ]
    known = sum(s["seconds"] for s in stages if s["seconds"] is not None)
    api = sum(s["cost"] for s in stages)
    hourly = a["local_compute_usd_per_hour"]
    return {"name": name, "reuse": reuse, "description": sc["description"], "stages": stages, "api_cost": api, "seconds": known,
            "workers": workers, "texts": texts, "texts_per_second": rate, "local_cost": None if hourly is None else hourly * known / 3600,
            "over_budget": api > a["budget_usd"]}


def build_report(m, unit, scenarios, assumptions, measurements, rates, multiplier):
    out = io.StringIO()
    w = lambda line="": out.write(line + "\n")
    inp = measurements["input"]
    cold = next(s for s in m["sessions"] if s["run_type"] == "cold")
    warm = next(s for s in m["sessions"] if s["run_type"] == "warm")
    w(f"# {inp['rows']:,}-review cost and runtime report")
    w()
    w("Generated by `python3 cost/calculator.py` from saved pilot measurements. No API key or model call is needed to reproduce it.")
    if multiplier != 1:
        w(f"\n**What-if view: every API rate multiplied by {multiplier:g}. Measured times and counts are unchanged.**")
    w()
    w(f"## 1. Measured on the {inp['rows']:,}-review run")
    w()
    w(f"- Input: `{inp['file']}`, {inp['rows']} rows, SHA-256 `{inp['sha256']}`. Every input ID has a saved record: {inp['every_input_id_has_a_record']}.")
    w(f"- Records: {m['records']['completed']} completed, {m['records']['quarantined']} quarantined, "
      f"{m['records']['total'] - m['records']['completed'] - m['records']['quarantined']} failed. Unique texts: {cold['unique_texts']}.")
    w(f"- Cold run: empty result cache, {cold['workers']} worker, all six stages. Warm run: the same command again on the saved results.")
    w(f"- Provider prompt caching: {measurements['provider_prompt_cache']}")
    w()
    w("| Run | Type | Completed | Failed | Result-cache hits | Attempts (failed) | New enrichment calls | Downstream calls | API cost | Wall clock | Summed call time | Records/s | Cost per 1,000 rows | Cost per completed record |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in m["sessions"]:
        w(f"| {s['run']} session {s['session']} | {s['run_type']} | {s['completed']} | {s['failed_records']} | {s['result_cache_hits']} | "
          f"{s['attempts']} ({s['failed_attempts']}) | {s['new_enrichment_calls']} | {s['downstream_calls']} | {money(s['api_cost'])} | "
          f"{duration(s['wall_seconds'])} | {duration(s['summed_call_seconds'])} | {s['records_per_second']:.2f} | {money(s['cost_per_1000_rows'])} | {money(s['cost_per_completed'], 6)} |")
    w()
    w("Wall clock is measured end to end with a monotonic clock. Summed call time adds each request's duration; with one worker it is below "
      "wall clock, and with several workers it can exceed it.")
    w()
    w(f"The warm run made {warm['new_enrichment_calls']} new enrichment calls and {warm['downstream_calls']} downstream calls, "
      f"for an incremental cost of {money(warm['api_cost'])} in {duration(warm['wall_seconds'])}.")
    failed = [s for s in m["sessions"] if s["run_type"] == "cold_failed_attempt"]
    if failed:
        w()
        w(f"**Failures on the record.** {len(failed)} earlier cold attempt(s) are kept in the call log. In `{failed[0]['run']}` every Haiku response was "
          f"rejected by an over-strict model-ID check in this project's code ({sum(st['failed'] for st in failed[0]['stages'].values())} failed attempts). "
          f"Those calls were billed and are counted above; the bug was fixed before the measured cold run.")
    w()
    w("### Cold run by stage")
    w()
    w("| Stage | Provider | Exact model | Effort | Prompt and schema version | Batch size | Workers | Attempts | Failed | Input tokens | Output tokens | Cache read / write | API cost | Stage wall clock |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for stage in STAGES:
        info, st = measurements["stages"][stage], cold["stages"].get(stage)
        batch = (f"{info['reviews_per_request']} review(s) per request" if "reviews_per_request" in info
                 else f"{info['issues_per_request']} issues per request" if "issues_per_request" in info else "n/a")
        if st:
            w(f"| {stage} | {info['provider']} | `{', '.join(sorted(st['models']))}` | {info['effort']} | `{info['label_config']}` | {batch} | "
              f"{cold['workers']} | {st['attempts']} | {st['failed']} | {st['input_tokens']:,} | {st['output_tokens']:,} | "
              f"{st['cache_read_tokens']:,} / {st['cache_write_tokens']:,} | {money(st['cost'])} | {duration(cold['stage_seconds'][stage])} |")
        else:
            w(f"| {stage} | local | none (code) | n/a | n/a | n/a | 1 | 0 | 0 | 0 | 0 | 0 / 0 | $0.0000 | {duration(cold['stage_seconds'][stage])} |")
    w()
    w("### Cost arithmetic")
    w()
    w("`item_cost = billed_units x price_per_unit`, summed over mutually exclusive items (uncached input, cache write, cache read, output). "
      "A per-million price is divided by 1,000,000 first. Reasoning tokens are part of output tokens and are not added again. "
      "All calls used the standard processing tier; no batch discount is applied to measured costs.")
    w()
    w("| Provider | Model | Billing item | Unit | Price per million | Currency | Checked | Source |")
    w("|---|---|---|---|---|---|---|---|")
    for r in rates:
        w(f"| {r['provider']} | `{r['model']}` | {r['billing_item']} | {r['unit']} | {r['unit_price'] * 1_000_000:g} | {r['currency']} | {r['checked_date']} | {r['source_url']} |")
    w()
    w(f"- Recomputed from usage and rates: {money(m['recomputed_total'], 6)} across all {m['attempts']} logged attempts. "
      f"Cost logged at run time: {money(m['logged_total'], 6)}." + ("" if multiplier != 1 else f" Difference: {money(abs(m['recomputed_total'] - m['logged_total']), 9)}."))
    w(f"- Calls with unknown usage (for example timeouts): {m['unknown_usage_calls']}." + (" These are charged at their reservation as a labeled estimate." if m["unknown_usage_calls"] else ""))
    w("- `usage.csv` lists billed units per run, stage, model and billing item; each row maps to the calls in `pilot_calls.jsonl` with the same run, session, role and model.")
    w("- Reconciliation with the providers' usage dashboards has not been done; these figures are computed from the usage each response reported.")
    w()
    w("### Local compute")
    w()
    hourly = assumptions["local_compute_usd_per_hour"]
    w("Orchestration, ingestion, export and ranking run on a laptop. " + (
        "Its cost was **not measured and is reported as unknown**, not zero. Set `local_compute_usd_per_hour` in `assumptions.json` to estimate it."
        if hourly is None else f"Estimated at ${hourly:g} per hour of wall clock (an assumption, shown separately from API spend)."))
    w()
    w("## 2. Estimated before the full run")
    w()
    p = assumptions["projection"]
    w(f"- All {p['source_rows']:,} rows accounted for: {p['nonempty_reviews']:,} nonempty reviews to classify and {p['empty_text_quarantines']} empty-text quarantines.")
    w(f"- With exact-text reuse, first-pass enrichment covers {p['distinct_nonempty_texts']:,} distinct texts; the no-reuse comparison sends all {p['nonempty_reviews']:,}.")
    w(f"- Per-unit figures come from the measured cold run: {unit['enrich_input_tokens_per_text']:,.1f} input tokens and {money(unit['enrich_cost_per_text'], 7)} per enriched text, "
      f"{unit['enrich_texts_per_second_one_worker']:.2f} texts/s with one worker, {money(unit['verify_cost_per_text'], 6)} per verified text, "
      f"{money(unit['group_cost_per_issue'], 5)} per named issue, {money(unit['memo_cost'])} per memo.")
    w(f"- These are estimates from {inp['rows']:,} reviews. They say little about rare failures or sustained throughput, and are refreshed at each checkpoint (100, 500, 10,000) before the full run.")
    w()
    w("| Scenario | Exact-text reuse | Workers | Enrichment rate | API cost | Elapsed (known stages) | Local compute | Budget check |")
    w("|---|---|---|---|---|---|---|---|")
    for s in scenarios:
        w(f"| {s['name']} | {'yes' if s['reuse'] else 'no'} | {s['workers']} | {s['texts_per_second']:.1f} texts/s | {money(s['api_cost'], 2)} | {duration(s['seconds'])} | "
          f"{money(s['local_cost'], 2)} | {'**EXCEEDS the $%g budget**' % assumptions['budget_usd'] if s['over_budget'] else 'within $%g' % assumptions['budget_usd']} |")
    w()
    for s in scenarios:
        if not s["reuse"]:
            continue
        w(f"### Scenario: {s['name']}")
        w()
        w(s["description"])
        w()
        w("| Stage | Kind | Work | API cost | Time | Basis |")
        w("|---|---|---|---|---|---|")
        for st in s["stages"]:
            w(f"| {st['stage']} | {st['kind']} | {st['work']} | {money(st['cost'])} | {duration(st['seconds'])} | {st['basis']} |")
        w(f"| **total** | | | **{money(s['api_cost'], 2)}** | **{duration(s['seconds'])}** | fixed overhead counted once |")
        w()
    over = [s["name"] + ("" if s["reuse"] else " (no reuse)") for s in scenarios if s["over_budget"]]
    w("> **Budget warning:** " + ", ".join(over) + f" exceed the declared budget of ${assumptions['budget_usd']:g}." if over
      else f"All scenarios are within the declared budget of ${assumptions['budget_usd']:g}.")
    w()
    w("## 3. Controls")
    w()
    c = assumptions["controls"]
    w(f"- **Spending limit:** ${assumptions['budget_usd']:g} for the full run (editable in `assumptions.json`). The pipeline enforces a cap per session with `--max-spend-usd`: "
      "it reserves worst-case cost before each call and stops admitting work when spent plus reserved plus the next reservation would exceed the cap.")
    w(f"- **Output-token caps per request:** verify {c['output_token_cap_per_request']['verify']:,}, group {c['output_token_cap_per_request']['group']:,}, "
      f"memo {c['output_token_cap_per_request']['memo']:,}. Enrichment: {c['output_token_cap_per_request']['enrich']}.")
    w(f"- **Maximum concurrency:** {c['max_workers']} workers, at most {c['max_requests_per_second']} request starts per second shared across workers "
      f"(provider limit {c['provider_requests_per_second_limit']} per second). Only one worker has been measured; multi-worker rates are modeled.")
    w(f"- **Maximum fallback fraction:** {c['max_fallback_fraction']:.0%} of texts. No fallback model is used in the measured pilot.")
    w("- **Retries:** rate-limit and server errors are retried with exponential backoff and jitter, at most 5 attempts for enrichment and 4 for Claude roles; "
      "invalid output is retried once and then quarantined; a stage stops after repeated identical failures.")
    w("- **Recovery:** results are saved in one transaction per batch; a rerun resumes from saved work and makes no call for a completed text.")
    w()
    w("## 4. Scaling decision")
    w()
    w("Not yet made. This report is refreshed at each checkpoint (100, 500, then 10,000 reviews) before the full run is started explicitly.")
    return out.getvalue()


def usage_csv(m, rates):
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["run", "session", "run_type", "stage", "provider", "model", "billing_item", "calls_with_item", "billed_units",
                     "price_per_million_units", "cost_usd"])
    for (run, session, run_type, role, provider, model, item), row in sorted(m["usage"].items()):
        price = unit_price(rates, provider, model, item)
        writer.writerow([run, session, run_type, role, provider, model, item, row["calls"], row["units"], f"{price * 1_000_000:g}", f"{row['units'] * price:.8f}"])
    return out.getvalue()


def compute(args, multiplier=None, overrides=None):
    multiplier = args.rate_multiplier if multiplier is None else multiplier
    rates = load_rates(args.rates, multiplier)
    calls, records = read_jsonl(args.calls), read_jsonl(args.records)
    measurements = json.loads(Path(args.measurements).read_text(encoding="utf-8"))
    assumptions = json.loads(Path(args.assumptions).read_text(encoding="utf-8"))
    for key, value in (overrides or {}).items():
        if value is not None:
            if key == "budget_usd":
                assumptions[key] = value
            else:
                assumptions["projection"][key] = value
    m = measure(calls, records, measurements, rates)
    unit = per_unit(calls, rates, measurements)
    scenarios = [project(unit, assumptions, measurements, name) for name in assumptions["scenarios"]]
    scenarios.append(project(unit, assumptions, measurements, "base", reuse=False))
    return m, unit, scenarios, assumptions, measurements, rates


def self_test(args):
    base = compute(args, 1.0)
    doubled = compute(args, 2.0)
    bigger = compute(args, 1.0, {"distinct_nonempty_texts": 2 * base[3]["projection"]["distinct_nonempty_texts"]})
    times = lambda r: [(s["wall_seconds"], s["attempts"], s["completed"]) for s in r[0]["sessions"]]
    costs = lambda r: [round(s["api_cost"], 12) for s in r[0]["sessions"]]
    checks = {
        "recomputed cost equals cost logged at run time": abs(base[0]["recomputed_total"] - base[0]["logged_total"]) < 1e-9,
        "doubling every API rate doubles the measured API subtotal": abs(doubled[0]["recomputed_total"] - 2 * base[0]["recomputed_total"]) < 1e-9,
        "doubling rates doubles each scenario's API cost": all(abs(d["api_cost"] - 2 * b["api_cost"]) < 1e-9 for b, d in zip(base[2], doubled[2])),
        "doubling rates leaves measured time and counts unchanged": times(base) == times(doubled),
        "doubling rates leaves projected time and local compute unchanged": [(s["seconds"], s["local_cost"]) for s in base[2]] == [(s["seconds"], s["local_cost"]) for s in doubled[2]],
        "changing projected volume leaves the measured pilot unchanged": times(base) == times(bigger) and costs(base) == costs(bigger),
        "changing projected volume changes the projection": bigger[2][0]["api_cost"] > base[2][0]["api_cost"],
        "one memo is counted once, not per review": sum(st["stage"] == "memo" for st in base[2][0]["stages"]) == 1 and base[2][0]["stages"][-1]["cost"] < 1,
    }
    for name, ok in checks.items():
        print(("PASS  " if ok else "FAIL  ") + name)
    return all(checks.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rates", type=Path, default=HERE / "rates.csv")
    parser.add_argument("--assumptions", type=Path, default=HERE / "assumptions.json")
    parser.add_argument("--measured", type=Path, default=HERE, help="Folder holding pilot_calls.jsonl, pilot_records.jsonl and "
                        "pilot_measurements.json; report.md and usage.csv are written there (default: the 100-review pilot)")
    parser.add_argument("--rate-multiplier", type=float, default=1.0, help="What-if: multiply every API rate (prints only)")
    parser.add_argument("--distinct-texts", type=int, help="What-if: projected distinct texts (prints only)")
    parser.add_argument("--nonempty-reviews", type=int, help="What-if: projected nonempty reviews (prints only)")
    parser.add_argument("--budget", type=float, help="What-if: spending limit in USD (prints only)")
    parser.add_argument("--self-test", action="store_true", help="Check the calculator's arithmetic properties")
    args = parser.parse_args()
    args.calls, args.records, args.measurements = (args.measured / name for name in ("pilot_calls.jsonl", "pilot_records.jsonl", "pilot_measurements.json"))
    if args.self_test:
        raise SystemExit(0 if self_test(args) else 1)
    overrides = {"distinct_nonempty_texts": args.distinct_texts, "nonempty_reviews": args.nonempty_reviews, "budget_usd": args.budget}
    what_if = args.rate_multiplier != 1 or any(v is not None for v in overrides.values())
    m, unit, scenarios, assumptions, measurements, rates = compute(args, overrides=overrides)
    report = build_report(m, unit, scenarios, assumptions, measurements, rates, args.rate_multiplier)
    cold = next(s for s in m["sessions"] if s["run_type"] == "cold")
    warm = next(s for s in m["sessions"] if s["run_type"] == "warm")
    print(f"Measured cold run: {money(cold['api_cost'])} API, {duration(cold['wall_seconds'])} wall clock, {cold['completed']} completed, {cold['failed_records']} failed")
    print(f"Measured warm run: {money(warm['api_cost'])} API, {duration(warm['wall_seconds'])}, {warm['new_enrichment_calls']} new enrichment calls")
    print(f"All logged attempts, including the failed first attempt: {money(m['recomputed_total'])}")
    for s in scenarios:
        print(f"Full run, {s['name']}{'' if s['reuse'] else ' without reuse'}: {money(s['api_cost'], 2)} API, {duration(s['seconds'])}"
              + ("  ** EXCEEDS BUDGET **" if s["over_budget"] else ""))
    if what_if:
        print("What-if view only: report.md and usage.csv were not rewritten.")
    else:
        (args.measured / "report.md").write_text(report, encoding="utf-8")
        (args.measured / "usage.csv").write_text(usage_csv(m, rates), encoding="utf-8")
        print(f"Wrote {args.measured / 'report.md'} and {args.measured / 'usage.csv'}")


if __name__ == "__main__":
    main()

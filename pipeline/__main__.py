"""Command-line entry point: python3 -m pipeline <command> ...

    ingest   read and profile a CSV, queue pending work            (no model calls)
    rank     recompute the ranking from saved files                (no model calls)
    publish  load a run's saved results into the dashboard database (no model calls)
    enrich   PAID: label pending reviews
    run      PAID: every stage in order for one input CSV; saved work is reused, so a rerun resumes
"""

import argparse
import json
import os
import time
from pathlib import Path

from .common import load_env, write_json
from .ingest import ingest

STAGES = ("ingest", "enrich", "verify", "group", "rank", "memo")


def add_run_options(p):
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--max-spend-usd", required=True, type=float, help="Hard cap on estimated API spend for this session, all stages together")
    p.add_argument("--workers", type=int, default=1, help="Concurrent enrichment requests (start with 1)")
    p.add_argument("--max-rps", type=float, default=10.0, help="Enrichment request starts per second, shared by all workers")
    p.add_argument("--max-seconds", type=float, help="Stop admitting enrichment work after this much wall-clock time")
    p.add_argument("--limit", type=int, help="Label at most this many distinct texts in this session")
    p.add_argument("--save-every", type=int, default=50, help="Texts per saved enrichment batch")
    p.add_argument("--enrich-model", default="jev-1.13.0", help="Pinned enrichment model ID")
    p.add_argument("--enrich-prompt", type=Path, default=Path("prompts/enrich_jev_v2.json"))
    p.add_argument("--lexicon", type=Path, default=Path("labels/entities.json"))
    p.add_argument("--rates", type=Path, default=Path("cost/rates.csv"))


def effort_for(model, effort):
    """The effort setting to send, or None for Haiku 4.5, which does not accept one."""
    return None if model.startswith("claude-haiku-4-5") else effort


def print_enrich(run_id, summary):
    t, c = summary["texts"], summary["calls"]
    print(f"[enrich] session {summary['session']} ({summary['phase']}), stopped because {summary['stop_reason']}")
    print(f"  texts completed {t['completed']:,} · quarantined {t['quarantined']:,} · left pending {summary['texts_pending_at_end']:,}")
    print(f"  calls {c['attempts']:,} ({c['failed']:,} failed) · input tokens {c['input_tokens']:,} · cost ${c['cost_usd']:.6f}")
    print(f"  wall time {summary['wall_seconds']}s · {summary['texts_per_second']} texts/s with {summary['workers']} worker(s)")
    print(f"  review statuses {summary['review_status_counts']}")
    if summary["fatal_detail"]:
        print(f"  provider said: {summary['fatal_detail']}")


def enricher(args, run_dir, ledger=None):
    from .enrich import Enricher  # imported here so offline commands never need the HTTP dependencies
    load_env()
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("TYPESAFE_API_KEY is not set. Copy .env.example to .env and add your key.")
    return Enricher(run_dir, prompt_path=args.enrich_prompt, lexicon_path=args.lexicon, rates_path=args.rates, model=args.enrich_model,
                    api_key=key, max_spend_usd=args.max_spend_usd, workers=args.workers, max_rps=args.max_rps,
                    max_seconds=args.max_seconds, save_every=args.save_every, ledger=ledger, progress=5)


def run_pipeline(args, *, enrich_factory=enricher, claude_factory=None):
    """Every stage in order. Each stage reads the previous stage's saved output and saves its own."""
    from .export import export_membership, export_records
    from .group import group
    from .ledger import SpendLedger, load_rates
    from .memo import memo
    from .rank import rank_run
    from .store import next_session, open_db
    from .verify import verify

    run_id = args.run_id or args.input.stem
    run_dir = args.runs_dir / run_id
    last = STAGES.index(args.stop_after)
    started = time.monotonic()
    timings, results = {}, {}

    def stage(name, work):
        clock = time.monotonic()
        results[name] = work()
        timings[name] = round(time.monotonic() - clock, 3)
        return results[name]

    manifest_path = args.input.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    report = stage("ingest", lambda: ingest(args.input, run_dir, manifest, run_id))
    print(f"[ingest] {report['accounting']['source_rows']:,} rows · pending {report['accounting']['pending_reviews']:,} · "
          f"quarantined {report['accounting']['quarantine_reasons']}")

    ledger = SpendLedger(args.max_spend_usd)
    db = open_db(run_dir)
    session = next_session(db)
    db.close()
    if last >= 1:
        summary = stage("enrich", lambda: enrich_factory(args, run_dir, ledger).run(limit=args.limit, session=session))
        print_enrich(run_id, summary)
        if summary["stop_reason"].startswith("fatal"):
            raise SystemExit("Enrichment stopped on a configuration error; later stages were not run.")
        if summary["stop_reason"] != "queue_empty" and last > 1:
            # Interrupted, or stopped by a spend or time cap: progress is saved. Later stages wait for a complete
            # enrichment, so no verification or memo call is paid for on partial results.
            print(f"[stopped] Enrichment stopped early ({summary['stop_reason']}) with work still pending. Saved progress is in {run_dir}/. "
                  "Run the same command again to resume; completed reviews are not sent again.")
            raise SystemExit(130 if summary["stop_reason"] == "interrupted" else 2)

    db = open_db(run_dir)
    if last >= 2:
        if claude_factory is None:
            from .claude import ClaudeCaller
            load_env()
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
            caller = ClaudeCaller(api_key=os.environ["ANTHROPIC_API_KEY"], rates=load_rates(args.rates), ledger=ledger)
        else:
            caller = claude_factory(ledger)
        v = stage("verify", lambda: verify(run_dir, db, caller, prompt_path=args.verify_prompt, model=args.verify_model,
                                           sample_size=args.verify_sample, seed=args.seed, session=session,
                                           batch_size=args.verify_batch, effort=effort_for(args.verify_model, args.verify_effort)))
        print(f"[verify] {v['compared']} texts compared · agreement {v['agreement']} · planted errors detected "
              f"{v['planted_error_test']['detected']}/{v['planted_error_test']['planted']}" + (f" · stopped: {v['stop_reason']}" if v["stop_reason"] else ""))
    if last >= 3:
        g = stage("group", lambda: group(run_dir, db, caller, rules_path=args.issue_rules, prompt_path=args.group_prompt,
                                         model=args.group_model, session=session, effort=effort_for(args.group_model, args.group_effort)))
        print(f"[group] {g['members']:,} complaint reviews in {g['issues']} issues · {g['unnamed']} without a model name"
              + (f" · stopped: {g['stop_reason']}" if g["stop_reason"] else ""))
    if last >= 4:
        def export_and_rank():
            counts = export_records(run_dir, db)
            export_membership(run_dir, db)
            return {"records": counts, **rank_run(run_dir)[0]}
        r = stage("rank", export_and_rank)
        print(f"[rank] {r['issues']} issues ranked from {r['grouped_complaint_records']:,} complaint records · problems {r['problems'] or 'none'}")
    if last >= 5:
        effort = effort_for(args.memo_model, args.memo_effort)
        m = stage("memo", lambda: memo(run_dir, db, caller, prompt_path=args.memo_prompt, model=args.memo_model, session=session, effort=effort))
        print(f"[memo] {'reused, no new call' if m.get('reused') else 'valid' if m['valid'] else 'REJECTED: ' + '; '.join(m['errors'])}"
              + (f" · recommends {m['recommended_priority']}" if m.get("recommended_priority") else ""))

    by_role = {role: {"attempts": a, "succeeded": s, "input_tokens": i, "output_tokens": o, "cache_read_tokens": cr, "cache_write_tokens": cw,
                      "cost_usd": round(c, 6)} for role, a, s, i, o, cr, cw, c in db.execute(
        "SELECT role, COUNT(*), SUM(outcome = 'succeeded'), SUM(input_tokens), SUM(output_tokens), SUM(cache_read_tokens), "
        "SUM(cache_write_tokens), SUM(cost_usd) FROM calls WHERE session = ? GROUP BY role", (session,))}
    statuses = dict(db.execute("SELECT status, COUNT(*) FROM reviews GROUP BY status"))
    db.close()
    wall = round(time.monotonic() - started, 3)
    summary = {"run_id": run_id, "session": session, "input": str(args.input), "stages_run": list(timings), "stage_seconds": timings,
               "wall_seconds": wall, "calls_this_session": by_role, "cost_usd_this_session": round(sum(r["cost_usd"] for r in by_role.values()), 6),
               "spend_cap_usd": args.max_spend_usd, "workers": args.workers, "review_status_counts": statuses,
               "models": {"enrich": args.enrich_model, "verify": args.verify_model, "group": args.group_model, "memo": args.memo_model},
               "settings": {"max_rps": args.max_rps, "save_every": args.save_every, "verify_sample": args.verify_sample,
                            "verify_batch": args.verify_batch, "seed": args.seed, "memo_effort": effort_for(args.memo_model, args.memo_effort),
                            "verify_effort": effort_for(args.verify_model, args.verify_effort),
                            "group_effort": effort_for(args.group_model, args.group_effort)}}
    write_json(run_dir / f"run_summary_session_{session:03d}.json", summary)
    write_json(run_dir / "run_summary.json", summary)
    print(f"[done] session {session}: {sum(r['attempts'] for r in by_role.values())} model calls, "
          f"${summary['cost_usd_this_session']:.6f} of ${args.max_spend_usd} cap, {wall}s wall clock. Outputs in {run_dir}/")
    return summary


def build_parser():
    parser = argparse.ArgumentParser(prog="pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("ingest", help="Read and profile an input CSV and queue pending work. No model calls.")
    p.add_argument("--input", required=True, type=Path, help="Reviews CSV with the six source columns")
    p.add_argument("--run-id", help="Stable name for this run (default: the input file name without .csv)")
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--course-manifest", type=Path,
                   help="Course manifest.json to check against (default: manifest.json beside the input, if present)")

    p = commands.add_parser("rank", help="Recompute ranking.csv from saved records and membership. No model calls.")
    p.add_argument("--run-id", required=True)
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))

    p = commands.add_parser("pilot-export", help="Copy a pilot's saved measurements into cost/ for the calculator. No model calls.")
    p.add_argument("--run", required=True, type=Path, help="The measured pilot run directory (cold session 1, warm session 2)")
    p.add_argument("--failed-run", type=Path, action="append", default=[], help="An earlier failed attempt to keep on the record")
    p.add_argument("--input", required=True, type=Path, help="The pilot input CSV")
    p.add_argument("--full-run", type=Path, help="A full-corpus run directory, for its measured ingestion time")
    p.add_argument("--out", type=Path, default=Path("cost"))

    p = commands.add_parser("publish", help="Load a run's saved results into the dashboard database. No model calls.")
    p.add_argument("--run-id", required=True)
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--golden-report", type=Path, default=Path("evals/golden/golden_report.json"))
    p.add_argument("--full-corpus-run", default="full", help="Run ID holding the full source file's ingestion report")

    p = commands.add_parser("enrich", help="PAID: label pending reviews with Jev. Resumes from saved progress.")
    p.add_argument("--run-id", required=True, help="A run already created by ingest")
    add_run_options(p)

    p = commands.add_parser("run", help="PAID: run every stage for an input CSV. Reuses saved work, so a rerun resumes.")
    p.add_argument("--input", required=True, type=Path, help="Reviews CSV with the six source columns")
    p.add_argument("--run-id", help="Stable name for this run (default: the input file name without .csv)")
    add_run_options(p)
    p.add_argument("--stop-after", choices=STAGES, default="memo")
    p.add_argument("--verify-sample", type=int, default=100, help="Distinct texts the independent verifier re-labels")
    p.add_argument("--verify-batch", type=int, default=10, help="Reviews per verifier request")
    p.add_argument("--seed", default="verify-v1", help="Seed for the verification sample")
    p.add_argument("--verify-model", default="claude-haiku-5-5")
    p.add_argument("--group-model", default="claude-haiku-5-5")
    p.add_argument("--verify-effort", default="low", help="Thinking effort for the verifier (lowest level that passes the evaluations)")
    p.add_argument("--group-effort", default="low", help="Thinking effort for issue naming")
    p.add_argument("--memo-model", default="claude-opus-5-5")
    p.add_argument("--memo-effort", default="high")
    p.add_argument("--verify-prompt", type=Path, default=Path("prompts/verify_claude_v2.md"))
    p.add_argument("--group-prompt", type=Path, default=Path("prompts/group_claude_v1.md"))
    p.add_argument("--memo-prompt", type=Path, default=Path("prompts/memo_claude_v2.md"))
    p.add_argument("--issue-rules", type=Path, default=Path("labels/issues.json"))
    return parser


def main():
    args = build_parser().parse_args()

    if args.command == "ingest":
        run_id = args.run_id or args.input.stem
        manifest_path = args.course_manifest or args.input.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
        report = ingest(args.input, args.runs_dir / run_id, manifest, run_id)
        a = report["accounting"]
        print(f"Run {run_id}: {a['source_rows']:,} rows read, all accounted for: {a['accounted_for']}")
        print(f"  pending reviews         {a['pending_reviews']:,}")
        print(f"  distinct pending texts  {a['pending_distinct_texts']:,}")
        print(f"  quarantined             {a['quarantine_reasons']}")
        print(f"  rejected rows           {a['rejected_rows']:,}")
        for check in report["expectation_checks"]:
            if not check["ok"]:
                print(f"  MISMATCH {check['check']}: expected {check['expected']}, got {check['actual']}")
        print(f"  expectations met        {report['all_expectations_met']} ({len(report['expectation_checks'])} checks)")
        print(f"Saved {args.runs_dir / run_id}/ingestion_report.json")

    elif args.command == "rank":
        from .rank import rank_run
        report, rows = rank_run(args.runs_dir / args.run_id)
        print(f"Ranked {report['issues']} issues from {report['grouped_complaint_records']:,} complaint records, no model calls. "
              f"Problems: {report['problems'] or 'none'}")
        for row in rows[:10]:
            print(f"  {row['rank']:>2}  {row['issue_id']:<34} count {row['complaint_count']:>7,}  mean {row['mean_severity']}  score {row['priority_score']:>8,}")

    elif args.command == "publish":
        from .publish import main_publish
        main_publish(args)

    elif args.command == "pilot-export":
        from .pilot import export_pilot
        print(json.dumps(export_pilot(args.run, args.failed_run, args.input, args.full_run, args.out, build_parser()), indent=1))

    elif args.command == "enrich":
        run_dir = args.runs_dir / args.run_id
        if not (run_dir / "state.db").exists():
            raise SystemExit(f"{run_dir} has no state. Run ingest first: python3 -m pipeline ingest --input <csv> --run-id {args.run_id}")
        print_enrich(args.run_id, enricher(args, run_dir).run(limit=args.limit))

    elif args.command == "run":
        run_pipeline(args)


if __name__ == "__main__":
    main()

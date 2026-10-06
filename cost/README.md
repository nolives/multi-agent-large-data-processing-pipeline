# Cost and runtime calculator

A real 100-review pilot of the full pipeline, saved as evidence, plus a calculator that recomputes cost and projects
the full run from that evidence. Start with [report.md](report.md).

## Offline replay (default: no API key, no network, no model calls)

```sh
python3 cost/calculator.py
```

This reads the saved pilot files, recomputes every cost as `billed_units × price_per_unit` from `rates.csv`, and
rewrites `report.md` and `usage.csv`. It uses only the Python standard library.

Check the arithmetic and try changes without touching the saved report:

```sh
python3 cost/calculator.py --self-test            # the properties listed below
python3 cost/calculator.py --rate-multiplier 2    # doubles API spend; measured time and local cost do not move
python3 cost/calculator.py --distinct-texts 250000 --budget 20
```

Refresh the estimate from a later checkpoint's saved measurements:

```sh
python3 cost/calculator.py --measured cost/refresh_500
```

To change a price, an assumption or a control, edit `rates.csv` or `assumptions.json` and rerun the first command.

`--self-test` confirms that: recomputed cost equals the cost logged at run time; doubling every rate doubles the API
subtotal and every scenario's API cost; doubling rates leaves measured and projected time and local compute
unchanged; changing the projected volume leaves the measured pilot unchanged; and one memo is counted once.

## Paid pilot execution (explicit, separate)

Opening or running the calculator never starts a paid call. The pilot itself is a different command that needs
`TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY` in a local `.env`, and must be given a spend cap:

```sh
.venv/bin/python -m pipeline run --input data/cost_100.csv --run-id pilot_100 --max-spend-usd 1 --workers 1   # cold: new run ID, empty result cache
.venv/bin/python -m pipeline run --input data/cost_100.csv --run-id pilot_100 --max-spend-usd 1 --workers 1   # warm: same command again
.venv/bin/python -m pipeline pilot-export --run runs/pilot_100 --input data/cost_100.csv --full-run runs/full --out cost
```

## Files

| File | What it holds |
|---|---|
| `calculator.py` | The calculator. Offline by default. |
| `report.md` | Measured 100-review results (cold and warm), full-run estimates, controls. Generated. |
| `pilot_records.jsonl` | One final record per pilot review ID, with the original row hash and the common labels. |
| `pilot_calls.jsonl` | Every attempted model call: run, session, cold or warm, role, exact model, settings version, review IDs, usage, timing, outcome, request IDs. Includes the failed first attempt. No API keys. |
| `pilot_measurements.json` | Input checksum, wall-clock and stage times, counts, and per-stage settings. |
| `rates.csv` | Editable prices in their billing units, with currency, the date checked and the source link. |
| `usage.csv` | Billed units per run, stage, model and billing item, with recomputed cost. Each row maps to the calls in `pilot_calls.jsonl` that share its run, session, role and model. Generated. |
| `assumptions.json` | Editable projection inputs: budget, volumes, verification sample, retry and fallback rates, workers. |
| `pilot/` | Console output of the cold run, the warm run, and the failed first attempt. |
| `refresh_500/` | The same evidence and report for the 500-review checkpoint (`checkpoint_500.csv`), measured cold and warm. |

## What is measured and what is estimated

- **Measured:** everything in section 1 of the report. Usage is what each API response reported; time is from a clock.
- **Estimated:** everything in section 2. Multi-worker speed is modeled from the one-worker measurement, and the
  fallback line is modeled because the pipeline has no fallback role yet.
- **Unknown:** local compute cost, and the time for export and ranking at full scale. They are shown as unknown, not as zero.
- **Not reconciled:** the figures have not been compared with the providers' billing dashboards.

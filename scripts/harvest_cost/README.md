# harvest_cost

Operator tool: price TwitterAPI harvest spend from cycle summary JSON.

## Run

```bash
# from repo root
python -m scripts.harvest_cost --latest
python -m scripts.harvest_cost --last-cycles 4
python -m scripts.harvest_cost --since 2026-08-10T00:00:00Z --until 2026-08-11T00:00:00Z
python -m scripts.harvest_cost --input data/runs/SOME_RUN.json --out report.md
python -m scripts.harvest_cost --tweet-credits 20 --input run.json
```

Legacy alias: `python scripts/harvester_cycle_cost.py …` (delegates here).

## Rates

Defaults from `docs/external_vendors/twitterapi*/twitterapi_index.md`.
Override with `--pricing-file`, `--tweet-credits`, `--call-floor-credits`, `--credits-per-usd`.

## Cycle emit

`monitor/cycle.py` calls `scripts.harvest_cost.emit.finalize_and_persist` after each cycle and writes `data/runs/<run_id>.json`.

## Layout

| Module | Role |
|--------|------|
| `pricing.py` | Parse pricing doc + CLI overrides |
| `engine.py` | Pure cost math + markdown render |
| `emit.py` | Persist cycle summary JSON |
| `cli.py` | argparse entry |

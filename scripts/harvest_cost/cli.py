#!/usr/bin/env python3
"""Price harvest cycle spend from structured cycle summary JSON.

Usage:
  python -m scripts.harvest_cost --latest
  python -m scripts.harvest_cost --last-cycles 4
  python -m scripts.harvest_cost --since 2026-08-10T00:00:00Z --until 2026-08-10T12:00:00Z
  python -m scripts.harvest_cost --input path/to/run.json --out report.md
  python -m scripts.harvest_cost --tweet-credits 20 --input run.json

Rates default from docs/external_vendors/twitterapi*/twitterapi_index.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from scripts.harvest_cost.engine import cost_period, render_markdown
from scripts.harvest_cost.pricing import PricingError, load_pricing


def _parse_dt(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _summary_finished_at(summary: dict[str, Any]) -> datetime | None:
    raw = summary.get("finished_at") or summary.get("started_at")
    if not raw:
        return None
    try:
        return _parse_dt(str(raw))
    except ValueError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


def _iter_run_files(runs_dir: Path) -> list[Path]:
    if not runs_dir.is_dir():
        return []
    files = [
        p
        for p in runs_dir.glob("*.json")
        if p.name != "latest.json" and p.is_file()
    ]
    return sorted(files, key=lambda p: p.stat().st_mtime)


def select_summaries(
    *,
    runs_dir: Path,
    input_paths: list[Path],
    latest: bool,
    last_cycles: int | None,
    since: datetime | None,
    until: datetime | None,
    stdin_data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []

    if stdin_data is not None:
        summaries.append(stdin_data)

    for p in input_paths:
        if p.is_dir():
            for f in _iter_run_files(p):
                summaries.append(_load_json(f))
        else:
            summaries.append(_load_json(p))

    if not summaries and (latest or last_cycles is not None or since or until):
        for f in _iter_run_files(runs_dir):
            try:
                summaries.append(_load_json(f))
            except (OSError, ValueError, json.JSONDecodeError):
                continue

    # Filter by finished_at when window set
    if since or until:
        filtered: list[dict[str, Any]] = []
        for s in summaries:
            ft = _summary_finished_at(s)
            if ft is None:
                # fall back to no filter exclusion if mtime-only files without stamp
                continue
            if since and ft < since:
                continue
            if until and ft >= until:
                continue
            filtered.append(s)
        summaries = filtered

    # Sort by finished_at then keep last N
    def sort_key(s: dict[str, Any]) -> str:
        return str(s.get("finished_at") or s.get("started_at") or "")

    summaries.sort(key=sort_key)

    n = last_cycles
    if latest and n is None:
        n = 1
    if n is not None:
        if n < 1:
            raise ValueError("--last-cycles must be >= 1")
        summaries = summaries[-n:]

    return summaries


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute TwitterAPI harvester cycle costs from cycle summary JSON"
    )
    p.add_argument(
        "--pricing-file",
        type=Path,
        default=None,
        help="Pricing markdown (default: docs/external_vendors/twitterapi*/twitterapi_index.md)",
    )
    p.add_argument("--tweet-credits", type=float, default=None)
    p.add_argument("--call-floor-credits", type=float, default=None)
    p.add_argument("--credits-per-usd", type=float, default=None)
    p.add_argument("--since", type=str, default=None, help="UTC start (ISO date/datetime)")
    p.add_argument("--until", type=str, default=None, help="UTC end exclusive (ISO)")
    p.add_argument("--latest", action="store_true", help="Only the most recent cycle")
    p.add_argument("--last-cycles", type=int, default=None, metavar="N")
    p.add_argument(
        "--runs-dir",
        type=Path,
        default=_PKG_ROOT / "data" / "runs",
        help="Directory of cycle summary JSON files",
    )
    p.add_argument(
        "--input",
        type=Path,
        action="append",
        default=[],
        help="Summary JSON file or directory (repeatable). Use - for stdin.",
    )
    p.add_argument("--out", type=Path, default=None, help="Write markdown report here")
    p.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        dest="fmt",
    )
    p.add_argument(
        "--require-cycles",
        action="store_true",
        help="Exit 2 if no cycles match the window",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _PKG_ROOT

    try:
        rates = load_pricing(
            pricing_file=args.pricing_file,
            repo_root=repo_root,
            tweet_credits=args.tweet_credits,
            call_floor_credits=args.call_floor_credits,
            credits_per_usd=args.credits_per_usd,
        )
    except PricingError as exc:
        print(f"pricing error: {exc}", file=sys.stderr)
        return 1

    stdin_data = None
    input_paths: list[Path] = []
    for raw in args.input:
        if str(raw) == "-":
            stdin_data = json.load(sys.stdin)
            if not isinstance(stdin_data, dict):
                print("stdin must be a JSON object", file=sys.stderr)
                return 1
        else:
            input_paths.append(raw)

    since = _parse_dt(args.since) if args.since else None
    until = _parse_dt(args.until) if args.until else None

    try:
        summaries = select_summaries(
            runs_dir=args.runs_dir,
            input_paths=input_paths,
            latest=bool(args.latest),
            last_cycles=args.last_cycles,
            since=since,
            until=until,
            stdin_data=stdin_data,
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 1

    if not summaries:
        msg = "no cycle summaries matched"
        if args.require_cycles or args.latest or args.last_cycles or since or until:
            print(msg, file=sys.stderr)
            return 2
        print(msg, file=sys.stderr)
        return 2

    period = cost_period(summaries, rates)

    if args.fmt == "json":
        payload = {
            "rates": {
                "tweet_credits": rates.tweet_credits,
                "call_floor_credits": rates.call_floor_credits,
                "credits_per_usd": rates.credits_per_usd,
                "source_path": rates.source_path,
            },
            "n_cycles": len(period.cycles),
            "total_credits": period.total_credits,
            "total_usd": period.total_usd(),
            "cycles": [
                {
                    "run_id": c.run_id,
                    "finished_at": c.finished_at,
                    "total_credits": c.total_credits,
                    "lines": [
                        {
                            "source": ln.source,
                            "label": ln.label,
                            "n_results": ln.n_results,
                            "credits": ln.credits,
                            "notes": ln.notes,
                        }
                        for ln in c.lines
                    ],
                }
                for c in period.cycles
            ],
        }
        out_text = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        out_text = render_markdown(period)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(out_text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

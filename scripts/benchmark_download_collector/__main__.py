"""Run from the repository: python -m scripts.benchmark_download_collector."""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta

import httpx

from .collect import collect, load_snapshots
from .demo import demo
from .identity import days, read_json, validate_inputs, write_new
from .report import render_report
from .series import build_report
from .sources import Budget

KEY_ENV = "PUSHINWEIGHT_OPENROUTER_DATA_API_KEY"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Isolated Arena/HF/OpenRouter observations and daily brand reports."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser(
        "validate", help="Validate a frozen catalog and reviewed mappings (offline)."
    )
    gather = sub.add_parser(
        "collect", help="Make bounded data API requests and save a new snapshot."
    )
    for command in (validate, gather):
        command.add_argument("--catalog", required=True)
        command.add_argument("--mapping", required=True)
    gather.add_argument("--directory", required=True)
    gather.add_argument("--start-date", required=True)
    gather.add_argument(
        "--end-date", default=(datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    )
    gather.add_argument(
        "--sources",
        nargs="+",
        choices=("arena", "hf", "openrouter", "opencode"),
        default=["arena", "hf", "openrouter"],
    )
    gather.add_argument("--max-requests", type=int, default=80)
    gather.add_argument("--max-seconds", type=float, default=180)
    gather.add_argument("--max-bytes", type=int, default=4 * 1024 * 1024)
    gather.add_argument("--max-pages", type=int, default=50)
    gather.add_argument(
        "--arena-history",
        action="store_true",
        help="Request historical publications through the HF filtered API (may need index warm-up).",
    )
    report = sub.add_parser(
        "report", help="Render an offline HTML report from saved snapshots."
    )
    report.add_argument("--directory", required=True)
    report.add_argument("--start-date", required=True)
    report.add_argument("--end-date", required=True)
    report.add_argument("--output", required=True)
    template = sub.add_parser(
        "mapping-template",
        help="List canonical products and optional unresolved source IDs; never guess links.",
    )
    template.add_argument("--catalog", required=True)
    template.add_argument(
        "--directory", help="Optional collected snapshots for exact provider model IDs."
    )
    template.add_argument("--output", required=True)
    example = sub.add_parser(
        "demo",
        help="Create synthetic snapshots and a report, without network or database access.",
    )
    example.add_argument("--directory", required=True)
    example.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"validate", "collect"}:
            catalog, mapping = read_json(args.catalog), read_json(args.mapping)
            validate_inputs(catalog, mapping)
            if args.command == "validate":
                print(
                    "Catalog, official HF selection and exact source mappings are valid."
                )
                return 0
            days(args.start_date, args.end_date)
            with httpx.Client(trust_env=False) as client:
                budget = Budget(
                    client,
                    max_requests=args.max_requests,
                    max_seconds=args.max_seconds,
                    max_bytes=args.max_bytes,
                )
                path, snapshot = collect(
                    catalog,
                    mapping,
                    args.directory,
                    budget,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    selected=args.sources,
                    openrouter_key=os.environ.get(KEY_ENV),
                    max_pages=args.max_pages,
                    arena_history=args.arena_history,
                )
            statuses = {
                name: result["status"] for name, result in snapshot["sources"].items()
            }
            print(json.dumps({"snapshot": str(path), "sources": statuses}))
            return 2 if any(v in {"error", "partial"} for v in statuses.values()) else 0
        if args.command == "mapping-template":
            catalog = read_json(args.catalog)
            value = {"schema_version": 1, "hf_product_keys": [], "mappings": []}
            validate_inputs(catalog, value)
            value["instructions"] = (
                "Select official HF product keys; add exact source/source_id/product_key/evidence entries after review. Candidates are not mappings."
            )
            value["canonical_products"] = catalog["products"]
            if args.directory:
                snapshots = load_snapshots(args.directory)
                report_data = build_report(
                    snapshots,
                    catalog["posts"]["start_date"],
                    catalog["posts"]["end_date"],
                )
                value["unresolved_source_ids"] = report_data["unresolved"]
            write_new(args.output, value)
            print(args.output)
            return 0
        if args.command == "demo":
            start, end = demo(args.directory)
        else:
            start, end = args.start_date, args.end_date
        data = build_report(load_snapshots(args.directory), start, end)
        render_report(data, args.output)
        print(args.output)
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"Collector input/output error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

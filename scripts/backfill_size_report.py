"""OpenAI and Anthropic collection size report (plan U8, requirements R14-R24).

Plan: docs/plans/2026-10-27-113859-ops-oai-anthropic-size-20261027-plan.md

The report never connects to a database. The operator saves two read-only
query results with the Render CLI and this script turns them into figures:

1. The test job's records in xbackfiller (KTD11):

   render psql dpg-dbfemu2vcj2c73fsafe0-a -o json --command \
     "$(.venv/bin/python -m scripts.backfill_size_report --print-xbackfiller-sql --job-id JOB_UUID)" \
     > DIR/xbackfiller.json

2. Production's saved posts for the same window and its US Pacific date:

   render psql dpg-d9koekqjobas73fvjqng-a -o json --command \
     "$(.venv/bin/python -m scripts.backfill_size_report --print-production-sql \
        --window-start-epoch START --window-end-epoch END)" > DIR/production.json

3. The new routes' window share from the pilot's slices (R21):

   .venv/bin/python -m scripts.backfill_size_report \
     --pilot-share-from ~/.local/share/render-operations/2026-10-27-oai-anthropic-volume-pilot/summaries.json \
     --pilot-slices 2,3,4 > DIR/pilot-share.json

4. The limits file at the deployed production revision (R23):

   git show e5edf737:config.yaml > DIR/config-e5edf737.yaml

5. The report, written to docs/analysis/<JST timestamp>-oai-anthropic-size-report.md and .json:

   .venv/bin/python -m scripts.backfill_size_report \
     --xbackfiller DIR/xbackfiller.json --production DIR/production.json \
     --frozen-queries docs/analysis/2026-10-27-215214-oai-anthropic-frozen-queries.json \
     --limits-config DIR/config-e5edf737.yaml --pilot-share DIR/pilot-share.json \
     [--size-before DIR/size-before.json] [--size-after DIR/size-after.json] \
     [--production-daily DIR/production-daily.json]

Spend watch during enrichment (R24): save the xbackfiller query with
``--watch-only`` (it skips the collection records) and run
``--watch DIR/watch.json``. The command exits with status 3 when the trigger
holds, so a monitoring loop can stop on it.

Every computation is a pure function over plain rows so the tests need no
database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
XBACKFILLER_SQL_PATH = ROOT / "scripts" / "backfill_size_report_xbackfiller.sql"
PRODUCTION_SQL_PATH = ROOT / "scripts" / "backfill_size_report_production.sql"
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "analysis"

XBACKFILLER_FORMAT = "oai-anthropic-size-input/v1"
PRODUCTION_FORMAT = "oai-anthropic-size-production/v1"
PILOT_SHARE_FORMAT = "oai-anthropic-pilot-share/v1"
REPORT_FORMAT = "oai-anthropic-size-report/v1"
XBACKFILLER_DATABASE = "xbackfiller"
FROZEN_QUERIES_SHA256 = "3d2c9c17114bd3de7a7070c60e35ad14eb54236fbf2efd048f657e804c994dec"

PACIFIC = ZoneInfo("America/Los_Angeles")
JST = ZoneInfo("Asia/Tokyo")

# R16: TwitterAPI.io search pricing used by the pilot and the plan.
CREDITS_PER_RESULT = 15
MIN_CREDITS_PER_REQUEST = 15
NO_BODY_MAX_CREDITS = 300  # a page holds at most 20 posts
ERROR_BODY_MAX_CREDITS = 15
CREDITS_PER_USD = 100_000
SEARCH_REQUEST_LIMIT = 7_000  # R10

# R22-R23: production runs every 15 minutes.
RUNS_PER_DAY = 96
ENGAGEMENT_REFRESH_CREDITS_PER_POST = 15

# R15: the brands this test adds. Identity comes from this constant, not from
# Brand.is_sentinel, because switch-off (U10) marks these two as sentinels.
NEW_BRANDS = frozenset({"openai", "anthropic"})

# R24: owner's expected rate.
R24_SPEND_USD = Decimal(2)
R24_PER_POST_USD = Decimal("0.0008")
WATCH_TRIGGER_EXIT = 3

# R18: tables only the backfill writes. Everything else is a table production
# would also grow. Production's harvest writes its own collection_* lineage
# rows too, so this split is conservative toward "bookkeeping".
BOOKKEEPING_TABLE_PREFIXES = ("collection_",)
BOOKKEEPING_TABLES = frozenset({"provider_batches", "original_content_calls"})

# R19.
EXCLUDED_PRODUCTION_SOURCES = ("RARE_EXTRA", "SPECIALEVENTS1", "SPECIALEVENTS2")
BASELINE_LABEL = (
    "The baseline excludes RARE_EXTRA and the two special-events searches "
    "(SPECIALEVENTS1, SPECIALEVENTS2, live from deployed revision e5edf737)."
)
SPECIAL_EVENTS_NOTE = (
    "Those searches have their own shared budget, so their search volume does not change "
    "with the new brands. Their posts that mention OpenAI or Anthropic would gain tracked "
    "tags; that added classification is not measured here."
)
RUN_TIME_NOTE = (
    "Run time per 15-minute run is not measured by this test: the backfiller runs a "
    "different execution shape. A staging trial of run_cycle is needed to measure it."
)

# R19: the pilot's estimates. Window figures come from the plan's Sizing
# Assumptions; per-day figures from docs/analysis/2026-10-27-221500-oai-anthropic-volume-pilot.md.
PILOT_WINDOW_ESTIMATES = {
    "source": "plan Sizing Assumptions (pilot's three in-window slices, 2026-10-25 Pacific)",
    "requests": {"production": 1_100, "new": 2_300, "total": 3_400},
    "search_usd": {"production": 0.73, "new": 3.97, "total": 4.70},
    "fetched": {"production": 4_100, "new": 21_000, "net_new": 20_200, "total": 24_000},
    "kept": {"production": 2_800, "new": 13_000, "total": 16_000},
}
PILOT_DAY_ESTIMATES = {
    "source": "docs/analysis/2026-10-27-221500-oai-anthropic-volume-pilot.md (2026-10-26 JST)",
    "baseline_fetched": 23_300,
    "new_fetched": 118_500,
    "net_new_fetched": 114_500,
    "net_new_kept": 73_000,
    "baseline_search_usd": 4.02,
    "new_search_usd": 22.86,
    "production_saved_posts": 15_988,
}


# ---------------------------------------------------------------------------
# SQL placeholders
# ---------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")
_UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_SAFE_LITERAL = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|TRUE|FALSE|[0-9]{1,12}")
_EPOCH_MIN, _EPOCH_MAX = 1_577_836_800, 4_102_444_800  # 2020-01-01 .. 2100-01-01


def validate_job_id(value: Any) -> str:
    """Return the canonical lower-case UUID text, or raise ValueError."""
    if not isinstance(value, str) or not _UUID_TEXT.fullmatch(value):
        raise ValueError(f"job id must be a UUID such as 0b5e3d1c-6f0e-4d6a-9f51-2f3f6c1b9a10, got {value!r}")
    return str(uuid.UUID(value))


def validate_epoch(value: Any) -> int:
    """Accept only an int Unix epoch between 2020 and 2100."""
    if type(value) is not int or not _EPOCH_MIN <= value < _EPOCH_MAX:
        raise ValueError(f"epoch must be an integer between 2020 and 2100, got {value!r}")
    return value


def render_sql(template: str, params: Mapping[str, str]) -> str:
    """Fill every placeholder with an already-validated literal."""
    names = set(_PLACEHOLDER.findall(template))
    if names != set(params):
        raise ValueError(f"placeholders {sorted(names)} do not match parameters {sorted(params)}")
    for name, value in params.items():
        if not isinstance(value, str) or not _SAFE_LITERAL.fullmatch(value):
            raise ValueError(f"unsafe value for {name}: {value!r}")
    return _PLACEHOLDER.sub(lambda match: params[match.group(1)], template)


def xbackfiller_sql(job_id: Any, *, include_collection: bool = True, template: str | None = None) -> str:
    template = XBACKFILLER_SQL_PATH.read_text() if template is None else template
    return render_sql(template, {
        "job_id": validate_job_id(job_id),
        "include_collection": "TRUE" if include_collection is True else "FALSE",
    })


def pacific_day_bounds(epoch: int) -> tuple[int, int]:
    """US Pacific midnight to midnight around ``epoch`` (23 or 25 hours on DST days)."""
    local = datetime.fromtimestamp(validate_epoch(epoch), PACIFIC)
    day = local.date()
    following = day + timedelta(days=1)
    start = datetime(day.year, day.month, day.day, tzinfo=PACIFIC)
    end = datetime(following.year, following.month, following.day, tzinfo=PACIFIC)
    return int(start.timestamp()), int(end.timestamp())


def production_sql(window_start_epoch: Any, window_end_epoch: Any, *, template: str | None = None) -> str:
    start, end = validate_epoch(window_start_epoch), validate_epoch(window_end_epoch)
    if end <= start:
        raise ValueError("window end must be after window start")
    day_start, day_end = pacific_day_bounds(start)
    if end > day_end:
        raise ValueError("the window must lie inside one US Pacific calendar day")
    template = PRODUCTION_SQL_PATH.read_text() if template is None else template
    return render_sql(template, {
        "window_start_epoch": str(start), "window_end_epoch": str(end),
        "day_start_epoch": str(day_start), "day_end_epoch": str(day_end),
    })


# ---------------------------------------------------------------------------
# Loading saved query output
# ---------------------------------------------------------------------------


def _find_document(value: Any, expected_format: str, depth: int = 0) -> dict | None:
    if depth > 10:
        return None
    if isinstance(value, dict):
        if value.get("format") == expected_format:
            return value
        children: Iterable[Any] = value.values()
    elif isinstance(value, list):
        children = value
    elif isinstance(value, str) and expected_format in value:
        try:
            return _find_document(json.loads(value), expected_format, depth + 1)
        except ValueError:
            return None
    else:
        return None
    for child in children:
        found = _find_document(child, expected_format, depth + 1)
        if found is not None:
            return found
    return None


def load_document(text: str, expected_format: str) -> dict:
    """Find the report document in Render CLI output (JSON, CSV or plain text)."""
    texts = [text]
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    found = _find_document(parsed, expected_format) if parsed is not None else None
    if found is not None:
        return found
    # `render psql -o json` wraps psql's aligned table text in {"output": "..."}.
    if isinstance(parsed, dict):
        texts.extend(value for value in parsed.values() if isinstance(value, str))
    decoder = json.JSONDecoder()
    for line in (line for candidate in texts for line in candidate.splitlines()):
        if expected_format not in line:
            continue
        for variant in (line, line.replace('""', '"')):
            start = variant.find("{")
            while start != -1:
                try:
                    value, _ = decoder.raw_decode(variant, start)
                except ValueError:
                    start = variant.find("{", start + 1)
                    continue
                found = _find_document(value, expected_format)
                if found is not None:
                    return found
                break
    raise ValueError(
        f"no {expected_format} document found; save the full output of the read-only query "
        "(psql must print the SELECT result, not only the last statement)"
    )


def load_table_sizes(text: str) -> dict[str, int]:
    """Accept a saved xbackfiller document, {table: bytes}, or [{table, bytes}] rows."""
    try:
        return {str(k): int(v) for k, v in load_document(text, XBACKFILLER_FORMAT)["table_sizes"].items()}
    except (ValueError, KeyError, TypeError):
        pass
    value = json.loads(text)
    if isinstance(value, dict) and value and all(isinstance(v, int) for v in value.values()):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, list):
        sizes = {}
        for row in value:
            name = row.get("table") or row.get("relname") or row.get("table_name")
            size = row.get("bytes", row.get("size", row.get("pg_total_relation_size")))
            if name is None or size is None:
                raise ValueError(f"size row needs a table name and a byte count: {row!r}")
            sizes[str(name)] = int(size)
        return sizes
    raise ValueError("unrecognised table size snapshot")


# ---------------------------------------------------------------------------
# Routes and runs (R14, KTD11)
# ---------------------------------------------------------------------------


def route_name(scope_key: str, route_metadata: Mapping[str, Any] | None = None) -> str:
    meta = (route_metadata or {}).get(scope_key)
    if isinstance(meta, Mapping) and meta.get("name"):
        return str(meta["name"])
    return str(scope_key).rsplit(":", 2)[0]


def slice_bounds(scope_key: str) -> tuple[int, int] | None:
    parts = str(scope_key).rsplit(":", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        return int(parts[1]), int(parts[2])
    return None


def _when(value: Any) -> datetime:
    return datetime.fromisoformat(str(value))


def select_report_run(doc: Mapping[str, Any]) -> str:
    """The job's last successful run, else its latest completed run.

    Resumed jobs copy every scope row onto the next run, so only one run's
    scopes may be read. The SQL makes the same choice; a disagreement stops.
    """
    job = doc.get("job")
    if not job:
        raise ValueError("the test job was not found in the saved output")
    chosen = job.get("last_success_id")
    if not chosen:
        completed = [run for run in doc.get("runs") or [] if run.get("completed_at")]
        if not completed:
            raise ValueError("the test job has no completed run to report on")
        chosen = max(completed, key=lambda run: (_when(run["completed_at"]), str(run.get("started_at") or "")))["id"]
    reported = doc.get("report_run_id")
    if reported is not None and str(reported) != str(chosen):
        raise ValueError(f"saved report run {reported} differs from the selected run {chosen}")
    return str(chosen)


def report_scopes(doc: Mapping[str, Any]) -> list[dict]:
    run_id = select_report_run(doc)
    return [row for row in doc.get("scopes") or [] if str(row.get("run_id")) == run_id]


@dataclass
class RouteSet:
    received: set[str] = field(default_factory=set)
    kept: set[str] = field(default_factory=set)
    dropped: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    pages: int = 0
    envelopes: int = 0
    raw_count: int = 0
    slices: int = 0
    outcomes: Counter = field(default_factory=Counter)
    request_raw_counts: dict[str, int] = field(default_factory=dict)


def route_post_sets(scopes: Iterable[Mapping[str, Any]], route_metadata: Mapping[str, Any] | None = None) -> dict[str, RouteSet]:
    """Group one run's scope rows by route, deduplicating post IDs."""
    routes: dict[str, RouteSet] = defaultdict(RouteSet)
    for row in scopes:
        key = str(row["scope_key"])
        target = routes[route_name(key, route_metadata)]
        target.slices += 1
        target.outcomes[str(row.get("outcome") or "unknown")] += 1
        for index, env in enumerate(row.get("envelopes") or []):
            target.envelopes += 1
            target.pages += int(env.get("pages_received") or 1)
            target.raw_count += int(env.get("raw_count") or 0)
            target.received.update(str(pid) for pid in env.get("received_post_ids") or [] if pid)
            target.kept.update(str(pid) for pid in env.get("post_ids") or [] if pid)
            for item in env.get("exclusions") or []:
                pid = item.get("post_id")
                marker = str(pid) if pid else ("no-id", key, index, item.get("appearance"))
                target.dropped[str(item.get("reason") or "unknown")].add(marker)
            if env.get("prefetch_request_id") and env.get("raw_count") is not None:
                target.request_raw_counts[str(env["prefetch_request_id"])] = int(env["raw_count"])
    return dict(routes)


def _union(sets: Iterable[set]) -> set:
    merged: set = set()
    for item in sets:
        merged |= item
    return merged


def _route_row(route: RouteSet) -> dict:
    dropped = {reason: len(ids) for reason, ids in sorted(route.dropped.items())}
    return {
        "fetched": len(route.received), "kept": len(route.kept), "dropped": dropped,
        "dropped_total": sum(dropped.values()), "pages": route.pages, "envelopes": route.envelopes,
        "slices": route.slices, "raw_count": route.raw_count,
        "terminal_state": dict(sorted(route.outcomes.items())),
    }


def collection_summary(route_sets: Mapping[str, RouteSet], production_routes: Iterable[str],
                       new_routes: Iterable[str]) -> dict:
    """R14 per-route rows plus group and overall unique counts."""
    production, new = set(production_routes), set(new_routes)
    groups = {"production": [n for n in route_sets if n in production], "new": [n for n in route_sets if n in new]}

    def group(names: list[str]) -> dict:
        members = [route_sets[n] for n in names]
        return {"fetched": len(_union(r.received for r in members)), "kept": len(_union(r.kept for r in members)),
                "pages": sum(r.pages for r in members), "routes": sorted(names)}

    return {
        "routes": {name: _route_row(route_sets[name]) for name in sorted(route_sets)},
        "groups": {name: group(names) for name, names in groups.items()},
        "totals": {**group(list(route_sets)), "routes": len(route_sets)},
        "unclassified_routes": sorted(set(route_sets) - production - new),
    }


# ---------------------------------------------------------------------------
# Growth (R15)
# ---------------------------------------------------------------------------

BASELINE = "baseline_equivalent"
PRODUCTION_UNTAGGED = "production_route_untagged"
PRODUCTION_NEW_KEYWORD = "production_route_new_keyword"
NEW_ROUTES_ONLY = "new_routes_only"
PRODUCTION_FETCHED_NEW_KEPT = "production_fetched_new_route_kept"
INCREMENTAL_BUCKETS = (PRODUCTION_NEW_KEYWORD, NEW_ROUTES_ONLY, PRODUCTION_FETCHED_NEW_KEPT)
BUCKET_LABELS = {
    BASELINE: "Kept on a production search with a tag from the current brands",
    PRODUCTION_UNTAGGED: "Kept on a production search with no brand tag (anomaly check)",
    PRODUCTION_NEW_KEYWORD: "Production search, kept only because of an OpenAI/Anthropic tag",
    NEW_ROUTES_ONLY: "Fetched only by the new searches",
    PRODUCTION_FETCHED_NEW_KEPT: "Fetched by a production search but kept only by a new search",
}


def _baseline_tags(tags: Iterable[str]) -> set[str]:
    return {tag for tag in tags if tag not in NEW_BRANDS}


def classify_kept_posts(route_sets: Mapping[str, RouteSet], post_tags: Mapping[str, Iterable[str]],
                        production_routes: Iterable[str]) -> dict[str, str]:
    production = set(production_routes)
    kept_production = _union(r.kept for n, r in route_sets.items() if n in production)
    received_production = _union(r.received for n, r in route_sets.items() if n in production)
    buckets = {}
    for post in _union(r.kept for r in route_sets.values()):
        tags = {str(tag).casefold() for tag in post_tags.get(post, ())}
        if post in kept_production:
            if _baseline_tags(tags):
                buckets[post] = BASELINE
            elif tags & NEW_BRANDS:
                buckets[post] = PRODUCTION_NEW_KEYWORD
            else:
                buckets[post] = PRODUCTION_UNTAGGED
        elif post in received_production:
            buckets[post] = PRODUCTION_FETCHED_NEW_KEPT
        else:
            buckets[post] = NEW_ROUTES_ONLY
    return buckets


def brand_set_key(tags: Iterable[str]) -> str:
    tags = {str(tag).casefold() for tag in tags}
    parts = sorted(tags & NEW_BRANDS)
    if _baseline_tags(tags):
        parts.append("existing brand")
    return "+".join(parts) or "no tag"


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return float(numerator) / float(denominator)


def growth_summary(route_sets: Mapping[str, RouteSet], post_tags: Mapping[str, Iterable[str]],
                   production_routes: Iterable[str], new_routes: Iterable[str],
                   buckets: Mapping[str, str] | None = None) -> dict:
    production, new = set(production_routes), set(new_routes)
    buckets = classify_kept_posts(route_sets, post_tags, production) if buckets is None else buckets
    counts = Counter(buckets.values())
    incremental = [post for post, bucket in buckets.items() if bucket in INCREMENTAL_BUCKETS]
    by_brand = Counter(brand_set_key(post_tags.get(post, ())) for post in incremental)
    baseline_fetched = _union(r.received for n, r in route_sets.items() if n in production)
    new_fetched = _union(r.received for n, r in route_sets.items() if n in new)
    baseline_kept = counts[BASELINE]
    by_discovery = {bucket: counts[bucket] for bucket in INCREMENTAL_BUCKETS}
    net_new = len(new_fetched - baseline_fetched)
    return {
        "baseline_equivalent_kept": baseline_kept,
        "production_route_untagged_kept": counts[PRODUCTION_UNTAGGED],
        "incremental_kept": {
            "total": len(incremental),
            "by_discovery": by_discovery,
            "by_brand_set": dict(sorted(by_brand.items())),
        },
        "kept_with_new_brands": len(buckets),
        "baseline_fetched": len(baseline_fetched),
        "new_routes_fetched": len(new_fetched),
        "net_new_fetched": net_new,
        "ratios": {
            "incremental_kept_to_baseline_kept": _ratio(len(incremental), baseline_kept),
            "kept_with_new_brands_to_baseline_kept": _ratio(len(buckets), baseline_kept),
            "net_new_fetched_to_baseline_fetched": _ratio(net_new, len(baseline_fetched)),
            "by_discovery_to_baseline_kept": {k: _ratio(v, baseline_kept) for k, v in by_discovery.items()},
            "by_brand_set_to_baseline_kept": {k: _ratio(v, baseline_kept) for k, v in sorted(by_brand.items())},
        },
    }


# ---------------------------------------------------------------------------
# Search credits (R16)
# ---------------------------------------------------------------------------


def request_credit_range(request: Mapping[str, Any], envelope_raw_count: int | None = None) -> tuple[int, int, str]:
    """(minimum, maximum, kind) credits for one physical request receipt."""
    receipt = request.get("receipt")
    if receipt is None and envelope_raw_count is not None:
        receipt = {"raw_count": envelope_raw_count, "body_lost": False}
    raw = receipt.get("raw_count") if isinstance(receipt, Mapping) else None
    if raw is None or (isinstance(receipt, Mapping) and receipt.get("body_lost") is True):
        return 0, NO_BODY_MAX_CREDITS, "no_body"
    status = request.get("http_status")
    if status is not None and int(status) >= 400:
        return 0, ERROR_BODY_MAX_CREDITS, "error_with_body"
    credits = max(MIN_CREDITS_PER_REQUEST, CREDITS_PER_RESULT * int(raw))
    return credits, credits, "billed"


def credit_summary(requests: Iterable[Mapping[str, Any]], route_metadata: Mapping[str, Any] | None = None,
                   envelope_raw_counts: Mapping[str, int] | None = None) -> dict:
    envelope_raw_counts = envelope_raw_counts or {}
    rows: dict[str, dict] = defaultdict(lambda: {"requests": 0, "billed": 0, "no_body": 0, "error_with_body": 0,
                                                 "credits_min": 0, "credits_max": 0, "retries": 0})
    pages: dict[tuple, int] = Counter()
    for request in requests:
        key = str(request.get("scope_key"))
        row = rows[route_name(key, route_metadata)]
        low, high, kind = request_credit_range(request, envelope_raw_counts.get(str(request.get("id"))))
        row["requests"] += 1
        row[kind] += 1
        row["credits_min"] += low
        row["credits_max"] += high
        pages[(key, request.get("cursor_before"))] += 1
    for (key, _), count in pages.items():
        rows[route_name(key, route_metadata)]["retries"] += count - 1
    routes = {name: _with_usd(row) for name, row in sorted(rows.items())}
    return {"routes": routes, "totals": _with_usd(_sum_rows(routes.values()))}


def _sum_rows(rows: Iterable[Mapping[str, Any]]) -> dict:
    total: dict[str, Any] = Counter()
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool) and not key.startswith("usd_"):
                total[key] += value
    return dict(total)


def _with_usd(row: Mapping[str, Any]) -> dict:
    return {**row, "usd_min": row.get("credits_min", 0) / CREDITS_PER_USD,
            "usd_max": row.get("credits_max", 0) / CREDITS_PER_USD}


# ---------------------------------------------------------------------------
# Model cost (R17, R24)
# ---------------------------------------------------------------------------

ZERO = Decimal(0)


def _money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def call_reported_usd(call: Mapping[str, Any]) -> Decimal:
    actual = _money(call.get("actual_usd"))
    return actual if call.get("state") == "completed" and actual is not None else ZERO


def call_settled_usd(call: Mapping[str, Any]) -> Decimal:
    """R11: provider-reported cost when finished, otherwise the reservation."""
    actual = _money(call.get("actual_usd"))
    if call.get("state") == "completed" and actual is not None:
        return actual
    return _money(call.get("reserved_usd")) or ZERO


def allocate_call_costs(calls: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Decimal]]:
    """Spread each request's cost evenly over its member posts."""
    allocation: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"reported": ZERO, "settled": ZERO})
    for call in calls:
        members = [str(pid) for pid in call.get("member_post_ids") or []]
        if not members:
            continue
        reported, settled = call_reported_usd(call), call_settled_usd(call)
        for pid in members:
            allocation[pid]["reported"] += reported / len(members)
            allocation[pid]["settled"] += settled / len(members)
    return dict(allocation)


def classified_post_ids(calls: Iterable[Mapping[str, Any]]) -> set[str]:
    return {str(pid) for call in calls if call.get("state") == "completed" and call.get("stage") == "classification"
            for pid in call.get("member_post_ids") or []}


def model_cost_summary(calls: list[Mapping[str, Any]], buckets: Mapping[str, str]) -> dict:
    by_stage: dict[str, dict] = defaultdict(lambda: {"requests": 0, "member_posts": 0, "reserved_usd": ZERO,
                                                     "reported_usd": ZERO, "settled_usd": ZERO,
                                                     "cost_unknown_requests": 0, "states": Counter()})
    for call in calls:
        key = str(call.get("stage") or "unknown")
        if call.get("operation"):
            key += f" ({call['operation']})"
        row = by_stage[key]
        row["requests"] += 1
        row["member_posts"] += len(call.get("member_post_ids") or [])
        row["reserved_usd"] += _money(call.get("reserved_usd")) or ZERO
        row["reported_usd"] += call_reported_usd(call)
        row["settled_usd"] += call_settled_usd(call)
        row["states"][str(call.get("state"))] += 1
        if call.get("state") != "reserved" and _money(call.get("actual_usd")) is None:
            row["cost_unknown_requests"] += 1
    allocation = allocate_call_costs(calls)
    by_bucket: dict[str, dict] = defaultdict(lambda: {"posts": 0, "reported_usd": ZERO, "settled_usd": ZERO})
    for pid, costs in allocation.items():
        row = by_bucket[buckets.get(pid, "not_kept")]
        row["posts"] += 1
        row["reported_usd"] += costs["reported"]
        row["settled_usd"] += costs["settled"]
    classified = classified_post_ids(calls)
    totals = {
        "requests": len(calls),
        "reserved_usd": sum((_money(c.get("reserved_usd")) or ZERO for c in calls), ZERO),
        "reported_usd": sum((call_reported_usd(c) for c in calls), ZERO),
        "settled_usd": sum((call_settled_usd(c) for c in calls), ZERO),
        "posts_with_cost": len(allocation),
        "classified_posts": len(classified),
        "classified_posts_not_kept": len(classified - set(buckets)),
    }
    totals["reported_usd_per_classified_post"] = totals["reported_usd"] / len(classified) if classified else None
    return {
        "by_stage": {k: {**v, "states": dict(v["states"])} for k, v in sorted(by_stage.items())},
        "by_bucket": dict(sorted(by_bucket.items())),
        "totals": totals,
    }


def staff_relevance_summary(runs: Iterable[Mapping[str, Any]]) -> dict:
    """Collection-time staff relevance checks: receipts and provider-reported cost."""
    receipts: dict[str, str] = {}
    responses = Counter()
    cost = ZERO
    for run in runs:
        for receipt in run.get("staff_relevance") or []:
            status = str(receipt.get("status"))
            if receipts.get(receipt.get("identity")) != "returned":
                receipts[str(receipt.get("identity"))] = status
        for response in run.get("model_responses") or []:
            responses[str(response.get("status"))] += 1
            value = _money(response.get("cost_usd"))
            if value is None:
                responses["without_cost"] += 1
            else:
                cost += value
    return {"checks": len(receipts), "checks_by_status": dict(Counter(receipts.values())),
            "responses": dict(responses), "reported_usd": cost}


def watch_summary(calls: Iterable[Mapping[str, Any]]) -> dict:
    """R24 spend watch over the test job's OriginalContentCall rows."""
    calls = list(calls)
    settled = sum((call_settled_usd(c) for c in calls), ZERO)
    reported = sum((call_reported_usd(c) for c in calls), ZERO)
    reserved = sum((_money(c.get("reserved_usd")) or ZERO for c in calls), ZERO)
    classified = len(classified_post_ids(calls))
    per_post = reported / classified if classified else None
    settled_per_post = settled / classified if classified else None
    over_spend = settled > R24_SPEND_USD
    trigger = over_spend and (per_post is None or per_post > R24_PER_POST_USD)
    return {
        "requests": len(calls), "settled_usd": settled, "reported_usd": reported, "reserved_usd": reserved,
        "classified_posts": classified, "reported_usd_per_classified_post": per_post,
        "settled_usd_per_classified_post": settled_per_post, "trigger": trigger,
        "volume_above_doubling": over_spend and not trigger,
        "thresholds": {"settled_usd": R24_SPEND_USD, "reported_usd_per_classified_post": R24_PER_POST_USD},
    }


def watch_text(watch: Mapping[str, Any]) -> str:
    per_post = watch["reported_usd_per_classified_post"]
    lines = [
        (f"Settled spend: {_usd(watch['settled_usd'])} (provider-reported {_usd(watch['reported_usd'])}, "
        f"reserved {_usd(watch['reserved_usd'])}, model requests {watch['requests']:,})"),
        f"Classified posts: {watch['classified_posts']:,}",
        "Provider-reported cost per classified post: " + (f"${per_post:.6f}" if per_post is not None else "n/a"),
    ]
    if watch["trigger"]:
        lines.append(f"R24 trigger: HOLDS (settled > ${R24_SPEND_USD} and cost per classified post > "
                     f"${R24_PER_POST_USD}). Pause enrichment and tell the owner something is wrong.")
    else:
        lines.append("R24 trigger: not met")
    if watch["volume_above_doubling"]:
        lines.append(f"Volume above doubling: settled spend passed ${R24_SPEND_USD} at or below "
                     f"${R24_PER_POST_USD} per post. The run continues; the report shows it.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Database growth (R18)
# ---------------------------------------------------------------------------


def is_bookkeeping_table(name: str) -> bool:
    return name.startswith(BOOKKEEPING_TABLE_PREFIXES) or name in BOOKKEEPING_TABLES


def db_growth(before: Mapping[str, int], after: Mapping[str, int]) -> dict:
    tables = {}
    for name in sorted(set(before) | set(after)):
        delta = int(after.get(name, 0)) - int(before.get(name, 0))
        if delta:
            tables[name] = {"before": int(before.get(name, 0)), "after": int(after.get(name, 0)), "delta": delta,
                            "kind": "bookkeeping" if is_bookkeeping_table(name) else "production_equivalent"}
    bookkeeping = sum(t["delta"] for t in tables.values() if t["kind"] == "bookkeeping")
    production = sum(t["delta"] for t in tables.values() if t["kind"] == "production_equivalent")
    return {"bookkeeping_bytes": bookkeeping, "production_equivalent_bytes": production,
            "total_bytes": bookkeeping + production, "tables": tables}


# ---------------------------------------------------------------------------
# Per-day estimates, projection and limits (R21-R23)
# ---------------------------------------------------------------------------


def window_share(window_count: float, day_count: float) -> float:
    if not day_count or window_count is None or window_count < 0 or window_count > day_count:
        raise ValueError(f"cannot form a window share from {window_count} of {day_count}")
    if window_count == 0:
        raise ValueError("the window has no saved posts, so its share of the day is unknown")
    return float(window_count) / float(day_count)


def _check_share(share: Any) -> float:
    if isinstance(share, bool) or not isinstance(share, (int, float)) or not 0 < share <= 1:
        raise ValueError(f"window share must be in (0, 1], got {share!r}")
    return float(share)


def per_day_estimate(window_value: Any, share: float, share_source: str) -> dict:
    share = _check_share(share)
    if window_value is None:
        per_day = None
    elif isinstance(window_value, Decimal):
        per_day = window_value / Decimal(repr(share))
    else:
        per_day = float(window_value) / share
    return {"window": window_value, "share": share, "per_day": per_day,
            "label": f"estimate: window figure ÷ window share {share:.4g} ({share_source})"}


def engagement_refresh_credits(kept_posts_per_day: float) -> int:
    return round(kept_posts_per_day * ENGAGEMENT_REFRESH_CREDITS_PER_POST)


def load_limits(config_text: str) -> dict[str, int]:
    config = yaml.safe_load(config_text) or {}
    paths = {
        "search_max_results": ("search", "max_results"),
        "enrichment_claim_per_cycle": ("harvest", "enrichment", "claim_per_cycle"),
        "metrics_refresh_per_cycle_cap": ("metrics_refresh", "per_cycle_cap"),
        "run_deadline_seconds": ("harvest", "run_deadline_seconds"),
    }
    limits = {}
    for name, path in paths.items():
        value: Any = config
        for part in path:
            value = value.get(part) if isinstance(value, dict) else None
        if type(value) is not int or value <= 0:
            raise ValueError(f"config.yaml lacks a positive integer {'.'.join(path)}")
        limits[name] = value
    return limits


def limit_comparison(projected_kept_per_day: float, route_fetched_per_day: Mapping[str, float],
                     limits: Mapping[str, int]) -> list[dict]:
    rows = []
    per_run = {name: value / RUNS_PER_DAY for name, value in route_fetched_per_day.items() if value is not None}
    busiest = max(per_run, key=per_run.get) if per_run else None
    search_limit = limits["search_max_results"]
    peak = per_run.get(busiest, 0.0) if busiest else 0.0
    rows.append({
        "limit": "search.max_results", "value": search_limit, "unit": "posts per search per run",
        "per_day_capacity": None, "projected": peak, "route": busiest, "factor": peak / search_limit,
        "exceeded": peak > search_limit, "per_route_per_run": dict(sorted(per_run.items())),
        "note": "Average 15-minute run; busy runs fetch more than the average.",
    })
    for name, key, unit in (
        ("harvest.enrichment.claim_per_cycle", "enrichment_claim_per_cycle", "posts enriched per run"),
        ("metrics_refresh.per_cycle_cap", "metrics_refresh_per_cycle_cap", "posts refreshed per run"),
    ):
        capacity = limits[key] * RUNS_PER_DAY
        rows.append({
            "limit": name, "value": limits[key], "unit": unit, "per_day_capacity": capacity,
            "projected": projected_kept_per_day, "route": None, "factor": projected_kept_per_day / capacity,
            "exceeded": projected_kept_per_day > capacity, "note": f"{limits[key]} per run × {RUNS_PER_DAY} runs per day.",
        })
    rows.append({
        "limit": "harvest.run_deadline_seconds", "value": limits["run_deadline_seconds"], "unit": "seconds per run",
        "per_day_capacity": None, "projected": None, "route": None, "factor": None, "exceeded": None,
        "note": RUN_TIME_NOTE,
    })
    return rows


def pilot_share_from_summaries(rows: Iterable[Mapping[str, Any]], in_window_slices: Iterable[int],
                               *, source: str = "pilot summaries.json") -> dict:
    """Window share from the pilot's sampled slices: in-window slice mean ÷ all-slice mean × 6h/24h."""
    rows = list(rows)
    all_slices = sorted({int(row["slice"]) for row in rows})
    wanted = sorted({int(s) for s in in_window_slices})
    if not wanted or not set(wanted) <= set(all_slices):
        raise ValueError(f"in-window slices {wanted} must be among the pilot slices {all_slices}")
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"in": 0, "all": 0})
    for row in rows:
        for key in (str(row["query"]), f"group:{row['group']}"):
            totals[key]["all"] += int(row["tweets"])
            if int(row["slice"]) in wanted:
                totals[key]["in"] += int(row["tweets"])

    def share(value: Mapping[str, int]) -> float | None:
        if not value["all"]:
            return None
        return (value["in"] / len(wanted)) / (value["all"] / len(all_slices)) * 0.25

    per_route = {k: share(v) for k, v in sorted(totals.items()) if not k.startswith("group:") and share(v)}
    return {
        "format": PILOT_SHARE_FORMAT, "source": f"{source}, in-window slices {wanted} of {all_slices}",
        "slices": wanted, "new_routes_share": share(totals["group:new"]),
        "baseline_routes_share": share(totals["group:baseline"]), "per_route": per_route,
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def _source_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return {str(row.get("source_query_id") or ""): int(row.get("posts") or 0) for row in rows or []}


def _scale(value: Any, share: float | None) -> Any:
    if value is None or not share:
        return None
    if isinstance(value, Decimal):
        return value / Decimal(repr(share))
    return float(value) / share


def _add(*values: Any) -> Any:
    if any(value is None for value in values):
        return None
    if any(isinstance(value, Decimal) for value in values):
        return sum((Decimal(str(value)) for value in values), ZERO)
    return sum(values)


def build_report(xb: Mapping[str, Any], production: Mapping[str, Any], frozen: Mapping[str, Any],
                 limits: Mapping[str, int], pilot_share: Mapping[str, Any], *,
                 size_before: Mapping[str, int] | None = None, size_after: Mapping[str, int] | None = None,
                 production_daily: Mapping[str, Any] | None = None, inputs: Mapping[str, Any] | None = None) -> dict:
    if xb.get("database") != XBACKFILLER_DATABASE:
        raise ValueError(f"the test job output came from database {xb.get('database')!r}, not xbackfiller")
    if xb.get("include_collection") is False:
        raise ValueError("the xbackfiller output was saved with --watch-only; save the full query for the report")
    if production.get("database") == XBACKFILLER_DATABASE:
        raise ValueError("the production output came from xbackfiller")
    production_routes = [str(row["name"]) for row in frozen["baseline"]]
    new_routes = [str(row["name"]) for row in frozen["new"]]
    route_metadata = (xb.get("job") or {}).get("route_metadata") or {}
    run_id = select_report_run(xb)
    run = next((r for r in xb.get("runs") or [] if str(r.get("id")) == run_id), {})
    scopes = report_scopes(xb)
    route_sets = route_post_sets(scopes, route_metadata)
    unknown = sorted(set(route_sets) - set(production_routes) - set(new_routes))
    if unknown:
        raise ValueError(f"routes outside the frozen query set: {unknown}")

    start, end = int(production["window_start_epoch"]), int(production["window_end_epoch"])
    bounds = [b for b in (slice_bounds(s["scope_key"]) for s in scopes) if b]
    if bounds and (min(b[0] for b in bounds) != start or max(b[1] for b in bounds) != end):
        raise ValueError("the test job's slices do not cover the production comparison window")

    brands = {str(b["nickname"]).casefold(): bool(b.get("is_sentinel")) for b in xb.get("brands") or []}
    post_tags: dict[str, set[str]] = defaultdict(set)
    for post_id, brand in xb.get("post_brands") or []:
        brand = str(brand).casefold()
        if brand in NEW_BRANDS or not brands.get(brand, False):
            post_tags[str(post_id)].add(brand)
    buckets = classify_kept_posts(route_sets, post_tags, production_routes)
    collection = collection_summary(route_sets, production_routes, new_routes)
    growth = growth_summary(route_sets, post_tags, production_routes, new_routes, buckets=buckets)

    envelope_raw_counts = {k: v for route in route_sets.values() for k, v in route.request_raw_counts.items()}
    credits = credit_summary(xb.get("requests") or [], route_metadata, envelope_raw_counts)
    credit_groups = {
        group: _with_usd(_sum_rows(row for name, row in credits["routes"].items() if name in names))
        for group, names in (("production", set(production_routes)), ("new", set(new_routes)))
    }
    calls = list(xb.get("calls") or [])
    model = model_cost_summary(calls, buckets)
    staff = staff_relevance_summary(xb.get("runs") or [])

    after = size_after if size_after is not None else {k: int(v) for k, v in (xb.get("table_sizes") or {}).items()}
    growth_db = db_growth(size_before, after) if size_before is not None else None

    # R21 shares.
    window_counts = _source_counts(production.get("window_posts"))
    day_counts = _source_counts(production.get("day_posts"))
    prod_window = sum(window_counts.get(name, 0) for name in production_routes)
    prod_day = sum(day_counts.get(name, 0) for name in production_routes)
    prod_share = window_share(prod_window, prod_day)
    new_share = _check_share(pilot_share.get("new_routes_share"))
    window_date = datetime.fromtimestamp(start, PACIFIC).date().isoformat()
    prod_source = f"production saved posts on the 8 production searches, {window_date} Pacific"
    new_source = f"pilot slices: {pilot_share.get('source', 'pilot share file')}"
    route_shares = {}
    for name in production_routes:
        day = day_counts.get(name, 0)
        route_shares[name] = window_counts.get(name, 0) / day if day and window_counts.get(name, 0) else prod_share
    for name in new_routes:
        value = (pilot_share.get("per_route") or {}).get(name)
        route_shares[name] = float(value) if isinstance(value, (int, float)) and 0 < value <= 1 else new_share

    by_discovery = growth["incremental_kept"]["by_discovery"]
    kept_window = {
        BASELINE: growth["baseline_equivalent_kept"], PRODUCTION_UNTAGGED: growth["production_route_untagged_kept"],
        **by_discovery,
    }
    bucket_share = {BASELINE: prod_share, PRODUCTION_UNTAGGED: prod_share, PRODUCTION_NEW_KEYWORD: prod_share,
                    NEW_ROUTES_ONLY: new_share, PRODUCTION_FETCHED_NEW_KEPT: new_share}
    kept_day = {bucket: _scale(count, bucket_share[bucket]) for bucket, count in kept_window.items()}
    baseline_day = kept_day[BASELINE] + kept_day[PRODUCTION_UNTAGGED]
    incremental_day = sum(kept_day[b] for b in INCREMENTAL_BUCKETS)
    kept_total_window = sum(kept_window.values())
    kept_total_day = baseline_day + incremental_day
    effective_share = kept_total_window / kept_total_day if kept_total_day else None
    effective_source = "kept-post-weighted mix of the production and pilot shares"

    def bucket_cost(field_name: str, buckets_wanted: Iterable[str]) -> Decimal:
        return sum((model["by_bucket"].get(b, {}).get(field_name, ZERO) for b in buckets_wanted), ZERO)

    cost_day = {}
    for field_name in ("reported_usd", "settled_usd"):
        cost_day[field_name] = {
            "baseline": _add(_scale(bucket_cost(field_name, (BASELINE, PRODUCTION_UNTAGGED)), prod_share)),
            "incremental": _add(_scale(bucket_cost(field_name, (PRODUCTION_NEW_KEYWORD,)), prod_share),
                                _scale(bucket_cost(field_name, (NEW_ROUTES_ONLY, PRODUCTION_FETCHED_NEW_KEPT)), new_share)),
            "not_kept": _scale(bucket_cost(field_name, ("not_kept",)), effective_share),
        }
    search_day = {group: {"credits_min": _scale(credit_groups[group].get("credits_min", 0), share),
                          "credits_max": _scale(credit_groups[group].get("credits_max", 0), share)}
                  for group, share in (("production", prod_share), ("new", new_share))}
    for row in search_day.values():
        row["usd_min"] = row["credits_min"] / CREDITS_PER_USD
        row["usd_max"] = row["credits_max"] / CREDITS_PER_USD

    headline = {
        "posts_kept_baseline": per_day_estimate(growth["baseline_equivalent_kept"], prod_share, prod_source),
        "posts_kept_incremental": {**per_day_estimate(growth["incremental_kept"]["total"], new_share, new_source),
                                   "per_day": incremental_day,
                                   "label": "estimate: production-search part ÷ production share "
                                            f"{prod_share:.4g}, new-search part ÷ pilot share {new_share:.4g}"},
        "posts_kept_with_new_brands": {"window": kept_total_window, "per_day": kept_total_day,
                                       "share": effective_share, "label": f"estimate: sum of the parts ({effective_source})"},
        "fetched_baseline": per_day_estimate(growth["baseline_fetched"], prod_share, prod_source),
        "fetched_net_new": per_day_estimate(growth["net_new_fetched"], new_share, new_source),
        "search_usd_production_routes": {
            "window": [credit_groups["production"]["usd_min"], credit_groups["production"]["usd_max"]],
            "per_day": [search_day["production"]["usd_min"], search_day["production"]["usd_max"]],
            "share": prod_share, "label": f"estimate: window ÷ production share {prod_share:.4g}"},
        "search_usd_new_routes": {
            "window": [credit_groups["new"]["usd_min"], credit_groups["new"]["usd_max"]],
            "per_day": [search_day["new"]["usd_min"], search_day["new"]["usd_max"]],
            "share": new_share, "label": f"estimate: window ÷ pilot share {new_share:.4g}"},
        "classification_reported_usd": {
            "window": model["totals"]["reported_usd"],
            "per_day": _add(*cost_day["reported_usd"].values()),
            "share": effective_share,
            "label": "estimate: each post's allocated cost ÷ the share of the search group that kept it"},
        "staff_relevance_reported_usd": {**per_day_estimate(staff["reported_usd"], effective_share or 1, effective_source)}
        if effective_share else None,
    }
    if growth_db is not None and effective_share:
        headline["db_growth_production_equivalent_bytes"] = per_day_estimate(
            growth_db["production_equivalent_bytes"], effective_share, effective_source)
        headline["db_growth_bookkeeping_bytes"] = per_day_estimate(
            growth_db["bookkeeping_bytes"], effective_share, effective_source)

    # R22 projection.
    daily = dict(production_daily or {})
    current_saved = daily.get("saved_posts_per_day")
    if current_saved is None:
        current_saved = sum(day_counts.values())
        saved_source = f"production saved posts on {window_date} Pacific (all searches)"
    else:
        saved_source = daily.get("source", "operator-supplied")
    projected_saved = current_saved + incremental_day
    bytes_per_kept = (growth_db["production_equivalent_bytes"] / kept_total_window
                      if growth_db is not None and kept_total_window else None)
    quote_rate = (daily["quote_credits_per_day"] / current_saved
                  if daily.get("quote_credits_per_day") is not None and current_saved else None)
    incremental_cost_day = cost_day["reported_usd"]["incremental"]
    current_classification = _money(daily.get("classification_usd_per_day"))
    projection = [
        {"need": "Saved posts per day", "current": current_saved, "added": incremental_day,
         "projected": projected_saved, "note": f"current from {saved_source}"},
        {"need": "Search credits per day", "current": daily.get("search_credits_per_day"),
         "added": [search_day["new"]["credits_min"], search_day["new"]["credits_max"]],
         "projected": [_add(daily.get("search_credits_per_day"), search_day["new"]["credits_min"]),
                       _add(daily.get("search_credits_per_day"), search_day["new"]["credits_max"])],
         "note": "added = new searches' window credits ÷ pilot share; production's 15-minute windows "
                 "pay fewer per-request minimums than 5-minute slices"},
        {"need": "Engagement-refresh credits per day", "current": daily.get("engagement_refresh_credits_per_day"),
         "added": engagement_refresh_credits(incremental_day),
         "projected": engagement_refresh_credits(projected_saved),
         "note": "projected = projected saved posts per day × 15 credits (one refresh per saved post)"},
        {"need": "Quote-tweet credits per day", "current": daily.get("quote_credits_per_day"),
         "added": quote_rate * incremental_day if quote_rate is not None else None,
         "projected": _add(daily.get("quote_credits_per_day"), quote_rate * incremental_day) if quote_rate is not None else None,
         "note": "scaled from production's current quote-tweet credits per saved post"},
        {"need": "Classification cost per day (USD)", "current": current_classification,
         "added": incremental_cost_day, "projected": _add(current_classification, incremental_cost_day),
         "note": "added = provider-reported cost allocated to the added posts ÷ their search group's share"},
        {"need": "Database growth per day (bytes)", "current": daily.get("db_growth_bytes_per_day"),
         "added": bytes_per_kept * incremental_day if bytes_per_kept is not None else None,
         "projected": _add(daily.get("db_growth_bytes_per_day"), bytes_per_kept * incremental_day)
         if bytes_per_kept is not None else None,
         "note": "production-equivalent tables only, at the test's bytes per kept post"},
    ]

    # R23 limits.
    route_fetched_day = {name: len(route.received) / route_shares[name] for name, route in route_sets.items()}
    limits_rows = limit_comparison(projected_saved, route_fetched_day, limits)

    # R19 comparison.
    excluded = {name: window_counts.get(name, 0) for name in EXCLUDED_PRODUCTION_SOURCES}
    other_sources = {k: v for k, v in window_counts.items()
                     if k not in production_routes and k not in EXCLUDED_PRODUCTION_SOURCES}
    comparison = {
        "label": BASELINE_LABEL, "note": SPECIAL_EVENTS_NOTE,
        "production_window": {
            "saved_posts_production_routes": prod_window, "saved_posts_excluded_searches": excluded,
            "saved_posts_other_sources": other_sources,
            "test_kept_on_production_routes": collection["groups"]["production"]["kept"],
            "test_baseline_equivalent_kept": growth["baseline_equivalent_kept"],
            "test_to_production_ratio": _ratio(collection["groups"]["production"]["kept"], prod_window),
        },
        "pilot_window": {
            "estimates": PILOT_WINDOW_ESTIMATES,
            "measured": {
                "requests": {"production": credit_groups["production"].get("requests", 0),
                             "new": credit_groups["new"].get("requests", 0),
                             "total": credits["totals"].get("requests", 0)},
                "search_usd": {"production": [credit_groups["production"]["usd_min"], credit_groups["production"]["usd_max"]],
                               "new": [credit_groups["new"]["usd_min"], credit_groups["new"]["usd_max"]],
                               "total": [credits["totals"]["usd_min"], credits["totals"]["usd_max"]]},
                "fetched": {"production": growth["baseline_fetched"], "new": growth["new_routes_fetched"],
                            "net_new": growth["net_new_fetched"], "total": collection["totals"]["fetched"]},
                "kept": {"production": collection["groups"]["production"]["kept"],
                         "new": collection["groups"]["new"]["kept"], "total": collection["totals"]["kept"]},
            },
        },
        "pilot_day": {
            "estimates": PILOT_DAY_ESTIMATES,
            "measured": {"baseline_fetched": headline["fetched_baseline"]["per_day"],
                         "net_new_fetched": headline["fetched_net_new"]["per_day"],
                         "incremental_kept": incremental_day,
                         "baseline_search_usd": [search_day["production"]["usd_min"], search_day["production"]["usd_max"]],
                         "new_search_usd": [search_day["new"]["usd_min"], search_day["new"]["usd_max"]]},
        },
    }

    observed = {str(pid) for pid in xb.get("observed_post_ids") or []}
    kept_all = set(buckets)
    return {
        "format": REPORT_FORMAT,
        "job": {"id": (xb.get("job") or {}).get("id"), "job_key": (xb.get("job") or {}).get("job_key"),
                "state": (xb.get("job") or {}).get("state")},
        "report_run": {"id": run_id, "status": run.get("status"), "completed_at": run.get("completed_at"),
                       "runs_in_job": len(xb.get("runs") or [])},
        "window": {"start_epoch": start, "end_epoch": end, "pacific_date": window_date,
                   "pacific_clock": f"{datetime.fromtimestamp(start, PACIFIC):%H:%M}–"
                                    f"{datetime.fromtimestamp(end, PACIFIC):%H:%M}",
                   "start_utc": datetime.fromtimestamp(start, ZoneInfo("UTC")).isoformat(),
                   "end_utc": datetime.fromtimestamp(end, ZoneInfo("UTC")).isoformat()},
        "inputs": dict(inputs or {}),
        "collection": collection,
        "growth": growth,
        "credits": {**credits, "groups": credit_groups, "request_limit": SEARCH_REQUEST_LIMIT},
        "model_cost": model,
        "staff_relevance": staff,
        "db_growth": growth_db,
        "table_sizes_after": after,
        "shares": {
            "production_routes": {"share": prod_share, "window_posts": prod_window, "day_posts": prod_day,
                                  "source": prod_source},
            "new_routes": {"share": new_share, "source": new_source},
            "effective": {"share": effective_share, "source": effective_source},
            "per_route": route_shares,
        },
        "headline": headline,
        "kept_per_day_by_bucket": kept_day,
        "classification_per_day": cost_day,
        "projection": projection,
        "limits": {"values": dict(limits), "comparison": limits_rows},
        "comparison": comparison,
        "watch": watch_summary(calls),
        "reconciliation": {
            "kept_posts": len(kept_all), "observed_posts": len(observed),
            "kept_not_observed": len(kept_all - observed), "observed_not_kept": len(observed - kept_all),
            "classified_posts_not_kept": model["totals"]["classified_posts_not_kept"],
        },
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _num(value: Any, digits: int = 0) -> str:
    if value is None:
        return "not supplied"
    if isinstance(value, (list, tuple)):
        low, high = (_num(v, digits) for v in value)
        return low if low == high else f"{low}–{high}"
    return f"{float(value):,.{digits}f}"


def _usd(value: Any, digits: int = 2) -> str:
    if value is None:
        return "not supplied"
    if isinstance(value, (list, tuple)):
        low, high = (_usd(v, digits) for v in value)
        return low if low == high else f"{low}–{high}"
    return f"${float(value):,.{digits}f}"


def _mb(value: Any) -> str:
    return "not available" if value is None else f"{float(value) / 1_000_000:,.1f} MB"


def _factor(value: Any) -> str:
    return "—" if value is None else f"{value:.2f}×"


def render_markdown(report: Mapping[str, Any]) -> str:
    w, g, h = report["window"], report["growth"], report["headline"]
    shares = report["shares"]
    lines = [
        "# OpenAI and Anthropic collection size report",
        "",
        f"- Window: {w['start_utc']} to {w['end_utc']} ({w['pacific_clock']} US Pacific on {w['pacific_date']}).",
        (f"- Test job `{report['job']['id']}`; figures read from run `{report['report_run']['id']}` "
        f"(status {report['report_run']['status']}, one of {report['report_run']['runs_in_job']} runs)."),
        ("- Every measured figure comes from the test job's database records (R20). Per-day figures are "
        "estimates: the window figure divided by the window's share of a day's volume (R21)."),
        f"- {BASELINE_LABEL}",
        "",
        "## What this answers",
        "",
        ("How much more the production harvester would collect, pay and store per day if OpenAI and "
        "Anthropic became tracked brands. One 6-hour window ran production's 8 searches and the 10 new "
        "searches side by side; the baseline is what production's searches keep for the current brands."),
        "",
        "## Headline figures",
        "",
        "| Figure | Window (measured) | Per day (estimate) | How the estimate was made |",
        "|---|---|---|---|",
        (f"| Posts kept, baseline | {_num(h['posts_kept_baseline']['window'])} | "
        f"{_num(h['posts_kept_baseline']['per_day'])} | {h['posts_kept_baseline']['label']} |"),
        (f"| Posts kept, added by OpenAI/Anthropic | {_num(h['posts_kept_incremental']['window'])} | "
        f"{_num(h['posts_kept_incremental']['per_day'])} | {h['posts_kept_incremental']['label']} |"),
        (f"| Posts kept with OpenAI/Anthropic | {_num(h['posts_kept_with_new_brands']['window'])} | "
        f"{_num(h['posts_kept_with_new_brands']['per_day'])} | {h['posts_kept_with_new_brands']['label']} |"),
        (f"| Search cost, production searches | {_usd(h['search_usd_production_routes']['window'])} | "
        f"{_usd(h['search_usd_production_routes']['per_day'])} | {h['search_usd_production_routes']['label']} |"),
        (f"| Search cost, new searches | {_usd(h['search_usd_new_routes']['window'])} | "
        f"{_usd(h['search_usd_new_routes']['per_day'])} | {h['search_usd_new_routes']['label']} |"),
        (f"| Classification cost (provider-reported) | {_usd(h['classification_reported_usd']['window'], 4)} | "
        f"{_usd(h['classification_reported_usd']['per_day'], 4)} | {h['classification_reported_usd']['label']} |"),
    ]
    if "db_growth_production_equivalent_bytes" in h:
        row = h["db_growth_production_equivalent_bytes"]
        lines.append(f"| Database growth, production-equivalent tables | {_mb(row['window'])} | "
                     f"{_mb(row['per_day'])} | {row['label']} |")
    else:
        lines.append("| Database growth | not available | not available | no before-size snapshot was supplied |")

    lines += ["", "## Daily harvester needs with OpenAI and Anthropic added (R22)", "",
              "| Need | Production now, per day | Added (estimate) | Projected per day | Note |", "|---|---|---|---|---|"]
    for row in report["projection"]:
        money = "USD" in row["need"]
        fmt = (lambda v: _usd(v, 2)) if money else _num
        lines.append(f"| {row['need']} | {fmt(row['current'])} | {fmt(row['added'])} | {fmt(row['projected'])} | {row['note']} |")

    lines += ["", "## Harvester limits (R23)", "",
              ("Projected posts per day are compared with the per-run limits in config.yaml at the deployed "
              "production revision; a run happens every 15 minutes (96 per day)."), "",
              "| Limit | Value | Daily capacity | Projected | Factor | Exceeded? |", "|---|---|---|---|---|---|"]
    for row in report["limits"]["comparison"]:
        exceeded = "not measured" if row["exceeded"] is None else ("yes" if row["exceeded"] else "no")
        projected = _num(row["projected"]) + (f" ({row['route']}, per run)" if row["route"] else "")
        capacity = "—" if row["per_day_capacity"] is None else _num(row["per_day_capacity"])
        lines.append(f"| `{row['limit']}` | {row['value']:,} {row['unit']} | {capacity} | "
                     f"{projected if row['projected'] is not None else '—'} | {_factor(row['factor'])} | {exceeded} |")
    lines += ["", RUN_TIME_NOTE]

    lines += ["", "## Each search (R14)", "",
              ("Fetched counts unique posts the search returned; kept counts posts it saved; a post found by "
              "two searches appears in both rows but once in the totals."), "",
              "| Search | Group | Fetched | Kept | Dropped (by reason) | Pages | Requests | Retries | Credits | Slice outcomes |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    production_routes = set(report["collection"]["groups"]["production"]["routes"])
    for name, row in report["collection"]["routes"].items():
        credit = report["credits"]["routes"].get(name, {})
        dropped = ", ".join(f"{k} {v:,}" for k, v in row["dropped"].items()) or "none"
        outcomes = ", ".join(f"{k} {v}" for k, v in row["terminal_state"].items())
        lines.append(f"| {name} | {'production' if name in production_routes else 'new'} | {row['fetched']:,} | "
                     f"{row['kept']:,} | {dropped} | {row['pages']:,} | {credit.get('requests', 0):,} | "
                     f"{credit.get('retries', 0):,} | {_num([credit.get('credits_min', 0), credit.get('credits_max', 0)])} | {outcomes} |")
    totals = report["collection"]["totals"]
    lines.append(f"| **All searches** | | {totals['fetched']:,} | {totals['kept']:,} | | {totals['pages']:,} | "
                 f"{report['credits']['totals'].get('requests', 0):,} | {report['credits']['totals'].get('retries', 0):,} | "
                 f"{_num([report['credits']['totals'].get('credits_min', 0), report['credits']['totals'].get('credits_max', 0)])} | |")

    ratios = g["ratios"]
    lines += ["", "## Growth (R15)", "",
              (f"- Baseline-equivalent kept: {g['baseline_equivalent_kept']:,} (kept by a production search with "
              "a tag from the current brands)."),
              (f"- Added kept posts: {g['incremental_kept']['total']:,} "
              f"(×{_ratio_text(ratios['incremental_kept_to_baseline_kept'])} of baseline); all kept with the new "
              f"brands: {g['kept_with_new_brands']:,} (×{_ratio_text(ratios['kept_with_new_brands_to_baseline_kept'])})."),
              (f"- Net-new fetched: {g['net_new_fetched']:,} posts the production searches never returned "
              f"(×{_ratio_text(ratios['net_new_fetched_to_baseline_fetched'])} of the baseline's "
              f"{g['baseline_fetched']:,} fetched)."),
              f"- Kept by a production search with no brand tag (should be 0): {g['production_route_untagged_kept']:,}.",
              "", "| How the added post was found | Posts | Ratio to baseline |", "|---|---|---|"]
    for bucket, count in g["incremental_kept"]["by_discovery"].items():
        lines.append(f"| {BUCKET_LABELS[bucket]} | {count:,} | {_ratio_text(ratios['by_discovery_to_baseline_kept'][bucket])} |")
    lines += ["", "| Brand set of the added posts | Posts | Ratio to baseline |", "|---|---|---|"]
    for key, count in g["incremental_kept"]["by_brand_set"].items():
        lines.append(f"| {key} | {count:,} | {_ratio_text(ratios['by_brand_set_to_baseline_kept'][key])} |")

    c = report["credits"]
    lines += ["", "## Search requests and credits (R16)", "",
              ("Each request with a returned body costs max(15, 15 × posts returned) credits. A request with no "
              "returned body (unknown outcome, transport error or lost body) counts as 0–300 credits, and an "
              "error response with a body (such as HTTP 520) as 0–15. 100,000 credits = $1."), "",
              "| Group | Requests | Billed | No body | Error with body | Retries | Credits | USD |", "|---|---|---|---|---|---|---|---|"]
    for name, row in [*c["groups"].items(), ("all", c["totals"])]:
        lines.append(f"| {name} | {row.get('requests', 0):,} | {row.get('billed', 0):,} | {row.get('no_body', 0):,} | "
                     f"{row.get('error_with_body', 0):,} | {row.get('retries', 0):,} | "
                     f"{_num([row.get('credits_min', 0), row.get('credits_max', 0)])} | {_usd([row['usd_min'], row['usd_max']])} |")
    lines.append(f"\nRequests used: {c['totals'].get('requests', 0):,} of the {c['request_limit']:,} limit (R10).")

    m = report["model_cost"]
    lines += ["", "## Model cost (R17)", "",
              ("Reserved is what admission held back; provider-reported is what DeepInfra reported for finished "
              "requests; settled counts finished requests at reported cost and the rest at their reservation (R11)."),
              "", "| Stage | Requests | Member posts | Reserved | Provider-reported | Settled | Cost unknown |", "|---|---|---|---|---|---|---|"]
    for stage, row in m["by_stage"].items():
        lines.append(f"| {stage} | {row['requests']:,} | {row['member_posts']:,} | {_usd(row['reserved_usd'], 4)} | "
                     f"{_usd(row['reported_usd'], 4)} | {_usd(row['settled_usd'], 4)} | {row['cost_unknown_requests']:,} |")
    t = m["totals"]
    lines.append(f"| **All** | {t['requests']:,} | | {_usd(t['reserved_usd'], 4)} | {_usd(t['reported_usd'], 4)} | "
                 f"{_usd(t['settled_usd'], 4)} | |")
    lines += ["", "Each request's cost is split evenly across its member posts, then summed by how the post was found:", "",
              "| Posts | Count | Provider-reported | Settled |", "|---|---|---|---|"]
    for bucket, row in m["by_bucket"].items():
        lines.append(f"| {BUCKET_LABELS.get(bucket, bucket)} | {row['posts']:,} | {_usd(row['reported_usd'], 4)} | "
                     f"{_usd(row['settled_usd'], 4)} |")
    s = report["staff_relevance"]
    lines.append(f"\nCollection-time staff relevance checks, reported separately from enrichment: checks "
                 f"{s['checks']:,}, provider-reported {_usd(s['reported_usd'], 4)}, responses {s['responses']}.")

    lines += ["", "## Database growth (R18)", ""]
    if report["db_growth"] is None:
        lines.append("No before-size snapshot was supplied, so growth is not reported.")
    else:
        d = report["db_growth"]
        lines += [f"- Backfill bookkeeping tables (collection_*, provider_batches, original_content_calls): {_mb(d['bookkeeping_bytes'])}.",
                  f"- Tables production would also grow: {_mb(d['production_equivalent_bytes'])}.",
                  "", "| Table | Kind | Growth |", "|---|---|---|"]
        for name, row in sorted(report["db_growth"]["tables"].items(), key=lambda item: -abs(item[1]["delta"])):
            lines.append(f"| {name} | {row['kind']} | {_mb(row['delta'])} |")

    comp = report["comparison"]
    pw, est, meas = comp["production_window"], comp["pilot_window"]["estimates"], comp["pilot_window"]["measured"]
    lines += ["", "## Comparison with the pilot and production (R19)", "", f"**{comp['label']}** {comp['note']}", "",
              (f"- Production saved {pw['saved_posts_production_routes']:,} posts in this window from its 8 searches; "
              f"the test's production searches kept {pw['test_kept_on_production_routes']:,} "
              f"(ratio {_ratio_text(pw['test_to_production_ratio'])})."),
              "- Left out of the production count: " + ", ".join(f"{k} {v:,}" for k, v in pw["saved_posts_excluded_searches"].items())
              + ("; other sources: " + ", ".join(f"{k or '(none)'} {v:,}" for k, v in pw["saved_posts_other_sources"].items())
                 if pw["saved_posts_other_sources"] else "") + ".",
              "", "| Window figure | Pilot estimate | Measured |", "|---|---|---|"]
    for key in ("production", "new", "total"):
        lines.append(f"| Requests, {key} | {_num(est['requests'][key])} | {_num(meas['requests'][key])} |")
        lines.append(f"| Search cost, {key} | {_usd(est['search_usd'][key])} | {_usd(meas['search_usd'][key])} |")
    for key in ("production", "new", "net_new", "total"):
        lines.append(f"| Fetched, {key} | {_num(est['fetched'][key])} | {_num(meas['fetched'][key])} |")
    for key in ("production", "new", "total"):
        lines.append(f"| Kept, {key} | {_num(est['kept'][key])} | {_num(meas['kept'][key])} |")
    day_est, day_meas = comp["pilot_day"]["estimates"], comp["pilot_day"]["measured"]
    lines += ["", f"Pilot window estimates: {est['source']}.", "",
              "| Per-day figure | Pilot estimate | This test (estimate) |", "|---|---|---|",
              f"| Baseline fetched | {_num(day_est['baseline_fetched'])} | {_num(day_meas['baseline_fetched'])} |",
              f"| Net-new fetched | {_num(day_est['net_new_fetched'])} | {_num(day_meas['net_new_fetched'])} |",
              f"| Added kept posts | {_num(day_est['net_new_kept'])} | {_num(day_meas['incremental_kept'])} |",
              f"| Baseline search cost | {_usd(day_est['baseline_search_usd'])} | {_usd(day_meas['baseline_search_usd'])} |",
              f"| New searches' search cost | {_usd(day_est['new_search_usd'])} | {_usd(day_meas['new_search_usd'])} |",
              "", f"Pilot per-day estimates: {day_est['source']}."]

    lines += ["", "## Shares used for per-day estimates (R21)", "",
              (f"- Production searches: {shares['production_routes']['share']:.4f} — "
              f"{shares['production_routes']['window_posts']:,} of {shares['production_routes']['day_posts']:,} "
              f"saved posts ({shares['production_routes']['source']})."),
              f"- New searches: {shares['new_routes']['share']:.4f} ({shares['new_routes']['source']}).",
              f"- Mixed figures: {_ratio_text(shares['effective']['share'], 4)} ({shares['effective']['source']})."]

    wt = report["watch"]
    lines += ["", "## Spend check (R24)", "", watch_text(wt)]

    r = report["reconciliation"]
    lines += ["", "## Reconciliation and sources (R20)", "",
              (f"- Kept posts from scope records: {r['kept_posts']:,}; posts with collection observations: "
              f"{r['observed_posts']:,}; kept but not observed: {r['kept_not_observed']:,}; observed but not kept: "
              f"{r['observed_not_kept']:,}."),
              f"- Classified posts that were not kept (should be 0, R13): {r['classified_posts_not_kept']:,}.",
              ("- Historical search may omit posts the live harvest would see; figures are "
              "provider_filtered_not_exhaustive, as for the July backfill."), "", "Inputs (sha256):", ""]
    for name, digest in report["inputs"].items():
        lines.append(f"- {name}: `{digest}`")
    return "\n".join(lines) + "\n"


def _ratio_text(value: Any, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_jsonable(v) for v in value)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.backfill_size_report",
        description="OpenAI/Anthropic collection size report from saved read-only query output (plan U8).",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print-xbackfiller-sql", action="store_true", help="print the xbackfiller query for --job-id")
    mode.add_argument("--print-production-sql", action="store_true", help="print the production query for the window")
    mode.add_argument("--pilot-share-from", metavar="SUMMARIES_JSON", help="print the pilot share JSON")
    mode.add_argument("--watch", metavar="JSON", help="R24 spend watch over saved xbackfiller output")
    parser.add_argument("--job-id", help="test CollectionJob UUID")
    parser.add_argument("--watch-only", action="store_true", help="with --print-xbackfiller-sql: skip collection records")
    parser.add_argument("--window-start-epoch", type=int)
    parser.add_argument("--window-end-epoch", type=int)
    parser.add_argument("--pilot-slices", help="comma-separated pilot slice indexes inside the window, such as 2,3,4")
    parser.add_argument("--xbackfiller", type=Path)
    parser.add_argument("--production", type=Path)
    parser.add_argument("--frozen-queries", type=Path)
    parser.add_argument("--limits-config", type=Path, help="config.yaml at the deployed production revision")
    parser.add_argument("--pilot-share", type=Path)
    parser.add_argument("--size-before", type=Path)
    parser.add_argument("--size-after", type=Path, help="defaults to the sizes inside --xbackfiller")
    parser.add_argument("--production-daily", type=Path, help="operator-supplied production daily figures (R22)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timestamp", help="JST file timestamp YYYY-MM-DD-HHMMSS (default: now)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.print_xbackfiller_sql:
            print(xbackfiller_sql(args.job_id, include_collection=not args.watch_only))
            return 0
        if args.print_production_sql:
            print(production_sql(args.window_start_epoch, args.window_end_epoch))
            return 0
        if args.pilot_share_from:
            if not args.pilot_slices:
                parser.error("--pilot-share-from needs --pilot-slices")
            path = Path(args.pilot_share_from).expanduser()
            slices = [int(part) for part in args.pilot_slices.split(",") if part.strip()]
            share = pilot_share_from_summaries(json.loads(path.read_text()), slices,
                                               source=f"{path.name} sha256 {_sha256(path)[:12]}")
            print(json.dumps(share, indent=2))
            return 0
        if args.watch:
            doc = load_document(Path(args.watch).read_text(), XBACKFILLER_FORMAT)
            if doc.get("database") != XBACKFILLER_DATABASE:
                raise ValueError(f"watch output came from database {doc.get('database')!r}, not xbackfiller")
            if doc.get("job") is None:
                # A well-formed but wrong --job-id returns no calls; never report that as zero spend.
                raise ValueError("the watched --job-id matched no CollectionJob in xbackfiller")
            watch = watch_summary(doc.get("calls") or [])
            print(watch_text(watch))
            return WATCH_TRIGGER_EXIT if watch["trigger"] else 0
        return _write_report(args, parser)
    except (ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _write_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    required = ("xbackfiller", "production", "frozen_queries", "limits_config", "pilot_share")
    missing = [f"--{name.replace('_', '-')}" for name in required if getattr(args, name) is None]
    if missing:
        parser.error("report mode needs " + ", ".join(missing))
    if _sha256(args.frozen_queries) != FROZEN_QUERIES_SHA256:
        raise ValueError(f"{args.frozen_queries} is not the frozen query set (sha256 {FROZEN_QUERIES_SHA256})")
    timestamp = args.timestamp or datetime.now(JST).strftime("%Y-%m-%d-%H%M%S")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{6}", timestamp):
        raise ValueError("--timestamp must look like 2026-10-30-120000")
    pilot = load_document(args.pilot_share.read_text(), PILOT_SHARE_FORMAT)
    inputs = {name: _sha256(getattr(args, name)) for name in
              (*required, "size_before", "size_after", "production_daily") if getattr(args, name) is not None}
    inputs["xbackfiller_sql"] = _sha256(XBACKFILLER_SQL_PATH)
    inputs["production_sql"] = _sha256(PRODUCTION_SQL_PATH)
    report = build_report(
        load_document(args.xbackfiller.read_text(), XBACKFILLER_FORMAT),
        load_document(args.production.read_text(), PRODUCTION_FORMAT),
        json.loads(args.frozen_queries.read_text()),
        load_limits(args.limits_config.read_text()),
        pilot,
        size_before=load_table_sizes(args.size_before.read_text()) if args.size_before else None,
        size_after=load_table_sizes(args.size_after.read_text()) if args.size_after else None,
        production_daily=json.loads(args.production_daily.read_text()) if args.production_daily else None,
        inputs=inputs,
    )
    report["generated_at_jst"] = timestamp
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"{timestamp}-oai-anthropic-size-report"
    md_path, json_path = stem.with_suffix(".md"), stem.with_suffix(".json")
    for path in (md_path, json_path):
        if path.exists():
            raise ValueError(f"{path} already exists; choose another --timestamp")
    json_path.write_text(json.dumps(_jsonable(report), indent=2, sort_keys=True) + "\n")
    md_path.write_text(render_markdown(report))
    print(md_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

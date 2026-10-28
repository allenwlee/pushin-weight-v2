"""OpenAI and Anthropic size test: read-only launch preflight (plan U7).

Plan: docs/plans/2026-10-27-113859-ops-oai-anthropic-size-20261027-plan.md

The preflight never connects to a database and never writes anywhere. The
operator saves one read-only query result with the Render CLI, then this script
checks it together with the saved manifest, the keyword and roster tables and
the frozen query file:

1. Save the xbackfiller state (read only, rolled back):

   render psql dpg-dbfemu2vcj2c73fsafe0-a -o json --command \
     "$(.venv/bin/python -m scripts.backfill_size_preflight --print-xbackfiller-sql)" \
     > DIR/preflight-xbackfiller.json

2. Check it (stage ``pre-seed`` before ``backfill_size_seed seed``, ``post-seed`` after):

   .venv/bin/python -m scripts.backfill_size_preflight --stage pre-seed \
     --manifest DIR/manifest.json --xbackfiller DIR/preflight-xbackfiller.json \
     --keywords docs/analysis/2026-10-28-182625-oai-anthropic-keywords.csv \
     --roster docs/analysis/2026-10-28-182625-oai-anthropic-roster.csv \
     --deployed-revision e5edf737 [--check-credentials] > DIR/preflight-pre-seed.json

The JSON result goes to standard output and a short table to standard error.
The exit status is 0 only when every check required at that stage passes,
1 when one fails and 2 for unusable input. The saved JSON result is also the
database before-snapshot: pass it to ``backfill_size_report --size-before``.

Checks (U7): 1 identity, 2 July held, 3 queries, 4 route exclusions,
5 keywords (pending before the seed), 6 lab-list author roles (pending before
the seed), 7 on-demand credentials (only with ``--check-credentials``),
8 free space, 9 table sizes before seeding. The classifier catalog digest is
recorded by the seed command's undo receipt, not here.

``--check-credentials`` reads exactly ``TWITTERAPI_IO_ON_DEMAND_API_KEY`` and
``DEEPINFRA_ON_DEMAND`` from the literal ``NAME=value`` lines of
``~/.env.secrets`` (never executing the file, never another name) and makes two
GET requests that cost nothing: the TwitterAPI balance and the DeepInfra
account. Only numbers and HTTP statuses are reported; key values are never
printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from scripts.backfill_size_report import (
    CREDITS_PER_USD,
    FROZEN_QUERIES_SHA256,
    NO_BODY_MAX_CREDITS,
    SEARCH_REQUEST_LIMIT,
    XBACKFILLER_FORMAT,
    load_document,
    render_sql,
    validate_job_id,
)
from scripts.backfill_size_seed import (
    BRANDS,
    LAB_LISTS,
    KeywordRow,
    RosterRow,
    SeedRefused,
    read_keyword_csv,
    read_roster_csv,
)

ROOT = Path(__file__).resolve().parents[1]
XBACKFILLER_SQL_PATH = ROOT / "scripts" / "backfill_size_preflight_xbackfiller.sql"
POLICY_RELATIVE_PATH = "config/harvest_policy.yaml"
DEFAULT_FROZEN_QUERIES = ROOT / "docs" / "analysis" / "2026-10-27-215214-oai-anthropic-frozen-queries.json"

PREFLIGHT_FORMAT = "oai-anthropic-size-preflight/v1"
RESULT_FORMAT = "oai-anthropic-size-preflight-result/v1"
STAGES = ("pre-seed", "post-seed")

# R6: the dedicated backfill database (Render ID, database and role name).
XBACKFILLER = "xbackfiller"
XBACKFILLER_IDENTITY = {"name": XBACKFILLER, "user": XBACKFILLER}
XBACKFILLER_RENDER_ID = "dpg-dbfemu2vcj2c73fsafe0-a"
CREDENTIAL_PURPOSE = "on-demand"

# R8: July's paused collector job. Job states are paused, ready, completed and
# cancelled (core.models.CollectionJob); "ready" is runnable, so it is not held.
JULY_JOB_ID = "d4440f2e-0366-44ec-9bfe-fe12ac3df79c"
JULY_HELD_STATES = frozenset({"paused", "completed", "cancelled"})
DEFAULT_MAX_SNAPSHOT_AGE = timedelta(minutes=60)

# KTD4: the main list (config.yaml x_monitor_list_id); lab lists come from the seed.
MAIN_LIST_ID = 2067062923525275922

# R2: X advanced search counts characters, suffix included.
QUERY_CHARACTER_LIMIT = 512

# Branch-only harvest policy block (U1). It may be the only difference from the
# deployed production policy, and it may only add the two size-test brands.
BRANCH_POLICY_MARKER = "# Branch-only (ops/oai-anthropic-size-20261027)"

# R10: 7,000 requests at most 20 posts (300 credits) each.
REQUIRED_TWITTERAPI_CREDITS = SEARCH_REQUEST_LIMIT * NO_BODY_MAX_CREDITS
TWITTERAPI_KEY_NAME = "TWITTERAPI_IO_ON_DEMAND_API_KEY"
DEEPINFRA_KEY_NAME = "DEEPINFRA_ON_DEMAND"
SECRET_NAMES = frozenset({TWITTERAPI_KEY_NAME, DEEPINFRA_KEY_NAME})
DEFAULT_SECRETS_FILE = Path("~/.env.secrets")
TWITTERAPI_INFO_URL = "https://api.twitterapi.io/oapi/my/info"
DEEPINFRA_ME_URL = "https://api.deepinfra.com/v1/me"
PROBE_URLS = frozenset({TWITTERAPI_INFO_URL, DEEPINFRA_ME_URL})
USER_AGENT = "pushinweight-size-preflight/1"
REDACTED = "[redacted]"

# Check 8. 1 GB = 10^9 bytes, the smaller reading of the 20 GB disk.
BYTES_PER_GB = 10**9
DEFAULT_DISK_GB = 20.0
# About 4x the ~0.5 GB expected: the plan's ~24,000 fetched and ~16,000 kept
# posts at the 2026-10-26 xbackfiller sizing rates (~9.3 KB of collection rows
# per fetched post, ~16.9 KB of enrichment rows per kept post).
DEFAULT_PROJECTED_GROWTH_GB = 2.0

MAX_LISTED = 50
REVISION = re.compile(r"[0-9a-f]{7,40}")


# ---------------------------------------------------------------------------
# SQL and saved output
# ---------------------------------------------------------------------------

_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|CREATE|GRANT|REVOKE|COPY|MERGE|CALL|VACUUM|LOCK|COMMIT)\b",
    re.IGNORECASE,
)


def xbackfiller_sql(*, template: str | None = None) -> str:
    """The read-only preflight query with the July job filled in."""
    template = XBACKFILLER_SQL_PATH.read_text() if template is None else template
    if not template.startswith("BEGIN TRANSACTION READ ONLY;\n") or not template.rstrip().endswith("ROLLBACK;"):
        raise ValueError("preflight SQL must be one read-only transaction that rolls back")
    if _FORBIDDEN_SQL.search(template) or set(template) & set('"$`\\'):
        raise ValueError("preflight SQL may only read and must be safe inside a double-quoted shell argument")
    return render_sql(template, {"july_job_id": validate_job_id(JULY_JOB_ID)})


def load_preflight_document(text: str) -> dict:
    return load_document(text, PREFLIGHT_FORMAT)


def read_deployed_policy(revision: str) -> bytes | None:
    """The harvest policy file at the deployed production revision (read-only git)."""
    try:
        return subprocess.run(
            ["git", "show", f"{revision}:{POLICY_RELATIVE_PATH}"],
            cwd=ROOT, capture_output=True, check=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def strip_branch_only_policy(text: str) -> tuple[str, list[str]]:
    """Remove the branch-only openai/anthropic block; return the rest and its brands.

    The block starts at the marker comment and runs over the following indented,
    non-blank lines. It may only define the two size-test brands with
    ``paths: [none]``.
    """
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith(BRANCH_POLICY_MARKER)]
    if not starts:
        return text, []
    if len(starts) > 1:
        raise ValueError("the branch-only policy block appears more than once")
    start = end = starts[0]
    while end < len(lines) and lines[end].startswith(" ") and lines[end].strip():
        end += 1
    block = yaml.safe_load("brands:\n" + "".join(lines[start:end]))
    brands = (block or {}).get("brands") or {}
    if set(brands) != set(BRANDS):
        raise ValueError(f"the branch-only policy block defines {sorted(brands)}, not exactly {sorted(BRANDS)}")
    for name, entry in brands.items():
        if not isinstance(entry, Mapping) or entry.get("paths") != ["none"]:
            raise ValueError(f"branch-only brand {name} must use paths: [none]")
    return "".join(lines[:start] + lines[end:]), sorted(brands)


# ---------------------------------------------------------------------------
# Check records
# ---------------------------------------------------------------------------


def _check(number: int, name: str, status: str, summary: str, *, evidence: Mapping[str, Any] | None = None,
           problems: Iterable[str] = (), warnings: Iterable[str] = ()) -> dict:
    return {
        "id": number, "name": name, "status": status, "summary": summary,
        "problems": list(problems), "warnings": list(warnings), "evidence": dict(evidence or {}),
    }


def _verdict(problems: list[str]) -> str:
    return "fail" if problems else "pass"


def _when(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _first_difference(left: str, right: str) -> int:
    for index, (a, b) in enumerate(zip(left, right, strict=False)):
        if a != b:
            return index
    return min(len(left), len(right))


@dataclass(frozen=True)
class Unit:
    window: int
    scope_key: str
    name: str
    is_route: bool
    query: Any
    since: Any
    until: Any


def _scopes(manifest: Mapping[str, Any]) -> Iterator[tuple[int, dict]]:
    windows = manifest.get("windows")
    if not isinstance(windows, list) or not windows:
        raise ValueError("the manifest has no windows")
    for position, window in enumerate(windows, start=1):
        scope = ((window or {}).get("collection_definition") or {}).get("scope")
        if not isinstance(scope, dict):
            raise TypeError(f"manifest window {position} has no collection scope")
        yield int(window.get("index") or position), scope


def manifest_units(manifest: Mapping[str, Any]) -> list[Unit]:
    units = []
    for window, scope in _scopes(manifest):
        metadata = scope.get("route_metadata") or {}
        for unit in scope.get("units") or []:
            key = str(unit.get("scope_key"))
            ownership = unit.get("ownership") or {}
            meta = metadata.get(key)
            is_route = isinstance(meta, Mapping)
            units.append(Unit(
                window=window, scope_key=key,
                name=str(meta.get("name")) if is_route else str(ownership.get("call_id")),
                is_route=is_route, query=ownership.get("query"),
                since=ownership.get("since_epoch"), until=ownership.get("until_epoch"),
            ))
    return units


# ---------------------------------------------------------------------------
# Check 1: identity
# ---------------------------------------------------------------------------


def _host_matches(host: Any) -> bool:
    return isinstance(host, str) and (host == XBACKFILLER_RENDER_ID or host.startswith(XBACKFILLER_RENDER_ID + "."))


def check_identity(manifest: Mapping[str, Any], doc: Mapping[str, Any]) -> dict:
    problems = []
    if doc.get("database") != XBACKFILLER or doc.get("session_user") != XBACKFILLER:
        problems.append(f"saved query ran as database {doc.get('database')!r}, session_user "
                        f"{doc.get('session_user')!r}; both must be {XBACKFILLER!r}")
    if doc.get("transaction_read_only") != "on":
        problems.append("saved query did not run in a read-only transaction")
    if manifest.get("database") != XBACKFILLER_IDENTITY:
        problems.append(f"manifest database {manifest.get('database')!r} is not {XBACKFILLER_IDENTITY}")
    if manifest.get("credential_purpose") != CREDENTIAL_PURPOSE:
        problems.append(f"manifest credential purpose {manifest.get('credential_purpose')!r} is not {CREDENTIAL_PURPOSE!r}")
    windows = []
    for window, scope in _scopes(manifest):
        row = {key: scope.get(key) for key in ("response_storage", "database", "database_host", "credential_purpose")}
        windows.append({"window": window, **row})
        if row["response_storage"] != "database":
            problems.append(f"window {window}: response_storage {row['response_storage']!r} is not 'database'")
        if row["database"] != XBACKFILLER_IDENTITY:
            problems.append(f"window {window}: database {row['database']!r} is not {XBACKFILLER_IDENTITY}")
        if not _host_matches(row["database_host"]):
            problems.append(f"window {window}: database_host {row['database_host']!r} is not {XBACKFILLER_RENDER_ID}")
        if row["credential_purpose"] != CREDENTIAL_PURPOSE:
            problems.append(f"window {window}: credential purpose {row['credential_purpose']!r} is not {CREDENTIAL_PURPOSE!r}")
    hosts = sorted({str(row["database_host"]) for row in windows})
    summary = (f"database {doc.get('database')}, session_user {doc.get('session_user')}, read only "
               f"{doc.get('transaction_read_only')}; {len(windows)} window(s) on "
               f"{', '.join(sorted({str(row['response_storage']) for row in windows}))} storage at {', '.join(hosts)}")
    evidence = {
        "database": doc.get("database"), "session_user": doc.get("session_user"),
        "current_user": doc.get("current_user"), "transaction_read_only": doc.get("transaction_read_only"),
        "manifest_database": manifest.get("database"), "windows": windows,
    }
    return _check(1, "identity", _verdict(problems), summary, evidence=evidence, problems=problems)


# ---------------------------------------------------------------------------
# Check 2: July held
# ---------------------------------------------------------------------------


def july_snapshot(doc: Mapping[str, Any]) -> dict:
    july = doc.get("july") or {}
    job = july.get("job") or {}
    return {
        "job_id": job.get("id"), "job_key": job.get("job_key"), "state": job.get("state"),
        "definition_sha256": job.get("definition_sha256"), "active_run_id": job.get("active_run_id"),
        "author_contexts": job.get("author_contexts"), "run_count": july.get("run_count"),
        "runs_by_status": july.get("runs_by_status"), "scope_rows": july.get("scope_rows"),
    }


def check_july(doc: Mapping[str, Any], *, now: datetime, max_age: timedelta = DEFAULT_MAX_SNAPSHOT_AGE) -> dict:
    problems, warnings = [], []
    taken = _when(doc.get("generated_at"))
    age = now - taken
    if age > max_age or age < -timedelta(minutes=5):
        problems.append(f"the saved xbackfiller state is {age.total_seconds() / 60:.0f} minutes old "
                        f"(limit {max_age.total_seconds() / 60:.0f}); save it again just before the preflight")
    snapshot = july_snapshot(doc)
    if snapshot["job_id"] != JULY_JOB_ID:
        problems.append(f"July job {JULY_JOB_ID} was not found in xbackfiller")
    elif snapshot["state"] not in JULY_HELD_STATES:
        problems.append(f"July job {snapshot['job_key']} is {snapshot['state']!r}, not paused")
    live, stale = [], []
    for run in doc.get("running_historical_runs") or []:
        lease = run.get("lease_expires_at")
        row = {key: run.get(key) for key in ("run_id", "job_id", "job_key", "job_state", "lease_expires_at")}
        (live if lease is None or _when(lease) > taken else stale).append(row)
    for row in live:
        lease = row["lease_expires_at"] or "no expiry"
        problems.append(f"historical run {row['run_id']} of {row['job_key']} holds a live lease ({lease})")
    locks = [lock for lock in doc.get("advisory_locks") or [] if lock.get("granted")]
    if locks:
        problems.append(f"{len(locks)} advisory lock(s) held by other sessions: a backfill controller may be running")
    ready = doc.get("ready_historical_jobs") or []
    if ready:
        warnings.append(f"{len(ready)} other historical job(s) are 'ready' (runnable): "
                        + ", ".join(str(job.get("job_key")) for job in ready[:MAX_LISTED]))
    summary = (f"July {snapshot['job_key']} {snapshot['state']}; {snapshot['run_count']} runs "
               f"{json.dumps(snapshot['runs_by_status'], sort_keys=True)}; {snapshot['scope_rows']} scope rows; "
               f"{len(live)} live lease(s), {len(stale)} stale running run(s), {len(locks)} advisory lock(s); "
               f"state saved {age.total_seconds() / 60:.0f} min ago")
    evidence = {
        "snapshot_taken_at": taken.isoformat(), "snapshot_age_seconds": int(age.total_seconds()),
        "july": snapshot, "live_leases": live, "stale_running_runs": stale,
        "advisory_locks": locks, "ready_historical_jobs": ready,
    }
    return _check(2, "July held", _verdict(problems), summary, evidence=evidence, problems=problems, warnings=warnings)


# ---------------------------------------------------------------------------
# Check 3: queries
# ---------------------------------------------------------------------------


def _frozen_tables(frozen: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Mapping[str, Any]]]:
    baseline = {str(row["name"]): row["text"] for row in frozen.get("baseline") or []}
    new = {str(row["name"]): row for row in frozen.get("new") or []}
    return baseline, new


def check_queries(manifest: Mapping[str, Any], frozen: Mapping[str, Any], *, frozen_sha256: str,
                  deployed_revision: str, deployed_policy: bytes | None, branch_policy: bytes) -> dict:
    problems: list[str] = []
    if frozen_sha256 != FROZEN_QUERIES_SHA256:
        problems.append(f"frozen query file sha256 {frozen_sha256} is not the plan's {FROZEN_QUERIES_SHA256}")
    baseline, new = _frozen_tables(frozen)
    stats: dict[str, dict[str, Any]] = {}
    mismatched: dict[str, list[int]] = {}
    too_long: dict[str, list[int]] = {}
    unknown: Counter = Counter()
    for unit in manifest_units(manifest):
        expected = new[unit.name]["text"] if unit.is_route and unit.name in new else (
            None if unit.is_route else baseline.get(unit.name))
        if expected is None:
            unknown[unit.name] += 1
            continue
        row = stats.setdefault(unit.name, {"kind": "route" if unit.is_route else "production",
                                           "units": 0, "max_suffixed_length": 0})
        row["units"] += 1
        query = unit.query if isinstance(unit.query, str) else ""
        if query != expected:
            mismatched.setdefault(unit.name, []).append(_first_difference(query, expected))
        length = len(f"{query} since_time:{unit.since} until_time:{unit.until}")
        row["max_suffixed_length"] = max(row["max_suffixed_length"], length)
        if length > QUERY_CHARACTER_LIMIT:
            too_long.setdefault(unit.name, []).append(length)
    for name, count in sorted(unknown.items()):
        problems.append(f"{name}: not a frozen query ({count} units)")
    for name in [*baseline, *new]:
        if name not in stats:
            problems.append(f"{name}: frozen query missing from the manifest")
    for name, positions in mismatched.items():
        problems.append(f"{name}: query differs from the frozen text at character {min(positions)} "
                        f"in {len(positions)} of {stats[name]['units']} units")
    for name, lengths in too_long.items():
        problems.append(f"{name}: suffixed query is {max(lengths)} characters (limit {QUERY_CHARACTER_LIMIT}) "
                        f"in {len(lengths)} units")
    policy: dict[str, Any] = {
        "path": POLICY_RELATIVE_PATH, "deployed_revision": deployed_revision,
        "branch_sha256": hashlib.sha256(branch_policy).hexdigest(),
        "deployed_sha256": hashlib.sha256(deployed_policy).hexdigest() if deployed_policy is not None else None,
    }
    if deployed_policy is None:
        problems.append(f"{POLICY_RELATIVE_PATH} at deployed revision {deployed_revision} could not be read "
                        "(git show failed; fetch the revision)")
    else:
        try:
            stripped, added = strip_branch_only_policy(branch_policy.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
            problems.append(f"{POLICY_RELATIVE_PATH}: branch-only block is not the expected one: {exc}")
        else:
            policy["branch_only_brands"] = added
            same = stripped.encode("utf-8") == deployed_policy
            policy["identical_outside_branch_block"] = same
            if not same:
                at = _first_difference(stripped.encode("utf-8").decode("latin-1"), deployed_policy.decode("latin-1"))
                problems.append(f"{POLICY_RELATIVE_PATH} at deployed revision {deployed_revision} differs from this "
                                f"branch's file outside the branch-only block (first difference at byte {at})")
    total = sum(row["units"] for row in stats.values())
    longest = max((row["max_suffixed_length"] for row in stats.values()), default=0)
    summary = (f"{total} units over {len(stats)} queries checked against the frozen file; longest suffixed "
               f"query {longest}/{QUERY_CHARACTER_LIMIT}; policy at {deployed_revision} "
               f"{'identical outside the branch-only block' if policy.get('identical_outside_branch_block') else 'NOT identical'}")
    evidence = {"frozen_sha256": frozen_sha256, "queries": dict(sorted(stats.items())), "harvest_policy": policy}
    return _check(3, "queries", _verdict(problems), summary, evidence=evidence, problems=problems)


# ---------------------------------------------------------------------------
# Check 4: route exclusions
# ---------------------------------------------------------------------------


def check_not_include(manifest: Mapping[str, Any], frozen: Mapping[str, Any]) -> dict:
    _, new = _frozen_tables(frozen)
    problems = []
    routes: dict[str, dict[str, Any]] = {}
    differing: dict[str, list] = {}
    for _, scope in _scopes(manifest):
        for meta in (scope.get("route_metadata") or {}).values():
            name = str(meta.get("name"))
            if name not in new:
                differing.setdefault(name, []).append(meta.get("not_include"))
                continue
            row = routes.setdefault(name, {"units": 0, "host_call_ids": set(),
                                           "not_include": list(new[name].get("not_include") or [])})
            row["units"] += 1
            row["host_call_ids"].add(str(meta.get("host_call_id")))
            if meta.get("not_include") != row["not_include"]:
                differing.setdefault(name, []).append(meta.get("not_include"))
    for name, values in differing.items():
        if name not in new:
            problems.append(f"{name}: route is not in the frozen file")
            continue
        problems.append(f"{name}: not_include {values[0]!r} differs from the frozen list "
                        f"{routes[name]['not_include']!r} in {len(values)} of {routes[name]['units']} units")
    for name in new:
        if name not in routes:
            problems.append(f"{name}: no route metadata in the manifest")
    evidence = {name: {**row, "host_call_ids": sorted(row["host_call_ids"])} for name, row in sorted(routes.items())}
    summary = f"{len(routes)} routes; not_include equals the frozen list in every unit" if not problems else (
        f"{len(problems)} route exclusion problem(s)")
    return _check(4, "route not_include", _verdict(problems), summary, evidence={"routes": evidence},
                  problems=problems)


# ---------------------------------------------------------------------------
# Check 5: literal BrandKeyword rows
# ---------------------------------------------------------------------------


def check_keywords(stage: str, keywords: list[KeywordRow], doc: Mapping[str, Any]) -> dict:
    rows = doc.get("brand_keywords") or []
    literal = {(row.get("brand"), row.get("pattern")) for row in rows if row.get("is_regex") is False}
    missing = [{"brand": kw.brand, "pattern": kw.pattern} for kw in keywords if (kw.brand, kw.pattern) not in literal]
    expected = {(kw.brand, kw.pattern) for kw in keywords}
    present = len(keywords) - len(missing)
    evidence = {
        "csv_rows": dict(Counter(kw.brand for kw in keywords)),
        "database_rows": dict(Counter(str(row.get("brand")) for row in rows)),
        "regex_rows": sum(1 for row in rows if row.get("is_regex") is not False),
        "rows_not_in_csv": sum(1 for row in rows if (row.get("brand"), row.get("pattern")) not in expected),
        "missing_count": len(missing),
        "missing": missing[:MAX_LISTED],
    }
    if stage == "pre-seed":
        return _check(5, "keywords", "pending",
                      f"pending until the seed; {present} of {len(keywords)} literal keyword rows present now",
                      evidence=evidence)
    problems = [f"{row['brand']}: no literal BrandKeyword row for {row['pattern']!r}" for row in missing[:MAX_LISTED]]
    if len(missing) > MAX_LISTED:
        problems.append(f"... and {len(missing) - MAX_LISTED} more")
    summary = f"{present} of {len(keywords)} keyword CSV rows have a literal BrandKeyword row"
    return _check(5, "keywords", _verdict(problems), summary, evidence=evidence, problems=problems)


# ---------------------------------------------------------------------------
# Check 6: lab-list author roles
# ---------------------------------------------------------------------------


def _author_scope(manifest: Mapping[str, Any]) -> tuple[dict[str, Mapping], list[str], list[int]]:
    contexts: dict[str, Mapping] = {}
    degraded: list[str] = []
    list_ids: list[int] = []
    for _, scope in _scopes(manifest):
        author_scope = scope.get("author_scope") or {}
        for author, context in (author_scope.get("contexts") or {}).items():
            contexts.setdefault(str(author), context)
        degraded.extend(str(note) for note in author_scope.get("degraded") or [] if str(note) not in degraded)
        for value in author_scope.get("list_ids") or [author_scope.get("list_id")]:
            if value is not None and int(value) not in list_ids:
                list_ids.append(int(value))
    return contexts, degraded, list_ids


def check_roster(stage: str, roster: list[RosterRow], manifest: Mapping[str, Any], doc: Mapping[str, Any]) -> dict:
    contexts, degraded, list_ids = _author_scope(manifest)
    roster_ids = {row.author_id for row in roster}
    members: dict[str, set[str]] = {}
    for row in doc.get("list_memberships") or []:
        members.setdefault(str(row.get("list_id")), set()).add(str(row.get("author_id")))
    main_members = members.get(str(MAIN_LIST_ID), set())
    problems, warnings = [], []
    for brand, list_id in LAB_LISTS.items():
        if list_id not in list_ids:
            problems.append(f"manifest author scope does not include the {brand} lab list {list_id}")
    roster_failures = 0
    for row in roster:
        context = contexts.get(row.author_id)
        if context is None:
            problems.append(f"{row.brand} {row.role} @{row.username} ({row.author_id}) has no author context")
        elif row.brand not in (context.get(f"{row.role}_brands") or []):
            problems.append(f"{row.brand} {row.role} @{row.username} ({row.author_id}) context lacks the "
                            f"{row.role} role for {row.brand}")
        else:
            continue
        roster_failures += 1
    roster_degraded = [note for note in degraded if note.split(":")[1:2] and note.split(":")[1] in roster_ids]
    overlap = [{"author_id": row.author_id, "username": row.username, "brand": row.brand}
               for row in roster if row.author_id in main_members]
    other_brands = []
    for row in roster:
        context = contexts.get(row.author_id) or {}
        official = sorted(set(context.get("official_brands") or []) - {row.brand})
        staff = sorted(set(context.get("staff_brands") or []) - {row.brand})
        if official or staff:
            other_brands.append({"author_id": row.author_id, "username": row.username, "brand": row.brand,
                                 "other_official": official, "other_staff": staff})
    main_contexts = sum(1 for author in contexts if author not in roster_ids)
    july_contexts = july_snapshot(doc).get("author_contexts")
    if main_contexts == 0:
        message = (f"the manifest freezes no main list author contexts (July's job froze {july_contexts}); "
                   "Call A posts by main-list members would lose their official/staff roles")
        warnings.append(message)
        problems.append(message)
    if not main_members:
        warnings.append(f"xbackfiller has no active memberships for the main list {MAIN_LIST_ID}, so a manifest "
                        "built there freezes no main-list author roles")
    lab_missing = {brand: sorted(row.author_id for row in roster if row.brand == brand
                                 and row.author_id not in members.get(str(list_id), set()))
                   for brand, list_id in LAB_LISTS.items()}
    evidence = {
        "roster_authors": len(roster), "manifest_contexts": len(contexts), "main_list_contexts": main_contexts,
        "july_author_contexts": july_contexts, "manifest_list_ids": [str(value) for value in list_ids],
        "database_memberships": {list_id: len(ids) for list_id, ids in sorted(members.items())},
        "roster_missing_from_lab_membership": {brand: len(ids) for brand, ids in lab_missing.items()},
        "roster_degraded": roster_degraded, "main_list_overlap": overlap, "other_brand_roles": other_brands,
    }
    if stage == "pre-seed":
        summary = (f"pending until the seed; manifest has {len(contexts)} contexts ({main_contexts} main-list); "
                   f"{len(overlap)} roster author(s) on the main list")
        return _check(6, "lab-list roles", "pending", summary, evidence=evidence, warnings=warnings)
    summary = (f"{len(roster) - roster_failures} of {len(roster)} roster authors "
               f"carry their role; {len(roster_degraded)} degraded; {len(overlap)} on the main list; "
               f"{len(other_brands)} with other brands; {main_contexts} main-list contexts")
    return _check(6, "lab-list roles", _verdict(problems), summary, evidence=evidence, problems=problems,
                  warnings=[w for w in warnings if w not in problems])


# ---------------------------------------------------------------------------
# Check 7: on-demand credentials
# ---------------------------------------------------------------------------


def _unquote(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in {"'", '"'}:
        end = raw.find(raw[0], 1)
        return raw[1:end] if end != -1 else ""
    return raw.split()[0] if raw else ""


def read_secret(path: Path, name: str) -> str | None:
    """Parse only the literal ``[export ]NAME=value`` line for an allowed name."""
    if name not in SECRET_NAMES:
        raise ValueError(f"{name} is not an on-demand credential this preflight may read")
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8")
    except OSError:
        return None
    pattern = re.compile(r"\s*(?:export\s+)?" + re.escape(name) + r"=(.*)")
    value = None
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if match:
            value = _unquote(match.group(1))
    return value or None


def http_get_json(url: str, headers: Mapping[str, str], *, timeout: float = 20.0) -> tuple[int, Any]:
    """GET one of the two free account endpoints; return (status, parsed body or None)."""
    if url not in PROBE_URLS:
        raise ValueError("only the TwitterAPI balance and DeepInfra account endpoints may be probed")
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, body = response.status, response.read(1_000_000)
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, None
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None


def _redact(value: Any, secrets: Iterable[str]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, Mapping):
        return {key: _redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(item, secrets) for item in value]
    return value


def check_credentials(*, secrets_path: Path, http_get: Callable[[str, Mapping[str, str]], tuple[int, Any]]) -> dict:
    problems: list[str] = []
    twitter_key = read_secret(secrets_path, TWITTERAPI_KEY_NAME)
    deepinfra_key = read_secret(secrets_path, DEEPINFRA_KEY_NAME)
    secrets = [key for key in (twitter_key, deepinfra_key) if key]
    twitter: dict[str, Any] = {"credential": TWITTERAPI_KEY_NAME, "purpose": CREDENTIAL_PURPOSE,
                               "resolved": bool(twitter_key), "required_credits": REQUIRED_TWITTERAPI_CREDITS,
                               "required_usd": REQUIRED_TWITTERAPI_CREDITS / CREDITS_PER_USD}
    deepinfra: dict[str, Any] = {"credential": DEEPINFRA_KEY_NAME, "purpose": CREDENTIAL_PURPOSE,
                                 "resolved": bool(deepinfra_key)}
    if not twitter_key:
        problems.append(f"{TWITTERAPI_KEY_NAME} is not set in {secrets_path}")
    else:
        try:
            status, body = http_get(TWITTERAPI_INFO_URL, {"X-API-Key": twitter_key, "User-Agent": USER_AGENT})
        except Exception as exc:  # noqa: BLE001 - any transport failure fails the check
            problems.append(f"TwitterAPI balance request failed: {type(exc).__name__}: {exc}")
        else:
            credits = body.get("recharge_credits") if isinstance(body, Mapping) else None
            twitter["http_status"] = status
            if status != 200 or type(credits) is not int:
                problems.append(f"TwitterAPI balance request returned HTTP {status} without a recharge_credits number")
            else:
                twitter["recharge_credits"] = credits
                twitter["usd"] = credits / CREDITS_PER_USD
                if credits < REQUIRED_TWITTERAPI_CREDITS:
                    problems.append(f"TwitterAPI balance {credits:,} credits is below the "
                                    f"{REQUIRED_TWITTERAPI_CREDITS:,} needed for {SEARCH_REQUEST_LIMIT:,} requests")
    if not deepinfra_key:
        problems.append(f"{DEEPINFRA_KEY_NAME} is not set in {secrets_path}")
    else:
        try:
            status, _ = http_get(DEEPINFRA_ME_URL, {"Authorization": f"Bearer {deepinfra_key}", "User-Agent": USER_AGENT})
        except Exception as exc:  # noqa: BLE001 - any transport failure fails the check
            problems.append(f"DeepInfra account request failed: {type(exc).__name__}: {exc}")
        else:
            deepinfra["http_status"] = status
            if status != 200:
                problems.append(f"DeepInfra account request returned HTTP {status}")
    summary = (f"TwitterAPI {twitter.get('recharge_credits', 'unknown')} credits (need "
               f"{REQUIRED_TWITTERAPI_CREDITS:,}); DeepInfra HTTP {deepinfra.get('http_status', 'not called')}")
    check = _check(7, "credentials", _verdict(problems), summary,
                   evidence={"twitterapi": twitter, "deepinfra": deepinfra}, problems=problems)
    return _redact(check, secrets)


def credentials_not_run() -> dict:
    return _check(7, "credentials", "not_run", "not checked; rerun with --check-credentials before launch")


# ---------------------------------------------------------------------------
# Checks 8 and 9: free space and the before-snapshot
# ---------------------------------------------------------------------------


def _gb_bytes(value: float) -> int:
    return int(Decimal(str(value)) * BYTES_PER_GB)


def check_free_space(doc: Mapping[str, Any], *, disk_gb: float, projected_growth_gb: float) -> dict:
    used = doc.get("database_bytes")
    if type(used) is not int:
        return _check(8, "free space", "fail", "database size missing from the saved state",
                      problems=["database_bytes missing from the saved xbackfiller state"])
    disk, growth = _gb_bytes(disk_gb), _gb_bytes(projected_growth_gb)
    free, floor = disk - used, used + growth
    problems = []
    if free < 2 * growth:
        problems.append(f"free space {free / BYTES_PER_GB:.2f} GB is below twice the projected growth "
                        f"({2 * growth / BYTES_PER_GB:.2f} GB)")
    evidence = {
        "disk_bytes": disk, "database_bytes": used, "free_bytes": free, "projected_growth_bytes": growth,
        "required_free_bytes": 2 * growth, "stop_floor_database_bytes": floor,
        "free_bytes_at_stop_floor": disk - floor,
        "note": "1 GB = 10^9 bytes; pg_database_size excludes WAL and server overhead on the same disk",
    }
    summary = (f"database {used / BYTES_PER_GB:.2f} GB of {disk_gb:g} GB; free {free / BYTES_PER_GB:.2f} GB "
               f"vs 2 x {projected_growth_gb:g} GB projected; stop floor {floor / BYTES_PER_GB:.2f} GB")
    return _check(8, "free space", _verdict(problems), summary, evidence=evidence, problems=problems)


def size_before(doc: Mapping[str, Any]) -> dict | None:
    """Table sizes in the report's input shape, so --size-before accepts the result file."""
    sizes, total = doc.get("table_sizes"), doc.get("database_bytes")
    if not isinstance(sizes, Mapping) or not sizes or not all(type(v) is int for v in sizes.values()):
        return None
    if type(total) is not int:
        return None
    return {"format": XBACKFILLER_FORMAT, "source": "backfill_size_preflight", "database": doc.get("database"),
            "generated_at": doc.get("generated_at"), "table_sizes": dict(sizes), "database_bytes": total}


def check_sizes(doc: Mapping[str, Any]) -> dict:
    snapshot = size_before(doc)
    if snapshot is None:
        return _check(9, "size snapshot", "fail", "table sizes missing from the saved state",
                      problems=["table_sizes or database_bytes missing from the saved xbackfiller state"])
    largest = sorted(snapshot["table_sizes"].items(), key=lambda item: (-item[1], item[0]))[:5]
    evidence = {"tables": len(snapshot["table_sizes"]), "table_bytes": sum(snapshot["table_sizes"].values()),
                "database_bytes": snapshot["database_bytes"], "largest_tables": dict(largest)}
    summary = (f"{len(snapshot['table_sizes'])} tables, database {snapshot['database_bytes'] / BYTES_PER_GB:.3f} GB "
               "recorded as the before-snapshot")
    return _check(9, "size snapshot", "pass", summary, evidence=evidence)


# ---------------------------------------------------------------------------
# Evaluation and output
# ---------------------------------------------------------------------------


def required_checks(stage: str, *, credentials_checked: bool) -> list[int]:
    required = [1, 2, 3, 4, 8, 9] if stage == "pre-seed" else [1, 2, 3, 4, 5, 6, 8, 9]
    return sorted([*required, 7]) if credentials_checked else required


def evaluate(*, stage: str, manifest: Mapping[str, Any], doc: Mapping[str, Any], frozen: Mapping[str, Any],
             frozen_sha256: str, keywords: list[KeywordRow], roster: list[RosterRow], deployed_revision: str,
             deployed_policy: bytes | None, branch_policy: bytes, disk_gb: float = DEFAULT_DISK_GB,
             projected_growth_gb: float = DEFAULT_PROJECTED_GROWTH_GB, now: datetime | None = None,
             credentials: dict | None = None, max_snapshot_age: timedelta = DEFAULT_MAX_SNAPSHOT_AGE) -> dict:
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    now = now or datetime.now(UTC)
    checks = [
        check_identity(manifest, doc),
        check_july(doc, now=now, max_age=max_snapshot_age),
        check_queries(manifest, frozen, frozen_sha256=frozen_sha256, deployed_revision=deployed_revision,
                      deployed_policy=deployed_policy, branch_policy=branch_policy),
        check_not_include(manifest, frozen),
        check_keywords(stage, keywords, doc),
        check_roster(stage, roster, manifest, doc),
        credentials if credentials is not None else credentials_not_run(),
        check_free_space(doc, disk_gb=disk_gb, projected_growth_gb=projected_growth_gb),
        check_sizes(doc),
    ]
    required = required_checks(stage, credentials_checked=credentials is not None)
    ok = all(item["status"] == "pass" for item in checks if item["id"] in required)
    return {
        "format": RESULT_FORMAT,
        "stage": stage,
        "generated_at": now.isoformat(),
        "ok": ok,
        "required_checks": required,
        "checks": checks,
        "warnings": [warning for item in checks for warning in item["warnings"]],
        "july_snapshot": july_snapshot(doc),
        "size_before": size_before(doc),
    }


def render_table(result: Mapping[str, Any]) -> str:
    verdict = "PASS" if result["ok"] else "FAIL"
    lines = [f"OpenAI/Anthropic size-test preflight: stage {result['stage']}, result {verdict}",
             f"{'#':>2}  {'status':<8} {'check':<18} evidence"]
    for item in result["checks"]:
        required = "" if item["id"] in result["required_checks"] else " (not required)"
        lines.append(f"{item['id']:>2}  {item['status']:<8} {item['name']:<18} {item['summary']}{required}")
        lines.extend(f"{'':>30}- {problem}" for problem in item["problems"])
    if result["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in result["warnings"])
    return "\n".join(lines)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--print-xbackfiller-sql", action="store_true",
                        help="print the read-only xbackfiller query and exit")
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--manifest", type=Path, help="saved run_backfill --windows dry-run output")
    parser.add_argument("--xbackfiller", type=Path, help="saved render psql -o json output of the preflight query")
    parser.add_argument("--keywords", type=Path, help="keyword CSV from backfill_size_seed build")
    parser.add_argument("--roster", type=Path, help="roster CSV from backfill_size_seed build")
    parser.add_argument("--deployed-revision", help="production revision currently deployed (e.g. e5edf737)")
    parser.add_argument("--frozen-queries", type=Path, default=DEFAULT_FROZEN_QUERIES)
    parser.add_argument("--disk-gb", type=float, default=DEFAULT_DISK_GB)
    parser.add_argument("--projected-growth-gb", type=float, default=DEFAULT_PROJECTED_GROWTH_GB)
    parser.add_argument("--max-snapshot-age-minutes", type=int, default=int(DEFAULT_MAX_SNAPSHOT_AGE.total_seconds() // 60))
    parser.add_argument("--check-credentials", action="store_true",
                        help="probe the TwitterAPI balance and the DeepInfra key (two free GET requests)")
    parser.add_argument("--secrets-file", type=Path, default=DEFAULT_SECRETS_FILE)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.print_xbackfiller_sql:
        print(xbackfiller_sql())
        return 0
    needed = {"--stage": args.stage, "--manifest": args.manifest, "--xbackfiller": args.xbackfiller,
              "--keywords": args.keywords, "--roster": args.roster, "--deployed-revision": args.deployed_revision}
    missing = [flag for flag, value in needed.items() if value is None]
    if missing:
        parser.error("missing " + ", ".join(missing))
    if not REVISION.fullmatch(args.deployed_revision):
        parser.error("--deployed-revision must be a hexadecimal git revision")
    if args.disk_gb <= 0 or args.projected_growth_gb <= 0 or args.max_snapshot_age_minutes <= 0:
        parser.error("--disk-gb, --projected-growth-gb and --max-snapshot-age-minutes must be positive")
    try:
        manifest = json.loads(args.manifest.read_text())
        doc = load_preflight_document(args.xbackfiller.read_text())
        frozen_bytes = args.frozen_queries.read_bytes()
        frozen = json.loads(frozen_bytes)
        keywords = read_keyword_csv(args.keywords)
        roster = read_roster_csv(args.roster)
        branch_policy = (ROOT / POLICY_RELATIVE_PATH).read_bytes()
    except (OSError, ValueError, SeedRefused) as exc:
        print(f"preflight input error: {exc}", file=sys.stderr)
        return 2
    credentials = None
    if args.check_credentials:
        credentials = check_credentials(secrets_path=args.secrets_file, http_get=http_get_json)
    try:
        result = evaluate(
            stage=args.stage, manifest=manifest, doc=doc, frozen=frozen,
            frozen_sha256=hashlib.sha256(frozen_bytes).hexdigest(), keywords=keywords, roster=roster,
            deployed_revision=args.deployed_revision, deployed_policy=read_deployed_policy(args.deployed_revision),
            branch_policy=branch_policy, disk_gb=args.disk_gb, projected_growth_gb=args.projected_growth_gb,
            credentials=credentials, max_snapshot_age=timedelta(minutes=args.max_snapshot_age_minutes),
        )
    except (KeyError, TypeError, ValueError) as exc:
        print(f"preflight input error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    inputs = {name: {"path": str(path), "sha256": _sha256_file(path)} for name, path in (
        ("manifest", args.manifest), ("xbackfiller", args.xbackfiller), ("keywords", args.keywords),
        ("roster", args.roster), ("frozen_queries", args.frozen_queries))}
    inputs.update(deployed_revision=args.deployed_revision, disk_gb=args.disk_gb,
                  projected_growth_gb=args.projected_growth_gb, credentials_checked=credentials is not None)
    result = {**result, "inputs": inputs}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(render_table(result), file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

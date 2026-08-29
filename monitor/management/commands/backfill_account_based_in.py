"""Populate typed Account fields from TwitterAPI User About on staging."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from core.models import Account
from monitor.twitterapi.user_about import FetchSelection, fetch_user_about_batch

PILOT_LIMIT = 100
PILOT_ATTEMPTS = 110
PILOT_CREDITS = 1_980
PILOT_WALL_SECONDS = 1_800
PILOT_QPS = 5.0
STAGING_DATABASE_NAME = "pushinweight_staging"


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return round(ordered[index], 3)


def _select_accounts(*, limit: int, seed: str, refresh: bool) -> list[FetchSelection]:
    queryset = Account.objects.exclude(handle__isnull=True).exclude(handle="")
    if not refresh:
        queryset = queryset.filter(account_based_in_fetched_at__isnull=True)
    rows = list(queryset.values_list("author_id", "handle"))
    rows.sort(key=lambda row: hashlib.sha256(f"{seed}:{row[0]}".encode()).hexdigest())
    return [
        FetchSelection(author_id=str(author_id), handle=str(handle))
        for author_id, handle in rows[:limit]
    ]


def _is_authorized_staging_executor() -> bool:
    if settings.OLLIJA_STAGING_MODE:
        return True
    if os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") != "staging":
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    return bool(row and row[0] == STAGING_DATABASE_NAME)


def _render_markdown(report: dict[str, Any]) -> str:
    outcome = report["outcome"]
    usage = report["usage"]
    lines = [
        "# TwitterAPI User About staging pilot",
        "",
        f"- Started: {report['started_at']}",
        f"- Finished: {report['finished_at']}",
        f"- Mode: {report['mode']}",
        f"- Selected Accounts: {report['sample']['selected']}",
        f"- Accepted: {outcome['accepted']}",
        f"- Changed: {outcome['changed']}",
        f"- Success-empty: {outcome['success_empty']}",
        f"- Attempts: {usage['attempts']}",
        f"- Retries: {usage['retries']}",
        f"- Projected credits: {usage['projected_credits']}",
        f"- Projected USD: ${usage['projected_usd']:.5f}",
        f"- Wall seconds: {usage['wall_seconds']}",
        f"- Effective QPS: {usage['effective_qps']}",
        f"- Stop reason: {outcome['stop_reason'] or 'none'}",
        f"- Schema diagnostics: `{json.dumps(outcome['schema_diagnostics'])}`",
        "",
        "## Aggregate distributions",
        "",
        f"- Provider outcomes: `{json.dumps(outcome['provider_reasons'], sort_keys=True)}`",
        f"- Country yield: `{json.dumps(outcome['country_yield'], sort_keys=True)}`",
        f"- Location accurate: `{json.dumps(outcome['location_accurate'], sort_keys=True)}`",
        f"- About source: `{json.dumps(outcome['about_source'], sort_keys=True)}`",
        "",
        "## Cost reconciliation",
        "",
        (
            "The command records a published-rate projection only. The provider's "
            "Recent API Calls ledger requires a separate dashboard session token. "
            "Until that exact UTC-window ledger is attached, actual credit burn is "
            "inconclusive and this pilot cannot authorize expansion."
        ),
        "",
    ]
    return "\n".join(lines)


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument("--limit", type=int, default=PILOT_LIMIT)
        parser.add_argument("--max-attempts", type=int, default=PILOT_ATTEMPTS)
        parser.add_argument("--max-credits", type=int, default=PILOT_CREDITS)
        parser.add_argument("--max-wall-seconds", type=int, default=PILOT_WALL_SECONDS)
        parser.add_argument("--max-qps", type=float, default=PILOT_QPS)
        parser.add_argument("--provider-qps", type=float)
        parser.add_argument("--seed", default="account-based-in-pilot-v1")
        parser.add_argument("--json-report", type=Path)
        parser.add_argument("--markdown-report", type=Path)

    def handle(self, **options):
        limit = options["limit"]
        if limit <= 0:
            raise CommandError("limit must be positive")
        if options["apply"] and (
            limit > PILOT_LIMIT
            or options["max_attempts"] > PILOT_ATTEMPTS
            or options["max_credits"] > PILOT_CREDITS
            or options["max_wall_seconds"] > PILOT_WALL_SECONDS
            or options["max_qps"] > PILOT_QPS
        ):
            raise CommandError("requested value exceeds the staging pilot cap")
        if options["apply"] and not _is_authorized_staging_executor():
            raise CommandError("apply is restricted to the managed staging environment")
        selections = _select_accounts(
            limit=limit,
            seed=options["seed"],
            refresh=options["refresh"],
        )
        if len(selections) < limit:
            raise CommandError(
                f"only {len(selections)} eligible Accounts exist; requested {limit}"
            )

        if not options["apply"]:
            summary = {
                "mode": "dry_run",
                "selected": len(selections),
                "seed": options["seed"],
                "http_calls": 0,
                "writes": 0,
            }
            self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
            return

        if options["max_attempts"] < limit:
            raise CommandError("max-attempts cannot be lower than selected Accounts")
        if options["max_credits"] < limit * 18:
            raise CommandError(
                "max-credits cannot cover one projected call per Account"
            )
        provider_qps = options["provider_qps"]
        if provider_qps is None or provider_qps <= 0:
            raise CommandError("provider-qps must be verified and supplied for apply")
        if options["max_qps"] <= 0:
            raise CommandError("max-qps must be positive")
        if not options["json_report"] or not options["markdown_report"]:
            raise CommandError("apply requires both aggregate report paths")
        api_key = os.environ.get("TWITTERAPI_IO_API_KEY", "")
        if not api_key:
            raise CommandError(
                "TWITTERAPI_IO_API_KEY is absent from managed environment"
            )

        effective_qps = min(float(options["max_qps"]), float(provider_qps))
        started_at = timezone.now()
        batch = asyncio.run(
            fetch_user_about_batch(
                selections,
                api_key=api_key,
                rate_qps=effective_qps,
                max_attempts=options["max_attempts"],
                max_credits=options["max_credits"],
                max_wall_seconds=options["max_wall_seconds"],
            )
        )

        selected_ids = {selection.author_id for selection in selections}
        provider_reasons: Counter[str] = Counter()
        rejected_fields: Counter[str] = Counter()
        leaf_coverage: Counter[str] = Counter()
        country_yield: Counter[str] = Counter()
        location_accurate: Counter[str] = Counter()
        about_source: Counter[str] = Counter()
        schema_diagnostics: set[str] = set()
        accepted = changed = unchanged = success_empty = 0
        for fetched in batch.outcomes:
            provider_reasons[fetched.reason] += 1
            if fetched.schema_diagnostic:
                schema_diagnostics.update(fetched.schema_diagnostic)
            observation = fetched.observation
            if observation is None or fetched.author_id not in selected_ids:
                continue
            outcome = Account.apply_observation(
                author_id=fetched.author_id,
                observed_author_id=observation.author_id,
                source="user_about",
                observed_at=observation.candidates["account_based_in_fetched_at"],
                candidates=observation.candidates,
                present_fields=observation.present_fields,
            )
            if outcome.identity_rejected:
                provider_reasons["identity_mismatch"] += 1
                continue
            accepted += 1
            if outcome.applied_fields:
                changed += 1
            else:
                unchanged += 1
            rejected_fields.update(outcome.rejected_fields)
            leaf_coverage.update(observation.present_fields)
            code = observation.candidates.get("country_code")
            country_yield["mapped" if code else "unmapped"] += 1
            if not observation.candidates.get("account_based_in"):
                success_empty += 1
            if "location_accurate" in observation.present_fields:
                value = observation.candidates.get("location_accurate")
                location_accurate[str(value).lower()] += 1
            if "source" in observation.present_fields:
                value = observation.candidates.get("source")
                about_source[str(value) if value else "empty"] += 1

        finished_at = timezone.now()
        full_population = Account.objects.filter(
            ~Q(handle__isnull=True), ~Q(handle="")
        ).count()
        report = {
            "schema_version": 1,
            "mode": "staging_apply",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "sample": {
                "selected": len(selections),
                "seed": options["seed"],
                "selection": "missing-first deterministic SHA-256 order",
            },
            "budgets": {
                "accounts": limit,
                "attempts": options["max_attempts"],
                "projected_credits": options["max_credits"],
                "wall_seconds": options["max_wall_seconds"],
                "operator_qps": options["max_qps"],
                "provider_qps": provider_qps,
                "effective_qps": effective_qps,
            },
            "usage": {
                "attempts": batch.attempts,
                "retries": batch.retries,
                "projected_credits": batch.projected_credits,
                "projected_usd": round(batch.projected_credits / 100_000, 6),
                "actual_credits": None,
                "wall_seconds": batch.wall_seconds,
                "effective_qps": round(batch.attempts / batch.wall_seconds, 3)
                if batch.wall_seconds
                else None,
                "latency_ms": {
                    "p50": _percentile(batch.latencies_ms, 0.50),
                    "p95": _percentile(batch.latencies_ms, 0.95),
                },
            },
            "outcome": {
                "attempted_accounts": len(batch.outcomes),
                "accepted": accepted,
                "changed": changed,
                "unchanged": unchanged,
                "success_empty": success_empty,
                "not_attempted": len(selections) - len(batch.outcomes),
                "provider_reasons": dict(sorted(provider_reasons.items())),
                "rejected_fields": dict(sorted(rejected_fields.items())),
                "leaf_coverage": dict(sorted(leaf_coverage.items())),
                "country_yield": dict(sorted(country_yield.items())),
                "location_accurate": dict(sorted(location_accurate.items())),
                "about_source": dict(sorted(about_source.items())),
                "schema_diagnostics": sorted(schema_diagnostics),
                "stop_reason": batch.stop_reason,
            },
            "projection": {
                "callable_accounts": full_population,
                "credits": full_population * 18,
                "usd": round(full_population * 18 / 100_000, 6),
                "seconds_at_effective_qps": round(full_population / effective_qps, 1),
            },
            "provider_ledger": {
                "status": "pending_external_reconciliation",
                "actual_credits": None,
                "expansion_authorized": False,
            },
        }
        json_path = Path(options["json_report"])
        markdown_path = Path(options["markdown_report"])
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(_render_markdown(report), encoding="utf-8")
        self.stdout.write(json.dumps(report, indent=2, sort_keys=True))

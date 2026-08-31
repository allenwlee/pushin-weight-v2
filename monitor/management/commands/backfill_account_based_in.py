"""Populate typed Account fields from TwitterAPI User About."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import time
from collections import Counter
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Q
from django.utils import timezone
from psycopg import sql

from core.models import Account
from monitor.twitterapi.user_about import FetchSelection, fetch_user_about_batch
from x_monitor.twitterapi_credentials import (
    TwitterApiCredentialPurpose,
    require_twitterapi_api_key,
)

PILOT_LIMIT = 100
PILOT_ATTEMPTS = 110
PILOT_CREDITS = 1_980
PILOT_WALL_SECONDS = 1_800
PILOT_QPS = 5.0
STAGING_DATABASE_NAME = "pushinweight_staging"
PRODUCTION_DATABASE_NAME = "pushinweight_shadow"
PRODUCTION_LIMIT = 100_000
PRODUCTION_ATTEMPTS = 110_000
PRODUCTION_CREDITS = 1_980_000
PRODUCTION_WALL_SECONDS = 86_400
PRODUCTION_QPS = 20.0
PRODUCTION_CONCURRENCY = 20
PRODUCTION_CHUNK_SIZE = 1_000
PRODUCTION_RECEIPT_MAX_AGE = timedelta(hours=24)
PRODUCTION_RUN_LOCK_ID = 7_221_168_864_462_031_081
REQUIRED_MIGRATIONS = {
    "0020_account_account_based_in_and_more",
    "0021_account_user_about_live_schema",
    "0022_account_verification_reason_timestamp",
    "0023_account_user_about_unavailable",
    "0024_account_identity_profile_label_long_description",
    "0025_account_verification_override_year",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TWITTER_SNOWFLAKE_EPOCH_MS = 1_288_834_974_657
_AGE_BUCKETS = ("old_pre_2015", "middle_2015_2019", "new_2020_plus")
_SIZE_BUCKETS = ("small_lt_1k", "medium_1k_100k", "large_100k_plus", "unknown")
_GEOGRAPHY_BUCKETS = ("us", "eu", "jp", "other", "unknown")
_JP_LOCATION = re.compile(
    r"japan|日本|tokyo|東京|osaka|大阪|kyoto|京都|yokohama|横浜",
    re.IGNORECASE,
)
_US_LOCATION = re.compile(
    r"united states|(?:^|[^a-z])usa(?:[^a-z]|$)|u[.]s[.]|new york|"
    r"california|los angeles|san francisco|washington,? dc|texas|florida|"
    r"chicago|boston|seattle",
    re.IGNORECASE,
)
_EU_LOCATION = re.compile(
    r"united kingdom|(?:^|[^a-z])uk(?:[^a-z]|$)|england|london|france|"
    r"paris|germany|berlin|spain|madrid|italy|rome|netherlands|amsterdam|"
    r"belgium|brussels|sweden|stockholm|norway|oslo|denmark|copenhagen|"
    r"finland|helsinki|poland|warsaw|ireland|dublin|portugal|lisbon|"
    r"austria|vienna|switzerland|zurich|czech|prague|greece|athens|europe|"
    r"(?:^|[^a-z])eu(?:[^a-z]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RecoveryReceipt:
    receipt_sha256: str
    created_at: datetime
    snapshot_account_count: int
    row_digest: str
    storage: str
    snapshot_relation: str


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return round(ordered[index], 3)


def _eligible_accounts(*, refresh: bool, eligible_before: datetime | None = None):
    queryset = (
        Account.objects.filter(author_id__regex=r"^[0-9]+$")
        .exclude(handle__isnull=True)
        .exclude(handle="")
    )
    if not refresh:
        queryset = queryset.filter(account_based_in_fetched_at__isnull=True)
    if eligible_before is not None:
        queryset = queryset.filter(first_seen_at__lte=eligible_before)
    return queryset


def _select_accounts(
    *,
    limit: int,
    seed: str,
    refresh: bool,
    eligible_before: datetime | None = None,
    strategy: str = "deterministic_hash",
) -> list[FetchSelection]:
    queryset = _eligible_accounts(
        refresh=refresh,
        eligible_before=eligible_before,
    )
    if strategy == "diversity_stratified":
        return _select_stratified_accounts(queryset=queryset, limit=limit, seed=seed)
    rows = list(queryset.values_list("author_id", "handle"))
    rows.sort(key=lambda row: hashlib.sha256(f"{seed}:{row[0]}".encode()).hexdigest())
    return [
        FetchSelection(author_id=str(author_id), handle=str(handle))
        for author_id, handle in rows[:limit]
    ]


def _account_age_bucket(author_id: str, created_at: datetime | None) -> str:
    account_date = created_at
    if account_date is None:
        try:
            milliseconds = (int(author_id) >> 22) + _TWITTER_SNOWFLAKE_EPOCH_MS
            account_date = datetime.fromtimestamp(milliseconds / 1_000, tz=UTC)
        except (OverflowError, ValueError, OSError):
            return "unknown"
    if account_date < datetime(2015, 1, 1, tzinfo=UTC):
        return "old_pre_2015"
    if account_date < datetime(2020, 1, 1, tzinfo=UTC):
        return "middle_2015_2019"
    return "new_2020_plus"


def _account_size_bucket(followers_count: int | None) -> str:
    if followers_count is None:
        return "unknown"
    if followers_count < 1_000:
        return "small_lt_1k"
    if followers_count < 100_000:
        return "medium_1k_100k"
    return "large_100k_plus"


def _account_geography_bucket(location: str | None) -> str:
    if not location or not location.strip():
        return "unknown"
    if _JP_LOCATION.search(location):
        return "jp"
    if _US_LOCATION.search(location):
        return "us"
    if _EU_LOCATION.search(location):
        return "eu"
    return "other"


def _balanced_targets(labels: tuple[str, ...], limit: int) -> dict[str, int]:
    quotient, remainder = divmod(limit, len(labels))
    return {
        label: quotient + (1 if index < remainder else 0)
        for index, label in enumerate(labels)
    }


def _select_stratified_accounts(*, queryset, limit: int, seed: str):
    rows = list(
        queryset.values_list(
            "author_id",
            "handle",
            "created_at",
            "followers_count",
            "location",
        )
    )
    candidates = []
    for author_id, handle, created_at, followers_count, location in rows:
        author_id = str(author_id)
        age_bucket = _account_age_bucket(author_id, created_at)
        if age_bucket == "unknown":
            continue
        candidates.append(
            (
                hashlib.sha256(f"{seed}:{author_id}".encode()).hexdigest(),
                FetchSelection(author_id=author_id, handle=str(handle)),
                age_bucket,
                _account_size_bucket(followers_count),
                _account_geography_bucket(location),
            )
        )
    candidates.sort(key=lambda candidate: candidate[0])

    targets = (
        _balanced_targets(_AGE_BUCKETS, limit),
        _balanced_targets(_SIZE_BUCKETS, limit),
        _balanced_targets(_GEOGRAPHY_BUCKETS, limit),
    )
    counts = (Counter(), Counter(), Counter())
    selected: list[FetchSelection] = []
    selected_indexes: set[int] = set()
    for _ in range(min(limit, len(candidates))):
        best_index = -1
        best_score = -1.0
        for index, candidate in enumerate(candidates):
            if index in selected_indexes:
                continue
            score = 0.0
            for dimension, bucket in enumerate(candidate[2:]):
                target = targets[dimension].get(bucket, 0)
                if target:
                    deficit = max(target - counts[dimension][bucket], 0)
                    score += deficit / target
            if score > best_score:
                best_index = index
                best_score = score
        selected_indexes.add(best_index)
        selected.append(candidates[best_index][1])
        for dimension, bucket in enumerate(candidates[best_index][2:]):
            counts[dimension][bucket] += 1
    return selected


def _selection_distribution(
    selections: list[FetchSelection],
) -> dict[str, dict[str, int]]:
    author_ids = [selection.author_id for selection in selections]
    rows = Account.objects.filter(author_id__in=author_ids).values_list(
        "author_id",
        "created_at",
        "followers_count",
        "location",
    )
    age: Counter[str] = Counter()
    size: Counter[str] = Counter()
    geography: Counter[str] = Counter()
    for author_id, created_at, followers_count, location in rows:
        age[_account_age_bucket(str(author_id), created_at)] += 1
        size[_account_size_bucket(followers_count)] += 1
        geography[_account_geography_bucket(location)] += 1
    return {
        "account_age": dict(sorted(age.items())),
        "audience_size": dict(sorted(size.items())),
        "profile_location_proxy": dict(sorted(geography.items())),
    }


def _current_database_name() -> str | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    return str(row[0]) if row else None


def _is_authorized_staging_executor() -> bool:
    if settings.OLLIJA_STAGING_MODE:
        return True
    if os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") != "staging":
        return False
    return _current_database_name() == STAGING_DATABASE_NAME


def _is_authorized_executor(target: str) -> bool:
    if target == "staging":
        return _is_authorized_staging_executor()
    if target == "production":
        return (
            os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "production"
            and _current_database_name() == PRODUCTION_DATABASE_NAME
        )
    return False


def _required_migrations_applied() -> bool:
    applied = set(
        MigrationRecorder.Migration.objects.filter(
            app="core",
            name__in=REQUIRED_MIGRATIONS,
        ).values_list("name", flat=True)
    )
    return applied == REQUIRED_MIGRATIONS


def _parse_recovery_receipt(encoded: str | None) -> RecoveryReceipt:
    if not encoded:
        raise CommandError("production apply requires a recovery receipt")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(padded.encode())
        payload = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandError("production recovery receipt is invalid") from exc
    if not isinstance(payload, dict):
        raise CommandError("production recovery receipt is invalid")
    expected_keys = {
        "schema_version",
        "database",
        "created_at",
        "snapshot_account_count",
        "snapshot_row_digest",
        "restore_account_count",
        "restore_row_digest",
        "storage",
        "snapshot_relation",
        "restore_proof",
        "receipt_sha256",
    }
    if set(payload) != expected_keys or payload.get("schema_version") != 1:
        raise CommandError("production recovery receipt is invalid")
    receipt_sha256 = payload.pop("receipt_sha256", None)
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    expected_sha256 = hashlib.sha256(canonical).hexdigest()
    if not isinstance(receipt_sha256, str) or not hmac.compare_digest(
        receipt_sha256,
        expected_sha256,
    ):
        raise CommandError("production recovery receipt digest does not match")
    if payload.get("database") != PRODUCTION_DATABASE_NAME:
        raise CommandError("production recovery receipt database does not match")
    snapshot_digest = payload.get("snapshot_row_digest")
    restore_digest = payload.get("restore_row_digest")
    if (
        not isinstance(snapshot_digest, str)
        or not _SHA256.fullmatch(snapshot_digest)
        or restore_digest != snapshot_digest
    ):
        raise CommandError("production recovery receipt restore digest does not match")
    snapshot_count = payload.get("snapshot_account_count")
    restore_count = payload.get("restore_account_count")
    if (
        type(snapshot_count) is not int
        or snapshot_count <= 0
        or restore_count != snapshot_count
    ):
        raise CommandError("production recovery receipt restore count does not match")
    if payload.get("storage") != "render-postgres-encrypted-at-rest":
        raise CommandError("production recovery receipt storage is not approved")
    snapshot_relation = payload.get("snapshot_relation")
    if not isinstance(snapshot_relation, str) or not re.fullmatch(
        r"account_user_about_backup\.accounts_[0-9]{8}t[0-9]{6}z",
        snapshot_relation,
    ):
        raise CommandError("production recovery receipt relation is invalid")
    if payload.get("restore_proof") != "temporary-relation-count-and-digest-match":
        raise CommandError("production recovery receipt restore proof is invalid")
    try:
        created_at = datetime.fromisoformat(str(payload.get("created_at")))
    except ValueError as exc:
        raise CommandError("production recovery receipt timestamp is invalid") from exc
    if timezone.is_naive(created_at):
        raise CommandError("production recovery receipt timestamp is invalid")
    age = timezone.now() - created_at
    if age < -timedelta(minutes=5) or age > PRODUCTION_RECEIPT_MAX_AGE:
        raise CommandError("production recovery receipt is stale")
    return RecoveryReceipt(
        receipt_sha256=receipt_sha256,
        created_at=created_at,
        snapshot_account_count=snapshot_count,
        row_digest=snapshot_digest,
        storage=str(payload["storage"]),
        snapshot_relation=snapshot_relation,
    )


def _verify_recovery_snapshot(receipt: RecoveryReceipt) -> None:
    schema_name, table_name = receipt.snapshot_relation.split(".", 1)
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [receipt.snapshot_relation])
        if cursor.fetchone()[0] is None:
            raise CommandError("production recovery snapshot relation is unavailable")
        cursor.execute(
            sql.SQL("SELECT count(*) FROM {}").format(
                sql.Identifier(schema_name, table_name)
            )
        )
        snapshot_count = int(cursor.fetchone()[0])
    if snapshot_count != receipt.snapshot_account_count:
        raise CommandError("production recovery snapshot Account count does not match")


@contextmanager
def _production_run_lock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [PRODUCTION_RUN_LOCK_ID])
        acquired = bool(cursor.fetchone()[0])
    if not acquired:
        raise CommandError("another production User About backfill is running")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [PRODUCTION_RUN_LOCK_ID])


def _render_markdown(report: dict[str, Any]) -> str:
    outcome = report["outcome"]
    usage = report["usage"]
    target = str(report["target"])
    lines = [
        f"# TwitterAPI User About {target} backfill",
        "",
        f"- Started: {report['started_at']}",
        f"- Finished: {report['finished_at']}",
        f"- Mode: {report['mode']}",
        f"- Selected Accounts: {report['sample']['selected']}",
        f"- Selection strategy: {report['sample']['selection']}",
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
        f"- Remaining eligible: {outcome['remaining_eligible']}",
        f"- Schema diagnostics: `{json.dumps(outcome['schema_diagnostics'])}`",
        "",
        "## Sample distribution",
        "",
        f"- Account age: `{json.dumps(report['sample']['distribution']['account_age'], sort_keys=True)}`",
        f"- Audience size: `{json.dumps(report['sample']['distribution']['audience_size'], sort_keys=True)}`",
        f"- Profile-location proxy: `{json.dumps(report['sample']['distribution']['profile_location_proxy'], sort_keys=True)}`",
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
            "Until that exact UTC-window ledger is attached, actual credit burn "
            "remains inconclusive."
        ),
        "",
    ]
    return "\n".join(lines)


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument(
            "--target",
            choices=("staging", "production"),
            default="staging",
        )
        parser.add_argument("--limit", type=int, default=PILOT_LIMIT)
        parser.add_argument("--max-attempts", type=int, default=PILOT_ATTEMPTS)
        parser.add_argument("--max-credits", type=int, default=PILOT_CREDITS)
        parser.add_argument("--max-wall-seconds", type=int, default=PILOT_WALL_SECONDS)
        parser.add_argument("--max-qps", type=float, default=PILOT_QPS)
        parser.add_argument("--provider-qps", type=float)
        parser.add_argument("--concurrency", type=int, default=1)
        parser.add_argument("--chunk-size", type=int, default=PILOT_LIMIT)
        parser.add_argument("--recovery-receipt")
        parser.add_argument("--require-complete", action="store_true")
        parser.add_argument("--seed", default="account-based-in-pilot-v1")
        parser.add_argument(
            "--selection-strategy",
            choices=("deterministic_hash", "diversity_stratified"),
            default="deterministic_hash",
        )
        parser.add_argument("--json-report", type=Path)
        parser.add_argument("--markdown-report", type=Path)

    def handle(self, **options):
        target = options["target"]
        limit = options["limit"]
        if limit <= 0:
            raise CommandError("limit must be positive")
        if options["concurrency"] <= 0:
            raise CommandError("concurrency must be positive")
        if options["chunk_size"] <= 0:
            raise CommandError("chunk-size must be positive")
        if target == "production" and options["refresh"]:
            raise CommandError("production refresh is not authorized")
        if options["require_complete"] and (
            target != "production" or not options["apply"]
        ):
            raise CommandError("require-complete is restricted to production apply")

        recovery_receipt: RecoveryReceipt | None = None
        eligible_before: datetime | None = None
        if options["apply"]:
            if target == "staging":
                exceeds_cap = (
                    limit > PILOT_LIMIT
                    or options["max_attempts"] > PILOT_ATTEMPTS
                    or options["max_credits"] > PILOT_CREDITS
                    or options["max_wall_seconds"] > PILOT_WALL_SECONDS
                    or options["max_qps"] > PILOT_QPS
                    or options["concurrency"] > 1
                    or options["chunk_size"] > PILOT_LIMIT
                )
                cap_name = "staging pilot"
            else:
                exceeds_cap = (
                    limit > PRODUCTION_LIMIT
                    or options["max_attempts"] > PRODUCTION_ATTEMPTS
                    or options["max_credits"] > PRODUCTION_CREDITS
                    or options["max_wall_seconds"] > PRODUCTION_WALL_SECONDS
                    or options["max_qps"] > PRODUCTION_QPS
                    or options["concurrency"] > PRODUCTION_CONCURRENCY
                    or options["chunk_size"] > PRODUCTION_CHUNK_SIZE
                )
                cap_name = "production safety"
            if exceeds_cap:
                raise CommandError(f"requested value exceeds the {cap_name} cap")
            if not _is_authorized_executor(target):
                raise CommandError(
                    f"apply is restricted to the managed {target} environment"
                )
            if not _required_migrations_applied():
                raise CommandError("required User About migrations are not applied")
            if target == "production":
                recovery_receipt = _parse_recovery_receipt(options["recovery_receipt"])
                _verify_recovery_snapshot(recovery_receipt)
                eligible_before = recovery_receipt.created_at
                snapshotted_rows = Account.objects.filter(
                    first_seen_at__lte=eligible_before
                ).count()
                if snapshotted_rows != recovery_receipt.snapshot_account_count:
                    raise CommandError(
                        "production recovery receipt Account count does not match"
                    )

        eligible_count = _eligible_accounts(
            refresh=options["refresh"],
            eligible_before=eligible_before,
        ).count()
        selections = _select_accounts(
            limit=limit,
            seed=options["seed"],
            refresh=options["refresh"],
            eligible_before=eligible_before,
            strategy=options["selection_strategy"],
        )
        selection_distribution = _selection_distribution(selections)
        if target == "staging" and len(selections) < limit:
            raise CommandError(
                f"only {len(selections)} eligible Accounts exist; requested {limit}"
            )

        if not options["apply"]:
            summary = {
                "mode": "dry_run",
                "target": target,
                "eligible": eligible_count,
                "selected": len(selections),
                "seed": options["seed"],
                "selection_strategy": options["selection_strategy"],
                "selection_distribution": selection_distribution,
                "http_calls": 0,
                "writes": 0,
            }
            self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
            return

        if not selections:
            raise CommandError("no eligible Accounts exist")
        if options["max_attempts"] < len(selections):
            raise CommandError("max-attempts cannot be lower than selected Accounts")
        if options["max_credits"] < len(selections) * 18:
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

        effective_qps = min(float(options["max_qps"]), float(provider_qps))
        provider_reasons: Counter[str] = Counter()
        rejected_fields: Counter[str] = Counter()
        leaf_coverage: Counter[str] = Counter()
        country_yield: Counter[str] = Counter()
        location_accurate: Counter[str] = Counter()
        about_source: Counter[str] = Counter()
        schema_diagnostics: set[str] = set()
        accepted = changed = unchanged = success_empty = 0
        attempts = retries = projected_credits = attempted_accounts = 0
        latencies_ms: list[float] = []
        chunk_receipts: list[dict[str, Any]] = []
        stop_reason: str | None = None
        started_at = timezone.now()
        run_started = time.monotonic()

        lock = _production_run_lock() if target == "production" else nullcontext()
        with lock:
            try:
                api_key = require_twitterapi_api_key(
                    TwitterApiCredentialPurpose.ON_DEMAND
                )
            except RuntimeError as exc:
                raise CommandError(str(exc)) from exc

            for chunk_number, offset in enumerate(
                range(0, len(selections), options["chunk_size"]),
                start=1,
            ):
                elapsed = time.monotonic() - run_started
                remaining_wall = options["max_wall_seconds"] - elapsed
                if remaining_wall <= 0:
                    stop_reason = "wall_time_budget"
                    break
                remaining_attempts = options["max_attempts"] - attempts
                if remaining_attempts <= 0:
                    stop_reason = "attempt_budget"
                    break
                remaining_credits = options["max_credits"] - projected_credits
                if remaining_credits < 18:
                    stop_reason = "credit_budget"
                    break

                chunk = selections[offset : offset + options["chunk_size"]]
                batch = asyncio.run(
                    fetch_user_about_batch(
                        chunk,
                        api_key=api_key,
                        rate_qps=effective_qps,
                        concurrency=options["concurrency"],
                        max_attempts=remaining_attempts,
                        max_credits=remaining_credits,
                        max_wall_seconds=remaining_wall,
                    )
                )
                attempts += batch.attempts
                retries += batch.retries
                projected_credits += batch.projected_credits
                attempted_accounts += len(batch.outcomes)
                latencies_ms.extend(batch.latencies_ms)

                chunk_ids = {selection.author_id for selection in chunk}
                chunk_handles = {
                    selection.author_id: selection.handle for selection in chunk
                }
                accepted_before = accepted
                changed_before = changed
                for fetched in batch.outcomes:
                    provider_reasons[fetched.reason] += 1
                    if fetched.schema_diagnostic:
                        schema_diagnostics.update(fetched.schema_diagnostic)
                    observation = fetched.observation
                    if observation is None or fetched.author_id not in chunk_ids:
                        continue
                    outcome = Account.apply_observation(
                        author_id=fetched.author_id,
                        observed_author_id=observation.author_id,
                        source="user_about",
                        observed_at=observation.candidates[
                            "account_based_in_fetched_at"
                        ],
                        candidates=observation.candidates,
                        present_fields=observation.present_fields,
                        expected_handle=(
                            chunk_handles[fetched.author_id]
                            if observation.candidates.get("unavailable") is True
                            else None
                        ),
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

                chunk_receipt = {
                    "chunk": chunk_number,
                    "selected": len(chunk),
                    "attempted": len(batch.outcomes),
                    "accepted": accepted - accepted_before,
                    "changed": changed - changed_before,
                    "attempts": batch.attempts,
                    "retries": batch.retries,
                    "projected_credits": batch.projected_credits,
                    "stop_reason": batch.stop_reason,
                }
                chunk_receipts.append(chunk_receipt)
                self.stdout.write(
                    json.dumps({"progress": chunk_receipt}, sort_keys=True)
                )
                if batch.stop_reason:
                    stop_reason = batch.stop_reason
                    break

        finished_at = timezone.now()
        wall_seconds = round(time.monotonic() - run_started, 3)
        full_population = Account.objects.filter(
            ~Q(handle__isnull=True), ~Q(handle="")
        ).count()
        remaining_eligible = _eligible_accounts(
            refresh=options["refresh"],
            eligible_before=eligible_before,
        ).count()
        report = {
            "schema_version": 2,
            "mode": f"{target}_apply",
            "target": target,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "sample": {
                "selected": len(selections),
                "eligible_before_run": eligible_count,
                "eligible_cutoff": eligible_before.isoformat()
                if eligible_before
                else None,
                "seed": options["seed"],
                "selection": options["selection_strategy"],
                "distribution": selection_distribution,
            },
            "budgets": {
                "accounts": limit,
                "attempts": options["max_attempts"],
                "projected_credits": options["max_credits"],
                "wall_seconds": options["max_wall_seconds"],
                "operator_qps": options["max_qps"],
                "provider_qps": provider_qps,
                "effective_qps": effective_qps,
                "concurrency": options["concurrency"],
                "chunk_size": options["chunk_size"],
            },
            "usage": {
                "attempts": attempts,
                "retries": retries,
                "projected_credits": projected_credits,
                "projected_usd": round(projected_credits / 100_000, 6),
                "actual_credits": None,
                "wall_seconds": wall_seconds,
                "effective_qps": round(attempts / wall_seconds, 3)
                if wall_seconds
                else None,
                "latency_ms": {
                    "p50": _percentile(latencies_ms, 0.50),
                    "p95": _percentile(latencies_ms, 0.95),
                },
            },
            "outcome": {
                "attempted_accounts": attempted_accounts,
                "accepted": accepted,
                "changed": changed,
                "unchanged": unchanged,
                "success_empty": success_empty,
                "not_attempted": len(selections) - attempted_accounts,
                "remaining_eligible": remaining_eligible,
                "provider_reasons": dict(sorted(provider_reasons.items())),
                "rejected_fields": dict(sorted(rejected_fields.items())),
                "leaf_coverage": dict(sorted(leaf_coverage.items())),
                "country_yield": dict(sorted(country_yield.items())),
                "location_accurate": dict(sorted(location_accurate.items())),
                "about_source": dict(sorted(about_source.items())),
                "schema_diagnostics": sorted(schema_diagnostics),
                "stop_reason": stop_reason,
            },
            "chunks": chunk_receipts,
            "projection": {
                "callable_accounts": full_population,
                "credits": full_population * 18,
                "usd": round(full_population * 18 / 100_000, 6),
                "seconds_at_effective_qps": round(full_population / effective_qps, 1),
            },
            "provider_ledger": {
                "status": "pending_external_reconciliation",
                "actual_credits": None,
                "production_authorized": target == "production",
            },
            "recovery": (
                {
                    "receipt_sha256": recovery_receipt.receipt_sha256,
                    "created_at": recovery_receipt.created_at.isoformat(),
                    "snapshot_account_count": recovery_receipt.snapshot_account_count,
                    "storage": recovery_receipt.storage,
                    "snapshot_relation": recovery_receipt.snapshot_relation,
                    "restore_proved": True,
                }
                if recovery_receipt
                else None
            ),
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
        if target == "production" and stop_reason:
            raise CommandError(f"production backfill stopped: {stop_reason}")
        if options["require_complete"] and remaining_eligible:
            raise CommandError(
                "production backfill incomplete: "
                f"{remaining_eligible} eligible Accounts remain"
            )

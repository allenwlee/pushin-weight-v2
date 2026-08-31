"""Normalize persisted Account Based In values without provider I/O."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Count
from django.utils import timezone

from core.models import (
    Account,
    AccountBasedInMapping,
    Country,
    CountryLabel,
    CountryRegion,
    Region,
    RegionLabel,
)
from monitor.account_geography import MANIFEST_SHA256
from monitor.account_geography_recovery import (
    PRODUCTION_DATABASE_NAME,
    GeographyRecoveryReceipt,
    parse_geography_recovery_receipt,
    verify_geography_recovery_snapshot,
)

STAGING_DATABASE_NAME = "pushinweight_staging"
GEOGRAPHY_RUN_LOCK_ID = 7_221_168_864_462_031_109
REQUIRED_MIGRATIONS = {
    "0026_account_geography_taxonomy",
    "0027_account_country_foreign_key",
}
MANIFEST_PATH = Path("monitor/data/account_geography.json")
CENSUS_PATH = Path("monitor/data/account_based_in_census.json")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class Classification:
    totals: dict[str, int]
    unresolved_values: dict[str, int]
    unknown_values: tuple[str, ...]
    nonblank_accounts: int
    distinct_values: int
    census_sha256: str
    would_change: int


def _current_database_name() -> str | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    return str(row[0]) if row else None


def _is_authorized_executor(target: str) -> bool:
    if target == "staging":
        if settings.OLLIJA_STAGING_MODE:
            return True
        return (
            os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "staging"
            and _current_database_name() == STAGING_DATABASE_NAME
        )
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


@contextmanager
def _geography_run_lock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [GEOGRAPHY_RUN_LOCK_ID])
        acquired = bool(cursor.fetchone()[0])
    if not acquired:
        raise CommandError("another account geography reconciliation is running")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [GEOGRAPHY_RUN_LOCK_ID])


def _load_manifest() -> dict[str, Any]:
    path = Path(settings.BASE_DIR) / MANIFEST_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if hashlib.sha256(canonical).hexdigest() != MANIFEST_SHA256:
        raise CommandError("account geography manifest digest does not match")
    return payload


def _load_frozen_census() -> dict[str, Any]:
    path = Path(settings.BASE_DIR) / CENSUS_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "captured_at",
        "database",
        "row_encoding",
        "census_sha256",
        "distinct_values",
        "nonblank_accounts",
        "classification",
        "unresolved_values",
    }
    if (
        set(payload) != required
        or payload["schema_version"] != 1
        or payload["database"] != PRODUCTION_DATABASE_NAME
        or not _SHA256.fullmatch(str(payload["census_sha256"]))
    ):
        raise CommandError("frozen account_based_in census is invalid")
    return payload


def _verify_taxonomy_seed(manifest: dict[str, Any]) -> None:
    expected_regions = {
        (
            item["key"],
            item["m49_code"],
            item["source"],
            item["level"],
            item["parent"],
        )
        for item in manifest["regions"]
    }
    actual_regions = set(
        Region.objects.values_list("key", "m49_code", "source", "level", "parent_id")
    )
    expected_region_labels = {
        (item["key"], lang, label)
        for item in manifest["regions"]
        for lang, label in item["labels"].items()
    }
    actual_region_labels = set(
        RegionLabel.objects.values_list("region_id", "lang", "label")
    )
    expected_countries = {
        (
            item["code"],
            item["m49_code"],
            item["display_parent_country"],
            item["display_parent_relationship_type"],
        )
        for item in manifest["countries"]
    }
    actual_countries = set(
        Country.objects.values_list(
            "code",
            "m49_code",
            "display_parent_country_id",
            "display_parent_relationship_type",
        )
    )
    expected_country_labels = {
        (item["code"], lang, label)
        for item in manifest["countries"]
        for lang, label in item["labels"].items()
    }
    actual_country_labels = set(
        CountryLabel.objects.values_list("country_id", "lang", "label")
    )
    expected_country_regions = {
        (
            item["code"],
            item["region_key"],
            "owner-reviewed" if item["code"] == "TW" else "un-m49",
        )
        for item in manifest["countries"]
    }
    actual_country_regions = set(
        CountryRegion.objects.values_list("country_id", "region_id", "source")
    )
    expected_mappings = {
        (
            item["value"],
            item["country_code"],
            item["region_key"],
            item["review_note"],
        )
        for item in manifest["account_based_in_mappings"]
    }
    actual_mappings = set(
        AccountBasedInMapping.objects.values_list(
            "value", "country_id", "region_id", "review_note"
        )
    )
    if (
        actual_regions != expected_regions
        or actual_region_labels != expected_region_labels
        or actual_countries != expected_countries
        or actual_country_labels != expected_country_labels
        or actual_country_regions != expected_country_regions
        or actual_mappings != expected_mappings
    ):
        raise CommandError("account geography taxonomy seed does not match manifest")


def _census_digest(rows: list[tuple[str, int]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(rows)
    return hashlib.sha256(stream.getvalue().encode()).hexdigest()


def _classify_accounts(queryset, manifest: dict[str, Any]) -> Classification:
    normalized = queryset.exclude(account_based_in__isnull=True).exclude(
        account_based_in=""
    )
    mappings = {
        item["value"]: (item["country_code"], item["region_key"])
        for item in manifest["account_based_in_mappings"]
    }
    explicit_unresolved = set(manifest["explicit_unresolved_values"])

    census_rows = list(
        normalized.values("account_based_in")
        .annotate(row_count=Count("author_id"))
        .order_by("account_based_in")
        .values_list("account_based_in", "row_count")
    )
    state_rows = normalized.values(
        "account_based_in", "country_id", "based_in_region_id"
    ).annotate(row_count=Count("author_id"))

    totals: Counter[str] = Counter()
    unresolved_values: Counter[str] = Counter()
    unknown_values: set[str] = set()
    would_change = 0
    for raw, country_id, region_id, row_count in state_rows.values_list(
        "account_based_in", "country_id", "based_in_region_id", "row_count"
    ):
        target = mappings.get(raw)
        if target is not None:
            expected_country, expected_region = target
            kind = "country" if expected_country is not None else "region"
        elif raw in explicit_unresolved:
            expected_country = expected_region = None
            kind = "unresolved"
            unresolved_values[raw] += row_count
        else:
            unknown_values.add(raw)
            continue
        totals[kind] += row_count
        if (country_id, region_id) != (expected_country, expected_region):
            would_change += row_count

    return Classification(
        totals={key: totals.get(key, 0) for key in ("country", "region", "unresolved")},
        unresolved_values=dict(sorted(unresolved_values.items())),
        unknown_values=tuple(sorted(unknown_values)),
        nonblank_accounts=sum(count for _value, count in census_rows),
        distinct_values=len(census_rows),
        census_sha256=_census_digest(census_rows),
        would_change=would_change,
    )


def _verify_frozen_production_census(
    classification: Classification,
    frozen: dict[str, Any],
) -> None:
    if (
        classification.census_sha256 != frozen["census_sha256"]
        or classification.distinct_values != frozen["distinct_values"]
        or classification.nonblank_accounts != frozen["nonblank_accounts"]
        or classification.totals != frozen["classification"]
        or classification.unresolved_values != frozen["unresolved_values"]
    ):
        raise CommandError(
            "production account_based_in census does not match frozen input"
        )


def _render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Account geography reconciliation",
            "",
            f"- Target: {report['target']}",
            f"- Mode: {report['mode']}",
            f"- Started: {report['started_at']}",
            f"- Finished: {report['finished_at']}",
            f"- Nonblank Accounts: {report['nonblank_accounts']}",
            f"- Distinct values: {report['distinct_values']}",
            f"- Classification: `{json.dumps(report['classification'], sort_keys=True)}`",
            f"- Unresolved values: `{json.dumps(report['unresolved_values'], sort_keys=True)}`",
            f"- Changed: {report['changed']}",
            f"- Unchanged: {report['unchanged']}",
            f"- Rejected: {report['rejected']}",
            "- HTTP calls: 0",
            "- Provider credits: 0",
            "",
        ]
    )


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--target", choices=("staging", "production"), default="staging"
        )
        parser.add_argument("--confirm-database")
        parser.add_argument("--recovery-receipt")
        parser.add_argument("--chunk-size", type=int, default=1_000)
        parser.add_argument("--json-report", type=Path)
        parser.add_argument("--markdown-report", type=Path)

    def handle(self, **options):
        target = options["target"]
        if options["chunk_size"] <= 0 or options["chunk_size"] > 5_000:
            raise CommandError("chunk-size must be between 1 and 5000")
        if not _required_migrations_applied():
            raise CommandError("required geography migrations are not applied")

        manifest = _load_manifest()
        frozen_census = _load_frozen_census()
        _verify_taxonomy_seed(manifest)

        recovery: GeographyRecoveryReceipt | None = None
        account_queryset = Account.objects.all()
        if options["apply"]:
            expected_database = (
                STAGING_DATABASE_NAME
                if target == "staging"
                else PRODUCTION_DATABASE_NAME
            )
            if options["confirm_database"] != expected_database:
                raise CommandError(
                    f"apply requires --confirm-database {expected_database}"
                )
            if not _is_authorized_executor(target):
                raise CommandError(
                    f"apply is restricted to the managed {target} environment"
                )
            if not options["json_report"] or not options["markdown_report"]:
                raise CommandError("apply requires both aggregate report paths")
            if target == "production":
                recovery = parse_geography_recovery_receipt(options["recovery_receipt"])

        started_at = timezone.now()
        if not options["apply"]:
            classification = _classify_accounts(account_queryset, manifest)
            if classification.unknown_values:
                raise CommandError(
                    "unreviewed account_based_in values: "
                    f"{list(classification.unknown_values)!r}"
                )
            report = {
                "schema_version": 1,
                "mode": "dry_run",
                "target": target,
                "classification": classification.totals,
                "unresolved_values": classification.unresolved_values,
                "nonblank_accounts": classification.nonblank_accounts,
                "distinct_values": classification.distinct_values,
                "census_sha256": classification.census_sha256,
                "manifest_sha256": MANIFEST_SHA256,
                "would_change": classification.would_change,
                "writes": 0,
                "http_calls": 0,
                "provider_credits": 0,
            }
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        changed = 0
        rejected_accounts = 0
        rejected_fields: Counter[str] = Counter()
        with _geography_run_lock():
            if recovery is not None:
                account_queryset = verify_geography_recovery_snapshot(recovery)

            before = _classify_accounts(account_queryset, manifest)
            if before.unknown_values:
                raise CommandError(
                    "unreviewed account_based_in values: "
                    f"{list(before.unknown_values)!r}"
                )
            if target == "production":
                _verify_frozen_production_census(before, frozen_census)

            mappings = {
                item["value"]: (item["country_code"], item["region_key"])
                for item in manifest["account_based_in_mappings"]
            }
            unresolved = set(manifest["explicit_unresolved_values"])
            candidates = account_queryset.exclude(
                account_based_in__isnull=True
            ).exclude(account_based_in="")
            for account in candidates.iterator(chunk_size=options["chunk_size"]):
                target_pair = mappings.get(account.account_based_in)
                if target_pair is None and account.account_based_in in unresolved:
                    target_pair = (None, None)
                if (
                    target_pair is None
                    or (
                        account.country_id,
                        account.based_in_region_id,
                    )
                    == target_pair
                ):
                    continue
                outcome = Account.apply_observation(
                    author_id=account.author_id,
                    observed_author_id=account.author_id,
                    source="user_about",
                    observed_at=account.account_based_in_fetched_at or timezone.now(),
                    candidates={
                        "country_code": target_pair[0],
                        "based_in_region_key": target_pair[1],
                    },
                    present_fields={"country_code", "based_in_region_key"},
                )
                if outcome.rejected_fields or outcome.identity_rejected:
                    rejected_accounts += 1
                    rejected_fields.update(outcome.rejected_fields)
                elif outcome.applied_fields:
                    changed += 1

            after = _classify_accounts(account_queryset, manifest)

        finished_at = timezone.now()
        report = {
            "schema_version": 1,
            "mode": f"{target}_apply",
            "target": target,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "classification": after.totals,
            "unresolved_values": after.unresolved_values,
            "nonblank_accounts": after.nonblank_accounts,
            "distinct_values": after.distinct_values,
            "census_sha256": after.census_sha256,
            "frozen_census_sha256": frozen_census["census_sha256"],
            "manifest_sha256": MANIFEST_SHA256,
            "would_change_before": before.would_change,
            "remaining_changes": after.would_change,
            "changed": changed,
            "unchanged": after.nonblank_accounts - changed - rejected_accounts,
            "rejected": rejected_accounts,
            "rejected_fields": dict(sorted(rejected_fields.items())),
            "writes": changed,
            "http_calls": 0,
            "provider_credits": 0,
            "recovery": (
                {
                    "receipt_sha256": recovery.receipt_sha256,
                    "created_at": recovery.created_at.isoformat(),
                    "snapshot_account_count": recovery.snapshot_account_count,
                    "storage": recovery.storage,
                    "snapshot_relation": recovery.snapshot_relation,
                    "restore_proved": True,
                }
                if recovery
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

        if rejected_accounts or after.would_change:
            raise CommandError(
                "account geography reconciliation incomplete: "
                f"rejected={rejected_accounts}, remaining={after.would_change}"
            )

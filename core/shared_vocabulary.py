"""Controlled catalogue seed writes and context-specific reference resolution.

Callers retain their original reported value. A failed lookup returns no reference;
this module never substitutes UTC, English, or the app's Chinese edition for it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models.functions import Lower

from core.models import (
    Currency,
    EmploymentType,
    JobFunction,
    Language,
    Locale,
    MeasurementUnit,
    OrganizationAIRelationshipType,
    RoleAIRelationshipType,
    SalaryPeriod,
    SeniorityLevel,
    TimeZone,
    WorkplaceType,
)

SEED_DIRECTORY = Path(settings.BASE_DIR) / "data"
CATALOGUES = {
    "time_zones": (TimeZone, "shared_time_zones.csv", ("code",)),
    "languages": (Language, "shared_languages.csv", ("code",)),
    "locales": (Locale, "shared_locales.csv", ("code", "language_code")),
    "measurement_units": (MeasurementUnit, "shared_measurement_units.csv", ("code",)),
    "currencies": (Currency, "shared_currencies.csv", ("code",)),
    "salary_periods": (SalaryPeriod, "shared_salary_periods.csv", ("code",)),
    "job_functions": (JobFunction, "shared_job_functions.csv", ("code",)),
    "seniority_levels": (SeniorityLevel, "shared_seniority_levels.csv", ("code",)),
    "employment_types": (EmploymentType, "shared_employment_types.csv", ("code",)),
    "workplace_types": (WorkplaceType, "shared_workplace_types.csv", ("code",)),
    "organization_ai_relationship_types": (OrganizationAIRelationshipType, "shared_organization_ai_relationship_types.csv", ("code",)),
    "role_ai_relationship_types": (RoleAIRelationshipType, "shared_role_ai_relationship_types.csv", ("code",)),
}
CODE_GRAMMARS = {
    "time_zones": r"[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*",
    "languages": r"[a-z]{2,8}",
    "locales": r"[a-z]{2,8}(-[A-Za-z0-9]{1,8})*",
    "measurement_units": r"[a-z][a-z0-9_]*",
    "currencies": r"[A-Z]{3}",
    **{name: r"[a-z][a-z0-9_]*" for name in (
        "salary_periods", "job_functions", "seniority_levels", "employment_types",
        "workplace_types", "organization_ai_relationship_types", "role_ai_relationship_types",
    )},
}


def load_seed_rows() -> dict[str, list[dict[str, str]]]:
    """Verify the entire reviewed input before any database write."""
    try:
        manifest = json.loads(
            (SEED_DIRECTORY / "shared_vocabulary_manifest.json").read_bytes()
        )
    except (OSError, ValueError) as exc:
        raise ValueError("Missing or invalid shared vocabulary seed manifest") from exc
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported shared vocabulary seed manifest version")
    result = {}
    for name, (_model, filename, header) in CATALOGUES.items():
        try:
            raw = (SEED_DIRECTORY / filename).read_bytes()
            expected = manifest["seeds"][filename]
        except (OSError, KeyError, TypeError) as exc:
            raise ValueError(
                f"Missing seed input or manifest entry: {filename}"
            ) from exc
        if hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise ValueError(f"Seed hash mismatch: {filename}")
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
        if reader.fieldnames != list(header):
            raise ValueError(f"Unexpected seed columns: {filename}")
        rows = list(reader)
        if len(rows) != expected["rows"] or len({row["code"] for row in rows}) != len(
            rows
        ):
            raise ValueError(f"Duplicate or missing seed rows: {filename}")
        if any(
            set(row) != set(header)
            or not re.fullmatch(CODE_GRAMMARS[name], row["code"])
            for row in rows
        ):
            raise ValueError(f"Invalid seed code: {filename}")
        result[name] = rows
    languages = {row["code"] for row in result["languages"]}
    for row in result["locales"]:
        if (
            row["language_code"] not in languages
            or row["code"].split("-", 1)[0] != row["language_code"]
        ):
            raise ValueError(
                "Locale seed has a contradictory or missing language parent"
            )
    return result


def seed_shared_vocabulary(
    *,
    database: str = "default",
    catalogues: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    rows = load_seed_rows()
    selected = tuple(CATALOGUES) if catalogues is None else catalogues
    if not selected or any(name not in CATALOGUES for name in selected):
        raise ValueError("Unknown or empty catalogue selection")
    counts = {name: len(rows[name]) for name in CATALOGUES if name in selected}
    if dry_run:
        return counts
    # Dependency order is fixed even when CLI options arrive in a different order.
    with transaction.atomic(using=database):
        for name, (model, _filename, _header) in CATALOGUES.items():
            if name not in selected:
                continue
            objects = [
                model(
                    code=row["code"],
                    **(
                        {"language_id": row["language_code"]}
                        if name == "locales"
                        else {}
                    ),
                )
                for row in rows[name]
            ]
            model.objects.using(database).bulk_create(
                objects, batch_size=500, ignore_conflicts=True
            )
            expected = {row["code"] for row in rows[name]}
            actual = set(
                model.objects.using(database)
                .filter(code__in=expected)
                .values_list("code", flat=True)
            )
            if actual != expected:
                raise ValueError(f"Canonical seed identity conflict: {name}")
    return counts


def resolve_locale(
    reported: str | None, *, context: str = "source", database: str = "default"
) -> Locale | None:
    if context not in {"source", "app_edition"}:
        raise ValueError("Unsupported locale resolution context")
    if not reported:
        return None
    tag = reported.replace("_", "-")
    if context == "app_edition" and tag.casefold() == "zh-cn":
        tag = "zh-Hans"
    # Match the expression of the catalogue's case-insensitive unique index.
    return (
        Locale.objects.using(database)
        .alias(canonical_lookup=Lower("code"))
        .filter(canonical_lookup=tag.lower())
        .first()
    )


def resolve_time_zone(
    reported: str | None, *, database: str = "default"
) -> TimeZone | None:
    if not reported:
        return None
    return TimeZone.objects.using(database).filter(pk=reported).first()

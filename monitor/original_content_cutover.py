"""Readiness and an auditable cutover timestamp; never changes service flags."""

import re

from django.db import transaction
from django.utils import timezone

from core.models import (
    EditorialBudget,
    EditorialEdition,
    OriginalContentRun,
    OriginalContentText,
)
from monitor.original_content import (
    advisory_lock,
    budget_totals,
    citation_values,
    shared_storage,
)
from monitor.original_content_backfill import backfill_original_content

ADAPTER_VERSION = "original-content-storage-v1"
CONSUMERS = frozenset({"web", "headlines", "editorial", "pictures"})


def validate_consumers(receipts, candidate):
    if not re.fullmatch(r"[0-9a-f]{40}", candidate or ""):
        raise ValueError("full candidate revision required")
    if set(receipts) != CONSUMERS:
        raise ValueError("missing provider or reader consumer receipt")
    for name, receipt in receipts.items():
        if (
            receipt.get("revision") != candidate
            or receipt.get("adapter_version") != ADAPTER_VERSION
        ):
            raise ValueError(f"incompatible consumer: {name}")


def readiness():
    report = backfill_original_content(apply=False)
    missing = EditorialEdition.objects.exclude(
        pk__in=OriginalContentText.objects.filter(public_id__isnull=False).values(
            "public_id"
        )
    ).count()
    if missing:
        report["exceptions"].append({"kind": "unimported_editions", "count": missing})
    for edition in EditorialEdition.objects.iterator(chunk_size=200):
        text = (
            OriginalContentText.objects.filter(public_id=edition.pk)
            .select_related("narrative")
            .prefetch_related("sources")
            .first()
        )
        if text is None:
            continue
        content = text.narrative
        expected = citation_values(edition.evidence.get("sources", []), legacy=True)
        actual = list(text.sources.all())
        copy_equal = (
            text.headline,
            text.secondary,
            text.body,
            text.locale,
            content.story_id,
            content.revision,
            content.published_at,
        ) == (
            edition.headline,
            edition.byline,
            edition.article,
            edition.locale,
            edition.story_id,
            edition.revision,
            edition.published_at,
        )
        sources_equal = [(s.post_id, s.url_snapshot) for s in actual] == [
            (s["post_id"], s["url_snapshot"]) for s in expected
        ]
        if not copy_equal or not sources_equal:
            report["exceptions"].append(
                {"kind": "shared_edition_parity", "id": str(edition.pk)}
            )
    for budget in EditorialBudget.objects.all():
        totals = budget_totals("editorial", budget.day)
        if totals != {
            "reserved_usd": budget.reserved_usd,
            "calls": budget.calls,
            "media_calls": budget.media_calls,
        }:
            report["exceptions"].append(
                {"kind": "shared_budget", "id": budget.day.isoformat()}
            )
    report["ready"] = not report["exceptions"]
    report.update(
        adapter_version=ADAPTER_VERSION,
        storage="shared" if shared_storage() else "legacy",
    )
    return report


def record_cutover(receipts, candidate):
    validate_consumers(receipts, candidate)
    if not shared_storage():
        raise ValueError("observe shared activation before recording cutover")
    with transaction.atomic():
        advisory_lock("original-content-cutover")
        report = readiness()
        if not report["ready"]:
            raise ValueError("cutover reconciliation is incomplete")
        now = timezone.now()
        run, _ = OriginalContentRun.objects.get_or_create(
            source_cycle_id=f"storage-cutover:{candidate}",
            workflow_key="editorial-dispatch",
            scope_key="migration:original-content:cutover",
            defaults={
                "facts_as_of": now,
                "packet_schema_version": 1,
                "snapshot": {},
                "execution_state": "complete",
                "outcome": {
                    "cutover_at": now.isoformat(),
                    "revision": candidate,
                    "consumers": receipts,
                    "provider_send": False,
                },
            },
        )
        return run.outcome

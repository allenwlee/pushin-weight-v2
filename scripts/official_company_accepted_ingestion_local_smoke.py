"""Rehearse ingestion against this task's local fixture database only.

Run with ``python manage.py shell < scripts/official_company_accepted_ingestion_local_smoke.py``.
This intentionally creates a small set of synthetic records and never calls a provider.
"""

import secrets
import socket
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.utils import timezone

from core.models import (
    Account,
    BrandAccount,
    BrandCompany,
    CompanyAccount,
    DataSource,
    Language,
    Locale,
    OfficialCompanyAccountState,
    OfficialCompanyAttempt,
    OfficialCompanyListIntent,
)
from core.official_company_accepted_ingestion import (
    apply_preview,
    freeze_accepted,
    preview_accepted,
)
from core.official_company_accounts import enqueue_account
from core.official_company_queue_pass import (
    _database_identity,
    _environment,
    freeze_queue,
)
from x_monitor.config import OfficialCompanyConfig


def main():
    # This executable fixture must never target any other database.
    if _environment(allow_isolated_fixture=True) != "test" or _database_identity() != {
        "name": "test_pw_queue_pass_ingest_20261120",
        "system_identifier": "7693527921830478235",
    }:
        raise RuntimeError(
            "this rehearsal requires the task-owned local fixture database"
        )
    if OfficialCompanyAccountState.objects.filter(
        status__in=("pending", "retry_due", "claimed"), candidate_priority__in=(1, 2, 3)
    ).exists():
        raise RuntimeError("staging fixture queue is not empty")

    run = secrets.token_hex(6)
    base_id = 7000000000000000000 + secrets.randbelow(1000000000000) * 10
    DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"}
    )
    Language.objects.get_or_create(pk="und")
    Locale.objects.get_or_create(pk="und", defaults={"language_id": "und"})
    states = []
    for index in range(8):
        account = Account.objects.create(
            author_id=str(base_id + index), bio="We develop AI models"
        )
        state = enqueue_account(account)
        state.candidate_priority = 1
        state.save()
        states.append(state)
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)

    # The database connection is already open; forbid any new outbound connections.
    with (
        patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("unexpected network call"),
        ),
        TemporaryDirectory(prefix="pw-ingest-stage-") as directory,
    ):
        root = Path(directory)
        queue = freeze_queue(
            path=root / "queue.json",
            total_limit=Decimal(1),
            allow_isolated_fixture=True,
        )
        if {item["state_id"] for item in queue["members"]} != {
            state.pk for state in states
        }:
            raise AssertionError("fixture queue membership changed")
        names = [
            f"Fixture Twin {run}",
            f"Fixture Twin {run}",
            f"Fixture Stale {run}",
            f"Fixture Intent {run}",
            f"Fixture Failed Retry {run}",
            f"Fixture Changed Retry {run}",
            f"Fixture Suppressed {run}",
            f"Fixture Native Mismatch {run}",
        ]
        for index, state in enumerate(states):
            state.status = "review_needed"
            state.last_error = "human_review_required"
            state.decision = {
                "outcome": "accepted",
                "organization_name": names[index],
            }
            state.save()
            OfficialCompanyAttempt.objects.create(
                state=state,
                evidence_hash=state.evidence_hash,
                evidence=(
                    {**state.evidence, "external_identifier": str(base_id + 99)}
                    if index == 7
                    else state.evidence
                ),
                claim_token=f"stage-fixture-{run}-{index}",
                model="fixture",
                policy_version="fixture",
                status="completed",
                decision=state.decision,
                reserved_usd=0,
                actual_usd=0,
                budget_keys=["queue-pass:" + queue["run_id"]],
                completed_at=timezone.now(),
            )
        OfficialCompanyListIntent.objects.create(
            state=states[3],
            account=states[3].account,
            list_id=int(cfg.list_id),
            evidence_hash="b" * 64,
            status="claimed",
            claim_token="fixture-preserve",
        )
        original_intents = list(
            OfficialCompanyListIntent.objects.order_by("pk").values()
        )
        manifest = freeze_accepted(queue=queue, path=root / "accepted.json")
        states[2].evidence_hash = "f" * 64
        states[2].save()
        states[6].status = "suppressed"
        states[6].save()
        for index in (4, 5):
            state = states[index]
            OfficialCompanyAttempt.objects.create(
                state=state,
                evidence_hash=state.evidence_hash if index == 4 else "d" * 64,
                evidence=state.evidence,
                claim_token=f"stage-retry-{run}-{index}",
                model="fixture",
                policy_version="fixture",
                status="failed",
                decision={},
                reserved_usd=0,
                actual_usd=0,
                budget_keys=["queue-pass:" + queue["run_id"]],
                completed_at=timezone.now(),
            )
        preview = preview_accepted(
            queue=queue, manifest=manifest, path=root / "preview.json"
        )
        if manifest["count"] != 8 or [
            row["disposition"] for row in preview["members"]
        ] != [
            "eligible",
            "conflict",
            "unresolved",
            "eligible",
            "eligible",
            "unresolved",
            "unresolved",
            "unresolved",
        ]:
            raise AssertionError(
                f"fixture preview did not reconcile: {preview['members']}"
            )
        if (
            preview["counts"]["new_brands"] != 3
            or preview["counts"]["new_companies"] != 3
            or preview["list_changes"] != 0
            or preview["counts"]["suppressed"] != 1
            or preview["counts"]["native_identity_changed"] != 1
        ):
            raise AssertionError("fixture preview counts changed")
        first_batch = apply_preview(
            queue=queue, manifest=manifest, preview=preview, cfg=cfg, max_writes=1
        )
        if [row["disposition"] for row in first_batch] != [
            "registered",
            *(["not_attempted"] * 7),
        ]:
            raise AssertionError(f"first batch did not reconcile: {first_batch}")
        second_batch = apply_preview(
            queue=queue, manifest=manifest, preview=preview, cfg=cfg, max_writes=2
        )
        if [row["disposition"] for row in second_batch] != [
            "already_registered",
            "conflict",
            "unresolved",
            "registered",
            "registered",
            "not_attempted",
            "not_attempted",
            "not_attempted",
        ]:
            raise AssertionError(f"second batch did not reconcile: {second_batch}")
        result = apply_preview(queue=queue, manifest=manifest, preview=preview, cfg=cfg)
        if [row["disposition"] for row in result] != [
            "already_registered",
            "conflict",
            "unresolved",
            "already_registered",
            "already_registered",
            "unresolved",
            "unresolved",
            "unresolved",
        ]:
            raise AssertionError(f"fixture application did not reconcile: {result}")
        if (
            list(OfficialCompanyListIntent.objects.order_by("pk").values())
            != original_intents
        ):
            raise AssertionError("list intents changed")
        account_ids = [states[0].account_id, states[3].account_id, states[4].account_id]
        if (
            BrandAccount.objects.filter(
                account_id__in=account_ids, role_id="official"
            ).count()
            != 3
        ):
            raise AssertionError("missing official brand links")
        if (
            CompanyAccount.objects.filter(
                account_id__in=account_ids, role_id="official"
            ).count()
            != 3
        ):
            raise AssertionError("missing official company links")
        for state in (states[0], states[3], states[4]):
            state.refresh_from_db()
            if not BrandCompany.objects.filter(
                brand_id=state.registered_brand_id,
                company_id=state.registered_company_id,
            ).exists():
                raise AssertionError("missing brand-company link")
        replay = apply_preview(queue=queue, manifest=manifest, preview=preview, cfg=cfg)
        if [row["disposition"] for row in replay] != [
            "already_registered",
            "conflict",
            "unresolved",
            "already_registered",
            "already_registered",
            "unresolved",
            "unresolved",
            "unresolved",
        ]:
            raise AssertionError("fixture replay is not idempotent")
    print(
        "Local fixture rehearsal passed: frozen=8, registered=3, duplicate=1, changed evidence=2, suppressed=1, native mismatch=1, list changes=0, replay=3 already registered."
    )


main()

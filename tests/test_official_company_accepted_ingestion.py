from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import OfficialCompanyAttempt
from core.official_company_queue_pass import freeze_queue
from tests.test_official_company_queue_pass import candidate

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_freeze_only_completed_acceptances_from_selected_pass(tmp_path, monkeypatch):
    from core.official_company_accepted_ingestion import freeze_accepted, read_accepted

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    first = candidate(982001, 1)
    second = candidate(982002, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))

    def attempt(state, outcome, key, token):
        return OfficialCompanyAttempt.objects.create(
            state=state,
            evidence_hash=state.evidence_hash,
            evidence=state.evidence,
            claim_token=token,
            model="test",
            policy_version="v1",
            status="completed",
            decision={"outcome": outcome, "organization_name": "Test Lab"},
            reserved_usd=0,
            actual_usd=0,
            budget_keys=[key],
            completed_at=timezone.now(),
        )

    key = "queue-pass:" + queue["run_id"]
    earlier = attempt(first, "accepted", key, "one")
    latest = attempt(first, "accepted", key, "two")
    attempt(second, "rejected", key, "three")
    attempt(second, "accepted", "queue-pass:other", "four")
    path = tmp_path / "accepted.json"
    manifest = freeze_accepted(queue=queue, path=path)
    assert read_accepted(path, queue=queue) == manifest
    assert manifest["count"] == 1
    assert manifest["members"][0]["attempt_id"] == latest.pk
    assert OfficialCompanyAttempt.objects.filter(pk=earlier.pk).exists()
    assert not path.stat().st_mode & 0o077


def test_preview_accounts_for_in_batch_name_collision_without_writes(
    tmp_path, monkeypatch
):
    from core.models import Brand, Company, OfficialCompanyListIntent
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    first = candidate(982011, 1)
    second = candidate(982012, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    for i, state in enumerate((first, second)):
        state.status = "review_needed"
        state.last_error = "human_review_required"
        state.decision = {"outcome": "accepted", "organization_name": "Same Lab"}
        state.save()
        OfficialCompanyAttempt.objects.create(
            state=state,
            evidence_hash=state.evidence_hash,
            evidence=state.evidence,
            claim_token=f"preview-{i}",
            model="test",
            policy_version="v1",
            status="completed",
            decision=state.decision,
            reserved_usd=0,
            actual_usd=0,
            budget_keys=["queue-pass:" + queue["run_id"]],
            completed_at=timezone.now(),
        )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert preview["counts"]["new_brands"] == 1
    assert preview["counts"]["new_companies"] == 1
    assert [row["disposition"] for row in preview["members"]] == [
        "eligible",
        "conflict",
    ]
    assert not Brand.objects.filter(nickname="same-lab").exists()
    assert not Company.objects.filter(nickname="same-lab").exists()
    assert not OfficialCompanyListIntent.objects.exists()


def test_freeze_refuses_changed_queue_and_manifest_tampering(tmp_path, monkeypatch):
    import json

    from core.official_company_accepted_ingestion import freeze_accepted, read_accepted

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    candidate(982021, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    frozen_path = tmp_path / "accepted.json"
    freeze_accepted(queue=queue, path=frozen_path)
    with pytest.raises(FileExistsError):
        freeze_accepted(queue=queue, path=frozen_path)
    changed = json.loads(frozen_path.read_text())
    changed["count"] += 1
    frozen_path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="checksum"):
        read_accepted(frozen_path, queue=queue)
    queue["count"] += 1
    with pytest.raises(ValueError, match="checksum"):
        freeze_accepted(queue=queue, path=tmp_path / "other.json")


def test_preview_reads_one_snapshot_while_another_writer_creates_brand(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from core import official_company_accounts
    from core.models import Brand
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    states = [candidate(982031, 1), candidate(982032, 1)]
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    for i, state in enumerate(states):
        state.status = "accepted"
        state.decision = {
            "outcome": "accepted",
            "organization_name": f"Snapshot Lab {i}",
        }
        state.save()
        OfficialCompanyAttempt.objects.create(
            state=state,
            evidence_hash=state.evidence_hash,
            evidence=state.evidence,
            claim_token=f"snapshot-{i}",
            model="test",
            policy_version="v1",
            status="completed",
            decision=state.decision,
            reserved_usd=0,
            actual_usd=0,
            budget_keys=["queue-pass:" + queue["run_id"]],
            completed_at=timezone.now(),
        )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    original = official_company_accounts.registration_identity
    created = False

    def insert_concurrently():
        try:
            Brand.objects.create(
                nickname="snapshot-lab-1", display_name="Snapshot Lab 1"
            )
        finally:
            connections.close_all()

    def concurrent_identity(state, account):
        nonlocal created
        if not created:
            created = True
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(insert_concurrently).result(timeout=10)
        return original(state, account)

    monkeypatch.setattr(
        official_company_accounts, "registration_identity", concurrent_identity
    )
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert [row["disposition"] for row in preview["members"]] == [
        "eligible",
        "eligible",
    ]
    assert preview["counts"]["new_brands"] == 2
    assert Brand.objects.filter(nickname="snapshot-lab-1").exists()


def test_preview_leaves_changed_evidence_unresolved(tmp_path, monkeypatch):
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982041, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Changed Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="changed-evidence",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    state.evidence_hash = "f" * 64
    state.save()
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["disposition"] == "unresolved"
    assert preview["members"][0]["reason"] == "evidence_or_decision_changed"
    assert preview["counts"]["new_brands"] == 0


def test_command_freezes_and_previews_without_external_calls(tmp_path, monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982051, 1)
    queue_path = tmp_path / "queue.json"
    queue = freeze_queue(path=queue_path, total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Command Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="command-one",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("provider network call attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    out = StringIO()
    manifest = tmp_path / "accepted.json"
    preview = tmp_path / "preview.json"
    call_command(
        "official_company_accepted_ingestion",
        "freeze",
        queue=str(queue_path),
        manifest=str(manifest),
        stdout=out,
    )
    call_command(
        "official_company_accepted_ingestion",
        "preview",
        queue=str(queue_path),
        manifest=str(manifest),
        preview=str(preview),
        stdout=out,
    )
    assert manifest.exists() and preview.exists()
    call_command(
        "official_company_accepted_ingestion",
        "apply",
        queue=str(queue_path),
        manifest=str(manifest),
        preview=str(preview),
        stdout=out,
    )
    state.refresh_from_db()
    assert state.status == "registered"


def test_apply_registers_saved_acceptance_and_keeps_list_intent(tmp_path, monkeypatch):
    from core.models import BrandAccount, CompanyAccount, OfficialCompanyListIntent
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982061, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "review_needed"
    state.last_error = "human_review_required"
    state.decision = {"outcome": "accepted", "organization_name": "Apply Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="apply-one",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)
    intent = OfficialCompanyListIntent.objects.create(
        state=state,
        account=state.account,
        list_id=int(cfg.list_id),
        evidence_hash="b" * 64,
        status="claimed",
        claim_token="preserved-claim",
    )
    old_intent = OfficialCompanyListIntent.objects.filter(pk=intent.pk).values().get()
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    result = apply_preview(queue=queue, manifest=frozen, preview=preview, cfg=cfg)
    assert result[0]["disposition"] == "registered"
    state.refresh_from_db()
    assert state.status == "registered"
    assert state.last_error == ""
    assert state.next_attempt_at is None
    assert BrandAccount.objects.filter(
        account=state.account, role_id="official"
    ).exists()
    assert CompanyAccount.objects.filter(
        account=state.account, role_id="official"
    ).exists()
    assert (
        OfficialCompanyListIntent.objects.filter(pk=intent.pk).values().get()
        == old_intent
    )
    assert (
        apply_preview(queue=queue, manifest=frozen, preview=preview, cfg=cfg)[0][
            "disposition"
        ]
        == "already_registered"
    )


def test_apply_reports_identity_drift_without_changing_state(tmp_path, monkeypatch):
    from core.models import Brand, BrandAccount
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982071, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "review_needed"
    state.last_error = "human_review_required"
    state.decision = {"outcome": "accepted", "organization_name": "Drift Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="drift-one",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    Brand.objects.create(nickname="other-identity", display_name="Drift Lab")
    result = apply_preview(
        queue=queue,
        manifest=frozen,
        preview=preview,
        cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
    )
    assert result[0]["disposition"] == "drift"
    state.refresh_from_db()
    assert (state.status, state.last_error) == (
        "review_needed",
        "human_review_required",
    )
    assert not BrandAccount.objects.filter(account=state.account).exists()


def test_apply_does_not_create_identity_when_another_writer_races(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from core import official_company_accounts
    from core.models import Brand
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982081, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Racing Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="race-one",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    original = official_company_accounts.registration_identity
    calls = 0

    def other_writer():
        try:
            Brand.objects.create(nickname="other-racing-lab", display_name="Racing Lab")
        finally:
            connections.close_all()

    def racing_identity(state, account):
        nonlocal calls
        result = original(state, account)
        calls += 1
        if calls == 2:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(other_writer).result(timeout=10)
        return result

    monkeypatch.setattr(
        official_company_accounts, "registration_identity", racing_identity
    )
    result = apply_preview(
        queue=queue,
        manifest=frozen,
        preview=preview,
        cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
    )
    assert result[0]["disposition"] == "drift"
    assert not Brand.objects.filter(nickname="racing-lab").exists()


def test_apply_rolls_back_identity_changed_after_preview_revalidation(
    tmp_path, monkeypatch
):
    from core import official_company_accounts
    from core.models import Brand, BrandDiscoveryCandidate
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982082, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Reviewed Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="candidate-race",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    alternate = Brand.objects.create(nickname="alternate-reviewed-lab")
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    original = official_company_accounts.register_account

    def changed_candidate(*args, **kwargs):
        now = timezone.now()
        BrandDiscoveryCandidate.objects.create(
            candidate_identity="e" * 64,
            observed_name="Reviewed Lab",
            verification_status="confirmed",
            reviewed_brand=alternate,
            source_identities=[f"official-company-state:{state.pk}"],
            first_observed_at=now,
            last_observed_at=now,
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(
        official_company_accounts, "register_account", changed_candidate
    )
    result = apply_preview(
        queue=queue,
        manifest=frozen,
        preview=preview,
        cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
    )
    assert result[0]["disposition"] == "drift"
    state.refresh_from_db()
    assert state.status == "accepted"
    assert state.registered_brand_id is None
    assert not BrandDiscoveryCandidate.objects.filter(
        candidate_identity="e" * 64
    ).exists()


def test_apply_detects_identity_created_after_final_read(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections
    from django.db.models.query import QuerySet

    from core.models import Brand, CompanyLabel
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982083, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Late Racing Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="late-race",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    original = QuerySet.exists
    raced = False

    def other_writer():
        try:
            Brand.objects.create(
                nickname="other-late-lab", display_name="Late Racing Lab"
            )
        finally:
            connections.close_all()

    def exists(queryset):
        nonlocal raced
        result = original(queryset)
        if (
            queryset.model is CompanyLabel
            and "NOT" in str(queryset.query)
            and not raced
        ):
            raced = True
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(other_writer).result(timeout=5)
        return result

    monkeypatch.setattr(QuerySet, "exists", exists)
    result = apply_preview(
        queue=queue,
        manifest=frozen,
        preview=preview,
        cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
    )
    assert raced
    assert result[0]["disposition"] == "drift"
    assert not Brand.objects.filter(nickname="late-racing-lab").exists()


def test_apply_refuses_production_even_when_other_inputs_are_present(monkeypatch):
    from core.official_company_accepted_ingestion import apply_preview

    monkeypatch.setattr(
        "core.official_company_accepted_ingestion._environment",
        lambda queue, **kwargs: "production",
    )
    with pytest.raises(ValueError, match="--allow-production"):
        apply_preview(queue={}, manifest={}, preview={}, cfg=None)


def test_production_apply_requires_matching_frozen_list_file(monkeypatch):
    from core.official_company_accepted_ingestion import apply_preview

    monkeypatch.setattr(
        "core.official_company_accepted_ingestion._environment",
        lambda queue, **kwargs: "production",
    )
    with pytest.raises(ValueError, match="frozen-list file"):
        apply_preview(
            queue={}, manifest={}, preview={}, cfg=None, allow_production=True
        )
    monkeypatch.setattr(
        "core.official_company_accepted_ingestion.read_accepted",
        lambda path, queue: {"different": True},
    )
    with pytest.raises(ValueError, match="does not match"):
        apply_preview(
            queue={},
            manifest={},
            preview={},
            cfg=None,
            allow_production=True,
            frozen_list_path="frozen.json",
        )

    # Reaching normal manifest validation proves the production-specific gate
    # accepts the explicit flag and matching file without performing a write.
    monkeypatch.setattr(
        "core.official_company_accepted_ingestion.read_accepted",
        lambda path, queue: {},
    )

    def validate_manifest(manifest, *, queue):
        raise ValueError("normal manifest validation reached")

    monkeypatch.setattr(
        "core.official_company_accepted_ingestion._validate_accepted",
        validate_manifest,
    )
    with pytest.raises(ValueError, match="normal manifest validation reached"):
        apply_preview(
            queue={},
            manifest={},
            preview={},
            cfg=None,
            allow_production=True,
            frozen_list_path="frozen.json",
        )


def test_command_passes_production_flag_frozen_file_and_batch_limit(
    tmp_path, monkeypatch
):
    from io import StringIO

    from django.core.management import call_command

    import monitor.management.commands.official_company_accepted_ingestion as command

    preview = tmp_path / "preview.json"
    preview.write_text("{}")
    monkeypatch.setattr(command, "read_manifest", lambda *args, **kwargs: {})
    monkeypatch.setattr(command, "read_accepted", lambda *args, **kwargs: {})
    captured = {}

    def fake_apply(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(command, "apply_preview", fake_apply)
    call_command(
        "official_company_accepted_ingestion",
        "apply",
        queue="queue.json",
        manifest="frozen.json",
        preview=str(preview),
        allow_production=True,
        max_writes=8,
        stdout=StringIO(),
    )
    assert captured["allow_production"] is True
    assert captured["frozen_list_path"] == "frozen.json"
    assert captured["max_writes"] == 8


def test_busy_account_is_skipped_without_waiting_or_writing(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections, transaction

    from core.models import OfficialCompanyAccountState
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982091, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Busy Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="busy-one",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    held, release = Event(), Event()

    def hold_state():
        try:
            with transaction.atomic():
                OfficialCompanyAccountState.objects.select_for_update().get(pk=state.pk)
                held.set()
                assert release.wait(10)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(hold_state)
        assert held.wait(10)
        try:
            result = apply_preview(
                queue=queue,
                manifest=frozen,
                preview=preview,
                cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
            )
            assert result[0]["disposition"] == "busy_or_missing"
        finally:
            release.set()
        task.result(timeout=10)
    state.refresh_from_db()
    assert state.status == "accepted"


def test_preview_uses_database_case_matching_for_batch_names(tmp_path, monkeypatch):
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    def unexpected_per_row_query(*args, **kwargs):
        raise AssertionError("preview performed a per-account reservation query")

    monkeypatch.setattr(
        "core.official_company_accepted_ingestion._reservation_conflicts",
        unexpected_per_row_query,
    )
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    states = [candidate(982101, 1), candidate(982102, 1)]
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    for i, (state, name) in enumerate(zip(states, ["i", "ı"], strict=True)):
        state.status = "accepted"
        state.decision = {"outcome": "accepted", "organization_name": name}
        state.save()
        OfficialCompanyAttempt.objects.create(
            state=state,
            evidence_hash=state.evidence_hash,
            evidence=state.evidence,
            claim_token=f"case-{i}",
            model="test",
            policy_version="v1",
            status="completed",
            decision=state.decision,
            reserved_usd=0,
            actual_usd=0,
            budget_keys=["queue-pass:" + queue["run_id"]],
            completed_at=timezone.now(),
        )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert [row["disposition"] for row in preview["members"]] == [
        "eligible",
        "conflict",
    ]
    assert preview["counts"]["new_brands"] == 1


def test_manifest_rejects_accounts_outside_original_queue(tmp_path, monkeypatch):
    import json

    from core.official_company_accepted_ingestion import freeze_accepted, read_accepted
    from core.official_company_accounts import digest

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982111, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="cohort-membership",
        model="test",
        policy_version="v1",
        status="completed",
        decision={"outcome": "accepted", "organization_name": "Cohort Lab"},
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    path = tmp_path / "accepted.json"
    freeze_accepted(queue=queue, path=path)
    value = json.loads(path.read_text())
    value["members"][0]["account_key"] = "an-account-outside-the-queue"
    value.pop("sha256")
    value["sha256"] = digest(value)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="queue membership"):
        read_accepted(path, queue=queue)


def test_preview_refuses_changed_saved_decision_with_same_evidence_hash(
    tmp_path, monkeypatch
):
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982121, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Original Lab"}
    state.save()
    attempt = OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="decision-revision",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    altered = {"outcome": "accepted", "organization_name": "Different Lab"}
    state.decision = altered
    state.save()
    attempt.decision = altered
    attempt.save()
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["disposition"] == "unresolved"
    assert preview["members"][0]["reason"] == "evidence_or_decision_changed"
    assert preview["counts"]["new_brands"] == 0


def test_already_registered_does_not_hide_changed_frozen_attempt(tmp_path, monkeypatch):
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )
    from core.official_company_accounts import register_account
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982131, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Registered Lab"}
    state.save()
    attempt = OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="registered-revision",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    register_account(
        state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    attempt.decision = {"outcome": "accepted", "organization_name": "Changed Lab"}
    attempt.save()
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["disposition"] == "unresolved"
    assert preview["members"][0]["reason"] == "evidence_or_decision_changed"


def test_batch_reservation_classes_match_database_comparisons():
    from django.db import connection

    from core.official_company_accepted_ingestion import _batch_reservation_classes

    values = [
        ("foo", "Foo"),
        ("FOO", "foo"),
        ("i", "i"),
        ("other-i", "ı"),
        ("accent", "é"),
        ("accent-two", "e\u0301"),
        ("sharp", "ß"),
        ("sharp-two", "ss"),
    ]
    classes = _batch_reservation_classes(values)
    for left, (slug_a, name_a) in enumerate(values):
        for right, (slug_b, name_b) in enumerate(values):
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT %s::text COLLATE "case_insensitive" = %s::text COLLATE "case_insensitive", UPPER(%s::text) = UPPER(%s::text)',
                    [slug_a, slug_b, name_a, name_b],
                )
                slug_equal, name_equal = cursor.fetchone()
            assert (classes[left][0] == classes[right][0]) == slug_equal
            assert (classes[left][1] == classes[right][1]) == name_equal


def test_batch_reservation_classes_rejects_unexpected_collations(monkeypatch):
    from core.official_company_accepted_ingestion import _batch_reservation_classes

    class UnexpectedCollation:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args):
            pass

        def fetchall(self):
            return [("brands", "nickname", "unexpected")]

    monkeypatch.setattr(
        "core.official_company_accepted_ingestion.connection.cursor",
        UnexpectedCollation,
    )
    with pytest.raises(ValueError, match="collation"):
        _batch_reservation_classes([("lab", "Lab")])


@pytest.mark.parametrize(
    ("later_status", "later_outcome", "evidence_changed", "expected"),
    [
        ("failed", None, False, "eligible"),
        ("failed", None, True, "unresolved"),
        ("completed", "accepted", False, "eligible"),
        ("completed", "rejected", False, "unresolved"),
        ("reserved", None, False, "unresolved"),
    ],
)
def test_preview_distinguishes_later_attempts(
    tmp_path, monkeypatch, later_status, later_outcome, evidence_changed, expected
):
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982141, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Retry Lab"}
    state.save()
    common = {
        "state": state,
        "evidence_hash": state.evidence_hash,
        "evidence": state.evidence,
        "model": "test",
        "policy_version": "v1",
        "reserved_usd": 0,
        "budget_keys": ["queue-pass:" + queue["run_id"]],
    }
    OfficialCompanyAttempt.objects.create(
        **common,
        claim_token="prior-accepted",
        status="completed",
        decision=state.decision,
        actual_usd=0,
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    later_decision = (
        state.decision
        if later_outcome == "accepted"
        else {"outcome": later_outcome}
        if later_outcome
        else {}
    )
    later_common = dict(common)
    if evidence_changed:
        later_common["evidence_hash"] = "d" * 64
    OfficialCompanyAttempt.objects.create(
        **later_common,
        claim_token="later-attempt",
        status=later_status,
        decision=later_decision,
        actual_usd=0 if later_status != "reserved" else None,
        completed_at=timezone.now() if later_status != "reserved" else None,
    )
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["disposition"] == expected


def test_replay_reports_drift_if_original_attempt_changes(tmp_path, monkeypatch):
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982151, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Replay Lab"}
    state.save()
    attempt = OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="replay-original",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)
    assert (
        apply_preview(queue=queue, manifest=manifest, preview=preview, cfg=cfg)[0][
            "disposition"
        ]
        == "registered"
    )
    attempt.decision = {"outcome": "accepted", "organization_name": "Altered Lab"}
    attempt.save()
    assert (
        apply_preview(queue=queue, manifest=manifest, preview=preview, cfg=cfg)[0][
            "disposition"
        ]
        == "drift"
    )


def test_preview_rejects_changed_native_x_identity(tmp_path, monkeypatch):
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982161, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Identity Lab"}
    state.save()
    evidence = {**state.evidence, "external_identifier": "982162"}
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=evidence,
        claim_token="native-identity",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["disposition"] == "unresolved"
    assert preview["members"][0]["reason"] == "native_account_changed"
    assert preview["counts"]["new_brands"] == 0


@pytest.mark.parametrize("problem", ["changed_evidence", "conflicting_official_link"])
def test_registered_accounts_with_stale_or_conflicting_identity_are_not_clean(
    tmp_path, monkeypatch, problem
):
    from core.models import Brand, BrandAccount, Role
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )
    from core.official_company_accounts import register_account
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982171, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Registered Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="registered-conflict",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    register_account(
        state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
    )
    state.refresh_from_db()
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    if problem == "changed_evidence":
        state.evidence_hash = "f" * 64
        state.save()
    else:
        brand = Brand.objects.create(
            nickname="second-official-brand", display_name="Another Lab"
        )
        BrandAccount.objects.create(
            account=state.account, brand=brand, role=Role.objects.get(pk="official")
        )
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["disposition"] in {"unresolved", "conflict"}
    assert preview["counts"]["already_registered"] == 0


def test_preview_records_native_identity_and_automatic_timestamp(tmp_path, monkeypatch):
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982181, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Native Repair Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="native-repair",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    row = preview["members"][0]
    assert row["state_before"]["native_account_id"] == state.account.author_id
    assert row["native_account_id_after"] == state.account.author_id
    assert "updated_at" in row["automatically_updated_state_fields"]
    result = apply_preview(
        queue=queue,
        manifest=frozen,
        preview=preview,
        cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
    )
    assert result[0]["disposition"] == "registered"
    state.refresh_from_db()
    assert state.native_account_id == row["native_account_id_after"]


@pytest.mark.parametrize("alteration", ["version", "queue_binding"])
def test_apply_rejects_rehashed_incompatible_preview(tmp_path, monkeypatch, alteration):
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from core.official_company_accounts import digest
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    candidate(982191, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    if alteration == "version":
        preview["version"] = 2
    else:
        preview["queue_sha256"] = "a" * 64
    preview.pop("sha256")
    preview["sha256"] = digest(preview)
    with pytest.raises(ValueError, match="preview"):
        apply_preview(
            queue=queue,
            manifest=manifest,
            preview=preview,
            cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
        )


def test_preview_holds_new_company_when_required_locale_is_missing(
    tmp_path, monkeypatch
):
    from core.models import Locale
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982201, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Missing Locale Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="missing-locale",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")

    class MissingLocale:
        def exists(self):
            return False

    monkeypatch.setattr(Locale.objects, "filter", lambda **kwargs: MissingLocale())
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["disposition"] == "unresolved"
    assert preview["members"][0]["reason"] == "missing_und_locale"
    assert preview["counts"]["new_companies"] == 0


def test_apply_reports_drift_if_shared_official_role_appears_after_preview(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from core import official_company_accounts
    from core.models import Role
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982211, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Role Race Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="role-race",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    Role.objects.filter(pk="official").delete()
    frozen = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=frozen, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["official_role_action"] == "create"
    original = official_company_accounts.registration_identity
    calls = 0

    def create_role():
        try:
            Role.objects.create(key="official")
        finally:
            connections.close_all()

    def racing_identity(state, account):
        nonlocal calls
        value = original(state, account)
        calls += 1
        if calls == 2:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(create_role).result(timeout=10)
        return value

    monkeypatch.setattr(
        official_company_accounts, "registration_identity", racing_identity
    )
    result = apply_preview(
        queue=queue,
        manifest=frozen,
        preview=preview,
        cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
    )
    assert result[0]["disposition"] == "drift"
    state.refresh_from_db()
    assert state.status == "accepted"


@pytest.mark.parametrize("status", ["suppressed", "rejected"])
def test_preview_reports_suppressed_and_rejected_separately(
    tmp_path, monkeypatch, status
):
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982221, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Held Status Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="held-status",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    state.status = status
    state.decision = {"outcome": "rejected"} if status == "rejected" else {}
    state.save()
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["current_status"] == status
    assert preview["members"][0]["reason"] == "state_" + status
    assert preview["counts"][status] == 1
    assert preview["counts"]["new_brands"] == 0


def test_preview_counts_suppressed_status_even_when_attempt_is_also_stale(
    tmp_path, monkeypatch
):
    from core.official_company_accepted_ingestion import (
        freeze_accepted,
        preview_accepted,
    )

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982231, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {
        "outcome": "accepted",
        "organization_name": "Stale Suppressed Lab",
    }
    state.save()
    attempt = OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="stale-suppressed",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    state.status = "suppressed"
    state.save()
    attempt.decision = {"outcome": "rejected"}
    attempt.save()
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["current_status"] == "suppressed"
    assert preview["counts"]["suppressed"] == 1
    assert preview["counts"]["unresolved"] == 1


def test_apply_rechecks_previewed_registered_account_before_reporting_success(
    tmp_path, monkeypatch
):
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from core.official_company_accounts import register_account
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982241, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {
        "outcome": "accepted",
        "organization_name": "Previously Registered Lab",
    }
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="registered-before-preview",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)
    register_account(state.pk, cfg=cfg)
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    assert preview["members"][0]["disposition"] == "already_registered"
    state.refresh_from_db()
    state.status = "suppressed"
    state.save()
    assert (
        apply_preview(queue=queue, manifest=manifest, preview=preview, cfg=cfg)[0][
            "disposition"
        ]
        == "drift"
    )


def test_replay_reports_missing_previously_created_brand_company_link(
    tmp_path, monkeypatch
):
    from core.models import BrandCompany
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982251, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Removed Edge Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="removed-edge",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)
    assert (
        apply_preview(queue=queue, manifest=manifest, preview=preview, cfg=cfg)[0][
            "disposition"
        ]
        == "registered"
    )
    state.refresh_from_db()
    BrandCompany.objects.filter(
        brand_id=state.registered_brand_id, company_id=state.registered_company_id
    ).delete()
    assert (
        apply_preview(queue=queue, manifest=manifest, preview=preview, cfg=cfg)[0][
            "disposition"
        ]
        == "drift"
    )


def test_apply_rejects_malformed_later_preview_row_before_any_writes(
    tmp_path, monkeypatch
):
    from core.models import BrandAccount
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from core.official_company_accounts import digest
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    states = [candidate(982261, 1), candidate(982262, 1)]
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    for index, state in enumerate(states):
        state.status = "accepted"
        state.decision = {
            "outcome": "accepted",
            "organization_name": f"Malformed Preview Lab {index}",
        }
        state.save()
        OfficialCompanyAttempt.objects.create(
            state=state,
            evidence_hash=state.evidence_hash,
            evidence=state.evidence,
            claim_token=f"malformed-preview-{index}",
            model="test",
            policy_version="v1",
            status="completed",
            decision=state.decision,
            reserved_usd=0,
            actual_usd=0,
            budget_keys=["queue-pass:" + queue["run_id"]],
            completed_at=timezone.now(),
        )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    del preview["members"][1]["official_role_action"]
    preview.pop("sha256")
    preview["sha256"] = digest(preview)
    with pytest.raises(ValueError, match="preview"):
        apply_preview(
            queue=queue,
            manifest=manifest,
            preview=preview,
            cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
        )
    assert not BrandAccount.objects.filter(
        account_id__in=[s.account_id for s in states]
    ).exists()


def test_scheduled_discovery_finishes_when_same_account_is_being_ingested(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, current_thread
    from time import monotonic

    from django.db import connection, connections

    from core import official_company_accounts
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from core.official_company_discovery import run_discovery_lane
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982271, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {
        "outcome": "accepted",
        "organization_name": "Concurrent Scheduler Lab",
    }
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="scheduled-same-account",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    cfg = OfficialCompanyConfig(
        enabled=True,
        registration_enabled=True,
        request_timeout_seconds=5,
        lane_deadline_seconds=30,
    )
    held, release, scheduled_started = Event(), Event(), Event()
    original = official_company_accounts.registration_identity
    calls = 0
    scheduled_pid = []

    def pause_ingestion(state, account):
        nonlocal calls
        result = original(state, account)
        if current_thread().name.startswith("ingest-contention"):
            calls += 1
            if calls == 2:
                held.set()
                assert release.wait(5)
        return result

    def ingest():
        try:
            return apply_preview(
                queue=queue, manifest=manifest, preview=preview, cfg=cfg
            )
        finally:
            connections.close_all()

    def scheduled():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                scheduled_pid.append(cursor.fetchone()[0])
            scheduled_started.set()
            return run_discovery_lane(
                cfg=cfg, run_id="scheduled-contention", call=None, allowance=2
            )
        finally:
            connections.close_all()

    monkeypatch.setattr(
        official_company_accounts, "registration_identity", pause_ingestion
    )
    with (
        ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ingest-contention"
        ) as ingest_pool,
        ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="scheduled-contention"
        ) as scheduled_pool,
    ):
        ingest_future = ingest_pool.submit(ingest)
        assert held.wait(5)
        scheduled_future = scheduled_pool.submit(scheduled)
        assert scheduled_started.wait(5)
        try:
            deadline = monotonic() + 3
            waited = False
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = %s",
                        [scheduled_pid[0]],
                    )
                    row = cursor.fetchone()
                if row and row[0]:
                    waited = True
                    break
                if scheduled_future.done():
                    break
                Event().wait(0.02)
            assert waited, "scheduled path did not reach the competing account lock"
        finally:
            release.set()
        result = ingest_future.result(timeout=10)
        scheduled_result = scheduled_future.result(timeout=10)
    assert result[0]["disposition"] == "registered"
    assert scheduled_result["status"] == "complete"
    state.refresh_from_db()
    assert state.status == "registered"


def test_stalled_ingestion_transaction_is_bounded_and_reported_unknown(
    tmp_path, monkeypatch
):
    from time import monotonic

    from django.db import connection

    from core import official_company_accounts
    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982281, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {"outcome": "accepted", "organization_name": "Stalled Writer Lab"}
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="stalled-ingestion",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    original = official_company_accounts.registration_identity
    calls = 0

    def stall(state, account):
        nonlocal calls
        result = original(state, account)
        calls += 1
        if calls == 2:
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_isolation")
                assert cursor.fetchone()[0] == "read committed"
                cursor.execute("SELECT pg_sleep(3)")
        return result

    monkeypatch.setattr(official_company_accounts, "registration_identity", stall)
    started = monotonic()
    result = apply_preview(
        queue=queue,
        manifest=manifest,
        preview=preview,
        cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
    )
    assert result[0]["disposition"] == "unknown_outcome"
    assert monotonic() - started < 5
    state.refresh_from_db()
    assert state.status == "accepted"


def test_ingestion_yields_when_same_organization_writer_is_active(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections, transaction

    from core.official_company_accepted_ingestion import (
        apply_preview,
        freeze_accepted,
        preview_accepted,
    )
    from core.organization_identity_locks import (
        acquire_writer_identity_locks,
        organization_lock_keys,
    )
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    state = candidate(982301, 1)
    queue = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.decision = {
        "outcome": "accepted",
        "organization_name": "Busy Organization Lab",
    }
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        evidence=state.evidence,
        claim_token="busy-org",
        model="test",
        policy_version="v1",
        status="completed",
        decision=state.decision,
        reserved_usd=0,
        actual_usd=0,
        budget_keys=["queue-pass:" + queue["run_id"]],
        completed_at=timezone.now(),
    )
    manifest = freeze_accepted(queue=queue, path=tmp_path / "accepted.json")
    preview = preview_accepted(
        queue=queue, manifest=manifest, path=tmp_path / "preview.json"
    )
    held, release = Event(), Event()

    def writer():
        try:
            with transaction.atomic():
                acquire_writer_identity_locks(
                    organization_lock_keys(name="Busy Organization Lab")
                )
                held.set()
                assert release.wait(5)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        assert held.wait(5)
        try:
            result = apply_preview(
                queue=queue,
                manifest=manifest,
                preview=preview,
                cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True),
            )
        finally:
            release.set()
        future.result(timeout=5)
    assert result[0]["disposition"] == "busy_retry"
    state.refresh_from_db()
    assert state.status == "accepted"

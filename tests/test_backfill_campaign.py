"""Explicit aggregate evaluation defers failures without declaring success."""

import pytest

from scripts.backfill_campaign import block_live_cursor_writes, run_sequence


def test_missing_on_demand_key_stops_before_any_collection(monkeypatch):
    from scripts.backfill_campaign import execute_window

    monkeypatch.setenv("DEEPINFRA_API_KEY", "scheduled-must-not-be-used")
    monkeypatch.delenv("DEEPINFRA_ON_DEMAND", raising=False)
    with pytest.raises(ValueError, match="DEEPINFRA_ON_DEMAND"):
        execute_window({}, frozen={}, cfg=None)


def test_windows_start_only_in_sequence_after_verification():
    visited = []
    result = run_sequence(
        [1, 2, 3], lambda window: visited.append(window) or {"status": "verified"}
    )
    assert visited == [1, 2, 3] and len(result) == 3


def test_failed_post_verification_stops_before_the_next_window():
    visited = []

    def run(window):
        visited.append(window)
        return {"status": "failed" if window == 2 else "verified"}

    with pytest.raises(ValueError, match="window_not_verified"):
        run_sequence([1, 2, 3], run)
    assert visited == [1, 2]


def test_provider_exception_stops_before_the_next_window():
    visited = []

    def run(window):
        visited.append(window)
        raise RuntimeError("provider_failure")

    with pytest.raises(RuntimeError, match="provider_failure"):
        run_sequence([1, 2, 3], run)
    assert visited == [1]


def test_aggregate_mode_attempts_later_windows_after_quality_and_provider_failure():
    visited = []

    def run(window):
        visited.append(window)
        if window == 2:
            raise RuntimeError("provider_failure")
        return {"status": "failed" if window == 1 else "attempted"}

    results = run_sequence([1, 2, 3], run, evaluate_at_end=True)
    assert visited == [1, 2, 3]
    assert [r["status"] for r in results] == ["failed", "deferred", "attempted"]
    assert results[1]["error_code"] == "provider_failure"


@pytest.mark.parametrize(
    "code",
    [
        "enrichment_database_identity_mismatch",
        "campaign_deadline_exhausted",
        "immutable_campaign_manifest_changed",
        "enrichment_configuration_changed",
        "enrichment_provider_admission_http_401",
        "enrichment_provider_admission_http_402",
        "enrichment_provider_admission_http_403",
        "backfill_storage_schema_incompatible",
    ],
)
def test_aggregate_evaluation_preserves_global_safety_guards(code):
    visited = []

    def run(window):
        visited.append(window)
        raise RuntimeError(code)

    with pytest.raises(RuntimeError, match=code):
        run_sequence([1, 2], run, evaluate_at_end=True)
    assert visited == [1]


@pytest.mark.parametrize(
    "sql",
    [
        'UPDATE "call_state" SET last_completed_at = now()',
        'INSERT INTO "harvest_backlog_windows" (id) VALUES (1)',
        "DELETE FROM call_state",
    ],
)
def test_live_cursor_mutations_are_blocked(sql):
    with pytest.raises(RuntimeError, match="campaign_live_cursor_write_forbidden"):
        block_live_cursor_writes(lambda *args: None, sql, [], False, {})


def test_normal_cursor_reads_and_post_writes_remain_allowed():
    captured = []
    for sql in ["SELECT * FROM call_state", 'UPDATE "posts" SET lang = %s']:
        block_live_cursor_writes(
            lambda *args: captured.append(args[0]), sql, [], False, {}
        )
    assert len(captured) == 2


@pytest.mark.parametrize("revision,configuration", [("c" * 40, "saved"), ("b" * 40, "changed")])
def test_selected_runtime_does_not_bypass_revision_or_configuration_pins(
    monkeypatch, revision, configuration,
):
    from scripts import backfill_campaign as campaign

    monkeypatch.setenv("RENDER_GIT_COMMIT", "b" * 40)
    monkeypatch.setattr(campaign, "configuration_pin", lambda cfg: configuration)
    with pytest.raises(RuntimeError, match="pinned_runtime_changed"):
        campaign.run(
            {"revision": "a" * 40, "configuration_pin": "saved"},
            None, runtime_revision=revision,
        )


@pytest.mark.parametrize("status", [401, 402, 403])
def test_permanent_provider_admission_failure_stops_aggregate_campaign(status):
    from monitor.backfill_collection import BackfillProviderSafetyError

    visited = []

    def run(window):
        visited.append(window)
        raise BackfillProviderSafetyError(status)

    with pytest.raises(BackfillProviderSafetyError):
        run_sequence([1, 2], run, evaluate_at_end=True)
    assert visited == [1]


@pytest.mark.requires_postgres
@pytest.mark.django_db
@pytest.mark.parametrize("table", ["events", "opportunities"])
def test_missing_timezone_reference_stops_campaign_before_any_paid_work(
    settings, monkeypatch, table,
):
    from pathlib import Path

    import psycopg
    from django.db import connection, transaction

    from scripts import backfill_campaign as campaign
    from x_monitor.config import load_config

    settings.X_MONITOR_LIST_ID = 123
    cfg = load_config(Path("config.yaml"))
    frozen = campaign.manifest(
        cfg, windows=[("2026-08-01", "2026-08-02")],
        campaign_name="timezone-preflight", expected_revision="a" * 40,
    )
    monkeypatch.setenv("RENDER_GIT_COMMIT", "b" * 40)

    def must_not_advance(*args, **kwargs):
        raise AssertionError("campaign advanced before checking storage compatibility")

    monkeypatch.setattr(psycopg, "connect", must_not_advance)
    monkeypatch.setattr(campaign, "run_sequence", must_not_advance)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                f'ALTER TABLE "{table}" RENAME COLUMN source_timezone_id TO missing_timezone_reference'
            )
        with pytest.raises(RuntimeError, match="backfill_storage_schema_incompatible"):
            campaign.run(frozen, cfg, runtime_revision="b" * 40)
        transaction.set_rollback(True)

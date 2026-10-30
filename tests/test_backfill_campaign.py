"""Explicit aggregate evaluation defers failures without declaring success."""

from datetime import UTC, datetime

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


@pytest.mark.parametrize("evaluate_at_end", [False, True])
def test_legacy_window_composes_phases_with_saved_concurrency(monkeypatch, evaluate_at_end):
    from scripts import backfill_campaign as campaign

    calls = []
    monkeypatch.setattr(campaign, "_collect_window", lambda *a, **kw: calls.append(("collect", kw)) or ("job", ["retained"]))
    monkeypatch.setattr(campaign, "_enrich_window", lambda *a, **kw: calls.append(("enrich", kw)) or {"status": "verified"})
    monkeypatch.setattr(campaign, "resolve_api_key", lambda *a: "test")
    saved = []
    monkeypatch.setattr(campaign, "save_campaign_report", lambda job, result: saved.append((job, result)))
    result = campaign.execute_window({}, frozen={"direct_concurrency": 32}, cfg=None, evaluate_at_end=evaluate_at_end)
    assert result["status"] == "verified"
    assert saved == ([("job", result)] if evaluate_at_end else [])
    assert [phase for phase, _ in calls] == ["collect", "enrich"]
    assert calls[0][1]["legacy_evaluate_at_end"] is evaluate_at_end
    assert calls[1][1]["enrichment_concurrency"] == 32
    assert calls[1][1]["initial_issues"] == ["retained"]


@pytest.mark.parametrize("selected", [0, True, 33, 9])
def test_new_phase_rejects_enrichment_above_saved_ceiling_before_lookup(monkeypatch, selected):
    from scripts import backfill_campaign as campaign

    with pytest.raises(ValueError, match="enrichment_concurrency"):
        campaign.enrich_window({}, frozen={"direct_concurrency": 8}, cfg=None, enrichment_concurrency=selected)


def test_enrichment_requires_existing_job_and_never_registers(monkeypatch):
    from types import SimpleNamespace

    from scripts import backfill_campaign as campaign

    monkeypatch.setattr(campaign, "CollectionJob", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: SimpleNamespace(first=lambda: None))))
    monkeypatch.setattr(campaign, "resolve_api_key", lambda *a: "test")
    monkeypatch.setattr(campaign, "register_job", lambda **kw: pytest.fail("enrichment registered a collection job"))
    frozen = {"instruction_format": "x-backfill-campaign/v2", "campaign": "test", "direct_concurrency": 32}
    with pytest.raises(ValueError, match="window_job_missing"):
        campaign.enrich_window({"index": 1}, frozen=frozen, cfg=None)


def test_collection_unknown_failure_stops_aggregate_sequence(monkeypatch):
    from types import SimpleNamespace

    from scripts import backfill_campaign as campaign

    visited = []
    def fail(window, **kwargs):
        visited.append(window)
        raise RuntimeError("unexpected_page_failure")
    monkeypatch.setattr(campaign, "_collect_window", fail)
    monkeypatch.setattr(campaign, "CollectionJob", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: SimpleNamespace(first=lambda: None))))
    with pytest.raises(RuntimeError, match="unexpected_page_failure"):
        run_sequence([{"index": 1}, {"index": 2}],
            lambda w: campaign.collect_window(w, frozen={"campaign": "test"}, cfg=None),
            evaluate_at_end=True)
    assert visited == [{"index": 1}]


@pytest.mark.parametrize("selected,expected", [(None, 8), (4, 4)])
def test_enrichment_phase_threads_effective_concurrency_to_both_shared_callers(monkeypatch, selected, expected):
    from types import SimpleNamespace

    from scripts import backfill_campaign as campaign

    job = SimpleNamespace(pk="existing", provider_batches=SimpleNamespace(order_by=lambda *a: SimpleNamespace(first=lambda: None)))
    monkeypatch.setattr(campaign, "_window_job", lambda *a: job)
    monkeypatch.setattr(campaign, "verify_collection_window", lambda *a, **kw: {"status": "verified"})
    monkeypatch.setattr(campaign, "verify_window", lambda *a, **kw: {"status": "verified"})
    monkeypatch.setattr(campaign, "prepare_current_contract", lambda *a: None)
    monkeypatch.setattr(campaign, "policy_snapshot", lambda **kw: {})
    monkeypatch.setattr(campaign, "resolve_api_key", lambda *a: "test")
    monkeypatch.setattr(campaign, "assert_no_provider_failure", lambda *a: None)
    monkeypatch.setattr(campaign, "_phase_receipt", lambda job, phase, result, **kw: result)
    monkeypatch.setattr(campaign, "OriginalContentCall", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: SimpleNamespace(aggregate=lambda **kw: {}))))
    seen = []
    def advance(*args, **kw):
        seen.append(kw["direct_concurrency"])
        return {"status": "completed"}
    monkeypatch.setattr(campaign, "execute_enrichment", advance)
    monkeypatch.setattr(campaign, "advance_targeted", advance)
    monkeypatch.setattr(campaign, "execute_job", lambda *a, **kw: pytest.fail("enrichment recollected"))
    frozen = {"direct_concurrency": 32, "deadline": "2099-01-01T00:00:00+00:00"}
    window = {"max_usd": "1", "maximum_model_requests": 100}
    assert campaign.enrich_window(window, frozen=frozen, cfg=None, enrichment_concurrency=selected)["status"] == "verified"
    assert seen == [expected, expected]


@pytest.mark.parametrize("options", [{"unknown": 1}, {"concurrency": 21}, {"concurrency": True}, {"starts_per_second": float("nan")}, {"starts_per_second": 0}])
def test_collection_options_rejected_before_registration(monkeypatch, options):
    from scripts import backfill_campaign as campaign

    monkeypatch.setattr(campaign, "_collect_window", lambda *a, **kw: pytest.fail("invalid preferences reached collection"))
    with pytest.raises(ValueError, match="collection"):
        campaign.collect_window({}, frozen={}, cfg=None, collection_options=options)


def test_failed_enrichment_receipt_preserves_collection_success(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from scripts import backfill_campaign as campaign

    collection = {"status": "verified", "checked_posts": 4}
    run = SimpleNamespace(report={"unrelated": {"keep": True}, "backfill_campaign": {"collection": collection}}, save=lambda **kw: None)
    monkeypatch.setattr(campaign.transaction, "atomic", nullcontext)
    monkeypatch.setattr(campaign, "CollectionRun", SimpleNamespace(objects=SimpleNamespace(select_for_update=lambda: SimpleNamespace(get=lambda **kw: run))))
    campaign.save_campaign_report(SimpleNamespace(last_attempt_id="run"), {"status": "failed"}, phase="enrichment")
    assert run.report["unrelated"] == {"keep": True}
    assert run.report["backfill_campaign"]["collection"] == collection
    assert run.report["backfill_campaign"]["enrichment"]["status"] == "failed"


def test_phase_receipt_accounts_inline_models_separately_from_later_enrichment(monkeypatch):
    from types import SimpleNamespace

    from scripts import backfill_campaign as campaign

    reports = [(2, [{"status": "returned", "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": ".01"}}]),
               (1, [{"status": "failed", "usage": None}])]
    runs = SimpleNamespace(aggregate=lambda **kw: {"n": 7},
                           values_list=lambda *args: SimpleNamespace(iterator=lambda: iter(reports)))
    job = SimpleNamespace(pk="existing", runs=runs)
    later = {"requests_sent": 3, "responses": 2, "input_tokens": 200, "output_tokens": 30,
             "reserved_usd": ".03", "provider_reported_usd": ".02"}
    monkeypatch.setattr(campaign, "OriginalContentCall", SimpleNamespace(objects=SimpleNamespace(
        filter=lambda **kw: SimpleNamespace(aggregate=lambda **kw: later))))
    monkeypatch.setattr(campaign, "save_campaign_report", lambda *a, **kw: None)
    legacy_usage = {"reserved_usd": ".03", "input_tokens": 200}
    value = campaign._phase_receipt(job, "collection", {"status": "verified", "usage": legacy_usage}, frozen={}, window={}, started_at="start")
    assert value["usage"] == legacy_usage
    usage = value["phase_usage"]
    assert usage["twitterapi_requests"] == 7
    assert usage["post_enrichment"] == later
    assert usage["collection_gate"] == {
        "requests_started": 3, "responses_recorded": 2, "outcomes_unrecorded": 1,
        "known_input_tokens": 100, "known_output_tokens": 20, "known_cost_usd": "0.01",
        "responses_missing_usage": 1,
    }


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_phase_receipt_keeps_unknown_enrichment_cost_visible(monkeypatch):
    from decimal import Decimal

    from django.utils import timezone

    from scripts import backfill_campaign as campaign
    from tests.test_provider_batches import batch, call_values

    group = batch.__wrapped__()
    now = timezone.now()
    rows = []
    for index, state in enumerate(("completed", "completed", "ambiguous", "reserved")):
        values = call_values(group) | {
            "request_identity": f"receipt-{index}", "batch_key": f"receipt-{index}",
            "state": state, "reserved_usd": Decimal(".03"),
        }
        if state != "reserved":
            values["sent_at"] = now
        if state == "completed":
            values.update(completed_at=now, response_hash="d" * 64)
        if index == 0:
            values.update(actual_usd=Decimal(".01"), input_tokens=100, output_tokens=20)
        rows.append(campaign.OriginalContentCall.objects.create(**values))
    calls = campaign.OriginalContentCall.objects.filter(pk__in=[row.pk for row in rows]).order_by("pk")
    before = list(calls.values())
    monkeypatch.setattr(campaign, "save_campaign_report", lambda *a, **kw: None)

    result = campaign._phase_receipt(group.source_collection_job, "enrichment", {},
                                    frozen={}, window={}, started_at=now.isoformat())
    usage = result["phase_usage"]["post_enrichment"]
    assert usage["requests_sent"] == 3 and usage["responses"] == 2
    assert usage["requests_ambiguous"] == 1
    assert usage["requests_without_reported_cost"] == 2
    assert usage["provider_reported_usd"] == Decimal(".01")
    assert usage["reserved_usd"] == Decimal(".12")
    assert usage["input_tokens"] == 100 and usage["output_tokens"] == 20
    assert list(calls.values()) == before


def _stub_manifest_inputs(monkeypatch):
    from types import SimpleNamespace

    from scripts import backfill_campaign as campaign

    planned = [SimpleNamespace(call_id=call, query_string=f"{call} query min_faves:0")
               for call in ("A", "B1", "C1")]
    monkeypatch.setattr(campaign, "plan_calls_for_cycle", lambda cfg, **kw: planned)
    monkeypatch.setattr(campaign, "database_identity", lambda: {"name": "xbackfiller", "user": "xbackfiller"})
    monkeypatch.setattr(campaign, "configuration_pin", lambda cfg: "pin")
    monkeypatch.setattr(campaign, "config_digest", lambda cfg, version: "digest")
    seen = []

    def definition(**kw):
        seen.append(kw)
        return {"scope": {"units": [
            {"scope_key": call.call_id, "scope_kind": "x_query", "ownership": {
                "call_id": call.call_id, "query": call.query_string,
                "since_epoch": kw["since_epoch"], "until_epoch": kw["until_epoch"]}}
            for call in planned]}}

    monkeypatch.setattr(campaign, "plan_job_definition", definition)
    return SimpleNamespace(enabled_models=["deepseek", "qwen"]), seen


def test_manifest_without_new_window_fields_keeps_its_july_shape(monkeypatch):
    """Regression net: today's campaign manifest stays byte-identical for July-style inputs."""
    from scripts import backfill_campaign as campaign

    cfg, seen = _stub_manifest_inputs(monkeypatch)
    deadline = datetime(2026, 10, 30, tzinfo=UTC)
    frozen = campaign.manifest(
        cfg, windows=[("2026-07-01T00:00:00+00:00", "2026-07-01T06:00:00+00:00")],
        campaign_name="july-regression", supplemental_queries=[("B1", "extra min_faves:0")],
        deadline=deadline, expected_revision="r" * 40,
    )
    window = frozen["windows"][0]
    assert {key: window[key] for key in window if key != "collection_definition"} == {
        "index": 1, "since": "2026-07-01T00:00:00+00:00", "until": "2026-07-01T06:00:00+00:00",
        "since_epoch": 1782864000, "until_epoch": 1782885600,
        "max_usd": "6.25", "maximum_api_requests": 1250, "maximum_model_requests": 12500,
    }
    assert window["collection_definition"]["scope"]["units"] == [
        {"scope_key": call, "scope_kind": "x_query", "ownership": {
            "call_id": call, "query": f"{call} query min_faves:0",
            "since_epoch": 1782864000, "until_epoch": 1782885600}}
        for call in ("A", "B1", "C1")
    ] + [{"scope_key": "B1:supplement:0", "scope_kind": "x_query", "ownership": {
        "call_id": "B1", "query": "extra min_faves:0",
        "since_epoch": 1782864000, "until_epoch": 1782885600}}]
    assert window["collection_definition"]["scope"]["deadline"] == deadline.isoformat()
    assert [{k: v for k, v in kw.items() if k != "cfg"} for kw in seen] == [{
        "since_epoch": 1782864000, "until_epoch": 1782885600, "brands": ["deepseek", "qwen"],
        "requests": 200, "model_requests": 500, "seconds": 300,
        "maximum_requests": 1250, "maximum_models": 12500,
    }]
    assert {key: frozen[key] for key in frozen if key != "windows"} == {
        "schema_version": 1, "instruction_format": "x-backfill-campaign/v2",
        "campaign": "july-regression", "revision": "r" * 40,
        "database": {"name": "xbackfiller", "user": "xbackfiller"},
        "configuration_pin": "pin", "deadline": deadline.isoformat(),
        "runtime_config_sha256": "digest", "brands": ["deepseek", "qwen"],
        "queries": [("A", "A query min_faves:0"), ("B1", "B1 query min_faves:0"),
                    ("C1", "C1 query min_faves:0"), ("B1", "extra min_faves:0")],
        "model_reservation_ceiling_usd": "6.25", "direct_concurrency": 32,
        "credential_purpose": "on-demand",
    }


@pytest.mark.parametrize("window_basis,expected", [(None, {}), ("settled", {"spend_basis": "settled"})])
def test_saved_spend_basis_reaches_the_enrichment_policy_only_when_present(monkeypatch, window_basis, expected):
    from types import SimpleNamespace

    from scripts import backfill_campaign as campaign

    job = SimpleNamespace(pk="existing", provider_batches=SimpleNamespace(order_by=lambda *a: SimpleNamespace(first=lambda: None)))
    monkeypatch.setattr(campaign, "_window_job", lambda *a: job)
    monkeypatch.setattr(campaign, "verify_collection_window", lambda *a, **kw: {"status": "verified"})
    monkeypatch.setattr(campaign, "verify_window", lambda *a, **kw: {"status": "verified"})
    monkeypatch.setattr(campaign, "prepare_current_contract", lambda *a: None)
    policies = []
    monkeypatch.setattr(campaign, "policy_snapshot", lambda **kw: policies.append(kw) or {})
    monkeypatch.setattr(campaign, "resolve_api_key", lambda *a: "test")
    monkeypatch.setattr(campaign, "assert_no_provider_failure", lambda *a: None)
    monkeypatch.setattr(campaign, "_phase_receipt", lambda job, phase, result, **kw: result)
    monkeypatch.setattr(campaign, "OriginalContentCall", SimpleNamespace(objects=SimpleNamespace(
        filter=lambda **kw: SimpleNamespace(aggregate=lambda **kw: {}))))
    monkeypatch.setattr(campaign, "execute_enrichment", lambda *a, **kw: {"status": "completed"})
    monkeypatch.setattr(campaign, "advance_targeted", lambda *a, **kw: {"status": "completed"})
    frozen = {"direct_concurrency": 32, "deadline": "2099-01-01T00:00:00+00:00"}
    window = {"max_usd": "30", "maximum_model_requests": 100000}
    if window_basis is not None:
        window["spend_basis"] = window_basis
    assert campaign.enrich_window(window, frozen=frozen, cfg=None)["status"] == "verified"
    assert policies == [{
        "max_usd": "30", "deadline": datetime(2099, 1, 1, tzinfo=UTC),
        "max_model_requests": 100000, "max_control_requests": 5000, **expected,
    }]


def test_window_spend_basis_is_frozen_into_the_manifest(monkeypatch):
    from scripts import backfill_campaign as campaign

    cfg, _ = _stub_manifest_inputs(monkeypatch)
    frozen = campaign.manifest(
        cfg, windows=[{"since": "2026-07-01T00:00:00+00:00", "until": "2026-07-01T06:00:00+00:00",
                       "spend_basis": "settled"}],
        campaign_name="settled-window", deadline=datetime(2026, 10, 30, tzinfo=UTC), expected_revision="r" * 40,
    )
    window = frozen["windows"][0]
    assert window["spend_basis"] == "settled"
    assert (window["max_usd"], window["maximum_api_requests"], window["maximum_model_requests"]) == ("6.25", 1250, 12500)


def test_bounds_only_window_object_matches_the_plain_pair(monkeypatch):
    from scripts import backfill_campaign as campaign

    cfg, _ = _stub_manifest_inputs(monkeypatch)
    bounds = ("2026-07-01T00:00:00+00:00", "2026-07-01T06:00:00+00:00")
    common = {"campaign_name": "bounds", "deadline": datetime(2026, 10, 30, tzinfo=UTC), "expected_revision": "r" * 40}
    assert campaign.manifest(cfg, windows=[{"since": bounds[0], "until": bounds[1]}], **common) == campaign.manifest(
        cfg, windows=[bounds], **common)


@pytest.mark.parametrize("row,error", [
    ({"since": "2026-07-01T00:00:00+00:00", "until": "2026-07-01T06:00:00+00:00", "spend_basis": "actual"},
     "invalid_spend_basis"),
    ({"since": "2026-07-01T00:00:00+00:00", "until": "2026-07-01T06:00:00+00:00", "slice_seconds": 300},
     "unknown_window_field"),
    ({"since": "2026-07-01T00:00:00+00:00", "spend_basis": "settled"}, "window_bounds_required"),
])
def test_invalid_window_object_is_rejected_before_planning(monkeypatch, row, error):
    from scripts import backfill_campaign as campaign

    cfg, seen = _stub_manifest_inputs(monkeypatch)
    with pytest.raises(ValueError, match=error):
        campaign.manifest(cfg, windows=[row], campaign_name="bad", deadline=datetime(2026, 10, 30, tzinfo=UTC))
    assert seen == []

from __future__ import annotations

import json
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from scripts.staging_refresh.policy import load_policy
from x_monitor.config import Config, SearchConfig

POLICY_PATH = "config/staging_refresh.yaml"


class _Cursor:
    def __init__(self, row: tuple[str, str]):
        self.row = row
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, _params=None):
        self.statements.append(statement)

    def fetchone(self):
        return self.row


class _Connection:
    vendor = "postgresql"

    def __init__(
        self,
        *,
        database: str = "pushinweight_staging",
        role: str = "pushinweight_staging",
        host: str = "dpg-d9vb8ds9v7es738lepsg-a",
    ):
        self.settings_dict = {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": host,
            "PORT": "5432",
            "NAME": database,
            "USER": role,
        }
        self.cursor_instance = _Cursor((database, role))
        self.connected = False

    def ensure_connection(self):
        self.connected = True

    def cursor(self):
        return self.cursor_instance


def _config() -> Config:
    return Config(
        enabled_models=["deepseek"],
        daily_ceiling=333,
        search=SearchConfig(max_results=2_000, max_pages=100, max_per_page=20),
        x_monitor_list_id=123,
    )


def _environment(**overrides) -> dict[str, str]:
    values = {
        "X_MONITOR_STAGING_ACCEPTANCE_ENABLED": "true",
        "X_MONITOR_DEPLOYMENT_ENVIRONMENT": "staging",
        "RENDER_SERVICE_NAME": "pushinweight-staging-harvest",
        "X_MONITOR_STAGING_ACCEPTANCE_SERVICE": "pushinweight-staging-harvest",
        "TWITTERAPI_IO_API_KEY": "twitter-fixture",
        "ANTHROPIC_API_KEY": "anthropic-fixture",
    }
    values.update(overrides)
    return values


def _options(**overrides):
    values = {
        "dry_run": False,
        "enqueue": False,
        "brands": None,
        "limit_per_call": None,
        "max_pages_per_call": None,
        "skip_fetch": False,
    }
    values.update(overrides)
    return values


def _accepted_stats() -> dict:
    return {
        "run_id": "stage-cycle-a",
        "finished_at": "2026-08-27T00:00:00+00:00",
        "status": "completed",
        "totals": {
            "n_calls_planned": 7,
            "n_calls_run": 1,
            "n_results": 3,
            "n_inserted": 2,
            "n_updated": 0,
            "n_persist_failed": 0,
            "n_attributed": 2,
        },
        "planned_calls": [{"call_id": "A", "query_string": "secret-query"}],
        "calls": [
            {
                "call_id": "A",
                "status": "completed",
                "n_results": 3,
                "n_kept": 2,
                "n_inserted": 2,
                "n_updated": 0,
                "cursor_advanced": True,
            }
        ],
        "post_fetch": {"n_enrichment_claimed": 2},
        "errors": [],
        "http_log": [{"params": {"query": "secret-query"}}],
    }


def _no_results_stats() -> dict:
    stats = _accepted_stats()
    stats["totals"].update(n_results=0, n_inserted=0, n_attributed=0)
    stats["calls"][0].update(
        status="no_results",
        n_results=0,
        n_kept=0,
        n_inserted=0,
        n_updated=0,
    )
    stats["post_fetch"]["n_enrichment_claimed"] = 0
    return stats


@pytest.mark.parametrize(
    ("call_status", "errors", "expected"),
    [
        ("completed", [], "inconclusive"),
        ("no_results", [], "inconclusive"),
        ("cursor_write_failed", ["cursor.A: write failed"], "failed"),
        ("no_results", ["provider: failed after response"], "failed"),
    ],
)
def test_acceptance_status_treats_safe_empty_sweeps_as_inconclusive(
    call_status: str,
    errors: list[str],
    expected: str,
) -> None:
    from monitor.management.commands.run_cycle import Command

    stats = _no_results_stats()
    stats["calls"][0]["status"] = call_status
    stats["errors"] = errors

    status, selected_call = Command._acceptance_status(stats, selected_call="A")

    assert status == expected
    assert selected_call["status"] == call_status


def test_acceptance_status_enforces_result_cap_for_safe_call_status() -> None:
    from monitor.management.commands.run_cycle import Command
    from monitor.staging_acceptance import MAX_RESULTS

    stats = _no_results_stats()
    stats["calls"][0]["n_results"] = MAX_RESULTS + 1

    status, _selected_call = Command._acceptance_status(stats, selected_call="A")

    assert status == "failed"


@pytest.mark.parametrize(
    ("environment", "connection", "error"),
    [
        (
            {"X_MONITOR_STAGING_ACCEPTANCE_ENABLED": "false"},
            None,
            "acceptance_not_enabled",
        ),
        (
            {"X_MONITOR_DEPLOYMENT_ENVIRONMENT": "production"},
            None,
            "deployment_environment_mismatch",
        ),
        (
            {"RENDER_SERVICE_NAME": "pushinweight-staging-web"},
            None,
            "service_identity_mismatch",
        ),
        (
            {"X_MONITOR_STAGING_ACCEPTANCE_SERVICE": "pushinweight-staging-web"},
            None,
            "configured_service_identity_mismatch",
        ),
        ({"TWITTERAPI_IO_API_KEY": ""}, None, "provider_credential_missing:twitter"),
        ({"ANTHROPIC_API_KEY": ""}, None, "provider_credential_missing:translator"),
        ({}, _Connection(host="production.internal"), "database_host_mismatch"),
        ({}, _Connection(database="pushinweight"), "database_name_mismatch"),
        ({}, _Connection(role="pushinweight_prod"), "database_role_mismatch"),
    ],
)
def test_preflight_fails_closed_for_identity_database_and_credentials(
    environment,
    connection,
    error,
):
    from monitor.staging_acceptance import (
        StagingAcceptanceError,
        prepare_staging_acceptance,
    )

    environ = _environment(**environment)
    database = connection or _Connection()

    with pytest.raises(StagingAcceptanceError, match=f"^{error}$"):
        prepare_staging_acceptance(
            "A",
            options=_options(),
            cfg=_config(),
            environ=environ,
            database=database,
            policy=load_policy(POLICY_PATH),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"dry_run": True},
        {"enqueue": True},
        {"skip_fetch": True},
        {"brands": "deepseek"},
        {"limit_per_call": 5},
        {"max_pages_per_call": 1},
    ],
)
def test_preflight_rejects_modes_and_operator_limits(overrides):
    from monitor.staging_acceptance import (
        StagingAcceptanceError,
        prepare_staging_acceptance,
    )

    with pytest.raises(StagingAcceptanceError, match="^incompatible_argument:"):
        prepare_staging_acceptance(
            "A",
            options=_options(**overrides),
            cfg=_config(),
            environ=_environment(),
            database=_Connection(),
            policy=load_policy(POLICY_PATH),
        )


def test_preflight_rejects_unconfigured_call_before_connecting():
    from monitor.staging_acceptance import (
        StagingAcceptanceError,
        prepare_staging_acceptance,
    )

    database = _Connection()
    with pytest.raises(StagingAcceptanceError, match="^call_id_not_configured$"):
        prepare_staging_acceptance(
            "NOT-A-CALL",
            options=_options(),
            cfg=_config(),
            environ=_environment(),
            database=database,
            policy=load_policy(POLICY_PATH),
        )
    assert not database.connected


def test_profile_derives_non_widenable_cycle_limits():
    from monitor.staging_acceptance import prepare_staging_acceptance

    prepared = prepare_staging_acceptance(
        "A",
        options=_options(),
        cfg=_config(),
        environ=_environment(),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )

    assert prepared.profile.selected_call == "A"
    assert prepared.config.search.max_results == 5
    assert prepared.config.search.max_pages == 1
    assert prepared.config.search.max_per_page == 5
    assert prepared.config.cycle.max_truncation_walks == 1
    assert prepared.config.metrics_refresh.enabled is False
    assert prepared.config.harvest.enrichment.claim_per_cycle == 5
    assert prepared.profile.as_dict()["caps"] == {
        "selected_calls": 1,
        "search_requests": 1,
        "results": 5,
        "pages": 1,
        "page_size": 5,
        "truncation_walks": 1,
        "metrics_refresh": False,
        "enrichment_claims": 5,
        "http_retries": 0,
    }


def test_bounded_provider_client_clamps_arguments_results_and_retries():
    from monitor.staging_acceptance import BoundedTwitterApiClient

    class Delegate:
        max_retries = 2

        def __init__(self):
            self.kwargs = None

        def run_search(self, query, **kwargs):
            self.kwargs = kwargs
            return [{"id": str(i)} for i in range(9)], False

    delegate = Delegate()
    client = BoundedTwitterApiClient(delegate)
    items, truncated = client.run_search(
        "fixture",
        max_results=999,
        max_pages=999,
        max_per_page=999,
    )

    assert delegate.max_retries == 0
    assert delegate.kwargs["max_results"] == 5
    assert delegate.kwargs["max_pages"] == 1
    assert delegate.kwargs["max_per_page"] == 5
    assert len(items) == 5
    assert truncated is True
    with pytest.raises(AttributeError):
        client.fetch_user_timeline("fixture")


def test_database_connection_failure_is_a_secret_free_refusal():
    from monitor.staging_acceptance import (
        StagingAcceptanceError,
        prepare_staging_acceptance,
    )

    database = _Connection()

    def fail_connection():
        raise RuntimeError("postgresql://secret@production.example/internal")

    database.ensure_connection = fail_connection
    with pytest.raises(StagingAcceptanceError, match="^database_identity_unavailable$"):
        prepare_staging_acceptance(
            "A",
            options=_options(),
            cfg=_config(),
            environ=_environment(),
            database=database,
            policy=load_policy(POLICY_PATH),
        )


def test_truncated_response_gets_only_one_search_pass():
    from monitor.cycle import CycleRunner
    from monitor.staging_acceptance import prepare_staging_acceptance
    from x_monitor.query_plan import PlannedCall

    prepared = prepare_staging_acceptance(
        "A",
        options=_options(),
        cfg=_config(),
        environ=_environment(),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    calls = []

    class Api:
        def run_search(self, query, **kwargs):
            calls.append((query, kwargs))
            return [{"id": "1", "created_at_epoch": 100}], True

    runner = CycleRunner(cfg=prepared.config)
    call = PlannedCall(
        call_id="A",
        call_kind="account",
        brand_id="*",
        bucket=None,
        query_string="(list:123) min_faves:1",
        query_length=24,
    )

    _items, outcome = runner._fetch_tweets(call, Api(), window=(50, 200))

    assert len(calls) == 1
    assert outcome == "truncated"


def test_real_cycle_runner_filters_planning_to_the_selected_call():
    from monitor.cycle import CycleRunner
    from monitor.staging_acceptance import prepare_staging_acceptance
    from x_monitor.query_plan import PlannedCall

    prepared = prepare_staging_acceptance(
        "A",
        options=_options(),
        cfg=_config(),
        environ=_environment(),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    runner = CycleRunner(
        cfg=prepared.config,
        dry_run=True,
        _backfill_call_ids=["A"],
    )
    runner._plan_calls = lambda: [
        PlannedCall("A", "account", "*", None, "list:123", 8),
        PlannedCall("B1", "brand_wide", "deepseek", None, "deepseek", 8),
    ]

    stats = runner.run()

    assert [call["call_id"] for call in stats["planned_calls"]] == ["A"]
    assert stats["calls"] == []


def test_command_refuses_before_writer_lock_or_provider_factory(monkeypatch):
    events: list[str] = []

    def forbidden_lock(**_kwargs):
        events.append("lock")
        raise AssertionError("writer lock acquired")

    def forbidden_client(*_args, **_kwargs):
        events.append("client")
        raise AssertionError("provider client constructed")

    monkeypatch.setenv("X_MONITOR_STAGING_ACCEPTANCE_ENABLED", "false")
    monkeypatch.setattr("monitor.run_lock.harvest_writer_lock", forbidden_lock)
    monkeypatch.setattr(
        "x_monitor.reattribute.build_anthropic_client_from_env",
        forbidden_client,
    )

    with pytest.raises(CommandError, match="acceptance_not_enabled"):
        call_command(
            "run_cycle",
            "--staging-acceptance",
            "A",
            stdout=StringIO(),
            stderr=StringIO(),
        )

    assert events == []


@pytest.mark.parametrize(
    ("runner_stats", "expected_status", "expected_dispatch"),
    [
        (
            _accepted_stats(),
            "accepted",
            {"status": "enqueued", "task_id": "task-a"},
        ),
        (
            _no_results_stats(),
            "inconclusive",
            {"status": "ineligible", "task_id": ""},
        ),
    ],
)
def test_command_threads_profile_and_emits_secret_free_json(
    monkeypatch,
    runner_stats: dict,
    expected_status: str,
    expected_dispatch: dict[str, str],
):
    import monitor.management.commands.run_cycle as command_module
    from monitor.staging_acceptance import prepare_staging_acceptance

    prepared = prepare_staging_acceptance(
        "A",
        options=_options(),
        cfg=_config(),
        environ=_environment(),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    captured = {}

    @contextmanager
    def acquired_lock(**kwargs):
        captured["lock"] = kwargs
        yield SimpleNamespace(acquired=True, contention=None)

    @contextmanager
    def acquired_coordination_lock(_url, **kwargs):
        captured["coordination_lock"] = kwargs
        yield

    class Runner:
        def __init__(self, **kwargs):
            captured["runner"] = kwargs

        def run(self):
            return runner_stats

    dispatch_calls = []

    def dispatch(*_args, **_kwargs):
        dispatch_calls.append(True)
        return SimpleNamespace(status="enqueued", task_id="task-a")

    monkeypatch.setattr(
        command_module, "prepare_staging_acceptance", lambda **_kwargs: prepared
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://stage:secret@stage/stage")
    monkeypatch.setattr(
        "scripts.database_lock.acquire_harvest_coordination_lock",
        acquired_coordination_lock,
    )
    monkeypatch.setattr("monitor.run_lock.harvest_writer_lock", acquired_lock)
    monkeypatch.setattr("monitor.cycle.CycleRunner", Runner)
    monkeypatch.setattr(
        "x_monitor.relevancy.build_binary_relevancy_llm_call",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_anthropic_client_from_env",
        lambda _cfg: None,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_dispatch.dispatch_harvest_completion",
        dispatch,
    )

    stdout = StringIO()
    call_command(
        "run_cycle",
        "--staging-acceptance",
        "A",
        stdout=stdout,
        stderr=StringIO(),
    )
    payload = json.loads(stdout.getvalue())

    assert captured["lock"]["execution_mode"] == "staging-acceptance"
    assert captured["coordination_lock"]["environment"] == "staging"
    assert captured["runner"]["cycle_kind"] == "manual"
    assert captured["runner"]["_backfill_call_ids"] == ["A"]
    assert captured["runner"]["cfg"].search.max_results == 5
    assert payload["status"] == expected_status
    assert payload["staging_acceptance"]["service"] == "pushinweight-staging-harvest"
    assert payload["cycle"]["status"] == "completed"
    assert (
        payload["cycle"]["selected_call"]["n_results"]
        == runner_stats["calls"][0]["n_results"]
    )
    assert payload["headline_dispatch"] == expected_dispatch
    assert len(dispatch_calls) == (1 if expected_status == "accepted" else 0)
    assert "secret-query" not in stdout.getvalue()
    assert "DATABASE_URL" not in stdout.getvalue()


@pytest.mark.parametrize("failure", ["runner", "dispatch"])
def test_command_emits_structured_json_for_acceptance_failures(
    monkeypatch, failure: str
) -> None:
    import monitor.management.commands.run_cycle as command_module
    from monitor.staging_acceptance import prepare_staging_acceptance

    prepared = prepare_staging_acceptance(
        "A",
        options=_options(),
        cfg=_config(),
        environ=_environment(),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )

    @contextmanager
    def coordination_lock(_url, **_kwargs):
        yield

    @contextmanager
    def writer_lock(**_kwargs):
        yield SimpleNamespace(acquired=True, contention=None)

    class Runner:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            if failure == "runner":
                raise RuntimeError("postgresql://secret@production/internal")
            return _accepted_stats()

    def dispatch(*_args, **_kwargs):
        if failure == "dispatch":
            raise RuntimeError("redis://secret@production/internal")
        return SimpleNamespace(status="enqueued", task_id="task-a")

    monkeypatch.setattr(
        command_module, "prepare_staging_acceptance", lambda **_kwargs: prepared
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://stage:secret@stage/stage")
    monkeypatch.setattr(
        "scripts.database_lock.acquire_harvest_coordination_lock",
        coordination_lock,
    )
    monkeypatch.setattr("monitor.run_lock.harvest_writer_lock", writer_lock)
    monkeypatch.setattr("monitor.cycle.CycleRunner", Runner)
    monkeypatch.setattr(
        "x_monitor.relevancy.build_binary_relevancy_llm_call",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_anthropic_client_from_env",
        lambda _cfg: None,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_dispatch.dispatch_harvest_completion", dispatch
    )

    stdout = StringIO()
    call_command(
        "run_cycle",
        "--staging-acceptance",
        "A",
        stdout=stdout,
        stderr=StringIO(),
    )
    payload = json.loads(stdout.getvalue())

    if failure == "runner":
        assert payload["status"] == "failed"
        assert payload["cycle"]["error_count"] == 1
        assert payload["headline_dispatch"]["status"] == "ineligible"
    else:
        assert payload["status"] == "accepted"
        assert payload["headline_dispatch"]["status"] == "dispatch_error"
    assert "secret" not in stdout.getvalue()


def test_ordinary_command_path_does_not_run_staging_preflight(monkeypatch):
    import monitor.management.commands.run_cycle as command_module

    def forbidden(**_kwargs):
        raise AssertionError("ordinary command entered staging preflight")

    monkeypatch.setattr(command_module, "prepare_staging_acceptance", forbidden)
    command = command_module.Command()
    monkeypatch.setattr(command, "_handle", lambda *_args, **_kwargs: "ordinary")

    assert (
        command.handle(
            enqueue=True,
            dry_run=False,
            staging_acceptance=None,
            brands=None,
            limit_per_call=None,
            max_pages_per_call=None,
            skip_fetch=False,
            as_json=False,
        )
        == "ordinary"
    )

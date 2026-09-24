from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from scripts.staging_refresh.policy import load_policy
from x_monitor.config import Config, LlmConfig, SearchConfig
from x_monitor.rare_type_extra_search import QUERY_VERSION, planned_query_string

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
        llm=LlmConfig(
            translator_model="google/gemma-4-31B-it-turbo",
            translator_base_url="https://api.deepinfra.com/v1/openai",
            translator_provider="deepinfra",
            translator_deepinfra_request_profile="gemma4_translation_v1",
            classifier_model="deepseek-ai/DeepSeek-V4-Flash-0731",
            classifier_base_url="https://api.deepinfra.com/v1/openai",
            classifier_provider="deepinfra",
            classifier_deepinfra_request_profile="deepseek_0731",
        ),
    )


def _environment(**overrides) -> dict[str, str]:
    values = {
        "X_MONITOR_STAGING_ACCEPTANCE_ENABLED": "true",
        "X_MONITOR_DEPLOYMENT_ENVIRONMENT": "staging",
        "RENDER_SERVICE_NAME": "pushinweight-staging-harvest",
        "X_MONITOR_STAGING_ACCEPTANCE_SERVICE": "pushinweight-staging-harvest",
        "TWITTERAPI_IO_ON_DEMAND_API_KEY": "twitter-fixture",
        "DEEPSEEK_API_KEY": "deepseek-fixture",
        "DEEPINFRA_API_KEY": "deepinfra-fixture",
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


def _rare_config(tmp_path: Path) -> Config:
    cfg = _config()
    query = planned_query_string()
    jev = cfg.discovery.rare_types.jev
    identity = {
        "query_version": QUERY_VERSION,
        "planner_query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "requested_model": jev.model,
        "attested_model": jev.model,
        "requested_provider": jev.provider,
        "attested_provider": jev.provider,
        "question_version": jev.question_set_version,
        "question_content_sha256": jev.question_content_sha256,
        "threshold_version": jev.threshold_version,
        "threshold_values_sha256": jev.threshold_values_sha256,
        "yes_threshold": format(jev.yes_threshold, "f"),
        "no_threshold": format(jev.no_threshold, "f"),
        "role_opening_threshold": format(jev.role_opening_threshold, "f"),
        "attendance_event_threshold": format(
            jev.attendance_event_threshold, "f"
        ),
        "fixture_sha256": "a" * 64,
        "corpus_content_sha256": "b" * 64,
    }
    assessment = {
        "schema_version": "rare-type-quality-assessment-v1",
        "identity": identity,
        "status": "pass",
        "quality_gate_passed": True,
        "enablement_eligible": False,
        "enablement_approved": False,
        "reasons": [],
    }
    assessment["assessment_digest"] = hashlib.sha256(
        json.dumps(
            assessment,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    path = tmp_path / "rare-type-assessment.json"
    path.write_text(json.dumps(assessment), encoding="utf-8")
    cfg.discovery.rare_types.enabled = True
    cfg.discovery.rare_types.assessment_path = str(path)
    cfg.discovery.rare_types.assessment_digest = assessment["assessment_digest"]
    cfg.discovery.rare_types.product_verification_enabled = True
    return cfg


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
        "post_fetch": {
            "n_enrichment_claimed": 2,
            "n_enrichment_claimed_current_cycle": 2,
            "n_enrichment_claimed_carryover": 0,
            "n_enrichment_succeeded": 2,
            "n_enrichment_succeeded_current_cycle": 2,
            "n_enrichment_succeeded_carryover": 0,
            "n_enrichment_pending": 0,
            "n_enrichment_pending_current_cycle": 0,
            "n_enrichment_pending_carryover": 0,
            "n_enrichment_failed": 0,
            "n_enrichment_failed_current_cycle": 0,
            "n_enrichment_failed_carryover": 0,
            "n_enrichment_deferred": 0,
            "n_enrichment_quarantined": 0,
            "inserted_post_ids": ["stage-post-1", "stage-post-2"],
            "enrichment_current_cycle_post_ids": [
                "stage-post-1",
                "stage-post-2",
            ],
            "enrichment_carryover_post_ids": [],
            "enrichment_state_facts": [
                {
                    "post_id": "stage-post-1",
                    "lane": "current_cycle",
                    "translation_status": "succeeded",
                    "classification_status": "succeeded",
                    "output_complete": True,
                },
                {
                    "post_id": "stage-post-2",
                    "lane": "current_cycle",
                    "translation_status": "succeeded",
                    "classification_status": "succeeded",
                    "output_complete": True,
                },
            ],
        },
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
    for key in tuple(stats["post_fetch"]):
        stats["post_fetch"][key] = (
            []
            if key.endswith("_ids") or key == "enrichment_state_facts"
            else 0
        )
    return stats


def _prepared_acceptance():
    from monitor.staging_acceptance import prepare_staging_acceptance

    return prepare_staging_acceptance(
        "A",
        options=_options(),
        cfg=_config(),
        environ=_environment(),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )


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
    from monitor.staging_acceptance import evaluate_staging_acceptance

    stats = _no_results_stats()
    stats["calls"][0]["status"] = call_status
    stats["errors"] = errors

    evaluation = evaluate_staging_acceptance(_prepared_acceptance(), stats)

    assert evaluation.status == expected
    assert evaluation.selected_call["status"] == call_status


def test_acceptance_status_enforces_result_cap_for_safe_call_status() -> None:
    from monitor.staging_acceptance import (
        MAX_RESULTS,
        evaluate_staging_acceptance,
    )

    stats = _no_results_stats()
    stats["calls"][0]["n_results"] = MAX_RESULTS + 1

    evaluation = evaluate_staging_acceptance(_prepared_acceptance(), stats)

    assert evaluation.status == "failed"


def test_acceptance_requires_exact_inserted_current_cycle_terminal_cohort():
    from monitor.staging_acceptance import evaluate_staging_acceptance

    evaluation = evaluate_staging_acceptance(
        _prepared_acceptance(), _accepted_stats()
    )

    assert evaluation.status == "accepted"
    assert evaluation.reason_codes == ("terminal_complete",)
    assert [row["post_id"] for row in evaluation.post_evidence] == [
        "stage-post-1",
        "stage-post-2",
    ]


def test_acceptance_understands_rare_extra_stored_result(tmp_path):
    from monitor.staging_acceptance import (
        evaluate_staging_acceptance,
        prepare_staging_acceptance,
    )

    prepared = prepare_staging_acceptance(
        "RARE_EXTRA",
        options=_options(),
        cfg=_rare_config(tmp_path),
        environ=_environment(TYPESAFE_API_KEY="typesafe-fixture"),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    stats = _accepted_stats()
    stats["calls"][0].update(
        call_id="RARE_EXTRA",
        status="stored",
        normalized_count=2,
        provider_called=True,
    )

    evaluation = evaluate_staging_acceptance(prepared, stats)

    assert evaluation.status == "accepted"
    assert evaluation.reason_codes == ("terminal_complete",)

    stats["calls"][0].update(
        status="truncated_replay_queued",
        coverage_transfer="transferred",
        backlog_window_id=42,
        cursor_advanced=True,
    )
    truncated = evaluate_staging_acceptance(prepared, stats)
    assert truncated.status == "failed"
    assert truncated.reason_codes == ("pipeline_or_bound_failure",)


def test_acceptance_allows_bounded_truncation_after_coverage_is_durably_transferred():
    from monitor.staging_acceptance import evaluate_staging_acceptance

    stats = _accepted_stats()
    stats["calls"][0].update(
        status="truncated_replay_queued",
        coverage_transfer="transferred",
        backlog_window_id=42,
        cursor_advanced=True,
    )

    evaluation = evaluate_staging_acceptance(_prepared_acceptance(), stats)

    assert evaluation.status == "accepted"
    assert evaluation.reason_codes == ("terminal_complete",)
    assert evaluation.selected_call["coverage_transfer"] == "transferred"
    assert evaluation.selected_call["backlog_window_id"] == 42


@pytest.mark.parametrize(
    "missing_field", ["coverage_transfer", "backlog_window_id", "cursor_advanced"]
)
def test_acceptance_rejects_incomplete_truncation_transfer_proof(missing_field):
    from monitor.staging_acceptance import evaluate_staging_acceptance

    stats = _accepted_stats()
    stats["calls"][0].update(
        status="truncated_replay_queued",
        coverage_transfer="transferred",
        backlog_window_id=42,
        cursor_advanced=True,
    )
    stats["calls"][0].pop(missing_field)

    evaluation = evaluate_staging_acceptance(_prepared_acceptance(), stats)

    assert evaluation.status == "failed"
    assert evaluation.reason_codes == ("pipeline_or_bound_failure",)


@pytest.mark.parametrize("backlog_window_id", [None, "42", True, 0, -1])
def test_acceptance_rejects_invalid_truncation_backlog_identity(backlog_window_id):
    from monitor.staging_acceptance import evaluate_staging_acceptance

    stats = _accepted_stats()
    stats["calls"][0].update(
        status="truncated_replay_queued",
        coverage_transfer="transferred",
        backlog_window_id=backlog_window_id,
        cursor_advanced=True,
    )

    evaluation = evaluate_staging_acceptance(_prepared_acceptance(), stats)

    assert evaluation.status == "failed"
    assert evaluation.reason_codes == ("pipeline_or_bound_failure",)


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_reason"),
    [
        ("update_only", "inconclusive", "update_only"),
        ("stale_succeeded", "inconclusive", "current_cycle_identity_mismatch"),
        ("pending", "inconclusive", "enrichment_pending"),
        ("failed", "failed", "enrichment_failed"),
        ("incomplete", "inconclusive", "output_incomplete"),
        ("carryover", "failed", "carryover_claimed"),
    ],
)
def test_acceptance_rejects_false_positive_enrichment_evidence(
    case: str,
    expected_status: str,
    expected_reason: str,
) -> None:
    from monitor.staging_acceptance import evaluate_staging_acceptance

    stats = _accepted_stats()
    post_fetch = stats["post_fetch"]
    if case == "update_only":
        stats["calls"][0].update(n_inserted=0, n_updated=2)
        stats["totals"].update(n_inserted=0, n_updated=2)
        post_fetch["inserted_post_ids"] = []
    elif case == "stale_succeeded":
        post_fetch["enrichment_current_cycle_post_ids"] = [
            "stale-post-1",
            "stale-post-2",
        ]
        for index, fact in enumerate(post_fetch["enrichment_state_facts"], start=1):
            fact["post_id"] = f"stale-post-{index}"
    elif case == "pending":
        post_fetch["enrichment_state_facts"][0]["translation_status"] = "pending"
        post_fetch["n_enrichment_succeeded"] = 1
        post_fetch["n_enrichment_succeeded_current_cycle"] = 1
        post_fetch["n_enrichment_pending"] = 1
        post_fetch["n_enrichment_pending_current_cycle"] = 1
    elif case == "failed":
        post_fetch["enrichment_state_facts"][0]["classification_status"] = "failed"
        post_fetch["n_enrichment_succeeded"] = 1
        post_fetch["n_enrichment_succeeded_current_cycle"] = 1
        post_fetch["n_enrichment_failed"] = 1
        post_fetch["n_enrichment_failed_current_cycle"] = 1
        post_fetch["n_enrichment_quarantined"] = 1
    elif case == "incomplete":
        post_fetch["enrichment_state_facts"][0]["output_complete"] = False
    elif case == "carryover":
        post_fetch["n_enrichment_claimed"] = 3
        post_fetch["n_enrichment_claimed_carryover"] = 1
        post_fetch["n_enrichment_succeeded"] = 3
        post_fetch["n_enrichment_succeeded_carryover"] = 1
        post_fetch["enrichment_carryover_post_ids"] = ["carryover-post"]
        post_fetch["enrichment_state_facts"].append(
            {
                "post_id": "carryover-post",
                "lane": "carryover",
                "translation_status": "succeeded",
                "classification_status": "succeeded",
                "output_complete": True,
            }
        )

    evaluation = evaluate_staging_acceptance(_prepared_acceptance(), stats)

    assert evaluation.status == expected_status
    assert expected_reason in evaluation.reason_codes


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("claim_count", "inconsistent_enrichment_evidence"),
        ("fact_identity", "inconsistent_enrichment_evidence"),
        ("outcome_count", "inconsistent_enrichment_evidence"),
        ("overlap", "carryover_claimed"),
        ("cap", "enrichment_cap_exceeded"),
        ("inserted_identity", "inserted_identity_count_mismatch"),
    ],
)
def test_acceptance_fails_closed_for_independently_corrupted_evidence(
    case: str, expected_reason: str
) -> None:
    from monitor.staging_acceptance import (
        MAX_ENRICHMENT_CLAIMS,
        evaluate_staging_acceptance,
    )

    stats = _accepted_stats()
    post_fetch = stats["post_fetch"]
    if case == "claim_count":
        post_fetch["n_enrichment_claimed"] = 1
    elif case == "fact_identity":
        post_fetch["enrichment_state_facts"][0]["post_id"] = "different-post"
    elif case == "outcome_count":
        post_fetch["n_enrichment_succeeded"] = 1
    elif case == "overlap":
        post_fetch["enrichment_carryover_post_ids"] = ["stage-post-1"]
    elif case == "cap":
        post_fetch["n_enrichment_claimed"] = MAX_ENRICHMENT_CLAIMS + 1
    elif case == "inserted_identity":
        post_fetch["inserted_post_ids"] = ["stage-post-1"]

    evaluation = evaluate_staging_acceptance(_prepared_acceptance(), stats)

    assert evaluation.status == "failed"
    assert evaluation.reason_codes == (expected_reason,)


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
        (
            {"TWITTERAPI_IO_ON_DEMAND_API_KEY": ""},
            None,
            "provider_credential_missing:twitter",
        ),
        ({"DEEPINFRA_API_KEY": ""}, None, "provider_credential_missing:translator"),
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

    with pytest.raises(StagingAcceptanceError, match=r"^incompatible_argument:"):
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
    with pytest.raises(StagingAcceptanceError, match=r"^call_id_not_configured$"):
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
    assert prepared.config.harvest.enrichment.current_cycle_claim_per_cycle == 5
    assert prepared.config.harvest.enrichment.carryover_claim_per_cycle == 0
    assert prepared.profile.as_dict()["caps"] == {
        "selected_calls": 1,
        "search_requests": 1,
        "results": 5,
        "pages": 1,
        "page_size": 5,
        "truncation_walks": 1,
        "metrics_refresh": False,
        "enrichment_claims": 5,
        "enrichment_current_cycle_claims": 5,
        "enrichment_carryover_claims": 0,
        "http_retries": 0,
    }


def test_rare_extra_preflight_requires_exact_assessment_and_rare_provider_key(
    tmp_path,
):
    from monitor.staging_acceptance import (
        StagingAcceptanceError,
        prepare_staging_acceptance,
    )

    cfg = _rare_config(tmp_path)
    missing_jev = _environment(TYPESAFE_API_KEY="")
    database = _Connection()
    with pytest.raises(
        StagingAcceptanceError, match=r"^provider_credential_missing:jev$"
    ):
        prepare_staging_acceptance(
            "RARE_EXTRA",
            options=_options(),
            cfg=cfg,
            environ=missing_jev,
            database=database,
            policy=load_policy(POLICY_PATH),
        )
    assert not database.connected

    cfg.discovery.rare_types.jev.threshold_version = "drifted-thresholds"
    with pytest.raises(
        StagingAcceptanceError, match=r"^rare_extra_assessment_mismatch$"
    ):
        prepare_staging_acceptance(
            "RARE_EXTRA",
            options=_options(),
            cfg=cfg,
            environ=_environment(TYPESAFE_API_KEY="typesafe-fixture"),
            database=database,
            policy=load_policy(POLICY_PATH),
        )
    assert not database.connected


def test_rare_extra_profile_pins_staging_jev_hf_and_enrichment_caps(tmp_path):
    from monitor.staging_acceptance import prepare_staging_acceptance

    prepared = prepare_staging_acceptance(
        "RARE_EXTRA",
        options=_options(),
        cfg=_rare_config(tmp_path),
        environ=_environment(TYPESAFE_API_KEY="typesafe-fixture"),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )

    rare = prepared.config.discovery.rare_types
    assert prepared.profile.selected_call == "RARE_EXTRA"
    assert rare.enabled is True
    assert rare.jev.staging_decisions_per_cycle == 5
    assert rare.product_verification_staging_requests == 1
    assert rare.targeted_extraction_enabled is True
    assert prepared.config.targeted_extraction.enabled is True
    assert prepared.config.targeted_extraction.max_calls_per_cycle == 20
    assert prepared.config.targeted_extraction.request_timeout_seconds == 30
    assert prepared.config.metrics_refresh.enabled is False
    assert prepared.config.harvest.enrichment.claim_per_cycle == 5
    assert prepared.config.harvest.enrichment.current_cycle_claim_per_cycle == 5
    assert prepared.config.harvest.enrichment.carryover_claim_per_cycle == 0
    assert prepared.profile.as_dict()["caps"]["jev_decisions"] == 5
    assert prepared.profile.as_dict()["caps"]["hf_requests"] == 1


def test_rare_extra_staging_override_enables_only_the_pinned_assessment(tmp_path):
    from monitor.staging_acceptance import (
        RARE_ASSESSMENT_DIGEST_ENVIRONMENT,
        RARE_ASSESSMENT_PATH_ENVIRONMENT,
        StagingAcceptanceError,
        prepare_staging_acceptance,
    )

    approved = _rare_config(tmp_path)
    path = approved.discovery.rare_types.assessment_path
    digest = approved.discovery.rare_types.assessment_digest
    checked_in = _config()
    environment = _environment(
        TYPESAFE_API_KEY="typesafe-fixture",
        **{
            RARE_ASSESSMENT_PATH_ENVIRONMENT: path,
            RARE_ASSESSMENT_DIGEST_ENVIRONMENT: digest,
        },
    )

    prepared = prepare_staging_acceptance(
        "RARE_EXTRA",
        options=_options(),
        cfg=checked_in,
        environ=environment,
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )

    assert checked_in.discovery.rare_types.enabled is False
    assert prepared.config.discovery.rare_types.enabled is True
    assert prepared.config.discovery.rare_types.assessment_path == path
    assert prepared.config.discovery.rare_types.assessment_digest == digest
    assert prepared.config.discovery.rare_types.product_verification_enabled is True
    assert prepared.config.discovery.rare_types.targeted_extraction_enabled is True
    assert prepared.config.targeted_extraction.enabled is True

    database = _Connection()
    environment.pop(RARE_ASSESSMENT_DIGEST_ENVIRONMENT)
    with pytest.raises(
        StagingAcceptanceError,
        match=r"^rare_extra_assessment_config_incomplete$",
    ):
        prepare_staging_acceptance(
            "RARE_EXTRA",
            options=_options(),
            cfg=checked_in,
            environ=environment,
            database=database,
            policy=load_policy(POLICY_PATH),
        )
    assert not database.connected


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


def test_bounded_provider_client_guards_rare_raw_page_caller():
    from monitor.staging_acceptance import (
        BoundedTwitterApiClient,
        StagingAcceptanceError,
    )

    class Delegate:
        max_retries = 2

        def __init__(self):
            self.calls = []

        def run_search_page_with_raw(self, query, **kwargs):
            self.calls.append((query, kwargs, self.max_retries))
            raw = {"tweets": [{"id": str(i)} for i in range(9)]}
            return b"{}", raw, list(raw["tweets"]), True, 0

    delegate = Delegate()
    client = BoundedTwitterApiClient(delegate)
    _body, raw, normalized, continuation, errors = (
        client.run_search_page_with_raw(
            "fixture",
            max_results=20,
            max_pages=20,
            max_per_page=20,
        )
    )

    assert delegate.calls == [
        (
            "fixture",
            {"max_results": 5, "max_pages": 1, "max_per_page": 5},
            0,
        )
    ]
    assert len(raw["tweets"]) == 9
    assert len(normalized) == 5
    assert continuation is True
    assert errors == 0
    with pytest.raises(
        StagingAcceptanceError, match=r"^search_request_cap_exceeded$"
    ):
        client.run_search_page_with_raw("fixture")
    assert len(delegate.calls) == 1
    with pytest.raises(
        StagingAcceptanceError, match=r"^search_retry_cap_exceeded$"
    ):
        client.max_retries = 1


def test_database_connection_failure_is_a_secret_free_refusal():
    from monitor.staging_acceptance import (
        StagingAcceptanceError,
        prepare_staging_acceptance,
    )

    database = _Connection()

    def fail_connection():
        raise RuntimeError("postgresql://secret@production.example/internal")

    database.ensure_connection = fail_connection
    with pytest.raises(
        StagingAcceptanceError, match=r"^database_identity_unavailable$"
    ):
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


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_rare_extra_staging_profile_reaches_shared_cycle_with_all_live_caps(
    tmp_path, monkeypatch
):
    from core.discovery import plan_discovery_calls
    from monitor.cycle import CycleRunner
    from monitor.staging_acceptance import (
        RARE_ASSESSMENT_DIGEST_ENVIRONMENT,
        RARE_ASSESSMENT_PATH_ENVIRONMENT,
        BoundedTwitterApiClient,
        prepare_staging_acceptance,
    )
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    approved = _rare_config(tmp_path)
    environment = _environment(
        TYPESAFE_API_KEY="typesafe-fixture",
        **{
            RARE_ASSESSMENT_PATH_ENVIRONMENT: (
                approved.discovery.rare_types.assessment_path
            ),
            RARE_ASSESSMENT_DIGEST_ENVIRONMENT: (
                approved.discovery.rare_types.assessment_digest
            ),
        },
    )
    prepared = prepare_staging_acceptance(
        "RARE_EXTRA",
        options=_options(),
        cfg=_config(),
        environ=environment,
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    call = next(
        call
        for call in plan_discovery_calls(prepared.config, list_id=42)
        if call.call_id == "RARE_EXTRA"
    )

    class Delegate:
        timeout_s = 30
        max_retries = 2

        def __init__(self):
            self.calls = []

        def run_search_page_with_raw(self, query, **kwargs):
            self.calls.append((query, kwargs, self.max_retries))
            return b"{}", {"tweets": []}, [], False, 0

    delegate = Delegate()
    api = BoundedTwitterApiClient(delegate)
    purposes = []
    drain_cutoffs = []
    metrics_configs = []
    hf_limits = []

    monkeypatch.setenv("RENDER_SERVICE_NAME", "pushinweight-staging-harvest")
    monkeypatch.setattr(CycleRunner, "_plan_calls", lambda _self: [call])
    monkeypatch.setattr("monitor.cycle._resolve_enabled_models", lambda *_a: [])
    monkeypatch.setattr("monitor.cycle._build_brand_index", lambda *_a: (None, {}))
    monkeypatch.setattr("monitor.cycle._load_brand_search_terms", dict)
    monkeypatch.setattr("monitor.cycle._resolve_x_monitor_list_id", lambda *_a: None)
    monkeypatch.setattr(
        "monitor.cycle.TwitterApiClient.from_env",
        lambda purpose: purposes.append(purpose) or api,
    )

    def drain(_self, **kwargs):
        drain_cutoffs.append(kwargs["fetched_since"])
        return {"selected": 0, "kept": 0, "junk": 0, "pending": 0}

    monkeypatch.setattr(CycleRunner, "_drain_rare_type_hits", drain)
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda *_a, **_kw: {})
    monkeypatch.setattr(
        CycleRunner, "_request_synthesis_prewarm", lambda *_a, **_kw: {}
    )

    def metrics(_api, cfg, **_kwargs):
        metrics_configs.append(cfg.metrics_refresh.enabled)
        return {"status": "disabled", "n_refreshed": 0}

    monkeypatch.setattr("monitor.metrics_refresh.run_metrics_refresh", metrics)

    def hf_drain(*, max_requests, deadline):
        hf_limits.append(max_requests)
        return SimpleNamespace(attempted=0, resolved=0, deferred=0)

    monkeypatch.setattr("monitor.cycle.drain_pending_verifications", hf_drain)
    monkeypatch.setattr(
        "scripts.harvest_cost.emit.finalize_and_persist",
        lambda summary, _api: summary,
    )

    stats = CycleRunner(
        cfg=prepared.config,
        cycle_kind="manual",
        _backfill_call_ids=["RARE_EXTRA"],
    ).run()

    assert purposes == [TwitterApiCredentialPurpose.ON_DEMAND]
    assert len(delegate.calls) == 1
    assert delegate.calls[0][1]["max_results"] == 5
    assert delegate.calls[0][1]["max_pages"] == 1
    assert delegate.calls[0][1]["max_per_page"] == 5
    assert delegate.calls[0][2] == 0
    assert drain_cutoffs and drain_cutoffs[0] is not None
    assert metrics_configs == [False]
    assert hf_limits == [1]
    assert stats["calls"][0]["status"] == "no_results"


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


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_real_nonempty_cycle_runner_reaches_same_cycle_terminal_acceptance(
    monkeypatch, settings, tmp_path, caplog, seeded_policy_keywords
):
    from django.utils import timezone

    from core.models import Post, PostEnrichmentState, PostTypeKey, SentimentKey
    from monitor.cycle import CycleRunner
    from monitor.harvest_summary import HARVEST_COHORT_PREFIX
    from monitor.post_enrichment import post_persisted_output_complete
    from monitor.staging_acceptance import (
        evaluate_staging_acceptance,
        prepare_staging_acceptance,
    )
    from x_monitor import attribution, reattribute, translator
    from x_monitor.query_plan import PlannedCall, XQuerySpec

    cfg = _config().model_copy(
        update={
            "x_query_specs": [
                XQuerySpec(
                    call_id="B1",
                    brands={"deepseek": ["deepseek"]},
                    co_occurrence=["AI"],
                )
            ]
        }
    )
    prepared = prepare_staging_acceptance(
        "B1",
        options=_options(),
        cfg=cfg,
        environ=_environment(),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    PostTypeKey.objects.get_or_create(key="releases_updates")
    SentimentKey.objects.get_or_create(key="positive")
    tweet_id = "999000000000001"
    now = timezone.now()
    provider_calls: list[dict] = []
    translation_ids: list[str] = []
    classification_ids: list[str] = []

    class Api:
        timeout_s = 60
        max_retries = 0

        def __init__(self):
            self._request_log: list[dict] = []

        def run_search(self, query, **kwargs):
            provider_calls.append({"query": query, **kwargs})
            return [
                {
                    "id": tweet_id,
                    "author_id": "900000000000001",
                    "author_handle": "deepseek_ai",
                    "text": "DeepSeek releases a stronger AI model.",
                    "created_at": now.isoformat(),
                    "created_at_epoch": int(now.timestamp()),
                }
            ], False

    api = Api()
    client = object()
    credential_purposes = []

    def fake_from_env(purpose):
        credential_purposes.append(purpose)
        return api

    monkeypatch.setattr("monitor.cycle.TwitterApiClient.from_env", fake_from_env)
    monkeypatch.setattr(
        reattribute, "build_translator_client_from_env", lambda _cfg: client
    )
    monkeypatch.setattr(
        reattribute, "build_classifier_client_from_env", lambda _cfg: client
    )
    monkeypatch.setattr(
        reattribute, "build_relevancy_client_from_env", lambda _cfg: client
    )

    def translate(tweets, _locales, _client, **_kwargs):
        translation_ids.extend(tweet["tweet_id"] for tweet in tweets)
        return [
            {
                "tweet_id": tweet["tweet_id"],
                "text_en": tweet["text"],
                "text_zh_cn": "DeepSeek 发布了更强的人工智能模型。",
                "en_equivalent": (
                    "The release raises competitive pressure across the model market."
                ),
                "cn_equivalent": "这次发布进一步加剧了模型市场的竞争压力。",
                "lang_detected": "en",
            }
            for tweet in tweets
        ]

    def classify(tweets, _brands, _client, **_kwargs):
        classification_ids.extend(tweet["tweet_id"] for tweet in tweets)
        return [
            {
                "valid": True,
                "by_brand": {
                    "deepseek": {
                        "outcome": "classified",
                        "post_types": ["releases_updates"],
                        "product_labels": [],
                        "sentiment": "positive",
                        "china_nationalism": None,
                        "us_nationalism": None,
                    }
                },
                "unsanctioned_flags": [],
            }
            for _tweet in tweets
        ]

    monkeypatch.setattr(translator, "translate_batch_pragmatics", translate)
    monkeypatch.setattr(
        attribution, "classify_batch_pragmatics_full", classify
    )
    policy_dir = tmp_path / "config"
    policy_dir.mkdir()
    repo_policy = Path(__file__).resolve().parents[1] / "config" / "harvest_policy.yaml"
    (policy_dir / "harvest_policy.yaml").write_text(
        repo_policy.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    settings.X_MONITOR_CYCLE_SINCE_TIME = int(now.timestamp()) - 120
    settings.X_MONITOR_CYCLE_UNTIL_TIME = int(now.timestamp()) + 1
    settings.X_MONITOR_LLM_PAUSE_SECONDS = 0
    settings.X_MONITOR_CYCLE_SKIP_FETCH = False

    runner = CycleRunner(
        cfg=prepared.config,
        cycle_kind="manual",
        _backfill_call_ids=["B1"],
    )
    runner._plan_calls = lambda: [
        PlannedCall(
            "B1", "brand_wide", "deepseek", None, "(deepseek) (AI)", 15
        )
    ]
    with caplog.at_level("INFO"):
        stats = runner.run()

    evaluation = evaluate_staging_acceptance(prepared, stats)
    post = Post.objects.get(tweet_id=tweet_id)
    state = PostEnrichmentState.objects.get(post=post)
    assert len(provider_calls) == 1
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    assert credential_purposes == [TwitterApiCredentialPurpose.ON_DEMAND]
    assert translation_ids == [tweet_id]
    assert classification_ids == [tweet_id]
    assert stats["totals"]["n_inserted"] == 1
    assert stats["post_fetch"]["inserted_post_ids"] == [tweet_id]
    assert stats["post_fetch"]["enrichment_current_cycle_post_ids"] == [
        tweet_id
    ]
    assert stats["post_fetch"]["n_enrichment_succeeded_current_cycle"] == 1
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert post_persisted_output_complete(post)
    assert evaluation.status == "accepted"
    assert evaluation.reason_codes == ("terminal_complete",)
    assert sum(
        record.message.startswith(HARVEST_COHORT_PREFIX)
        for record in caplog.records
    ) == 1


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
        "x_monitor.reattribute.build_relevancy_client_from_env",
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
        "x_monitor.reattribute.build_relevancy_client_from_env",
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
    if expected_status == "accepted":
        assert payload["reason_codes"] == ["terminal_complete"]
        assert [row["post_id"] for row in payload["cycle"]["enrichment_posts"]] == [
            "stage-post-1",
            "stage-post-2",
        ]
        assert payload["cycle"]["post_fetch"]["n_enrichment_claimed_current_cycle"] == 2
        assert payload["cycle"]["post_fetch"]["n_enrichment_claimed_carryover"] == 0
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
        "x_monitor.reattribute.build_relevancy_client_from_env",
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

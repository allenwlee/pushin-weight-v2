"""Fail-closed, cost-bounded staging harvest acceptance support.

This module is deliberately additive.  It derives a constrained Config for
the existing CycleRunner and temporarily wraps the Twitter client factory for
one synchronous management-command process.  Production run paths never call
this module.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from monitor.post_enrichment import (
    ENRICHMENT_COUNT_KEYS,
    enrichment_fact_terminal_complete,
    enrichment_stage_outcome,
)
from scripts.staging_refresh.policy import RefreshPolicy
from x_monitor.config import Config
from x_monitor.twitterapi_credentials import (
    TWITTERAPI_IO_SCHEDULED_API_KEY_ENV,
    TwitterApiCredentialPurpose,
)

ACCEPTANCE_ENABLE_ENVIRONMENT = "X_MONITOR_STAGING_ACCEPTANCE_ENABLED"
ACCEPTANCE_SERVICE_ENVIRONMENT = "X_MONITOR_STAGING_ACCEPTANCE_SERVICE"
DEPLOYMENT_ENVIRONMENT = "X_MONITOR_DEPLOYMENT_ENVIRONMENT"
EXPECTED_DEPLOYMENT_ENVIRONMENT = "staging"
EXPECTED_SERVICE_NAME = "pushinweight-staging-harvest"

MAX_RESULTS = 5
MAX_PAGES = 1
MAX_PER_PAGE = 5
MAX_TRUNCATION_WALKS = 1
MAX_ENRICHMENT_CLAIMS = 5
MAX_CURRENT_CYCLE_ENRICHMENT_CLAIMS = 5
MAX_CARRYOVER_ENRICHMENT_CLAIMS = 0

_SAFE_POST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FACT_KEYS = {
    "post_id",
    "lane",
    "translation_status",
    "classification_status",
    "output_complete",
}


class StagingAcceptanceError(ValueError):
    """A secret-free refusal safe to display in command output."""


@dataclass(frozen=True, slots=True)
class StagingAcceptanceProfile:
    selected_call: str
    service: str
    environment: str
    database: str
    role: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "environment": self.environment,
            "database": self.database,
            "database_role": self.role,
            "selected_call": self.selected_call,
            "caps": {
                "selected_calls": 1,
                "search_requests": 1,
                "results": MAX_RESULTS,
                "pages": MAX_PAGES,
                "page_size": MAX_PER_PAGE,
                "truncation_walks": MAX_TRUNCATION_WALKS,
                "metrics_refresh": False,
                "enrichment_claims": MAX_ENRICHMENT_CLAIMS,
                "enrichment_current_cycle_claims": (
                    MAX_CURRENT_CYCLE_ENRICHMENT_CLAIMS
                ),
                "enrichment_carryover_claims": MAX_CARRYOVER_ENRICHMENT_CLAIMS,
                "http_retries": 0,
            },
        }


@dataclass(frozen=True, slots=True)
class PreparedStagingAcceptance:
    profile: StagingAcceptanceProfile
    config: Config


@dataclass(frozen=True, slots=True)
class StagingAcceptanceEvaluation:
    status: str
    reason_codes: tuple[str, ...]
    selected_call: dict[str, Any]
    post_evidence: tuple[dict[str, Any], ...] = ()


def _configured_call_ids(cfg: Config) -> frozenset[str]:
    return frozenset(
        {"A"}
        | {
            spec.call_id
            for spec in cfg.x_query_specs
            if isinstance(spec.call_id, str) and spec.call_id
        }
    )


def _require_provider_credential(
    *,
    label: str,
    base_url: str | None,
    environ: Mapping[str, str],
) -> None:
    normalized = (base_url or "").lower()
    if "minimax.io" in normalized:
        present = bool(environ.get("MINIMAX_API_TOKEN"))
    elif "deepseek.com" in normalized:
        present = bool(
            environ.get("DEEPSEEK_API_KEY") or environ.get("DEEPSEEK_API_TOKEN")
        )
    else:
        present = bool(environ.get("ANTHROPIC_API_KEY") or environ.get("ANTHROPIC_KEY"))
    if not present:
        raise StagingAcceptanceError(f"provider_credential_missing:{label}")


def _validate_options(options: Mapping[str, Any]) -> None:
    incompatible = (
        ("dry_run", bool(options.get("dry_run"))),
        ("async", bool(options.get("enqueue"))),
        ("skip_fetch", bool(options.get("skip_fetch"))),
        ("brands", options.get("brands") is not None),
        ("limit_per_call", options.get("limit_per_call") is not None),
        (
            "max_pages_per_call",
            options.get("max_pages_per_call") is not None,
        ),
    )
    for name, supplied in incompatible:
        if supplied:
            raise StagingAcceptanceError(f"incompatible_argument:{name}")


def _inspect_database(database, policy: RefreshPolicy) -> tuple[str, str]:
    if database.vendor != "postgresql":
        raise StagingAcceptanceError("database_engine_mismatch")

    target = policy.target
    settings_dict = database.settings_dict
    host = str(settings_dict.get("HOST") or "").lower().rstrip(".")
    if host in policy.production_deny.hosts:
        raise StagingAcceptanceError("database_is_production")
    if host != target.host:
        raise StagingAcceptanceError("database_host_mismatch")

    raw_port = settings_dict.get("PORT") or 5432
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise StagingAcceptanceError("database_port_mismatch") from exc
    if port != target.port:
        raise StagingAcceptanceError("database_port_mismatch")

    try:
        database.ensure_connection()
        with database.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            row = cursor.fetchone()
    except Exception as exc:
        raise StagingAcceptanceError("database_identity_unavailable") from exc
    if not row or len(row) != 2:
        raise StagingAcceptanceError("database_identity_unavailable")

    database_name, role = (str(row[0]), str(row[1]))
    if database_name in policy.production_deny.databases:
        raise StagingAcceptanceError("database_is_production")
    if database_name != target.database:
        raise StagingAcceptanceError("database_name_mismatch")
    if role != target.role:
        raise StagingAcceptanceError("database_role_mismatch")
    if target.resource_id in policy.production_deny.resource_ids:
        raise StagingAcceptanceError("database_is_production")
    return database_name, role


def _bounded_config(cfg: Config) -> Config:
    enrichment = cfg.harvest.enrichment.model_copy(
        update={
            "claim_per_cycle": MAX_ENRICHMENT_CLAIMS,
            "current_cycle_claim_per_cycle": (
                MAX_CURRENT_CYCLE_ENRICHMENT_CLAIMS
            ),
            "carryover_claim_per_cycle": MAX_CARRYOVER_ENRICHMENT_CLAIMS,
        }
    )
    harvest = cfg.harvest.model_copy(update={"enrichment": enrichment})
    return cfg.model_copy(
        update={
            "search": cfg.search.model_copy(
                update={
                    "max_results": MAX_RESULTS,
                    "max_pages": MAX_PAGES,
                    "max_per_page": MAX_PER_PAGE,
                }
            ),
            "cycle": cfg.cycle.model_copy(
                update={"max_truncation_walks": MAX_TRUNCATION_WALKS}
            ),
            "metrics_refresh": cfg.metrics_refresh.model_copy(
                update={"enabled": False}
            ),
            "harvest": harvest,
        }
    )


def _safe_nonnegative_count(source: Mapping[str, Any], key: str) -> int:
    value = source.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StagingAcceptanceError(f"invalid_enrichment_count:{key}")
    return value


def _safe_post_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_ENRICHMENT_CLAIMS:
        raise StagingAcceptanceError("invalid_enrichment_post_ids")
    result = tuple(str(post_id) for post_id in value)
    if len(set(result)) != len(result) or any(
        not _SAFE_POST_ID_RE.fullmatch(post_id) for post_id in result
    ):
        raise StagingAcceptanceError("invalid_enrichment_post_ids")
    return result


def _safe_enrichment_facts(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_ENRICHMENT_CLAIMS:
        raise StagingAcceptanceError("invalid_enrichment_facts")
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != _FACT_KEYS:
            raise StagingAcceptanceError("invalid_enrichment_facts")
        post_id = str(raw.get("post_id") or "")
        lane = raw.get("lane")
        translation_status = raw.get("translation_status")
        classification_status = raw.get("classification_status")
        output_complete = raw.get("output_complete")
        if (
            not _SAFE_POST_ID_RE.fullmatch(post_id)
            or lane not in {"current_cycle", "carryover"}
            or not isinstance(output_complete, bool)
        ):
            raise StagingAcceptanceError("invalid_enrichment_facts")
        try:
            enrichment_stage_outcome(
                translation_status=translation_status,
                classification_status=classification_status,
            )
        except ValueError as exc:
            raise StagingAcceptanceError("invalid_enrichment_facts") from exc
        result.append(
            {
                "post_id": post_id,
                "lane": lane,
                "translation_status": translation_status,
                "classification_status": classification_status,
                "output_complete": output_complete,
            }
        )
    if len({fact["post_id"] for fact in result}) != len(result):
        raise StagingAcceptanceError("invalid_enrichment_facts")
    return tuple(sorted(result, key=lambda fact: fact["post_id"]))


def evaluate_staging_acceptance(
    prepared: PreparedStagingAcceptance,
    stats: Mapping[str, Any],
) -> StagingAcceptanceEvaluation:
    """Classify one bounded run from exact inserted and same-cycle facts."""

    selected_call = next(
        (
            dict(row)
            for row in stats.get("calls", [])
            if isinstance(row, Mapping)
            and row.get("call_id") == prepared.profile.selected_call
        ),
        {},
    )
    call_status = str(selected_call.get("status") or "missing")
    n_results = selected_call.get("n_results")
    n_inserted = selected_call.get("n_inserted")
    n_updated = selected_call.get("n_updated")
    if (
        stats.get("status") not in {"completed", "degraded"}
        or bool(stats.get("errors"))
        or call_status not in {"completed", "no_results"}
        or not isinstance(n_results, int)
        or isinstance(n_results, bool)
        or n_results < 0
        or n_results > MAX_RESULTS
        or not isinstance(n_inserted, int)
        or isinstance(n_inserted, bool)
        or n_inserted < 0
        or n_inserted > MAX_RESULTS
        or not isinstance(n_updated, int)
        or isinstance(n_updated, bool)
        or n_updated < 0
    ):
        return StagingAcceptanceEvaluation(
            status="failed",
            reason_codes=("pipeline_or_bound_failure",),
            selected_call=selected_call,
        )

    post_fetch = stats.get("post_fetch")
    if not isinstance(post_fetch, Mapping):
        return StagingAcceptanceEvaluation(
            status="failed",
            reason_codes=("invalid_enrichment_evidence",),
            selected_call=selected_call,
        )
    try:
        counts = {
            key: _safe_nonnegative_count(post_fetch, key)
            for key in ENRICHMENT_COUNT_KEYS
        }
        inserted_ids = _safe_post_ids(post_fetch.get("inserted_post_ids"))
        current_ids = _safe_post_ids(
            post_fetch.get("enrichment_current_cycle_post_ids")
        )
        carryover_ids = _safe_post_ids(
            post_fetch.get("enrichment_carryover_post_ids")
        )
        facts = _safe_enrichment_facts(post_fetch.get("enrichment_state_facts"))
    except StagingAcceptanceError:
        return StagingAcceptanceEvaluation(
            status="failed",
            reason_codes=("invalid_enrichment_evidence",),
            selected_call=selected_call,
        )

    if counts["n_enrichment_claimed_carryover"] or carryover_ids:
        return StagingAcceptanceEvaluation(
            status="failed",
            reason_codes=("carryover_claimed",),
            selected_call=selected_call,
            post_evidence=facts,
        )
    if (
        counts["n_enrichment_claimed"] > MAX_ENRICHMENT_CLAIMS
        or counts["n_enrichment_claimed_current_cycle"]
        > MAX_CURRENT_CYCLE_ENRICHMENT_CLAIMS
    ):
        return StagingAcceptanceEvaluation(
            status="failed",
            reason_codes=("enrichment_cap_exceeded",),
            selected_call=selected_call,
            post_evidence=facts,
        )

    fact_ids = {fact["post_id"] for fact in facts}
    claimed_ids = set(current_ids) | set(carryover_ids)
    derived = {
        f"n_enrichment_{outcome}_{lane}": sum(
            1
            for fact in facts
            if fact["lane"] == lane
            and enrichment_stage_outcome(
                translation_status=fact["translation_status"],
                classification_status=fact["classification_status"],
            )
            == outcome
        )
        for lane in ("current_cycle", "carryover")
        for outcome in ("succeeded", "pending", "failed")
    }
    derived.update(
        {
            f"n_enrichment_{outcome}": sum(
                derived[f"n_enrichment_{outcome}_{lane}"]
                for lane in ("current_cycle", "carryover")
            )
            for outcome in ("succeeded", "pending", "failed")
        }
    )
    evidence_consistent = (
        not (set(current_ids) & set(carryover_ids))
        and fact_ids == claimed_ids
        and counts["n_enrichment_claimed"] == len(claimed_ids)
        and counts["n_enrichment_claimed_current_cycle"] == len(current_ids)
        and counts["n_enrichment_claimed_carryover"] == len(carryover_ids)
        and all(counts[key] == value for key, value in derived.items())
    )
    if not evidence_consistent:
        return StagingAcceptanceEvaluation(
            status="failed",
            reason_codes=("inconsistent_enrichment_evidence",),
            selected_call=selected_call,
            post_evidence=facts,
        )
    if n_results == 0:
        return StagingAcceptanceEvaluation(
            status="inconclusive",
            reason_codes=("no_results",),
            selected_call=selected_call,
            post_evidence=facts,
        )
    if n_inserted == 0:
        return StagingAcceptanceEvaluation(
            status="inconclusive",
            reason_codes=(("update_only",) if n_updated else ("no_inserted_posts",)),
            selected_call=selected_call,
            post_evidence=facts,
        )
    if len(inserted_ids) != n_inserted:
        return StagingAcceptanceEvaluation(
            status="failed",
            reason_codes=("inserted_identity_count_mismatch",),
            selected_call=selected_call,
            post_evidence=facts,
        )

    acceptance_ids = set(inserted_ids)
    if not acceptance_ids or set(current_ids) != acceptance_ids:
        return StagingAcceptanceEvaluation(
            status="inconclusive",
            reason_codes=("current_cycle_identity_mismatch",),
            selected_call=selected_call,
            post_evidence=facts,
        )
    accepted_facts = tuple(
        fact for fact in facts if fact["post_id"] in acceptance_ids
    )
    if any(
        enrichment_stage_outcome(
            translation_status=fact["translation_status"],
            classification_status=fact["classification_status"],
        )
        == "failed"
        for fact in accepted_facts
    ):
        return StagingAcceptanceEvaluation(
            status="failed",
            reason_codes=("enrichment_failed",),
            selected_call=selected_call,
            post_evidence=facts,
        )
    if any(
        enrichment_stage_outcome(
            translation_status=fact["translation_status"],
            classification_status=fact["classification_status"],
        )
        == "pending"
        for fact in accepted_facts
    ):
        return StagingAcceptanceEvaluation(
            status="inconclusive",
            reason_codes=("enrichment_pending",),
            selected_call=selected_call,
            post_evidence=facts,
        )
    if not all(enrichment_fact_terminal_complete(fact) for fact in accepted_facts):
        return StagingAcceptanceEvaluation(
            status="inconclusive",
            reason_codes=("output_incomplete",),
            selected_call=selected_call,
            post_evidence=facts,
        )
    return StagingAcceptanceEvaluation(
        status="accepted",
        reason_codes=("terminal_complete",),
        selected_call=selected_call,
        post_evidence=accepted_facts,
    )


def prepare_staging_acceptance(
    call_id: str,
    *,
    options: Mapping[str, Any],
    cfg: Config,
    environ: Mapping[str, str],
    database,
    policy: RefreshPolicy,
) -> PreparedStagingAcceptance:
    """Validate every guard and return the only config the run may use."""

    _validate_options(options)
    if environ.get(ACCEPTANCE_ENABLE_ENVIRONMENT, "").lower() != "true":
        raise StagingAcceptanceError("acceptance_not_enabled")
    if environ.get(DEPLOYMENT_ENVIRONMENT) != EXPECTED_DEPLOYMENT_ENVIRONMENT:
        raise StagingAcceptanceError("deployment_environment_mismatch")
    if environ.get("RENDER_SERVICE_NAME") != EXPECTED_SERVICE_NAME:
        raise StagingAcceptanceError("service_identity_mismatch")
    if environ.get(ACCEPTANCE_SERVICE_ENVIRONMENT) != EXPECTED_SERVICE_NAME:
        raise StagingAcceptanceError("configured_service_identity_mismatch")

    if call_id not in _configured_call_ids(cfg):
        raise StagingAcceptanceError("call_id_not_configured")

    if not environ.get(TWITTERAPI_IO_SCHEDULED_API_KEY_ENV):
        raise StagingAcceptanceError("provider_credential_missing:twitter")

    translator_base_url = cfg.llm.translator_base_url or environ.get(
        "ANTHROPIC_BASE_URL"
    )
    classifier_base_url = environ.get(
        "X_MONITOR_CLASSIFIER_BASE_URL", environ.get("ANTHROPIC_BASE_URL")
    )
    _require_provider_credential(
        label="translator",
        base_url=translator_base_url,
        environ=environ,
    )
    _require_provider_credential(
        label="classifier",
        base_url=classifier_base_url,
        environ=environ,
    )

    database_name, role = _inspect_database(database, policy)
    profile = StagingAcceptanceProfile(
        selected_call=call_id,
        service=EXPECTED_SERVICE_NAME,
        environment=EXPECTED_DEPLOYMENT_ENVIRONMENT,
        database=database_name,
        role=role,
    )
    return PreparedStagingAcceptance(profile=profile, config=_bounded_config(cfg))


class BoundedTwitterApiClient:
    """Delegate that cannot exceed the acceptance request/result envelope."""

    def __init__(self, delegate):
        self._delegate = delegate
        self._delegate.max_retries = 0

    @property
    def timeout_s(self):
        return getattr(self._delegate, "timeout_s", 60)

    @property
    def max_retries(self) -> int:
        return 0

    @property
    def _request_log(self):
        return getattr(self._delegate, "_request_log", None)

    def run_search(self, query: str, **kwargs):
        kwargs.update(
            max_results=MAX_RESULTS,
            max_pages=MAX_PAGES,
            max_per_page=MAX_PER_PAGE,
        )
        items, truncated = self._delegate.run_search(query, **kwargs)
        items = list(items or [])
        over_limit = len(items) > MAX_RESULTS
        return items[:MAX_RESULTS], bool(truncated or over_limit)


@contextmanager
def bounded_twitter_client_factory() -> Iterator[None]:
    """Make CycleRunner's existing factory return one hard-bounded client.

    The management command is synchronous and each Render cron invocation is
    its own process, so the short-lived classmethod replacement cannot leak to
    another workload.  The original descriptor is restored even on failure.
    """

    from x_monitor.apify import TwitterApiClient

    original_descriptor = TwitterApiClient.__dict__["from_env"]
    original_factory = TwitterApiClient.from_env

    def _from_env(_cls, purpose: TwitterApiCredentialPurpose):
        return BoundedTwitterApiClient(original_factory(purpose))

    TwitterApiClient.from_env = classmethod(_from_env)
    try:
        yield
    finally:
        TwitterApiClient.from_env = original_descriptor


@contextmanager
def bounded_runtime_settings(settings_object) -> Iterator[None]:
    """Install exact CycleRunner settings and restore prior process state."""

    values = {
        "X_MONITOR_CYCLE_LIMIT_PER_CALL": MAX_RESULTS,
        "X_MONITOR_CYCLE_MAX_PAGES_PER_CALL": MAX_PAGES,
        "X_MONITOR_CYCLE_MAX_PER_PAGE": MAX_PER_PAGE,
        "X_MONITOR_CYCLE_SKIP_FETCH": False,
    }
    missing = object()
    previous = {name: getattr(settings_object, name, missing) for name in values}
    for name, value in values.items():
        setattr(settings_object, name, value)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is missing:
                delattr(settings_object, name)
            else:
                setattr(settings_object, name, value)

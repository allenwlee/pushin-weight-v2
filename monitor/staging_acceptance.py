"""Fail-closed, cost-bounded staging harvest acceptance support.

This module is deliberately additive.  It derives a constrained Config for
the existing CycleRunner and temporarily wraps the Twitter client factory for
one synchronous management-command process.  Production run paths never call
this module.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from scripts.staging_refresh.policy import RefreshPolicy
from x_monitor.config import Config

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
                "http_retries": 0,
            },
        }


@dataclass(frozen=True, slots=True)
class PreparedStagingAcceptance:
    profile: StagingAcceptanceProfile
    config: Config


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
        update={"claim_per_cycle": MAX_ENRICHMENT_CLAIMS}
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

    if not environ.get("TWITTERAPI_IO_API_KEY"):
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

    def _from_env(_cls):
        return BoundedTwitterApiClient(original_factory())

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

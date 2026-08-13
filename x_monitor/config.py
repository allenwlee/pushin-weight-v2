# {{AGENT_ATTRIBUTION}}
"""Pydantic config schema for x-monitor."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .query_plan import XQuerySpec

# Canonical model registry — adding a model here is the only "code change" needed.
# The data/queries/<brand_id>.yaml and data/accounts/<brand_id>.yaml files
# drop in alongside enabled_models in config.yaml.
KNOWN_MODELS: frozenset[str] = frozenset(
    {
        "minimax",
        "qwen",
        "deepseek",
        "glm",
        "mimo",
        "moonshot_kimi",
        "inclusionai",
        "mistral",
        "sakana_ai",
        "stepfun",
        "ernie",
        "hunyuan",
        "llama",
        "nemo_megatron",
        "doubao",
        "yi",
        "sensechat",
        "exaone",
        "kuaishou",
        "upstage",
    }
)

VALID_REVIEW_REASONS: frozenset[str] = frozenset(
    {"low_engagement", "off_topic", "suspicious_actor", "ambiguous_role", "banned_token"}
)

VALID_QUERY_IDS: tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")
# Plan 2026-07-11-002 (U3): post-consolidation the per-cycle call set is
# (Call A + C1 + C2 + B1 + B2 + B3). The skip order keys on call_id
# instead of the retired Q-IDs — Call A is the curated-list wide net
# (highest signal), the B-specs are wide-net per-brand (lowest recall),
# the C-specs are co-occurrence-constrained (middle). Skip order is
# B3 → B2 → B1 → C2 → C1 → A so lowest-recall calls drop first under
# credit pressure.
VALID_CALL_IDS: tuple[str, ...] = ("A", "B1", "B2", "B3", "C1", "C2")


class ClusteringConfig(BaseModel):
    min_commenters: int = Field(default=3, ge=2)
    min_posts: int = Field(default=2, ge=1)


class DashboardConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 5000
    poll_seconds: int = 30
    window_days: int = 14
    # Treemap volume + polarity-change window (days). The current and prior
    # windows for the polarity score are both this length, so the prior window
    # is always [anchor - 2*N, anchor - N). Must be <= window_days so the prior
    # window is fully covered by the post history; the model_validator below
    # enforces that.
    treemap_volume_window_days: int = 7

    @model_validator(mode="after")
    def _validate_treemap_window(self) -> DashboardConfig:
        # treemap_volume_window_days must be positive and <= window_days so the
        # prior window [anchor - 2N, anchor - N) is fully covered by post history.
        if self.treemap_volume_window_days <= 0:
            raise ValueError(
                f"treemap_volume_window_days must be positive (got {self.treemap_volume_window_days})"
            )
        if self.treemap_volume_window_days > self.window_days:
            raise ValueError(
                f"treemap_volume_window_days ({self.treemap_volume_window_days}) "
                f"must be <= window_days ({self.window_days}) so the polarity prior "
                f"window is fully covered by post history"
            )
        return self


class QuoteTweetConfig(BaseModel):
    """Quote-tweet capture knobs (2026-06-22). All optional with defaults;
    the QT-capture regimes run with no config.yaml entry."""

    # Official/staff regime (adaptive, every cycle): fetch a post's new QTs
    # when its quote_count grew by >= official_delta since the last fetch.
    official_delta: int = Field(default=5, ge=1)
    # How long (days) to keep refreshing an official post's quote_count after
    # it was created. Bounds the tracked set; old posts stop being polled.
    track_recency_days: int = Field(default=14, ge=1)
    # Max pages (20 QTs each) per get_quote_tweets call — bounds mega-floods.
    max_pages: int = Field(default=5, ge=1)
    # Hard cap on QT-fetch CALLS per cycle for the official regime.
    official_call_budget: int = Field(default=20, ge=0)

    # Non-official regime (daily pass; see plan Unit 5).
    daily_enabled: bool = True
    daily_recency_days: int = Field(default=7, ge=1)
    daily_call_budget: int = Field(default=50, ge=0)



class MetricsRefreshConfig(BaseModel):
    """One-shot metrics re-fetch knobs (plan 2026-08-10-002).

    After first ingest, each post is eligible for exactly one by-ID
    metrics refresh once it is at least `delay_hours` old (by
    `fetched_at`). Caps work per cycle so historical backlog drains
    without a single-tick credit spike.
    """

    enabled: bool = True
    delay_hours: float = Field(default=2.0, gt=0)
    per_cycle_cap: int = Field(default=200, ge=1)


class SearchConfig(BaseModel):
    """Search-cap knobs (U1, 2026-07-02). All optional with defaults;
    the main-loop search runs with no config.yaml entry.

    `max_results` is the upper bound on tweets returned per logical search
    call. `max_per_page` is the per-page request size passed to TwitterAPI.io
    (the platform caps responses at 20; we clamp to that). `max_pages` is a
    defensive cap on pagination depth — guards against a runaway cursor
    draining the credit budget.

    Defaults match today's hardcoded values (50 / 20 / 5) — this is a pure
    config-exposure refactor; omitting the `search:` block in config.yaml
    yields identical ship-path behavior.
    """

    max_results: int = Field(default=50, ge=1)
    max_per_page: int = Field(default=20, ge=1)
    max_pages: int = Field(default=5, ge=1)


class CycleConfig(BaseModel):
    """Cycle-level runtime constants (plan 2026-08-01-001).

    Defaults mirror the prior hardcoded values in monitor/cycle.py
    (_CURSOR_OVERLAP, _MAX_LOOKBACK, _C1_MAX_RESULTS, _C1_MAX_PAGES,
    _MAX_TRUNCATION_WALKS) so omitting the `cycle:` block in
    config.yaml preserves existing behavior.
    """

    cursor_overlap_seconds: int = Field(default=60, ge=0)
    max_lookback_hours: float = Field(default=0.25, gt=0, le=24)
    c1_max_results: int = Field(default=150, ge=1)
    c1_max_pages: int = Field(default=8, ge=1)
    max_truncation_walks: int = Field(default=5, ge=1)


@dataclass(frozen=True)
class MonotonicDeadline:
    """One cycle-wide budget shared by every scheduled consumer."""

    started_at: float
    deadline_at: float
    tip_target_at: float

    def remaining(self, *, monotonic: Callable[[], float] = time.monotonic) -> float:
        return max(self.deadline_at - monotonic(), 0.0)

    def can_start(
        self,
        worst_case_seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> bool:
        return worst_case_seconds <= self.remaining(monotonic=monotonic)


class BacklogConfig(BaseModel):
    pending_per_call: int = Field(default=8, ge=1)
    quarantined_per_call: int = Field(default=4, ge=1)
    max_attempts: int = Field(default=8, ge=1)
    max_age_hours: int = Field(default=24, ge=1)
    replays_per_cycle: int = Field(default=2, ge=1)


class ListMembershipConfig(BaseModel):
    page_size: int = Field(default=20, ge=1)
    max_pages: int = Field(default=100, ge=1)
    reconcile_interval_hours: int = Field(default=6, ge=1)
    request_timeout_seconds: int = Field(default=30, ge=1)


class EnrichmentConfig(BaseModel):
    """Bounded durable translation/classification queue."""

    claim_per_cycle: int = Field(default=20, ge=1)
    max_attempts: int = Field(default=8, ge=1)
    max_age_hours: int = Field(default=24, ge=1)
    claim_ttl_seconds: int = Field(default=180, ge=1)
    attempt_budget_seconds: int = Field(default=90, ge=1)


class HarvestConfig(BaseModel):
    """Bounded recovery and one-deadline scheduling contract."""

    run_deadline_seconds: int = Field(default=13 * 60, ge=1)
    next_slot_reserve_seconds: int = Field(default=2 * 60, ge=1)
    tip_sweep_target_seconds: int = Field(default=120, ge=1)
    relevancy_timeout_seconds: int = Field(default=30, ge=1)
    backlog: BacklogConfig = BacklogConfig()
    list_membership: ListMembershipConfig = ListMembershipConfig()
    enrichment: EnrichmentConfig = EnrichmentConfig()

    @model_validator(mode="after")
    def _validate_deadline_budget(self) -> HarvestConfig:
        if self.run_deadline_seconds + self.next_slot_reserve_seconds > 15 * 60:
            raise ValueError(
                "run_deadline_seconds + next_slot_reserve_seconds must fit "
                "inside the 15-minute schedule"
            )
        if self.tip_sweep_target_seconds > self.run_deadline_seconds:
            raise ValueError(
                "tip_sweep_target_seconds must not exceed run_deadline_seconds"
            )
        if self.relevancy_timeout_seconds > self.tip_sweep_target_seconds:
            raise ValueError(
                "relevancy_timeout_seconds must not exceed "
                "tip_sweep_target_seconds"
            )
        return self

    def start_deadline(
        self, *, monotonic: Callable[[], float] = time.monotonic
    ) -> MonotonicDeadline:
        started_at = monotonic()
        return MonotonicDeadline(
            started_at=started_at,
            deadline_at=started_at + self.run_deadline_seconds,
            tip_target_at=started_at + self.tip_sweep_target_seconds,
        )


class LlmConfig(BaseModel):
    """LLM model-name configuration (plan 2026-08-01-002 U1).

    Defaults mirror the values the v1 + v2 stacks used prior to this
    change; operators can override per-env via X_MONITOR_<role>_MODEL
    without editing config.yaml. The translator_base_url defaults to
    ANTHROPIC_BASE_URL env var (preserves the proxy path the v1 shell
    already configures).
    """

    translator_model: str = Field(
        default="deepseek-v4-pro",
        description="Model name for the translator stage. Default swapped to deepseek-v4-pro on 2026-08-04 (plan 2026-08-04-001) to lift the MiniMax M3 proxy-side response cap (~890-1800 tokens) that was truncating 12-50% of translator batches. Operators who need M3 back set X_MONITOR_TRANSLATOR_MODEL=minimax/MiniMax-M3.0[1m] and X_MONITOR_TRANSLATOR_BASE_URL=https://api.minimax.io/anthropic.",
    )
    translator_base_url: str | None = Field(
        default=None,
        description="Optional override for the translator's base URL. When None, falls back to ANTHROPIC_BASE_URL env (resolves to MiniMax proxy if set).",
    )
    classifier_model: str = Field(
        default="deepseek-v4-pro",
        description="Model name for the classifier stage. Default matches the 2026-07-15 swap plan.",
    )
    relevancy_model: str = Field(
        default="claude-haiku-4-5",
        description="Model name for the relevancy gate. Default matches x_monitor/relevancy.py::DEFAULT_RELEVANCY_MODEL.",
    )
    signal_model: str = Field(
        default="claude-haiku-4-5",
        description="Model name for the per-post signal classifier. Default matches x_monitor/attribution.py::_resolve_signal_model().",
    )


class HeadlineNarrativeConfig(BaseModel):
    """Cost-bounded role configuration for shared V22 trend narratives."""

    provider: Literal["anthropic", "deepseek", "minimax"] = "deepseek"
    base_url: str = "https://api.deepseek.com/anthropic"
    model: str = "deepseek-v4-pro"
    timeout_seconds: int = Field(default=45, ge=5, le=120)
    prompt_version: str = Field(
        default="headline-v4-analytical",
        min_length=1,
        max_length=64,
    )
    publication_epoch: int = Field(default=4, ge=1)
    cadence_minutes: dict[int, int] = Field(
        default_factory=lambda: {1: 30, 7: 60, 30: 360, 365: 1440}
    )
    stale_minutes: dict[int, int] = Field(
        default_factory=lambda: {1: 60, 7: 120, 30: 720, 365: 2880}
    )
    min_posts: int = Field(default=20, ge=1)
    min_authors: int = Field(default=10, ge=1)
    contested_ratio: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)
    minimum_coverage: Decimal = Field(default=Decimal("0.75"), ge=0, le=1)
    surging_ratio: Decimal = Field(default=Decimal("1.50"), ge=0)
    rising_ratio: Decimal = Field(default=Decimal("1.15"), ge=0)
    steady_ratio: Decimal = Field(default=Decimal("0.85"), ge=0)
    episode_peak_ratio: Decimal = Field(default=Decimal("3.0"), ge=1)
    fingerprint_band_percent: Literal[5] = 5
    call_cap: Literal[4] = 4
    max_body_en_chars: int = Field(default=240, ge=80, le=500)
    max_body_zh_cn_chars: int = Field(default=120, ge=40, le=300)
    task_expiry_seconds: int = Field(default=1800, ge=60, le=3600)
    lease_seconds: int = Field(default=90, ge=30, le=300)
    retention_days: int = Field(default=90, ge=1)
    retention_rows_per_window: int = Field(default=20, ge=1)
    serving_enabled: bool = False
    enqueue_enabled: bool = False
    provider_calls_enabled: bool = False
    control_revision: str = Field(default="off-v1", min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_headline_route_and_cadence(self) -> HeadlineNarrativeConfig:
        routes = {
            "anthropic": (
                "https://api.anthropic.com",
                "claude-haiku-4-5-20251001",
            ),
            "deepseek": (
                "https://api.deepseek.com/anthropic",
                "deepseek-v4-pro",
            ),
            "minimax": (
                "https://api.minimax.io/anthropic",
                "MiniMax-M3",
            ),
        }
        required_url, required_model = routes[self.provider]
        if self.base_url != required_url or self.model != required_model:
            raise ValueError(
                "headline provider, exact base_url, and evaluated model must match"
            )
        windows = {1, 7, 30, 365}
        if set(self.cadence_minutes) != windows:
            raise ValueError("headline cadences must cover 1, 7, 30, and 365 days")
        if set(self.stale_minutes) != windows:
            raise ValueError("headline stale limits must cover all fixed windows")
        if any(
            self.stale_minutes[window] != self.cadence_minutes[window] * 2
            for window in windows
        ):
            raise ValueError("headline stale limits must be twice each cadence")
        if not (
            self.surging_ratio >= self.rising_ratio >= self.steady_ratio
        ):
            raise ValueError("headline momentum ratios must descend")
        if self.lease_seconds <= self.timeout_seconds:
            raise ValueError("headline lease must exceed provider timeout")
        return self


class Config(BaseModel):
    enabled_models: list[str] = Field(min_length=1)
    daily_ceiling: int = Field(gt=0)
    apify_actor: str = "automation-lab/twitter-scraper"
    clustering: ClusteringConfig = ClusteringConfig()
    quote_tweets: QuoteTweetConfig = QuoteTweetConfig()
    metrics_refresh: MetricsRefreshConfig = MetricsRefreshConfig()
    search: SearchConfig = SearchConfig()
    cycle: CycleConfig = CycleConfig()
    harvest: HarvestConfig = HarvestConfig()
    llm: LlmConfig = LlmConfig()
    headline_narrative: HeadlineNarrativeConfig = HeadlineNarrativeConfig()
    query_rot_streak_threshold: int = Field(default=3, ge=1)
    query_rot_streak_threshold_per_model: dict[str, int] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=lambda: list(VALID_REVIEW_REASONS))
    # R17 (legacy): skip order was Q6 → Q5 → Q3 → Q2 → Q4 → Q1 (Q6
    # praise is high-volume / low-decision-signal).
    #
    # Plan 2026-07-11-002 (U3): post-consolidation the per-cycle call
    # set is (A + B1 + B2 + B3 + C1 + C2). Skip order is
    # B3 → B2 → B1 → C2 → C1 → A so the lowest-recall per-brand
    # wide-net calls drop first under credit pressure; the curated
    # X-list (Call A) is last because it carries the highest
    # signal-per-tweet ratio.
    degraded_skip_order: list[Literal["A", "B1", "B2", "B3", "C1", "C2"]] = Field(
        default_factory=lambda: ["B3", "B2", "B1", "C2", "C1", "A"]
    )
    # v1.7: x.com list ID for Call A (list-based fan-in). The list is
    # operator-managed (see v1.7 plan §"Operator manual step"). When
    # None, the pipeline runs in v1.6-compatible mode (per-brand
    # account calls) — this is a transitional affordance; v1.8 will
    # require the list unconditionally. See
    # docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
    # §"Call A — list-based fan-in".
    x_monitor_list_id: int | None = None
    # v2 (plan 2026-07-11-001): unified per-cycle call specs. Replaces
    # the v1.7.x `call_c_specs:` field. Each entry is an XQuerySpec
    # (see x_monitor.query_plan.XQuerySpec). Empty brands + empty
    # co_occurrence = Call A (the curated X-list wide net, rendered
    # with the list ID below). Non-empty brands = Call C-body shape
    # (the legacy co-occurrence-constrained form). See KTD1 / KTD5
    # in docs/plans/2026-07-11-001-*.md.
    #
    # For backwards compatibility with v1.7.x config files that still
    # use the old field name, ``load_config`` normalizes the legacy
    # `call_c_specs:` block to `x_query_specs:` at parse time.
    x_query_specs: list[XQuerySpec] = Field(default_factory=list)
    # Retired v1.7-era alias — kept so legacy config files parse
    # cleanly. U4 (smoketest) removal is a future plan.
    call_c_specs: list[XQuerySpec] = Field(default_factory=list)
    # Plan 2026-07-13-002 U4: the wide-net B path's per-brand split.
    # Brands listed here MUST NOT also appear in any call_c_specs /
    # x_query_specs entry — the C specs already cover polysemous
    # brands (llama, mimo, moonshot_kimi, yi via C1; ernie, upstage
    # via C2) via the co-occurrence AND-filter, so listing them in B
    # is duplicate TwitterAPI credit spend with no recall gain. The
    # model_validator below emits a warning if a future config
    # reintroduces a dupe.
    call_b_groups: list[list[str]] = Field(default_factory=list)
    dashboard: DashboardConfig = DashboardConfig()

    @field_validator("x_query_specs")
    @classmethod
    def _validate_x_query_spec_call_ids(cls, v: list[XQuerySpec]) -> list[XQuerySpec]:
        """Reject duplicate call_ids -- they would share a cursor row and
        one call's advance would overwrite the other's, collapsing the
        second call's next window to a 1-minute overlap.

        For B/C specs the cursor key also includes the planner's brand
        placeholder (first brand or first wide_net_brand), so two specs
        with the same call_id but different first brands are technically
        distinct. We only flag the truly-colliding case where the first
        brand also matches (the empty-brands fallback to "*" is treated
        as a match for that spec).
        """
        def _placeholder(spec: XQuerySpec) -> str:
            if spec.is_wide_net and spec.wide_net_brands:
                return spec.wide_net_brands[0]
            return next(iter(spec.brands), "*") if spec.brands else "*"

        seen: dict[tuple[str, str], int] = {}
        for i, spec in enumerate(v):
            key = (spec.call_id, _placeholder(spec))
            if key in seen:
                raise ValueError(
                    f"duplicate call_id+brand_placeholder {key} in "
                    f"x_query_specs (at indices {seen[key]} and {i}). Two "
                    "specs sharing both will address the same call_state "
                    "row, and one's advance will overwrite the other's, "
                    "collapsing the second call's next window to a 1-minute "
                    "overlap (peer finding, 2026-07-27)."
                )
            seen[key] = i
        return v

    @field_validator("enabled_models")
    @classmethod
    def _validate_models(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("enabled_models must be non-empty (operator must opt in)")
        seen = set()
        for m in v:
            if m not in KNOWN_MODELS:
                raise ValueError(
                    f"unknown brand_id '{m}'. Known: {sorted(KNOWN_MODELS)}"
                )
            if m in seen:
                raise ValueError(f"duplicate brand_id '{m}' in enabled_models")
            seen.add(m)
        return v

    @field_validator("review_reasons")
    @classmethod
    def _validate_reasons(cls, v: list[str]) -> list[str]:
        for r in v:
            if r not in VALID_REVIEW_REASONS:
                raise ValueError(
                    f"unknown review_reason '{r}'. Known: {sorted(VALID_REVIEW_REASONS)}"
                )
        return v

    @field_validator("degraded_skip_order")
    @classmethod
    def _validate_skip_order(cls, v: list[str]) -> list[str]:
        # Plan 2026-07-11-002 (U3): skip-order keys on call_ids now
        # (was Q1-Q6 in v1.6 / v1.7).
        if set(v) != set(VALID_CALL_IDS):
            raise ValueError(
                f"degraded_skip_order must contain exactly {list(VALID_CALL_IDS)}, got {v}"
            )
        if len(v) != len(VALID_CALL_IDS):
            raise ValueError(f"degraded_skip_order has duplicates: {v}")
        return v

    @model_validator(mode="after")
    def _warn_on_call_b_call_c_duplicates(self) -> "Config":
        """Plan 2026-07-13-002 U4: surface a warning when a brand
        appears in BOTH call_b_groups AND any x_query_specs / call_c_specs
        entry.

        The C specs cover polysemous brands (llama, mimo, moonshot_kimi,
        yi via C1; ernie, upstage via C2) via the co-occurrence
        AND-filter, so they should not also appear in the wide-net B
        path — that's duplicate TwitterAPI credit spend on the same
        recall. The validator emits logging.warning (NOT raise) so
        operators can override for A/B comparison runs.

        Reads x_query_specs (the v2 field) AND call_c_specs (the v1.7
        legacy alias) so legacy configs that still use call_c_specs:
        also get checked."""
        c_brands: set[str] = set()
        for spec in self.x_query_specs:
            c_brands.update((spec.brands or {}).keys())
        for spec in self.call_c_specs:
            c_brands.update((spec.brands or {}).keys())
        b_brands: set[str] = set()
        for group in self.call_b_groups:
            b_brands.update(group)
        dupes = sorted(b_brands & c_brands)
        if dupes:
            logging.warning(
                "call_b_groups shares %d brands with x_query_specs/"
                "call_c_specs: %s. The C specs already cover these via "
                "co-occurrence; removing them from B halves TwitterAPI "
                "credit spend on the wide-net path with no recall "
                "loss. See plan 2026-07-13-002 U4.",
                len(dupes), dupes,
            )
        return self

    @field_validator("query_rot_streak_threshold_per_model")
    @classmethod
    def _validate_rot_per_model(cls, v: dict[str, int]) -> dict[str, int]:
        for m, t in v.items():
            if m not in KNOWN_MODELS:
                raise ValueError(
                    f"query_rot_streak_threshold_per_model: unknown brand_id '{m}'"
                )
            if t < 1:
                raise ValueError(
                    f"query_rot_streak_threshold_per_model[{m}] must be >= 1, got {t}"
                )
        return v


def load_config(path: Path) -> Config:
    """Load and validate config.yaml. Raises ValidationError on bad input."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return Config.model_validate(raw)
    # Plan 2026-07-11-001 renamed `call_c_specs:` to `x_query_specs:` in
    # config.yaml. Older config files may still use the old key — copy
    # it into the new key when present so the Config model loads
    # regardless of which name the operator has.
    if "x_query_specs" not in raw and "call_c_specs" in raw:
        raw = {**raw, "x_query_specs": raw["call_c_specs"]}
    # Plan 2026-07-13-002 U4: same rename handling for call_b_groups.
    # Legacy v1.7.x config files may also carry this under a different
    # shape — pass through as-is when the key is present.
    # Plan 2026-08-01-002 U1: env-var resolution into Config.llm.*.
    # The translator's model name + base URL live in env vars on the
    # operator's shell (ANTHROPIC_MODEL, ANTHROPIC_BASE_URL) and may
    # differ from config.yaml. Merge env vars into Config.llm only
    # when the field is not already explicitly set in yaml — yaml wins.
    import os
    raw_llm = raw.get("llm", {}) if isinstance(raw.get("llm"), dict) else {}
    env_llm_overrides = {
        k: v for k, v in {
            "translator_model": os.environ.get("X_MONITOR_TRANSLATOR_MODEL"),
            "classifier_model": os.environ.get("X_MONITOR_CLASSIFIER_MODEL"),
            "relevancy_model": os.environ.get("X_MONITOR_RELEVANCY_MODEL"),
            "signal_model": os.environ.get("X_MONITOR_SIGNAL_MODEL"),
            "translator_base_url": os.environ.get("X_MONITOR_TRANSLATOR_BASE_URL"),
        }.items() if v is not None
    }
    if env_llm_overrides:
        # Plan 2026-08-04-001: yaml wins over env, BUT a yaml `null` is
        # not "set" — it's an explicit instruction to use the default
        # path (which falls back to ANTHROPIC_BASE_URL). Filter nulls
        # from yaml so the env override takes effect. Without this
        # filter, a yaml like `translator_base_url: null` clobbers an
        # env-set value and silently re-routes the translator to the
        # M3 proxy with the DS V4 model name (timeout, lang_detected
        # NULL on every post).
        raw_llm_filtered = {
            k: v for k, v in raw_llm.items() if v is not None
        }
        merged_llm = {**env_llm_overrides, **raw_llm_filtered}  # yaml wins over env (non-null only)
        raw = {**raw, "llm": merged_llm}
    raw_headline = (
        raw.get("headline_narrative", {})
        if isinstance(raw.get("headline_narrative"), dict)
        else {}
    )
    headline_env_names = {
        "provider": "X_MONITOR_HEADLINE_PROVIDER",
        "base_url": "X_MONITOR_HEADLINE_BASE_URL",
        "model": "X_MONITOR_HEADLINE_MODEL",
        "timeout_seconds": "X_MONITOR_HEADLINE_TIMEOUT_SECONDS",
        "prompt_version": "X_MONITOR_HEADLINE_PROMPT_VERSION",
        "publication_epoch": "X_MONITOR_HEADLINE_PUBLICATION_EPOCH",
        "serving_enabled": "X_MONITOR_HEADLINE_SERVING_ENABLED",
        "enqueue_enabled": "X_MONITOR_HEADLINE_ENQUEUE_ENABLED",
        "provider_calls_enabled": "X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED",
        "control_revision": "X_MONITOR_HEADLINE_CONTROL_REVISION",
    }
    env_headline_overrides = {
        field: os.environ[env_name]
        for field, env_name in headline_env_names.items()
        if env_name in os.environ
    }
    raw_headline_filtered = {
        key: value for key, value in raw_headline.items() if value is not None
    }
    if raw_headline or env_headline_overrides:
        raw = {
            **raw,
            "headline_narrative": {
                **env_headline_overrides,
                **raw_headline_filtered,
            },
        }
    try:
        return Config.model_validate(raw)
    except ValidationError:
        raise

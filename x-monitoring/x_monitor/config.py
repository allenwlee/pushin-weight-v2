# {{AGENT_ATTRIBUTION}}
"""Pydantic config schema for x-monitor."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .query_plan import CallCBrandSpec


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


class Config(BaseModel):
    enabled_models: list[str] = Field(min_length=1)
    daily_ceiling: int = Field(gt=0)
    apify_actor: str = "automation-lab/twitter-scraper"
    clustering: ClusteringConfig = ClusteringConfig()
    quote_tweets: QuoteTweetConfig = QuoteTweetConfig()
    search: SearchConfig = SearchConfig()
    query_rot_streak_threshold: int = Field(default=3, ge=1)
    query_rot_streak_threshold_per_model: dict[str, int] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=lambda: list(VALID_REVIEW_REASONS))
    # R17: skip order is Q6 first (lowest signal), then Q5, Q3, Q2, Q4, then Q1
    # last (highest signal-per-tweet — release announcements). Praise (Q6) is
    # skip-first because it is high-volume / low-decision-signal in a budget crunch.
    degraded_skip_order: list[Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]] = Field(
        default_factory=lambda: ["Q6", "Q5", "Q3", "Q2", "Q4", "Q1"]
    )
    # v1.7: x.com list ID for Call A (list-based fan-in). The list is
    # operator-managed (see v1.7 plan §"Operator manual step"). When
    # None, the pipeline runs in v1.6-compatible mode (per-brand
    # account calls) — this is a transitional affordance; v1.8 will
    # require the list unconditionally. See
    # docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
    # §"Call A — list-based fan-in".
    x_monitor_list_id: int | None = None
    # v1.7.x: optional Call C co-occurrence-constrained brand-wide
    # queries. See x_monitor.query_plan.CallCBrandSpec. Default empty
    # (no Call C; v1.7's 2-call baseline is preserved).
    call_c_specs: list[CallCBrandSpec] = Field(default_factory=list)
    # v1.7.x: optional Call B group split. When None (default), one
    # Call B is emitted spanning all enabled_models (legacy v1.7
    # behavior). When set, one Call B is emitted per inner list, in
    # the order given — each Call B's query is the OR of ORs of the
    # brands in its group. Use when the union of all enabled_models'
    # brand tokens exceeds the 512-char X advanced-search cap.
    # Each brand_id in a group must be in enabled_models and in
    # KNOWN_MODELS. Brands not in any group are skipped from Call B.
    call_b_groups: list[list[str]] | None = None
    dashboard: DashboardConfig = DashboardConfig()

    @field_validator("call_b_groups")
    @classmethod
    def _validate_call_b_groups(cls, v: list[list[str]] | None) -> list[list[str]] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("call_b_groups must be None or non-empty list of lists")
        seen: set[str] = set()
        for i, grp in enumerate(v):
            if not isinstance(grp, list) or not grp:
                raise ValueError(f"call_b_groups[{i}] must be a non-empty list of brand_ids")
            for b in grp:
                if b not in KNOWN_MODELS:
                    raise ValueError(
                        f"call_b_groups[{i}]: unknown brand_id '{b}'. Known: {sorted(KNOWN_MODELS)}"
                    )
                if b in seen:
                    raise ValueError(
                        f"call_b_groups: brand_id '{b}' appears in more than one group"
                    )
                seen.add(b)
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
        if set(v) != set(VALID_QUERY_IDS):
            raise ValueError(
                f"degraded_skip_order must contain exactly {list(VALID_QUERY_IDS)}, got {v}"
            )
        if len(v) != len(VALID_QUERY_IDS):
            raise ValueError(f"degraded_skip_order has duplicates: {v}")
        return v

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
    try:
        return Config.model_validate(raw)
    except ValidationError:
        raise

# {{AGENT_ATTRIBUTION}}
"""Pydantic config schema for x-monitor."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


# Canonical model registry — adding a model here is the only "code change" needed.
# The data/queries/<model_id>.yaml and data/accounts/<model_id>.yaml files
# drop in alongside enabled_models in config.yaml.
KNOWN_MODELS: frozenset[str] = frozenset(
    {
        "minimax",
        "qwen",
        "deepseek",
        "glm",
        "xiaomi_mimo",
        "moonshot_kimi",
        "inclusionai",
        "mistral",
        "stepfun",
        "ernie",
        "hunyuan",
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


class Config(BaseModel):
    enabled_models: list[str] = Field(min_length=1)
    daily_ceiling: int = Field(gt=0)
    apify_actor: str = "automation-lab/twitter-scraper"
    clustering: ClusteringConfig = ClusteringConfig()
    query_rot_streak_threshold: int = Field(default=3, ge=1)
    query_rot_streak_threshold_per_model: dict[str, int] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=lambda: list(VALID_REVIEW_REASONS))
    # R17: skip order is Q6 first (lowest signal), then Q5, Q3, Q2, Q4, then Q1
    # last (highest signal-per-tweet — release announcements). Praise (Q6) is
    # skip-first because it is high-volume / low-decision-signal in a budget crunch.
    degraded_skip_order: list[Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]] = Field(
        default_factory=lambda: ["Q6", "Q5", "Q3", "Q2", "Q4", "Q1"]
    )
    dashboard: DashboardConfig = DashboardConfig()

    @field_validator("enabled_models")
    @classmethod
    def _validate_models(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("enabled_models must be non-empty (operator must opt in)")
        seen = set()
        for m in v:
            if m not in KNOWN_MODELS:
                raise ValueError(
                    f"unknown model_id '{m}'. Known: {sorted(KNOWN_MODELS)}"
                )
            if m in seen:
                raise ValueError(f"duplicate model_id '{m}' in enabled_models")
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
                    f"query_rot_streak_threshold_per_model: unknown model_id '{m}'"
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

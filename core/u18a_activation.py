"""Frozen U18A user-facing activation decisions.

The classifier may persist every v4 field for shadow analysis.  Readers and
filters expose the seven Audience Topics selected by the owner after reviewing
the independently scored R94A evidence. Other families still require their own
activation decision; missing keys fail closed as ``shadow_only``.
"""

from __future__ import annotations

from typing import Final, Literal


ActivationState = Literal["enabled", "shadow_only"]

ACTIVATION_REVISION: Final = "u18a-owner-all-audience-topics-20260921-v1"
EVALUATOR_SHA256: Final = (
    "cf1ec56b963fe687eb0abb6a5d5e23d88ebf6475adc48b5b0818617cb4ac9678"
)
CANDIDATE_OUTPUT_SHA256: Final = (
    "9d47e93d019685be179bfaf8271b19b5eeee70b7b072d7b69298200b98f05cbb"
)
CANDIDATE_REPORT_SHA256: Final = (
    "dcf845e0c413c1240abd950dd32de05304d9328ab321d71927f590948d0be2ee"
)

FAMILY_DECISIONS: Final[dict[str, ActivationState]] = {
    "local_inference": "enabled",
    "cost_performance": "enabled",
    "model_distillation": "enabled",
    "evals_benchmarks": "enabled",
    "openness_license": "enabled",
    "agents_tools": "enabled",
    "api_developer_surface": "enabled",
    "news_reporting": "shadow_only",
    "investigate_claim": "shadow_only",
    "geopolitical": "shadow_only",
    "untracked_brand_promotions": "shadow_only",
}


def is_enabled(family: str) -> bool:
    """Return true only for an explicitly enabled, frozen family."""
    return FAMILY_DECISIONS.get(family) == "enabled"


def enabled_audience_topics(keys: tuple[str, ...]) -> tuple[str, ...]:
    """Keep independently enabled Audience Topic concepts in stable order."""
    return tuple(key for key in keys if is_enabled(key))

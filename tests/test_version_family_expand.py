"""Regression pins for U1 version-family policy expansion."""

from __future__ import annotations

import pytest

from x_monitor.harvest_policy import BrandPolicy, CoPack, HarvestPolicy, VersionFamily
from x_monitor.specs_from_policy import (
    expand_version_family,
    primary_keywords_from_policy,
    specs_from_policy,
)


def test_hunyuan_family_expands_previous_current_next_and_preview_suffixes():
    family = VersionFamily(
        prefix="Hy",
        current_major=4,
        lookback=1,
        lookahead=1,
        extra_suffixes=("-preview",),
    )

    assert expand_version_family(family) == [
        "Hy3",
        "Hy4",
        "Hy5",
        "Hy4-preview",
        "Hy5-preview",
    ]


def test_dots_lookback_zero_does_not_emit_dots_two():
    family = VersionFamily(prefix="dots", current_major=3, lookback=0, lookahead=1)

    assert expand_version_family(family) == ["dots3", "dots4"]
    assert "dots2" not in expand_version_family(family)


def test_versioned_bare_family_without_declared_tokens_expands():
    policy = HarvestPolicy(
        brands={
            "hunyuan": BrandPolicy(
                nickname="hunyuan",
                paths=frozenset({"versioned_bare"}),
                version_family=VersionFamily(
                    prefix="Hy", current_major=4, lookback=1, lookahead=1
                ),
            )
        }
    )

    assert primary_keywords_from_policy(policy)["hunyuan"] == [
        "Hy3",
        "Hy4",
        "Hy5",
    ]


def test_family_rejects_lookback_that_would_emit_negative_major():
    with pytest.raises(ValueError, match="lookback cannot exceed current_major"):
        VersionFamily(prefix="Hy", current_major=1, lookback=2, lookahead=1)


def test_bumping_current_major_changes_family_without_code_change():
    family = VersionFamily(
        prefix="Hy",
        current_major=5,
        lookback=1,
        lookahead=1,
        extra_suffixes=("-preview",),
    )

    assert expand_version_family(family) == [
        "Hy4",
        "Hy5",
        "Hy6",
        "Hy5-preview",
        "Hy6-preview",
    ]


def test_glm_prefix_is_preserved():
    family = VersionFamily(prefix="GLM-", current_major=5, lookback=1, lookahead=1)

    assert expand_version_family(family) == ["GLM-4", "GLM-5", "GLM-6"]


def test_family_tokens_are_ordered_and_deduplicated_with_declared_tokens():
    policy = HarvestPolicy(
        brands={
            "hunyuan": BrandPolicy(
                nickname="hunyuan",
                paths=frozenset({"bare"}),
                tokens=("Hunyuan", "Hy4"),
                version_family=VersionFamily(
                    prefix="Hy", current_major=4, lookback=1, lookahead=1
                ),
            )
        }
    )

    assert primary_keywords_from_policy(policy)["hunyuan"] == [
        "Hunyuan",
        "Hy4",
        "Hy3",
        "Hy5",
    ]


def test_one_family_expander_feeds_b1_and_c_pack_tokens():
    family = VersionFamily(
        prefix="Hy",
        current_major=4,
        lookback=1,
        lookahead=1,
        extra_suffixes=("-preview",),
    )
    policy = HarvestPolicy(
        brands={
            "hunyuan": BrandPolicy(
                nickname="hunyuan",
                paths=frozenset({"bare", "co"}),
                tokens=("Hunyuan",),
                co=("llm",),
                version_family=family,
            )
        },
        co_packs=(CoPack(brand_nicknames=("hunyuan",)),),
    )

    specs = specs_from_policy(policy)
    b1 = next(spec for spec in specs if spec.call_id == "B1")
    c1 = next(spec for spec in specs if spec.call_id == "C1")

    expected = ["Hunyuan", "Hy3", "Hy4", "Hy5", "Hy4-preview", "Hy5-preview"]
    assert primary_keywords_from_policy(policy)["hunyuan"] == expected
    assert c1.brands["hunyuan"] == expected
    assert "hunyuan" in b1.wide_net_brands

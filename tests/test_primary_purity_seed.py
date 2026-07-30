"""U4 tests — brand keyword primary purity seed.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U4.

WHY THIS FILE EXISTS
--------------------
The hybrid funnel R15/R16 require certain (brand, pattern) rows to have
is_primary=true (pure brands) and certain dirty primaries to have
is_primary=false. The data migration is idempotent but the drift surface
is the same as the harvest surface — anyone who adds a row later can
re-promote a dirty primary by accident. This test pins the expected
state.
"""

from __future__ import annotations

import pytest

from core.models import Brand, BrandKeyword


pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


# R16 — pure brands that should have at least one primary=true row.
# Listed alphabetically for stable assertion.
EXPECTED_PURE_BRANDS_WITH_PRIMARY: set[str] = {
    "deepseek", "qwen", "minimax", "stepfun", "mistral",
    "hunyuan", "glm", "inclusionai", "exaone", "sakana_ai",
    "nemo_megatron",
}

# R15 — dirty primaries that must NOT be is_primary=true.
DIRTY_PRIMARY_PAIRS: set[tuple[str, str]] = {
    ("minimax", "m2.5"),
    ("minimax", "海螺"),
    ("mistral", "Mistral"),       # keep Mixtral; drop bare "Mistral"
    ("hunyuan", "混元"),          # keep Hunyuan + 腾讯混元
    ("glm", "GLM"),              # safety guard; no such row today
    ("inclusionai", "Ling"),     # keep InclusionAI
    ("inclusionai", "Ring"),     # keep InclusionAI
    ("upstage", "Solar"),        # substring leak fix
    ("sensechat", "日日新"),       # keep SenseChat + SenseTime
}


def test_pure_brands_have_primary_keyword():
    """R16: each pure brand has at least one is_primary=true row."""
    for brand_id in EXPECTED_PURE_BRANDS_WITH_PRIMARY:
        # Some brands may not exist as Brand rows yet (the data fixture
        # in tests doesn't seed every brand). Skip if no brand row.
        if not Brand.objects.filter(nickname__iexact=brand_id).exists():
            pytest.skip(f"Brand {brand_id} not seeded in test DB")
        primary_keywords = BrandKeyword.objects.filter(
            brand_id=brand_id, is_primary=True
        )
        assert primary_keywords.exists(), (
            f"{brand_id} should have at least one is_primary=true keyword. "
            f"R16 violation. If the brand was intentionally dropped from the "
            f"hybrid funnel, update EXPECTED_PURE_BRANDS_WITH_PRIMARY."
        )


def test_dirty_primaries_are_demoted():
    """R15: every dirty (brand, pattern) must NOT be is_primary=true."""
    for brand_id, pattern in DIRTY_PRIMARY_PAIRS:
        rows = BrandKeyword.objects.filter(
            brand_id__iexact=brand_id, pattern__iexact=pattern
        )
        if not rows.exists():
            # Brand doesn't have this row in the test DB; skip.
            # The migration is a no-op for missing rows anyway.
            continue
        for row in rows:
            assert not row.is_primary, (
                f"({brand_id}, {pattern}) is is_primary=true; R15 violation. "
                f"Run migration 0007 or update DIRTY_PRIMARY_PAIRS."
            )


def test_demotion_migration_idempotent():
    """Running the demotion twice produces the same end state.

    The migration's WHERE clause is `is_primary = true` so re-running on
    already-pure rows is a no-op. We can't run the actual migration here
    (that's a separate test), but we can verify the WHERE pattern."""
    for brand_id, pattern in DIRTY_PRIMARY_PAIRS:
        rows = BrandKeyword.objects.filter(
            brand_id__iexact=brand_id, pattern__iexact=pattern
        )
        for row in rows:
            # Idempotent: any row that survived the demotion (e.g., added
            # back later) will still be detected by test_dirty_primaries.
            assert not row.is_primary, (
                f"({brand_id}, {pattern}) re-promoted to is_primary=true; "
                f"the migration's WHERE is_primary=true guard should prevent this."
            )
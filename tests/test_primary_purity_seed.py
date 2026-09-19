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

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.db import connection

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


@pytest.fixture(autouse=True)
def seeded_primary_purity_contract():
    """Load the checked-in keyword seed and apply the real purity migration."""
    seed_path = Path(__file__).resolve().parents[1] / "data" / "brand_keywords.json"
    rows = json.loads(seed_path.read_text(encoding="utf-8"))

    for brand_id in {row["brand_id"] for row in rows}:
        Brand.objects.get_or_create(
            nickname=brand_id,
            defaults={"display_name": brand_id},
        )
    for row in rows:
        BrandKeyword.objects.update_or_create(
            brand_id=row["brand_id"],
            pattern=row["pattern"],
            defaults={
                "is_primary": bool(row["is_primary"]),
                "is_regex": bool(row["is_regex"]),
            },
        )

    migration = importlib.import_module(
        "core.migrations.0007_brand_keyword_primary_purity"
    )
    schema_editor = SimpleNamespace(connection=connection)
    migration._demote_dirty_primarys(None, schema_editor)
    return migration, schema_editor


def test_pure_brands_have_primary_keyword():
    """R16: each pure brand has at least one is_primary=true row."""
    for brand_id in EXPECTED_PURE_BRANDS_WITH_PRIMARY:
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
            brand_id=brand_id, pattern__iexact=pattern
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


def test_demotion_migration_idempotent(seeded_primary_purity_contract):
    """Running the real demotion twice produces the same database state."""
    migration, schema_editor = seeded_primary_purity_contract
    before = list(
        BrandKeyword.objects.order_by("brand_id", "pattern").values_list(
            "brand_id", "pattern", "is_primary", "is_regex"
        )
    )

    migration._demote_dirty_primarys(None, schema_editor)

    after = list(
        BrandKeyword.objects.order_by("brand_id", "pattern").values_list(
            "brand_id", "pattern", "is_primary", "is_regex"
        )
    )
    assert after == before

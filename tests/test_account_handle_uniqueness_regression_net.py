"""U9 regression net - pin the accounts surface BEFORE the reconciliation.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U9.

WHY THIS FILE EXISTS
--------------------
The reconciliation half of the combined plan (U10-U14) collapses 2,142
duplicate handle groups in `accounts`, repoints ~25K FK rows from
placeholder author_ids (`handle:*`, `synthetic:*`) to canonical integer
author_ids, and adds a `LOWER(handle)` unique index so future drift is
impossible.

This file pins the BEFORE state so U10's apply can be verified against
known-good baseline numbers. After U13 the assertions flip to AFTER
state with a drift detector.

Pre-flight numbers (live audit on 2026-07-30):
  duplicate_handle_groups = 2142
  posts_at_placeholder    = 20079
  apa_at_placeholder      = 6803
  brands_at_placeholder   = 95
  companies_at_placeholder = 0

NOTE: these tests verify against the LIVE shadow DB. They are SKIPPED
when pytest runs against a fresh test DB (which has 0 rows). To run:
  DATABASE_URL=postgres://...pushinweight_shadow... pytest this_file
"""

from __future__ import annotations

import os

import pytest
from django.db import connection
from django.db.models import Count

from core.models import Account, Post, AccountPostAppearance, BrandAccount, CompanyAccount


# These tests verify against the LIVE shadow DB. We deliberately do NOT
# use the `django_db` marker's test-DB-creation behavior (which strips
# the ICU `case_insensitive` collation). Instead we connect to whatever
# DATABASE_URL points at. The live shadow DB has ~19K accounts; a
# fresh test DB has 0 — the guard in each test catches that and skips.
pytestmark = [pytest.mark.django_db(transaction=True)]


LIVE_SHADOW_MARKER = "pushinweight_shadow"


def _is_live_shadow_db() -> bool:
    db = os.environ.get("DATABASE_URL", "")
    return LIVE_SHADOW_MARKER in db


def _skip_if_not_live_shadow():
    if not _is_live_shadow_db():
        pytest.skip(
            "Test requires DATABASE_URL pointing at the live pushinweight_shadow "
            "DB (the row counts are pinned to the 2026-07-30 audit, not a "
            "fresh test DB)."
        )
    # Even when DATABASE_URL matches, Django's test runner may have
    # created a fresh `test_pushinweight_shadow` DB. Detect via row
    # count: the live DB has ~19K accounts; a fresh DB has 0.
    try:
        actual = Account.objects.count()
    except Exception as exc:
        pytest.skip(f"Could not query Account table: {type(exc).__name__}: {exc}")
    if actual < 100:
        pytest.skip(
            f"DB appears empty ({actual} accounts). Tests pin to the live "
            f"pushinweight_shadow DB (~19K accounts); pytest created a fresh "
            f"test DB. Run against the live shadow DB explicitly: "
            f"DATABASE_URL=postgres://...pushinweight_shadow... pytest"
        )


# Pinned BEFORE-state values (live at plan-write time, 2026-07-30).
# Update only when the plan body explicitly re-baselines.
EXPECTED_DUPES_AT_PLAN_TIME: int = 2142
EXPECTED_POSTS_AT_PLACEHOLDERS: int = 20079
EXPECTED_APPEARANCES_AT_PLACEHOLDERS: int = 6803
EXPECTED_BRANDS_AT_PLACEHOLDERS: int = 95
EXPECTED_COMPANIES_AT_PLACEHOLDERS: int = 0
EXPECTED_ACCOUNTS_TOTAL: int = 19284
EXPECTED_INTEGER_AUTHOR_IDS: int = 5776
EXPECTED_HANDLE_PREFIX_AUTHOR_IDS: int = 11964
EXPECTED_SYNTHETIC_PREFIX_AUTHOR_IDS: int = 1522


def test_duplicate_handle_groups():
    _skip_if_not_live_shadow()
    """BEFORE: 2,142 handle groups with multiple accounts (case-insensitive)."""
    qs = (
        Account.objects
        .exclude(handle__isnull=True)
        .exclude(handle="")
        .values("handle")
        .annotate(n=Count("author_id"))
        .filter(n__gt=1)
    )
    actual = qs.count()
    assert actual == EXPECTED_DUPES_AT_PLAN_TIME, (
        f"Duplicate handle group count drifted: expected "
        f"{EXPECTED_DUPES_AT_PLAN_TIME}, got {actual}. "
        f"Update EXPECTED_DUPES_AT_PLAN_TIME or investigate."
    )


def test_posts_at_placeholder_author_ids():
    _skip_if_not_live_shadow()
    """BEFORE: 20,079 posts point at placeholder (`handle:*`, `synthetic:*`) accounts."""
    count = (
        Post.objects
        .filter(author_id__regex=r"^(handle:|synthetic:)")
        .count()
    )
    assert count == EXPECTED_POSTS_AT_PLACEHOLDERS, (
        f"Posts at placeholder author_ids drifted: expected "
        f"{EXPECTED_POSTS_AT_PLACEHOLDERS}, got {count}."
    )


def test_apa_at_placeholder_author_ids():
    _skip_if_not_live_shadow()
    """BEFORE: 6,803 account_post_appearances at placeholders."""
    count = (
        AccountPostAppearance.objects
        .filter(author_id__regex=r"^(handle:|synthetic:)")
        .count()
    )
    assert count == EXPECTED_APPEARANCES_AT_PLACEHOLDERS, (
        f"APAs at placeholder drifted: expected "
        f"{EXPECTED_APPEARANCES_AT_PLACEHOLDERS}, got {count}."
    )


def test_brands_at_placeholder_author_ids():
    _skip_if_not_live_shadow()
    """BEFORE: 95 brands_accounts at placeholders."""
    count = (
        BrandAccount.objects
        .filter(accounts_id__regex=r"^(handle:|synthetic:)")
        .count()
    )
    assert count == EXPECTED_BRANDS_AT_PLACEHOLDERS, (
        f"brands_accounts at placeholder drifted: expected "
        f"{EXPECTED_BRANDS_AT_PLACEHOLDERS}, got {count}."
    )


def test_companies_at_placeholder_author_ids():
    _skip_if_not_live_shadow()
    """BEFORE: 0 companies_accounts at placeholders (audit pin)."""
    count = (
        CompanyAccount.objects
        .filter(author_id__regex=r"^(handle:|synthetic:)")
        .count()
    )
    assert count == EXPECTED_COMPANIES_AT_PLACEHOLDERS, (
        f"companies_accounts at placeholder drifted: expected "
        f"{EXPECTED_COMPANIES_AT_PLACEHOLDERS}, got {count}."
    )


def test_total_accounts():
    _skip_if_not_live_shadow()
    """BEFORE: 19,284 total accounts (so a wholesale wipe is caught)."""
    actual = Account.objects.count()
    assert actual == EXPECTED_ACCOUNTS_TOTAL, (
        f"Total accounts drifted: expected {EXPECTED_ACCOUNTS_TOTAL}, "
        f"got {actual}."
    )


def test_integer_author_ids_count():
    _skip_if_not_live_shadow()
    """BEFORE: 5,776 accounts have an integer author_id."""
    actual = (
        Account.objects
        .filter(author_id__regex=r"^[0-9]+$")
        .count()
    )
    assert actual == EXPECTED_INTEGER_AUTHOR_IDS, (
        f"Integer-author_id count drifted: expected "
        f"{EXPECTED_INTEGER_AUTHOR_IDS}, got {actual}."
    )


def test_handle_prefix_count():
    _skip_if_not_live_shadow()
    """BEFORE: 11,964 accounts have a `handle:*` author_id."""
    actual = Account.objects.filter(author_id__startswith="handle:").count()
    assert actual == EXPECTED_HANDLE_PREFIX_AUTHOR_IDS, (
        f"handle: prefix count drifted: expected "
        f"{EXPECTED_HANDLE_PREFIX_AUTHOR_IDS}, got {actual}."
    )


def test_synthetic_prefix_count():
    _skip_if_not_live_shadow()
    """BEFORE: 1,522 accounts have a `synthetic:*` author_id (one-shot
    2026-06-19 bulk seed; never re-inserted)."""
    actual = Account.objects.filter(author_id__startswith="synthetic:").count()
    assert actual == EXPECTED_SYNTHETIC_PREFIX_AUTHOR_IDS, (
        f"synthetic: prefix count drifted: expected "
        f"{EXPECTED_SYNTHETIC_PREFIX_AUTHOR_IDS}, got {actual}."
    )


def test_no_handle_unique_index_before():
    _skip_if_not_live_shadow()
    """BEFORE: the `LOWER(handle)` partial unique index does NOT yet exist.
    U11 creates it AFTER U10 reduces dupes to ≤ 1 per handle."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'accounts'
                  AND indexname = 'uniq_accounts_handle_lower'
            )
        """)
        exists = cur.fetchone()[0]
    assert not exists, (
        "uniq_accounts_handle_lower should NOT exist before U11. "
        "If this is failing, the index already shipped."
    )
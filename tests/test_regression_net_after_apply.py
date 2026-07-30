"""U14 regression net - pin the accounts surface AFTER Phase 2 partial apply.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U14.

The reconciliation collapsed 2,142 handle groups in `accounts` down to
29 (residual TwitterAPI 404 dead-letters). The Phase 2 partial apply
resolved 226 of 10,907 lonely placeholders before the aiohttp pre-pass
hit TwitterAPI rate limits and the apply was stopped to avoid further
DB drift. The remaining 10,681 lonely placeholders are DEFERRED.

AFTER-state values (pinned 2026-07-30 after partial Phase 2 apply):
  duplicate_handle_groups    = 29 (residual TwitterAPI 404 dead-letters)
  posts_at_placeholder       = 13667
  apa_at_placeholder         = 4780
  brands_at_placeholder      = 15
  companies_at_placeholder   = 0
  total_accounts             = 17059
  integer_author_ids         = 6356
  placeholder_rows           = 10681 (10,681 lonely placeholders DEFERRED)

The unique index `uniq_accounts_handle_lower` does NOT exist (U12
deferred -- the migration precheck refuses until dup_groups = 0).

NOTE: these tests verify against the LIVE shadow DB. They are SKIPPED
when pytest runs against a fresh test DB (which has 0 rows). To run:
  DATABASE_URL=postgres://...pushinweight_shadow... pytest
  tests/test_regression_net_after_apply.py
"""

from __future__ import annotations

import os

import pytest
from django.db import connection
from django.db.models import Count

from core.models import Account, Post, AccountPostAppearance, BrandAccount, CompanyAccount


pytestmark = [pytest.mark.django_db(transaction=True)]


LIVE_SHADOW_MARKER = "pushinweight_shadow"


def _is_live_shadow_db() -> bool:
    db = os.environ.get("DATABASE_URL", "")
    return LIVE_SHADOW_MARKER in db


def _skip_if_not_live_shadow():
    if not _is_live_shadow_db():
        pytest.skip(
            "Test requires DATABASE_URL pointing at the live pushinweight_shadow "
            "DB (the row counts are pinned to the post-Phase-2 audit)."
        )
    try:
        actual = Account.objects.count()
    except Exception as exc:
        pytest.skip(f"Could not query Account table: {type(exc).__name__}: {exc}")
    if actual < 100:
        pytest.skip(f"DB appears empty ({actual} accounts).")


EXPECTED_DUPES_AT_PLAN_TIME: int = 29
EXPECTED_POSTS_AT_PLACEHOLDERS: int = 13667
EXPECTED_APPEARANCES_AT_PLACEHOLDERS: int = 4780
EXPECTED_BRANDS_AT_PLACEHOLDERS: int = 15
EXPECTED_COMPANIES_AT_PLACEHOLDERS: int = 0
EXPECTED_ACCOUNTS_TOTAL: int = 17059
EXPECTED_INTEGER_AUTHOR_IDS: int = 6356
EXPECTED_PLACEHOLDER_ROWS: int = 10681


def test_duplicate_handle_groups():
    _skip_if_not_live_shadow()
    """AFTER: 29 dead-lettered residual groups (TwitterAPI 404)."""
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
    """AFTER: 13,667 posts point at placeholder rows."""
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
    """AFTER: 4,780 account_post_appearances at placeholders."""
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
    """AFTER: 15 brands_accounts at placeholders."""
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
    """AFTER: 0 companies_accounts at placeholders."""
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
    """AFTER: 17,059 total accounts."""
    actual = Account.objects.count()
    assert actual == EXPECTED_ACCOUNTS_TOTAL, (
        f"Total accounts drifted: expected {EXPECTED_ACCOUNTS_TOTAL}, "
        f"got {actual}."
    )


def test_integer_author_ids_count():
    _skip_if_not_live_shadow()
    """AFTER: 6,356 integer author_ids."""
    actual = (
        Account.objects
        .filter(author_id__regex=r"^[0-9]+$")
        .count()
    )
    assert actual == EXPECTED_INTEGER_AUTHOR_IDS, (
        f"Integer-author_id count drifted: expected "
        f"{EXPECTED_INTEGER_AUTHOR_IDS}, got {actual}."
    )


def test_placeholder_rows_count():
    _skip_if_not_live_shadow()
    """AFTER: 10,681 placeholder rows (DEFERRED — not yet canonicalized)."""
    actual = (
        Account.objects
        .filter(author_id__regex=r"^(handle:|synthetic:)")
        .count()
    )
    assert actual == EXPECTED_PLACEHOLDER_ROWS, (
        f"Placeholder rows drifted: expected "
        f"{EXPECTED_PLACEHOLDER_ROWS}, got {actual}."
    )


def test_placeholder_drift_after_phase_2():
    """AFTER: no new placeholder rows from first_seen_at > 2026-07-30T11:15.

    Drift detector: any brand-seeding or harvest code path that
    re-introduces a placeholder row AFTER the partial Phase 2 apply
    should fail this test.
    """
    _skip_if_not_live_shadow()
    cutoff = "2026-07-30T11:15:00Z"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM accounts
            WHERE (author_id LIKE 'handle:%%' OR author_id LIKE 'synthetic:%%')
              AND first_seen_at > %s
            """,
            (cutoff,),
        )
        new_placeholder_count = cur.fetchone()[0]
    assert new_placeholder_count == 0, (
        f"Drift detector: {new_placeholder_count} new placeholder rows "
        f"created at first_seen_at > {cutoff}."
    )


def test_unique_index_NOT_yet_shipped():
    """AFTER (Phase 2 partial): the unique index does NOT exist yet.

    U12 cannot ship because 10,681 lonely placeholders still exist.
    The migration's precheck refuses until dup_groups = 0.
    """
    _skip_if_not_live_shadow()
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
        "uniq_accounts_handle_lower should NOT exist yet. "
        "Phase 2 left the index deferred."
    )

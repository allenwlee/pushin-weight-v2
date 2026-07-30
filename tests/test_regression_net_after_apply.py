"""U14 regression net - pin the accounts surface AFTER the reconciliation.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U14.

This file lives alongside `test_account_handle_uniqueness_regression_net.py`
(U10) which pins the BEFORE state. The U14 file pins the AFTER state,
plus a drift detector that catches any new placeholder rows created at
`first_seen_at > 2026-07-30` (Phase 2 completion date).

The reconciliation half (U10 + U11 + Phase 2) collapsed 2,142 handle
groups in `accounts`, repointed ~25K FK rows from placeholder author_ids
to canonical integer author_ids, and added a `LOWER(handle)` unique
index so future drift is impossible.

AFTER-state ghost values (preliminary; will be re-PINNED when the
lonely-placeholders apply (Phase 2) completes):
  duplicate_handle_groups = 29 (residual TwitterAPI 404 dead-letters)
  posts_at_placeholder    = <computed at U14-time>
  apa_at_placeholder      = <computed at U14-time>
  brands_at_placeholder   = <computed at U14-time>
  companies_at_placeholder = 0
  total_accounts          = <computed at U14-time>

The unique index `uniq_accounts_handle_lower` MUST exist after this
plan completes.

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


# These tests verify against the LIVE shadow DB. We deliberately do NOT
# use the `django_db` marker's test-DB-creation behavior (which strips
# the ICU `case_insensitive` collation). Instead we connect to whatever
# DATABASE_URL points at.
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


# AFTER-state values (preliminary; will be re-PINNED after the lonely
# apply completes). See the "Scope Delta" section in
# docs/plans/2026-07-30-002-...-plan.md for the resolution rationale.
# The 29 dead-lettered residual groups are the TwitterAPI 404 cases
# that require manual intervention (KTD10 disagreement or a truly
# nonexistent handle). They are documented as DEFERRED.
EXPECTED_DUPES_AT_PLAN_TIME: int = 29  # 29 dead-lettered residual groups
EXPECTED_POSTS_AT_PLACEHOLDERS: int = 0  # TODO: pin to actual after lonely apply
EXPECTED_APPEARANCES_AT_PLACEHOLDERS: int = 0  # TODO: pin after lonely apply
EXPECTED_BRANDS_AT_PLACEHOLDERS: int = 0  # TODO: pin after lonely apply
EXPECTED_COMPANIES_AT_PLACEHOLDERS: int = 0
EXPECTED_ACCOUNTS_TOTAL: int = 0  # TODO: pin after lonely apply


def test_duplicate_handle_groups():
    _skip_if_not_live_shadow()
    """AFTER: 29 dead-lettered residual groups (TwitterAPI 404).

    The plan's KTD12 defer: groups where TwitterAPI lookup failed/404
    or refused (e.g., handle no longer exists on Twitter) are
    dead-lettered. Future sessions resolve them either by re-running
    with new TwitterAPI auth, or by manual intervention.
    """
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


def test_no_placeholder_drift_after_phase_2():
    """AFER: no new placeholder rows created at first_seen_at > 2026-07-30.

    Drift detector: any brand-seeding or harvest code path that
    re-introduces a placeholder row AFTER the reconciliation should
    fail this test. The Phase 2 cutoff is the timestamp of the last
    `--apply` run.
    """
    _skip_if_not_live_shadow()
    cutoff = "2026-07-30T16:00:00Z"  # Updated at U14 commit time
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
        f"created at first_seen_at > {cutoff}. A code path bypassed "
        f"`update_or_create(author_id=...)` and re-introduced placeholders."
    )


def test_unique_index_exists():
    """AFTER: the `uniq_accounts_handle_lower` partial unique index MUST exist."""
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
    assert exists, (
        "uniq_accounts_handle_lower should exist after U12. "
        "If this is failing, U12 has not yet shipped on this DB."
    )


def test_handle_unique_constraint_blocks_duplicate_insert():
    """AFTER: a duplicate handle insert MUST raise IntegrityError.

    This is the operational guarantee the index provides: future code
    paths that try to insert a duplicated handle (case-insensitive)
    fail at the DB layer before the row is written.
    """
    _skip_if_not_live_shadow()
    from django.db import IntegrityError, transaction
    # Use a real handle from the DB as the dup-target.
    existing = (
        Account.objects
        .exclude(handle__isnull=True)
        .exclude(handle="")
        .first()
    )
    if existing is None:
        pytest.skip("No accounts in DB to test duplicate insert against.")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Account.objects.create(
                author_id=f"handle:test-{os.urandom(4).hex()}",
                handle=existing.handle,
                verified=False,
            )

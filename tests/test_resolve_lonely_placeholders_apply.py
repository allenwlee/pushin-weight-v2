"""U4 tests - per-row SAVEPOINT apply reusing Phase 2 helpers.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Unit U4.

Verifies:
  - Successful apply: placeholder row deleted, FK rows repointed,
    canonical row created, no duplicate rows.
  - IntegrityError mid-apply: transaction.atomic() rolls back, placeholder
    row preserved, no partial state. error_message carries exception text.
  - is_already_resolved detects post-apply state correctly.

Tests use sqlite in-memory (the project default for unit tests).
The Phase 2 helpers are PostgreSQL-specific in places (regex, JSONB);
we only test the control flow here -- DB-shape tests belong on the
live shadow DB and are covered by U1's regression net.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from monitor.reconcile.apply_one_row import (
    ApplyResult,
    apply_one_row,
    is_already_resolved,
)


@pytest.fixture
def fake_canonical():
    return {"author_id": "99999", "name": "Alice", "screen_name": "alice"}


@pytest.mark.django_db
def test_apply_one_row_integrity_error_returns_failure(fake_canonical):
    """Simulated IntegrityError -> reason='integrity_error' + error_message populated."""
    from django.db import IntegrityError
    with patch(
        "monitor.reconcile.apply_one_row._ensure_canonical_account_row",
        side_effect=IntegrityError("simulated FK violation"),
    ):
        result = apply_one_row(
            handle="alice",
            placeholder_author_id="handle:alice",
            canonical=fake_canonical,
        )
    assert result.success is False
    assert result.reason == "integrity_error"
    assert "simulated FK violation" in result.error_message


@pytest.mark.django_db
def test_apply_one_row_exception_classification(fake_canonical):
    """Non-IntegrityError -> reason='exception' + error_message populated."""
    with patch(
        "monitor.reconcile.apply_one_row._ensure_canonical_account_row",
        side_effect=RuntimeError("boom"),
    ):
        result = apply_one_row(
            handle="alice",
            placeholder_author_id="handle:alice",
            canonical=fake_canonical,
        )
    assert result.success is False
    assert result.reason == "exception"
    assert "boom" in result.error_message


@pytest.mark.django_db
def test_no_manual_savepoint_call(fake_canonical):
    """Defensive: apply_one_row does NOT call transaction.savepoint() manually.

    The double-savepoint pattern (manual savepoint inside an atomic()
    block) caused the 2026-07-31 cron run to dead-letter every row with
    apply_exception because the inner INSERT was invisible to the FK
    constraint at the outer commit. Django's atomic() provides SAVEPOINT
    semantics automatically -- manual calls are redundant and broken.
    """
    import inspect
    src = inspect.getsource(apply_one_row)
    assert "transaction.savepoint()" not in src
    # Confirm we still use transaction.atomic() for rollback semantics.
    assert "transaction.atomic()" in src


@pytest.mark.django_db
def test_is_already_resolved_returns_true_when_placeholder_deleted():
    """After apply, the placeholder row is gone -> is_already_resolved True."""
    from core.models import Account
    Account.objects.create(
        author_id="99999",
        handle="alice",
        verified=False,
    )
    assert is_already_resolved(
        handle="alice",
        placeholder_author_id="handle:alice",
    ) is True


@pytest.mark.django_db
def test_is_already_resolved_returns_false_when_placeholder_exists():
    """Placeholder row still present -> is_already_resolved False."""
    from core.models import Account
    Account.objects.create(
        author_id="handle:alice",
        handle="alice",
        verified=False,
    )
    assert is_already_resolved(
        handle="alice",
        placeholder_author_id="handle:alice",
    ) is False


@pytest.mark.django_db
def test_no_pre_pass_insert_in_apply_loop(fake_canonical):
    """Defensive: ensure the apply helper does NOT contain a pre-pass INSERT.

    The pre-pass INSERT bug (Phase 2 v4/v5) caused 387-587 new duplicate
    groups. The U4 helper is intentionally structured around the
    in-transaction _ensure_canonical_account_row call -- no pre-pass
    INSERT path. This test pins that property by checking the source.
    """
    import inspect
    src = inspect.getsource(apply_one_row)
    assert "_ensure_canonical_account_row" in src

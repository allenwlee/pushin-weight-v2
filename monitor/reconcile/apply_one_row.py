"""U4 - per-row SAVEPOINT apply reusing Phase 2 helpers.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Unit U4.

`apply_one_row` wraps `_ensure_canonical_account_row` + `_repoint_fk`
from Phase 2 inside a single transaction.atomic() + SAVEPOINT so a
mid-row crash leaves zero residue (the outer transaction is open only
for the duration of one row's apply, ~50ms).

NO pre-pass INSERT of canonical rows (Phase 2 v4/v5 bug -- created
387-587 new duplicate groups). The existing `_ensure_canonical_account_row`
already handles the right KTD10 semantics; the apply INSERT happens
inside the same SAVEPOINT as the placeholder DELETE, so concurrent
readers never see a double-row state.

The apply helper is exposed as `apply_one_row` so U6 can test
mid-apply crash recovery.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import IntegrityError, connection, transaction

from monitor.management.commands.reconcile_account_duplicates import (
    _ensure_canonical_account_row,
    _repoint_fk,
)


log = logging.getLogger(__name__)


class ApplyResult:
    """Per-row apply outcome. Mirrors `LookupResult` shape for symmetry."""

    def __init__(
        self,
        *,
        handle: str,
        placeholder_author_id: str,
        success: bool,
        canonical_author_id: str | None = None,
        row_counts: dict[str, int] | None = None,
        reason: str | None = None,
    ):
        self.handle = handle
        self.placeholder_author_id = placeholder_author_id
        self.success = success
        self.canonical_author_id = canonical_author_id
        self.row_counts = row_counts or {}
        self.reason = reason  # None on success; "integrity_error" / "exception" on failure


def apply_one_row(
    *,
    handle: str,
    placeholder_author_id: str,
    canonical: dict,
) -> ApplyResult:
    """Apply one lonely placeholder resolution inside a SAVEPOINT.

    Steps (all inside one transaction.atomic() with a SAVEPOINT):
      1. _ensure_canonical_account_row -- INSERT the canonical row if
         missing (KTD10-correct semantics; no pre-pass bug).
      2. _repoint_fk -- UPDATE posts / apa / brands_accounts to point
         at the canonical integer, then DELETE the placeholder row.
      3. SAVEPOINT commit on success; SAVEPOINT rollback on
         IntegrityError or any other exception (the placeholder row
         stays, the apply is dead-lettered).

    Returns an ApplyResult. On success: `success=True`,
    `canonical_author_id` set. On IntegrityError: `success=False`,
    `reason="integrity_error"`. On any other exception:
    `success=False`, `reason="exception"` (the SAVEPOINT already
    rolled back so the DB is clean).
    """
    canonical_author_id = str(canonical["author_id"])
    row_counts: dict[str, int] = {}

    try:
        with transaction.atomic():
            sid = transaction.savepoint()
            try:
                # Step 1: ensure canonical row exists in accounts.
                # No-op if a row with this author_id already exists
                # (handles prior-run partial state). Pass integer_ids
                # as the KTD10 disagreement guard.
                _ensure_canonical_account_row(
                    connection.cursor(),
                    canonical=canonical_author_id,
                    handle=handle,
                    integer_ids=[canonical_author_id],
                )

                # Step 2: UPDATE-then-DELETE per FK table.
                row_counts = _repoint_fk(
                    connection.cursor(),
                    canonical=canonical_author_id,
                    placeholder_ids=[placeholder_author_id],
                    handle=handle,
                )
                transaction.savepoint_commit(sid)
                return ApplyResult(
                    handle=handle,
                    placeholder_author_id=placeholder_author_id,
                    success=True,
                    canonical_author_id=canonical_author_id,
                    row_counts=row_counts,
                )
            except IntegrityError as exc:
                transaction.savepoint_rollback(sid)
                log.warning(
                    "apply_one_row IntegrityError handle=%s placeholder=%s exc=%s",
                    handle, placeholder_author_id, exc,
                )
                return ApplyResult(
                    handle=handle,
                    placeholder_author_id=placeholder_author_id,
                    success=False,
                    reason="integrity_error",
                )
            except Exception as exc:
                transaction.savepoint_rollback(sid)
                log.warning(
                    "apply_one_row exception handle=%s placeholder=%s exc=%s",
                    handle, placeholder_author_id, exc,
                )
                return ApplyResult(
                    handle=handle,
                    placeholder_author_id=placeholder_author_id,
                    success=False,
                    reason="exception",
                )
    except Exception as exc:
        # Outer atomic() failure -- a DB-level issue (connection drop,
        # pool exhaustion). The inner SAVEPOINT already rolled back,
        # but the outer transaction may be in a bad state. The cron
        # will retry on the next tick.
        log.error(
            "apply_one_row outer failure handle=%s exc=%s",
            handle, exc,
        )
        return ApplyResult(
            handle=handle,
            placeholder_author_id=placeholder_author_id,
            success=False,
            reason="exception",
        )


def is_already_resolved(
    *,
    handle: str,
    placeholder_author_id: str,
) -> bool:
    """True if the placeholder row no longer exists (already resolved).

    Used by U6's re-entrancy test to confirm a fresh run picks up
    exactly where the prior crashed run stopped.
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM accounts WHERE author_id = %s LIMIT 1",
            (placeholder_author_id,),
        )
        return cur.fetchone() is None
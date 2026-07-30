"""U4 - per-row SAVEPOINT apply reusing Phase 2 helpers.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Unit U4.

`apply_one_row` wraps `_ensure_canonical_account_row` + `_repoint_fk`
from Phase 2 inside a single `transaction.atomic()`. Django's atomic()
provides the SAVEPOINT semantics automatically -- a nested
`transaction.savepoint()` inside an atomic block creates a
double-nested savepoint which DOES NOT preserve the INSERT visibility
across the inner UPDATEs (the 2026-07-31 cron run observed this with
FK constraint failures on commit: "posts_author_id ... is not present
in table accounts" because the canonical-row INSERT happened inside
one savepoint scope while the repoint UPDATE happened inside the
nested scope).

Fix: rely on `transaction.atomic()` alone. On IntegrityError the whole
block rolls back (no double-savepoint). On any other exception, same.

CRITICAL: pass integer_ids=[] (NOT [canonical_author_id]) to
_ensure_canonical_account_row. That helper has a defensive check
`if canonical in integer_ids: return canonical` that returns WITHOUT
inserting. The lonely-apply path has no separate group context, so
passing the canonical in integer_ids triggers the short-circuit every
time. The original reconcile path avoided this bug because it passed
integer_ids from _classify_group with the GROUP's integer list, not
just the canonical. The 2026-07-31 cron incident was triggered by
this defensive-check bug.

NO pre-pass INSERT of canonical rows (Phase 2 v4/v5 bug -- created
387-587 new duplicate groups). The existing `_ensure_canonical_account_row`
already handles the right KTD10 semantics; the apply INSERT happens
inside the same atomic() as the placeholder DELETE, so concurrent
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
        error_message: str | None = None,
    ):
        self.handle = handle
        self.placeholder_author_id = placeholder_author_id
        self.success = success
        self.canonical_author_id = canonical_author_id
        self.row_counts = row_counts or {}
        self.reason = reason  # None on success; "integrity_error" / "exception" on failure
        self.error_message = error_message  # last 200 chars of exception text


def apply_one_row(
    *,
    handle: str,
    placeholder_author_id: str,
    canonical: dict,
) -> ApplyResult:
    """Apply one lonely placeholder resolution inside transaction.atomic().

    Steps (all inside one transaction.atomic()):
      1. _ensure_canonical_account_row -- INSERT the canonical row if
         missing (KTD10-correct semantics; no pre-pass bug).
      2. _repoint_fk -- UPDATE posts / apa / brands_accounts to point
         at the canonical integer, then DELETE the placeholder row.

    On IntegrityError (e.g. brands_accounts_pkey collision, FK
    constraint failure): transaction.atomic() rolls back automatically;
    return success=False, reason="integrity_error", error_message=<text>.
    On any other exception: same rollback, reason="exception".

    Returns an ApplyResult.
    """
    canonical_author_id = str(canonical["author_id"])

    try:
        with transaction.atomic():
            # Step 1: ensure canonical row exists in accounts.
            # NOTE: pass integer_ids=[] -- see module docstring.
            _ensure_canonical_account_row(
                connection.cursor(),
                canonical=canonical_author_id,
                handle=handle,
                integer_ids=[],
            )

            # Step 2: UPDATE-then-DELETE per FK table.
            row_counts = _repoint_fk(
                connection.cursor(),
                canonical=canonical_author_id,
                placeholder_ids=[placeholder_author_id],
                handle=handle,
            )
            return ApplyResult(
                handle=handle,
                placeholder_author_id=placeholder_author_id,
                success=True,
                canonical_author_id=canonical_author_id,
                row_counts=row_counts,
            )
    except IntegrityError as exc:
        # transaction.atomic() already rolled back.
        log.warning(
            "apply_one_row IntegrityError handle=%s placeholder=%s exc=%s",
            handle, placeholder_author_id, exc,
        )
        return ApplyResult(
            handle=handle,
            placeholder_author_id=placeholder_author_id,
            success=False,
            reason="integrity_error",
            error_message=str(exc)[:500],
        )
    except Exception as exc:
        # transaction.atomic() already rolled back.
        log.warning(
            "apply_one_row exception handle=%s placeholder=%s exc=%s",
            handle, placeholder_author_id, exc,
        )
        return ApplyResult(
            handle=handle,
            placeholder_author_id=placeholder_author_id,
            success=False,
            reason="exception",
            error_message=str(exc)[:500],
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
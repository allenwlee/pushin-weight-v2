"""Ordered scope checkpoint history without inferred transport evidence."""

from django.db import transaction

from core.measurement_taxonomy import require
from core.models import CollectionScopeCursorReceipt, CollectionScopeRun


def validate_cursor_history(cursors):
    require(
        type(cursors) is list and all(type(cursor) is str for cursor in cursors),
        "cursor history must be an ordered list of strings",
    )


def scope_cursor_history(scope):
    rows = list(scope.cursor_receipts.order_by("position").values_list(
        "position", "cursor",
    ))
    if rows:
        require(
            [position for position, _ in rows] == list(range(1, len(rows) + 1)),
            "cursor history positions must be contiguous",
        )
        return [cursor for _, cursor in rows]
    # Additive rollout: old images still write the original checkpoint list.
    validate_cursor_history(scope.cursor_history)
    return list(scope.cursor_history)


@transaction.atomic
def replace_scope_cursor_history(scope, cursors):
    """Caller holds its run fence; a deliberate cursor restart may reset state."""
    validate_cursor_history(cursors)
    CollectionScopeRun.objects.select_for_update().get(pk=scope.pk)
    rows = list(scope.cursor_receipts.order_by("position").values_list(
        "position", "cursor",
    ))
    prefix = 0
    for position, cursor in rows:
        if position != prefix + 1 or prefix == len(cursors) or cursor != cursors[prefix]:
            break
        prefix += 1
    scope.cursor_receipts.filter(position__gt=prefix).delete()
    CollectionScopeCursorReceipt.objects.bulk_create([
        CollectionScopeCursorReceipt(scope_run=scope, position=position, cursor=cursor)
        for position, cursor in enumerate(cursors[prefix:], start=prefix + 1)
    ], batch_size=500)

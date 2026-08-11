"""Validated Django persistence for classifier unsanctioned flags.

The legacy SQLite Store remains retired production proof.  This module keeps
the live Django write boundary strict and returns only a bounded, redacted
dead-letter summary; model output and post text never cross that boundary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from core.models import PostUnsanctionedFlag, UnsanctionedFlagKey

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SAFE_FLAG_KEY = re.compile(r"^[a-z0-9_-]{1,64}$")
_REDACTED = "[redacted]"


@dataclass(frozen=True)
class FlagPersistenceResult:
    outcome: str
    known_keys: tuple[str, ...]
    rejected_keys: tuple[str, ...]
    degraded: bool
    dead_letter: dict[str, Any] | None = None


def _safe_identifier(value: Any) -> str:
    candidate = str(value or "")
    return candidate if _SAFE_IDENTIFIER.fullmatch(candidate) else _REDACTED


def _safe_rejected_key(value: Any) -> str:
    if isinstance(value, str) and _SAFE_FLAG_KEY.fullmatch(value):
        return value
    return _REDACTED


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _dead_letter(
    *,
    run_id: str,
    post_id: str,
    known: list[str],
    rejected: list[str],
    reason_code: str,
) -> dict[str, Any]:
    return {
        "run_id": _safe_identifier(run_id),
        "tweet_id": _safe_identifier(post_id),
        "stage": "classifier_flags",
        "known_keys": known[:4],
        "rejected_keys": _dedupe(rejected)[:4],
        "reason_code": reason_code,
    }


def persist_classifier_flags(
    *,
    post_id: str,
    classifier_result: Any,
    run_id: str,
) -> FlagPersistenceResult:
    """Persist one successful classifier flag result.

    Missing/malformed/unknown-only output preserves prior state.  An explicit
    successful empty list is the only condition that deletes an existing row.
    Mixed known/unknown output persists the known subset and returns a minimal
    dead letter for the rejected identifiers.
    """

    if not isinstance(classifier_result, dict) or "unsanctioned_flags" not in classifier_result:
        dead_letter = _dead_letter(
            run_id=run_id,
            post_id=post_id,
            known=[],
            rejected=[],
            reason_code="malformed_result",
        )
        return FlagPersistenceResult(
            outcome="preserved",
            known_keys=(),
            rejected_keys=(),
            degraded=True,
            dead_letter=dead_letter,
        )

    raw_flags = classifier_result["unsanctioned_flags"]
    if not isinstance(raw_flags, list):
        dead_letter = _dead_letter(
            run_id=run_id,
            post_id=post_id,
            known=[],
            rejected=[],
            reason_code="malformed_flags",
        )
        return FlagPersistenceResult(
            outcome="preserved",
            known_keys=(),
            rejected_keys=(),
            degraded=True,
            dead_letter=dead_letter,
        )

    if not raw_flags:
        with transaction.atomic():
            PostUnsanctionedFlag.objects.filter(post_id=post_id).delete()
        return FlagPersistenceResult(
            outcome="cleared",
            known_keys=(),
            rejected_keys=(),
            degraded=False,
        )

    allowed = set(UnsanctionedFlagKey.objects.values_list("key", flat=True))
    known: list[str] = []
    rejected: list[str] = []
    malformed = False
    for value in raw_flags:
        if isinstance(value, str) and value in allowed:
            if value not in known:
                known.append(value)
        else:
            malformed = malformed or not isinstance(value, str)
            rejected.append(_safe_rejected_key(value))

    if not known:
        dead_letter = _dead_letter(
            run_id=run_id,
            post_id=post_id,
            known=[],
            rejected=rejected,
            reason_code="malformed_flags" if malformed else "unknown_only",
        )
        return FlagPersistenceResult(
            outcome="preserved",
            known_keys=(),
            rejected_keys=tuple(_dedupe(rejected)),
            degraded=True,
            dead_letter=dead_letter,
        )

    with transaction.atomic():
        PostUnsanctionedFlag.objects.update_or_create(
            post_id=post_id,
            defaults={
                "flags": json.dumps(known, separators=(",", ":")),
                "flag_set": known,
                "evidence": None,
            },
        )

    dead_letter = None
    if rejected:
        dead_letter = _dead_letter(
            run_id=run_id,
            post_id=post_id,
            known=known,
            rejected=rejected,
            reason_code="unknown_keys",
        )
    return FlagPersistenceResult(
        outcome="persisted",
        known_keys=tuple(known),
        rejected_keys=tuple(_dedupe(rejected)),
        degraded=bool(rejected),
        dead_letter=dead_letter,
    )

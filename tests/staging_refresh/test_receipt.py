from __future__ import annotations

import json

import pytest

from scripts.staging_refresh.receipt import (
    Receipt,
    ReceiptError,
    decode_database_comment,
    encode_database_comment,
)


def _payload() -> dict[str, object]:
    return {
        "version": 1,
        "action": "refresh",
        "completed_at": "2026-08-27T01:02:03+00:00",
        "source_resource_id": "dpg-production-a",
        "source_database": "pushinweight_shadow",
        "target_resource_id": "dpg-staging-a",
        "canonical_database": "pushinweight_staging",
        "recovery_database": "pushinweight_staging_recovery_20260827t010203z",
        "snapshot_at": "2026-08-27T01:00:00+00:00",
        "dump_checksum": "a" * 64,
        "dump_bytes": 1234,
        "source_counts": {"posts": 12, "brands": 2},
        "candidate_counts": {"posts": 12, "brands": 2},
        "scrubbed_rows": {"auth_user": 1, "django_session": 4},
        "latest_timestamps": {"posts.created_at": "2026-08-27T01:00:00+00:00"},
        "rollback_confirmation": (
            "ROLLBACK staging/pushinweight_staging_recovery_20260827t010203z "
            "-> staging/pushinweight_staging"
        ),
    }


def test_receipt_round_trips_through_both_database_comments() -> None:
    receipt = Receipt.from_payload(_payload())
    active = encode_database_comment(
        marker_prefix="staging-refresh/v1",
        state="active",
        database="pushinweight_staging",
        receipt=receipt,
    )
    recovery = encode_database_comment(
        marker_prefix="staging-refresh/v1",
        state="recovery",
        database=receipt.recovery_database,
        receipt=receipt,
    )

    active_record = decode_database_comment(active, marker_prefix="staging-refresh/v1")
    recovery_record = decode_database_comment(
        recovery, marker_prefix="staging-refresh/v1"
    )

    assert active_record.state == "active"
    assert recovery_record.state == "recovery"
    assert active_record.receipt == recovery_record.receipt == receipt
    assert json.loads(receipt.to_json())["dump_checksum"] == "a" * 64


@pytest.mark.parametrize(
    "mutation",
    [
        {"password": "do-not-serialize"},
        {"environment": {"DATABASE_URL": "hidden"}},
        {"source_database": "postgresql://reader:test@source/database"},
        {"dump_checksum": "not-a-checksum"},
        {
            "rollback_confirmation": (
                "ROLLBACK staging/pushinweight_staging_recovery_20260826t010203z "
                "-> staging/pushinweight_staging"
            )
        },
    ],
)
def test_receipt_rejects_unknown_or_secret_shaped_fields(
    mutation: dict[str, object],
) -> None:
    payload = {**_payload(), **mutation}

    with pytest.raises(ReceiptError):
        Receipt.from_payload(payload)


def test_comment_rejects_unknown_state_database_or_payload_fields() -> None:
    receipt = Receipt.from_payload(_payload())

    with pytest.raises(ReceiptError, match="comment_state_invalid"):
        encode_database_comment(
            marker_prefix="staging-refresh/v1",
            state="building",
            database="pushinweight_staging",
            receipt=receipt,
        )

    raw = json.loads(
        encode_database_comment(
            marker_prefix="staging-refresh/v1",
            state="active",
            database="pushinweight_staging",
            receipt=receipt,
        ).removeprefix("staging-refresh/v1:")
    )
    raw["url"] = "postgresql://reader:test@source/database"
    tampered = "staging-refresh/v1:" + json.dumps(raw)

    with pytest.raises(ReceiptError, match="comment_unknown_fields"):
        decode_database_comment(tampered, marker_prefix="staging-refresh/v1")

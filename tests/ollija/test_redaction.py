from __future__ import annotations

import pytest

from scripts.ollija.redaction import (
    UnsafeOutputError,
    assert_safe_value,
    redact_text,
)


def test_redact_text_removes_database_and_api_credentials() -> None:
    unsafe = (
        "connection failed "
        + "postgresql://operator:"
        + "live-value"
        + "@example.invalid/database"
        + " token="
        + "sk-"
        + "abcdefghijklmnopqrstuvwxyz"
    )

    redacted = redact_text(unsafe)

    assert "live-value" not in redacted
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert redacted.count("[REDACTED") == 2
    assert_safe_value(redacted)


def test_nested_secret_fields_and_provider_bodies_are_rejected() -> None:
    with pytest.raises(UnsafeOutputError, match="secret-shaped field"):
        assert_safe_value(
            {"nested": {"captured_provider_response_body": "private output"}}
        )


def test_safe_resource_ids_and_shas_are_allowed() -> None:
    assert_safe_value(
        {
            "service_id": "srv-example",
            "database_resource_id": "dpg-example",
            "candidate_sha": "a" * 40,
        }
    )

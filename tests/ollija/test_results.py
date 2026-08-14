from __future__ import annotations

import pytest

from scripts.ollija.redaction import UnsafeOutputError, redact_text
from scripts.ollija.results import (
    CommandError,
    CommandResult,
    EvidenceRef,
    NextAction,
)

SHA = "a" * 40


def test_result_serialization_keeps_safe_resource_and_commit_evidence() -> None:
    result = CommandResult(
        command="status",
        status="ok",
        state="staged",
        summary="Candidate is live on staging.",
        next_action=NextAction(
            command="ollija approve desktop",
            reason="Desktop review is required.",
        ),
        evidence=(
            EvidenceRef(
                kind="render_deploy",
                identifier="dep-example",
                candidate_sha=SHA,
            ),
        ),
    )

    body = result.to_dict()

    assert body["schema_version"] == 1
    assert body["evidence"][0]["identifier"] == "dep-example"
    assert body["evidence"][0]["candidate_sha"] == SHA
    assert body["next_action"]["command"] == "ollija approve desktop"


@pytest.mark.parametrize(
    "unsafe_detail",
    [
        {"database_" + "url": "not-even-a-url"},
        {"api_" + "token": "not-even-a-token"},
        {"captured_provider_response_body": "private output"},
        {
            "detail": "postgresql://user:" + "live-value" + "@example.invalid/db"
        },
    ],
)
def test_result_serialization_rejects_secret_fields_and_database_urls(
    unsafe_detail: dict[str, str],
) -> None:
    result = CommandResult(
        command="doctor",
        status="blocked",
        state="blocked",
        summary="Unsafe evidence fixture.",
        details=unsafe_detail,
    )

    with pytest.raises(UnsafeOutputError):
        result.to_dict()


def test_error_redaction_removes_credentials_before_serialization() -> None:
    unsafe = (
        "failed at "
        + "postgresql://operator:"
        + "live-value"
        + "@example.invalid/db"
        + " using "
        + "sk-"
        + "abcdefghijklmnopqrstuvwxyz"
    )
    safe = redact_text(unsafe)
    result = CommandResult(
        command="doctor",
        status="failed",
        state="blocked",
        summary="An external check failed.",
        errors=(CommandError(code="external_check_failed", message=safe),),
    )

    body = result.to_dict()

    assert "live-value" not in body["errors"][0]["message"]
    assert "abcdefghijklmnopqrstuvwxyz" not in body["errors"][0]["message"]
    assert "[REDACTED]" in body["errors"][0]["message"]

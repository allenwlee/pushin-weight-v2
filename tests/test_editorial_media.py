import json
import struct
from datetime import timedelta

import pytest
from django.utils import timezone

from monitor.editorial.media import (
    poll_derivative,
    project_key,
    start_derivative,
    validate_mp4,
)
from monitor.editorial.persistence import claim_assessment
from monitor.editorial.pictures import select_picture
from tests.editorial_support import (  # noqa: F401
    active_config,
    editorial_storage,
    person_photo,
    selection,
)

pytestmark = [
    pytest.mark.usefixtures("editorial_storage"),
    pytest.mark.django_db(transaction=True),
    pytest.mark.requires_postgres,
]


def test_only_project_credential_is_allowed(monkeypatch):
    monkeypatch.delenv("PUSHINWEIGHT_MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "shared-test-key")
    with pytest.raises(ValueError, match="PUSHINWEIGHT"):
        project_key()


def test_derivative_resumes_task_and_keeps_original_when_disabled(monkeypatch):
    monkeypatch.setenv("PUSHINWEIGHT_MINIMAX_API_KEY", "project-test-key")
    person_photo("blue", "founder")
    cfg = active_config()
    assessment = claim_assessment(timezone.now(), "fixture")
    row = select_picture(
        selection(),
        {"posts": []},
        cfg,
        content_kind="chatter",
        content_id="one",
        revision="v1",
        assessment=assessment,
    )
    calls = []

    def transport(url, key, payload, **kwargs):
        calls.append((url, payload))
        assert key == "project-test-key"
        if payload:
            assert payload["content"][1]["image_url"].startswith(
                "data:image/png;base64,"
            )
            return 200, json.dumps({"task_id": "123"}).encode()
        return 200, json.dumps(
            {
                "task": {
                    "id": "123",
                    "model": "MiniMax-H3",
                    "status": "succeeded",
                    "content": {"url": "https://cdn.hailuoai.com/video.mp4"},
                }
            }
        ).encode()

    source_id = row.source_media_id
    row = start_derivative(row, assessment, cfg, transport=transport)
    start_derivative(row, assessment, cfg, transport=transport)
    assert len(calls) == 1
    row.next_poll_at = timezone.now() - timedelta(seconds=1)
    row.save()
    data = b"".join(
        struct.pack(">I4s", 8, kind) for kind in (b"ftyp", b"moov", b"mdat")
    )
    row = poll_derivative(
        row.pk,
        cfg.model_copy(update={"pictures": {"chatter": "off"}}),
        transport=transport,
        download=lambda url, **kwargs: data,
    )
    row = row.picture
    assert row.state == "complete" and row.generated_sha256
    assert row.source_media_id == source_id
    assert len(calls) == 2
    # The audit receipt stores the task only, never the image payload or key.
    receipt = assessment.calls.get().response
    assert receipt == {"task_id": "123"}


def test_corrupt_video_rejected():
    with pytest.raises(ValueError):
        validate_mp4(b"<html>not video</html>")


def test_duplicate_or_early_poll_does_not_fork_poll_chain(monkeypatch):
    from core.models import EditorialPicture

    monkeypatch.setenv("PUSHINWEIGHT_MINIMAX_API_KEY", "project-test-key")
    row = EditorialPicture.objects.create(
        content_kind="chatter",
        content_id="one",
        revision_hash="v1",
        mode="derive",
        state="pending",
        provider_task_id="123",
        next_poll_at=timezone.now() - timedelta(seconds=1),
    )
    calls = []

    def transport(*args, **kwargs):
        calls.append(1)
        return 200, b'{"task":{"id":"123","model":"MiniMax-H3","status":"processing"}}'

    cfg = active_config(media_max_polls=1)
    assert poll_derivative(row.pk, cfg, transport=transport).reschedule
    assert not poll_derivative(row.pk, cfg, transport=transport).reschedule
    EditorialPicture.objects.filter(pk=row.pk).update(
        next_poll_at=timezone.now() - timedelta(seconds=1)
    )
    result = poll_derivative(row.pk, cfg, transport=transport)
    assert result.picture.state == "exhausted" and not result.reschedule
    assert calls == [1]

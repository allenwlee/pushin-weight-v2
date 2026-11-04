"""The separate Graphics workflow cannot rewrite copy or switch a selected story."""

import pytest

from tests.editorial_support import editorial_storage  # noqa: F401
from tests.test_chatter_pool_readers import published

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_missing_credit_is_a_finding_and_does_not_reject_a_complete_package():
    from uuid import uuid4

    from monitor.editorial.graphics_contract import GraphicsResult

    result = GraphicsResult(
        request_fingerprint="a" * 64,
        story_id=uuid4(),
        revision=1,
        text_id=uuid4(),
        locale="en",
        outcome="complete",
        source_hashes=[],
        picture_id=uuid4(),
        producing_call_ids=[1],
        display_credit="",
        exports=[
            {
                "reference_id": "video",
                "sha256": "b" * 64,
                "kind": "video",
                "width": 1200,
                "height": 675,
            },
            {
                "reference_id": "still",
                "sha256": "c" * 64,
                "kind": "still",
                "width": 1200,
                "height": 675,
            },
        ],
        gaps=["Display credit is unknown."],
    )
    assert result.outcome == "complete" and result.display_credit == ""


def test_no_art_is_a_versioned_attributed_boundary_and_duplicate_is_idempotent(
    monkeypatch,
):
    from monitor.editorial.graphics_contract import make_request, no_art, receive_result

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    text = published("rest", "884101")
    headline = text.headline
    request = make_request(text)
    assert request.content_id == text.narrative_id and request.locale == text.locale
    assert request.source_locale == "en" and request.editorial_group == "rest"
    assert (
        request.sources and request.sources[0].sha256 == text.sources.get().source_hash
    )
    result = no_art(request)
    assert receive_result(request, result) == "unavailable"
    assert receive_result(request, result) == "unavailable"
    text.refresh_from_db()
    assert text.headline == headline
    forged = result.model_copy(update={"locale": "ja"})
    with pytest.raises(ValueError, match="identity"):
        receive_result(request, forged)


def test_late_result_cannot_replace_the_current_story(monkeypatch):
    from monitor.editorial.graphics_contract import make_request, no_art, receive_result

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    first = published("rest", "884102")
    request = make_request(first)
    newer = published("rest", "884103")
    assert receive_result(request, no_art(request)) == "stale"
    newer.refresh_from_db()
    assert "graphics_result" not in newer.provenance


@pytest.mark.usefixtures("editorial_storage")
def test_matching_graphics_uses_existing_picture_and_preserves_unknown_reuse(monkeypatch):
    from hashlib import sha256

    from core.models import EditorialPicture
    from monitor.editorial.graphics_contract import (
        GraphicsResult,
        make_request,
        receive_result,
    )
    from tests.editorial_support import person_photo

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    text = published("rest", "884104")
    request = make_request(text)
    _, _, photo = person_photo(
        "red", reuse="unknown"
    )  # Test input state, not a new product policy.
    video_hash = sha256(b"fixture export identity, not generated media").hexdigest()
    picture = EditorialPicture.objects.create(
        content_kind="chatter",
        content_id=str(text.public_id),
        revision_hash=request.fingerprint,
        mode="derive",
        state="complete",
        source_media=photo.media,
        generated_storage_name="fixture-only.mp4",
        generated_sha256=video_hash,
        provenance={"reuse_status": "unknown"},
    )
    result = GraphicsResult(
        request_fingerprint=request.fingerprint,
        story_id=request.story_id,
        revision=request.revision,
        text_id=request.text_id,
        locale=text.locale,
        outcome="complete",
        source_hashes=[source.sha256 for source in request.sources],
        picture_id=picture.pk,
        producing_call_ids=[text.producing_call_id],
        display_credit="Source attribution remains unknown.",
        references=[
            {
                "reference_id": str(photo.media_id),
                "sha256": photo.media_id,
                "kind": "reference",
                "width": 320,
                "height": 480,
            }
        ],
        exports=[
            {
                "reference_id": "fixture-video",
                "sha256": video_hash,
                "kind": "video",
                "width": 1200,
                "height": 675,
            },
            {
                "reference_id": "fixture-still",
                "sha256": photo.media_id,
                "kind": "still",
                "width": 320,
                "height": 480,
            },
        ],
    )
    assert receive_result(request, result) == "complete"
    assert receive_result(request, result) == "complete"
    picture.refresh_from_db()
    assert picture.provenance["reuse_status"] == "unknown"
    text.refresh_from_db()
    assert text.provenance["graphics_result"]["picture_id"] == str(picture.pk)

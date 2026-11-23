"""Classifier input uses source-bound translations without waiting for one."""
import json

import pytest
from django.utils import timezone

from core import models
from monitor.post_artifacts import read_post_content_many, source_content_fingerprint
from tests.test_classified_product_releases import setup_cycle

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize(
    ("artifact_state", "source_matches", "cached_text", "artifact_text", "expected"),
    [
        (None, True, "Available English", None, "Available English"),
        (None, True, "", None, ""),
        ("succeeded", True, "Older English", "Current English", "Current English"),
        ("succeeded", False, "Stale English", "Stale English", ""),
        ("failed", True, "", None, ""),
    ],
)
def test_worker_uses_only_current_or_legacy_english_without_waiting(
    monkeypatch, artifact_state, source_matches, cached_text, artifact_text, expected,
):
    state, runner, transport = setup_cycle(monkeypatch, empty=True)
    post = state.post
    post.text = "Qwen4 weights are available today. 日本語"
    post.lang = post.lang_detected = "ja"
    post.text_en = cached_text
    post.save(update_fields=["text", "lang", "lang_detected", "text_en"])
    state.translation_status = "pending"
    state.save(update_fields=["translation_status"])
    if artifact_state:
        now = timezone.now()
        artifact = models.PostTranslationArtifact.objects.create(
            post=post, source_content_fingerprint=(source_content_fingerprint(post) if source_matches else "f" * 64),
            source_language="ja", prompt_version="fixture", model="fixture", provider_role="literal_translation",
            state=artifact_state, is_current=artifact_state == "succeeded", started_at=now, completed_at=now,
            error_code="fixture_failure" if artifact_state == "failed" else "",
        )
        if artifact_text:
            models.PostTranslationText.objects.create(artifact=artifact, locale="en", text=artifact_text)
    assert read_post_content_many([post])[str(post.pk)].literal.get("en", "") == expected
    runner._run_post_fetch([], run_id="u5-translation-source")
    jev = next(call for call in transport.calls if not call["model"].startswith("deepseek"))
    request = json.loads(jev["messages"][0]["content"])
    assert request["state"]["english_translation"] == expected
    assert request["state"]["source_text"] == post.text
    assert len(transport.calls) == 2


def test_late_legacy_translation_is_used_on_a_later_classification(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch, empty=True)
    post = state.post
    post.text = "Qwen4 weights are available today. 日本語"
    post.lang = post.lang_detected = "ja"
    post.text_en = ""
    post.save(update_fields=["text", "lang", "lang_detected", "text_en"])
    state.translation_status = "pending"
    state.save(update_fields=["translation_status"])
    runner._run_post_fetch([], run_id="u5-before-translation")
    first = json.loads(next(call for call in transport.calls if not call["model"].startswith("deepseek"))["messages"][0]["content"])
    assert first["state"]["english_translation"] == ""

    post.text_en = "A translation arrived later."
    post.save(update_fields=["text_en"])
    state.refresh_from_db()
    state.classification_status = "pending"
    state.classification_next_attempt_at = None
    state.translation_status = "succeeded"
    state.save(update_fields=["classification_status", "classification_next_attempt_at", "translation_status"])
    runner._run_post_fetch([], run_id="u5-after-translation")
    jev_calls = [call for call in transport.calls if not call["model"].startswith("deepseek")]
    assert len(jev_calls) == 2
    assert json.loads(jev_calls[-1]["messages"][0]["content"])["state"]["english_translation"] == post.text_en

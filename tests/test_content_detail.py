import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import (
    PostBrandClassificationState,
    PostSynthesisArtifact,
    PostSynthesisDemand,
)
from tests.general_helpers import classified_post, saved_commentary
from tests.test_general_jobs_people import job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_atomic_post_and_old_saved_revision_survive_category_and_current_revision_changes(
    client,
):
    post = classified_post("4101")
    old = saved_commentary(post)
    old.is_current = False
    old.save(update_fields=["is_current"])
    newer = saved_commentary(post, revision="two")
    newer.texts.filter(locale="en").update(text="New commentary")
    PostBrandClassificationState.objects.filter(post=post).update(
        outcome="context_missing"
    )
    job(post, "Engineer")
    job(post, "Designer")
    url = f"/posts/{post.pk}/?lang=en&commentary={old.pk}"
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url, secure=True)
    assert response.status_code == 200
    body = response.content.decode()
    assert "Normalized commentary" in body and "New commentary" not in body
    assert "Original source 4101" in body and "Engineer" in body and "Designer" in body
    assert f"commentary={old.pk}" in body and 'property="og:url"' in body
    assert 'href="/general/' in body
    assert not any(
        row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for row in queries
    )
    assert PostSynthesisDemand.objects.count() == 0
    assert (
        "New commentary"
        in client.get(f"/posts/{post.pk}/?lang=en", secure=True).content.decode()
    )


def test_unknown_cross_post_failed_or_withdrawn_commentary_never_falls_back(client):
    first = classified_post("4201")
    second = classified_post("4202")
    foreign = saved_commentary(second)
    failed = saved_commentary(first, current=False, revision="failed")
    PostSynthesisArtifact.objects.filter(pk=failed.pk).update(
        state="failed", error_code="fixture"
    )
    withdrawn = saved_commentary(first, current=False, revision="withdrawn")
    PostSynthesisArtifact.objects.filter(pk=withdrawn.pk).update(
        review_state="withdrawn"
    )
    for revision in ("unknown", "99999999", foreign.pk, failed.pk, withdrawn.pk):
        assert (
            client.get(
                f"/posts/{first.pk}/?commentary={revision}", secure=True
            ).status_code
            == 404
        )
    assert client.get("/posts/missing/", secure=True).status_code == 404


def test_detail_escapes_source_and_commentary_rejects_unsafe_urls_and_preserves_language_fallback(
    client,
):
    post = classified_post("4301")
    post.text = '<script>alert("source")</script>'
    post.commentary_en = '<img src=x onerror=alert("commentary")>'
    post.tweet_url = "javascript:alert(1)"
    post.extended_entities = {
        "media": [
            {
                "type": "photo",
                "media_url_https": "https://example.org/photo.jpg",
                "ext_alt_text": "Photo",
            },
            {"type": "photo", "media_url_https": "javascript:alert(2)"},
        ]
    }
    post.save()
    body = client.get(f"/posts/{post.pk}/?lang=ja", secure=True).content.decode()
    assert "&lt;script&gt;" in body and "&lt;img" in body
    assert "javascript:" not in body
    assert "https://example.org/photo.jpg" in body
    assert 'lang="en"' in body
    assert "English" in body or "英語" in body
    assert "Legacy" in body or "以前の" in body


@pytest.mark.parametrize(
    "url", ["https://user:secret@example.org/post", "https://:secret@example.org/post"]
)
def test_source_and_media_links_never_emit_url_credentials(client, url):
    post = classified_post("4401")
    post.tweet_url = url
    post.extended_entities = {"media": [{"media_url_https": url}]}
    post.save()
    body = client.get(f"/posts/{post.pk}/?lang=en", secure=True).content.decode()
    assert "secret@" not in body

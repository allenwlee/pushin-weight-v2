"""General consumes G2's saved publications and complete relational citations."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import OriginalContentCall, Post
from monitor.original_content import WORKFLOWS, publish_content
from tests.test_original_content_models import saved_text

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize(
    ("locale", "forecast", "history", "projection", "audit", "learning", "reports"),
    [
        ("en", "Forecasts are not available yet.", "Observed history", "Forward projection", "Outcome reports", "Learning from outcomes", "Published reports"),
        ("zh-cn", "预测尚未开放。", "历史观测", "未来预测", "结果报告", "从结果中学习", "已发布报告"),
        ("ja", "予測はまだ利用できません。", "観測履歴", "将来予測", "結果レポート", "結果からの学習", "公開済みレポート"),
    ],
)
def test_pulse_framework_is_truthful_and_localized(
    client, monkeypatch, locale, forecast, history, projection, audit, learning, reports
):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("EDITORIAL_PUBLIC_ENABLED", "false")
    with CaptureQueriesContext(connection) as queries:
        response = client.get(f"/general/?lang={locale}", secure=True)
    body = response.content.decode()
    assert response.status_code == 200
    assert 'class="pulse-framework"' in body
    assert 'data-pulse-status="unavailable"' in body
    for label in (forecast, history, projection, audit, learning, reports):
        assert label in body
    assert 'data-forecast-value' not in body and 'data-forecast-probability' not in body
    assert not any(row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for row in queries)


def test_saved_general_edition_and_citations_survive_normal_history_cleanup(client, monkeypatch):
    from core.models import OriginalContentRun
    from monitor.trend_narrative_lifecycle import (
        prune_narrative_history,
        prune_per_brand_trend_narrative_history,
    )

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("EDITORIAL_PUBLIC_ENABLED", "true")
    text = published_story("pulse", source_count=7)
    old = timezone.now() - timedelta(days=120)
    OriginalContentRun.objects.filter(pk=text.narrative.run_id).update(
        created_at=old, activated_at=old, status="superseded"
    )
    assert text.narrative.run.window_days is None
    url = f"/stories/{text.narrative.story_id}/?track=pulse&lang=en&edition={text.public_id}"
    before = client.get(url, secure=True)
    assert before.status_code == 200
    prune_narrative_history(now=timezone.now(), keep_days=1, keep_per_window=1)
    prune_per_brand_trend_narrative_history(now=timezone.now(), keep_days=1, keep_per_window=1)
    after = client.get(url, secure=True)
    assert after.status_code == 200
    assert after.content == before.content
    assert text.sources.count() == 7


def published_story(track="chatter", locale="en", *, featured=False, source_count=7):
    draft = saved_text(locale)
    content = draft.narrative
    draft.delete()
    now = timezone.now()
    content.workflow_key = WORKFLOWS[track]
    content.published_at = content.occurred_at = now
    content.save()
    call = OriginalContentCall.objects.create(
        run=content.run,
        workflow_key=content.workflow_key,
        stage="write:story:" + locale,
        request_identity=str(uuid4()),
        request_hash="b" * 64,
        response_hash="c" * 64,
        state="completed",
        reserved_at=now,
        sent_at=now,
        completed_at=now,
    )
    sources = []
    for number in range(source_count):
        key = f"g5-{content.pk}-{number}"
        post = Post.objects.create(tweet_id=key, text="PRIVATE RAW EVIDENCE")
        sources.append(
            {
                "id": post.pk,
                "url": f"https://example.org/posts/{key}",
                "author_handle": f"source-{number}",
                "original_text": post.text,
            }
        )
    (text,) = publish_content(
        content,
        [
            {
                "locale": locale,
                "headline": f"{track} saved headline {locale}",
                "byline": f"{track} saved byline {locale}",
                "body": (f"{track} saved paragraph {locale}. " * 30)
                + "\n\nFinal saved paragraph.",
                "producing_call": call,
                "sources": sources,
            }
        ],
        selected_scope=f"featured:{content.workflow_key}:{locale}"
        if featured
        else None,
    )
    return text


@pytest.mark.parametrize("locale", ["en", "zh-cn", "ja"])
def test_general_renders_shared_publications_with_full_body_and_every_source(
    client, monkeypatch, locale
):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("EDITORIAL_PUBLIC_ENABLED", "true")
    texts = [
        published_story(track, locale, featured=track == "chatter")
        for track in ("chatter", "pulse")
    ]
    hidden = saved_text(locale)
    hidden.headline = "UNPUBLISHED DRAFT"
    hidden.save()
    with CaptureQueriesContext(connection) as queries:
        response = client.get(f"/general/?lang={locale}", secure=True)
    assert response.status_code == 200
    body = response.content.decode()
    for text in texts:
        assert text.headline in body
        assert text.secondary in body
        assert text.body.split("\n\n")[0] in body and "Final saved paragraph." in body
        assert f'data-edition-id="{text.public_id}"' in body
        assert f'data-source-count="{text.sources.count()}"' in body
        for source in text.sources.all():
            assert f'href="{source.url_snapshot}"' in body
        assert f"edition={text.public_id}" in body
    assert "UNPUBLISHED DRAFT" not in body and "PRIVATE RAW EVIDENCE" not in body
    assert not any(
        row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for row in queries
    )


def test_general_respects_shared_access_and_labels_english_fallback(
    client, monkeypatch
):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    text = published_story(featured=True)
    monkeypatch.setenv("EDITORIAL_PUBLIC_ENABLED", "false")
    hidden = client.get("/general/", secure=True)
    assert hidden.status_code == 200 and text.headline not in hidden.content.decode()
    monkeypatch.setenv("EDITORIAL_PUBLIC_ENABLED", "true")
    response = client.get("/general/?lang=ja", secure=True)
    assert text.headline in response.content.decode()
    assert response.context["editorial"]["chatter"]["fallback"]
    assert response.context["editorial"]["pulse"]["status"] == "empty"

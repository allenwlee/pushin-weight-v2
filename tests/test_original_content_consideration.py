"""Real storage boundaries for unpublished Chatter decisions and later locales."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from core.models import (
    EditorialStory,
    Language,
    Locale,
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
    OriginalContentSource,
    OriginalContentText,
    Post,
    SearchQuery,
)
from monitor.original_content import publish_content

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def consideration(**changes):
    now = timezone.now()
    Language.objects.get_or_create(code="en")
    Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    run = OriginalContentRun.objects.create(
        source_cycle_id=str(uuid4()), workflow_key="chatter-discovery",
        scope_key="chatter:" + str(uuid4()), facts_as_of=now, interval=now,
        cycle_started_at=now - timedelta(seconds=2), discovery_state="complete",
        packet_schema_version=1, snapshot={}, execution_state="running",
        lease_until=now + timedelta(minutes=15),
    )
    story = EditorialStory.objects.create(development_key=str(uuid4()))
    values = {
        "run": run, "workflow_key": "social-brief", "output_key": str(uuid4()),
        "subject_key": story.development_key, "story_id": story.pk, "development": story,
        "source_locale_id": "en", "editorial_group": "rest", "consideration_state": "passed_over",
        "consideration_reason": "A stronger supported development leads this pool.",
        "appearance_kind": "semantic_shortlist", "shortlist_position": 10,
        "status": "prepared", "attempted_at": now, "brand_key_snapshot": "",
    }
    values.update(changes)
    return OriginalContent.objects.create(**values)


def source_values(post):
    return {"post": post, "position": 0, "url_snapshot": f"https://x.com/i/status/{post.pk}",
                "source_hash": "a" * 64, "hash_basis": "writing_packet"}


def producer(content, locale):
    return OriginalContentCall.objects.create(
        run=content.run, workflow_key="social-brief", stage=f"writer:chatter:{locale}",
        request_identity=str(uuid4()), state="completed", reserved_at=timezone.now(),
        request_hash="b" * 64, request_packet={"fixture": "validated source packet"},
        sent_at=timezone.now(), completed_at=timezone.now(), response_hash="c" * 64,
        provider="fixture", model="fixture",
    )


def text_spec(content, post, locale):
    from monitor.editorial.chatter_history import (
        attach_sources,
        freeze_sources,
        project_post,
        read_sources,
    )

    if not content.consideration_sources.filter(post=post).exists():
        source = project_post(post)
        freeze_sources(content.run, [source], fence=content.run.fence)
        attach_sources(content, [post.pk], fence=content.run.fence)
    return {"locale": locale, "headline": "A release", "byline": "A source reports a release.",
                "body": "A company announced a model.", "producing_call": producer(content, locale),
                "sources": read_sources(content, usage="consideration")}


def test_passed_over_development_has_real_sources_without_fake_copy():
    row = consideration()
    post = Post.objects.create(tweet_id="880001", text="A company announced a model.")
    OriginalContentSource.objects.create(content=row, usage="consideration", **source_values(post))
    assert row.localized_texts.count() == 0
    assert row.published_at is None and row.verified_at is None
    assert OriginalContent.objects.filter(
        development=row.development, source_locale_id="en", editorial_group="rest",
        consideration_state="passed_over", consideration_sources__post=post,
    ).count() == 1
    with pytest.raises(ProtectedError):
        post.delete()


@pytest.mark.parametrize("ownership", ["neither", "both", "wrong_usage"])
def test_source_cannot_hide_or_mix_its_owner(ownership):
    row = consideration()
    post = Post.objects.create(tweet_id="880002")
    text = OriginalContentText.objects.create(
        narrative=row, locale="en", headline="A release", secondary="A source report."
    )
    owners = {} if ownership == "neither" else {"content": row}
    if ownership == "both":
        owners["text"] = text
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContentSource.objects.create(
            **owners, usage="citation" if ownership == "wrong_usage" else "consideration",
            **source_values(post),
        )


def test_candidate_membership_is_not_duplicated_for_background():
    row = consideration()
    post = Post.objects.create(tweet_id="880003")
    OriginalContentSource.objects.create(content=row, usage="background", **source_values(post))
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContentSource.objects.create(
            content=row, usage="consideration", **{**source_values(post), "position": 1}
        )


@pytest.mark.parametrize("changes", [
    {"consideration_state": "invented"},
    {"consideration_state": "selected", "source_locale_id": None},
    {"consideration_state": "selected", "editorial_group": None},
    {"consideration_state": "selected", "development": None},
    {"appearance_kind": "keyword_rediscovery"},
    {"shortlist_position": 0},
])
def test_invalid_new_contract_cannot_be_bulk_written(changes):
    with pytest.raises(IntegrityError), transaction.atomic():
        consideration(**changes)


def test_query_versions_keep_the_exact_prior_wording():
    row = consideration()
    first = SearchQuery.objects.create(query_id=str(uuid4()), query_text="original query",
                                       development=row.development)
    second = SearchQuery.objects.create(query_id=str(uuid4()), query_text="revised query",
                                        development=row.development, previous_version=first)
    assert second.previous_version.query_text == "original query"
    with pytest.raises(IntegrityError), transaction.atomic():
        SearchQuery.objects.filter(pk=second.pk).update(previous_version=second)


def test_later_chatter_locale_keeps_the_first_publication_and_is_idempotent(monkeypatch):
    row = consideration(consideration_state="selected")
    post = Post.objects.create(tweet_id="880004", text="A company announced a model.", created_at=timezone.now())
    first_spec = text_spec(row, post, "en")
    (first,) = publish_content(row, [first_spec], fence=row.run.fence)
    row.refresh_from_db()
    published_at = row.published_at
    later = first.created_at + timedelta(seconds=20)
    monkeypatch.setattr(timezone, "now", lambda: later)
    second_spec = text_spec(row, post, "ja")
    (second,) = publish_content(row, [second_spec], fence=row.run.fence)
    row.refresh_from_db()
    assert row.published_at == published_at
    assert first.created_at <= second.created_at
    from monitor.original_content_readers import saved_edition

    assert saved_edition(second).published_at == second.created_at
    assert publish_content(row, [second_spec], fence=row.run.fence)[0].pk == second.pk
    assert row.localized_texts.count() == 2
    changed = {**second_spec, "headline": "A different draft"}
    with pytest.raises(ValueError, match="immutable"):
        publish_content(row, [changed], fence=row.run.fence)
    row.run.fence += 1
    row.run.save(update_fields=["fence"])
    with pytest.raises(ValueError, match="stale"):
        publish_content(row, [second_spec], fence=row.run.fence - 1)


def test_new_contract_cannot_use_legacy_publication_or_skip_its_fence():
    row = consideration(consideration_state="selected")
    post = Post.objects.create(tweet_id="880005", text="A company announced a model.", created_at=timezone.now())
    spec = text_spec(row, post, "en")
    with pytest.raises(ValueError, match="current fence"):
        publish_content(row, [spec])
    with pytest.raises(ValueError, match="current fence"):
        publish_content(row, [spec], fence=row.run.fence, legacy=True)
    assert not row.localized_texts.exists()
    other = consideration()
    row.run_id = other.run_id
    with pytest.raises(ValueError, match="stale"):
        publish_content(row, [spec], fence=other.run.fence)


def test_only_one_lead_can_be_selected_in_each_pool():
    row = consideration(consideration_state="selected")
    with pytest.raises(IntegrityError), transaction.atomic():
        consideration(run=row.run, consideration_state="selected")
    other = consideration(run=row.run, consideration_state="selected", editorial_group="giant")
    assert other.pk != row.pk


def test_website_citation_uses_its_real_dossier_source_without_a_fake_post(tmp_path):
    from core.event_dossiers import create_dossier, identity_key
    from core.models import CollectionObservation, EventDossierSource
    from monitor.editorial.chatter_history import (
        attach_sources,
        freeze_sources,
        read_sources,
    )
    from monitor.original_content import source_payload
    from tests.test_product_release_documents import captured_document

    receipt, _, options = captured_document(tmp_path)
    observation = CollectionObservation.objects.get(pk=receipt["observation_id"])
    event = create_dossier(event_kind="product_release", identity_key=identity_key("test", "doc"))
    document_source = EventDossierSource.objects.create(
        event_dossier=event, collection_observation=observation
    )
    row = consideration(consideration_state="selected")
    source = {
        "kind": "dossier_source", "id": f"dossier-source:{document_source.pk}",
        "dossier_source_id": document_source.pk, "url": options["url"],
        "original_text": "We announce Model Flash. API access is available now.",
        "created_at": None, "observed_at": timezone.now().isoformat(),
    }
    freeze_sources(row.run, [source], fence=row.run.fence)
    attach_sources(row, [source["id"]], fence=row.run.fence)
    spec = {
        "locale": "en", "headline": "Model Flash arrives", "byline": "A publisher announces a model.",
        "body": "The publisher says API access is available.", "producing_call": producer(row, "en"),
        "sources": read_sources(row, usage="consideration"),
    }
    (text,) = publish_content(row, [spec], fence=row.run.fence)
    assert not Post.objects.exists()
    citation = text.sources.get()
    assert citation.post_id is None and citation.dossier_source_id == document_source.pk
    assert source_payload(text) == [{"url": options["url"], "label": "Source"}]
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContentSource.objects.create(
            text=text, dossier_source=document_source, usage="citation",
            **source_values(Post.objects.create(tweet_id="880006")),
        )


@pytest.mark.parametrize("fault", ["unconsidered", "rewritten", "wrong_url", "background_only"])
def test_new_publication_requires_the_exact_considered_source(fault):
    row = consideration(consideration_state="selected")
    post = Post.objects.create(tweet_id="880007", text="A source announces a model.", created_at=timezone.now())
    spec = text_spec(row, post, "en")
    if fault == "unconsidered":
        row.consideration_sources.all().delete()
    elif fault == "background_only":
        row.consideration_sources.update(usage="background")
    elif fault == "rewritten":
        spec["sources"][0]["original_text"] = "A fabricated replacement source."
    else:
        spec["sources"][0]["_writing_projection"] = dict(spec["sources"][0])
        spec["sources"][0]["url"] = "https://x.com/i/status/999999"
    with pytest.raises(ValueError, match="considered source"):
        publish_content(row, [spec], fence=row.run.fence)
    assert not row.localized_texts.exists()

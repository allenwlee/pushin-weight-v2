import pytest
from django.utils import timezone

from core.models import EditorialPicture
from monitor.editorial.config import EditorialConfig
from monitor.editorial.pictures import select_picture
from tests.editorial_support import (  # noqa: F401
    editorial_storage,
    person_photo,
    selection,
)

pytestmark = [
    pytest.mark.usefixtures("editorial_storage"),
    pytest.mark.django_db,
    pytest.mark.requires_postgres,
]


def test_agent_team_before_founder_and_named_subject_before_team():
    founder, _, _ = person_photo("blue", "founder")
    _engineer, _, portrait = person_photo("red", team="Agent development")
    cfg = EditorialConfig(pictures={"chatter": "select_only"})
    row = select_picture(
        selection(),
        {"posts": []},
        cfg,
        content_kind="chatter",
        content_id="one",
        revision="v1",
    )
    assert row.person_media == portrait
    row = select_picture(
        selection(person_ids=[founder.pk]),
        {"posts": []},
        cfg,
        content_kind="chatter",
        content_id="two",
        revision="v1",
    )
    assert row.person_media.person_id == founder.pk


def test_unverified_or_wrong_staff_falls_back_to_founder_and_off_keeps_source():
    founder, _, _ = person_photo("blue", "founder")
    researcher, _, _ = person_photo("red", team="Agent", review="pending")
    cfg = EditorialConfig(pictures={"chatter": "select_only", "atomic:x": "off"})
    row = select_picture(
        selection(person_ids=[researcher.pk]),
        {"posts": []},
        cfg,
        content_kind="chatter",
        content_id="one",
        revision="v1",
    )
    assert row.person_media.person_id == founder.pk
    assert row.provenance["fallback"]
    assert (
        select_picture(
            selection(),
            {},
            cfg,
            content_kind="atomic",
            source_platform="x",
            content_id="1",
            revision="v1",
        )
        is None
    )
    assert EditorialPicture.objects.count() == 1


def test_restricted_photo_and_former_or_superseded_role_cannot_be_selected():
    person_photo("red", "founder", reuse="restricted")
    person_photo("blue", team="Agent", status="former")
    row = select_picture(
        selection(),
        {"posts": []},
        EditorialConfig(pictures={"pulse": "select_only"}),
        content_kind="pulse",
        content_id="one",
        revision="v1",
    )
    assert row.state == "missing" and row.source_media_id is None


def test_atomic_publication_dispatches_same_optional_picture_service(monkeypatch):
    from unittest.mock import Mock

    from core.models import Post, PostBrand
    from monitor import tasks
    from monitor.editorial import dispatch
    from monitor.editorial.bindings import picture_for_content
    from monitor.post_artifacts import publish_post_synthesis

    person_photo("blue", "founder")
    cfg = EditorialConfig(pictures={"atomic": "select_only"})
    monkeypatch.setattr(dispatch, "load_editorial_config", lambda: cfg)
    queued = Mock()
    monkeypatch.setattr(tasks, "edit_content_picture", queued)
    post = Post.objects.create(
        tweet_id="42", text="Original source", created_at=timezone.now()
    )
    PostBrand.objects.create(post=post, brand_id="deepseek")
    # Capture Django's actual on-commit boundary under the enclosing test transaction.
    from django.test import TestCase

    with TestCase.captureOnCommitCallbacks(execute=True):
        artifact = publish_post_synthesis(
            post=post,
            values={
                "en": "The author describes a release.",
                "zh-cn": "作者介绍了模型发布。",
                "ja": "著者はモデルの公開を紹介しています。",
            },
            context_fingerprint="fixture",
            prompt_version="test",
            model="test",
            output_schema_version=1,
        )
    assert queued.apply_async.call_args.kwargs["args"] == [
        "atomic",
        str(artifact.pk),
        "x",
    ]
    result = picture_for_content("atomic", str(artifact.pk), cfg=cfg)
    assert result["state"] == "selected"
    picture = EditorialPicture.objects.get(pk=result["picture_id"])
    assert picture.provenance["person_name"] == "blue"


def test_affiliation_correction_invalidates_cached_source_and_selects_founder():
    from monitor.editorial.pictures import assignment_eligible

    founder, _, _ = person_photo("blue", "founder")
    person, role, _ = person_photo("red", team="Agent")
    cfg = EditorialConfig(pictures={"chatter": "select_only"})
    kwargs = {"content_kind": "chatter", "content_id": "one", "revision": "v1"}
    selected = selection(person_ids=[person.pk])
    first = select_picture(selected, {"posts": []}, cfg, **kwargs)
    role.status = "former"
    role.save()
    assert not assignment_eligible(first, cfg)
    second = select_picture(selected, {"posts": []}, cfg, **kwargs)
    assert second.pk != first.pk
    assert second.person_media.person_id == founder.pk
    assert second.provenance["fallback"]


def test_essential_post_image_is_used_instead_of_unrelated_portrait(monkeypatch):
    from core.staff_assets.media import media_storage

    _, _, photo = person_photo("blue", "founder")
    with media_storage().open(photo.media.storage_name, "rb") as stream:
        data = stream.read()
    url = "https://pbs.twimg.com/media/source.png"
    monkeypatch.setattr(
        "monitor.editorial.pictures.fetch_public",
        lambda requested: data if requested == url else pytest.fail("wrong image"),
    )
    cfg = EditorialConfig(
        pictures={"chatter": "select_only"}, permitted_reuse=["permitted", "unknown"]
    )
    row = select_picture(
        selection(visual_essential=True, source_image_url=url),
        {"posts": [{"id": "1", "images": [url]}]},
        cfg,
        content_kind="chatter",
        content_id="one",
        revision="v1",
    )
    assert row.source_media_id == photo.media_id and row.person_media is None
    assert row.provenance["source_kind"] == "original_post"


def test_existing_headline_publication_uses_shared_picture_binding(monkeypatch):
    from unittest.mock import Mock

    from django.test import TestCase

    from core.models import Post, PostBrand, TrendNarrativeRun
    from monitor import tasks
    from monitor.editorial import dispatch
    from monitor.editorial.bindings import picture_for_content
    from monitor.trend_narrative_lifecycle import prepare_brand_trend_narrative

    person_photo("blue", "founder")
    cfg = EditorialConfig(pictures={"current_headline": "select_only"})
    monkeypatch.setattr(dispatch, "load_editorial_config", lambda: cfg)
    queued = Mock()
    monkeypatch.setattr(tasks, "edit_content_picture", queued)
    post = Post.objects.create(
        tweet_id="89", text="DeepSeek announces a release.", created_at=timezone.now()
    )
    PostBrand.objects.create(post=post, brand_id="deepseek")
    now = timezone.now()
    run = TrendNarrativeRun.objects.create(
        source_cycle_id="picture-fixture",
        window_days=1,
        facts_as_of=now,
        packet_schema_version=3,
        snapshot={},
        brand_manifest=["deepseek"],
        batch_manifest=[],
        internal_order=["deepseek"],
    )
    with TestCase.captureOnCommitCallbacks(execute=True):
        narrative = prepare_brand_trend_narrative(
            run=run,
            brand_key="deepseek",
            brand_name_en="DeepSeek",
            brand_name_zh_cn="深度求索",
            status="approved",
            attempted_at=now,
            verified_at=now,
            headline_en="A new release",
            headline_zh_cn="新模型发布",
            secondary_en="Developers receive a new model.",
            secondary_zh_cn="开发者获得了新模型。",
            cited_evidence_ids=["opaque-id"],
            selected_evidence_packet=[
                {
                    "evidence_id": "opaque-id",
                    "excerpt": post.text,
                    "text_aliases": {"original_text": "excerpt"},
                    "created_at": post.created_at.isoformat(),
                }
            ],
        )
    assert queued.apply_async.call_args.kwargs["args"] == [
        "current_headline",
        str(narrative.pk),
        "x",
    ]
    assert (
        picture_for_content("current_headline", narrative.pk, cfg=cfg)["state"]
        == "selected"
    )

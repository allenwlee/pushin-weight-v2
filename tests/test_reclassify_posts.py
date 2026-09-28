"""Exact-ID repair must reject model drift before publishing any row."""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.core.management.base import CommandError

from monitor.cycle import _RepairRetryLimitedClient, _repair_result_matches_manifest
from monitor.management.commands import reclassify_posts


def test_repair_result_requires_complete_judgment_fingerprint_and_lineage():
    expected = {
        "input_context_fingerprint": "abc",
        "by_brand": {"glm": {"outcome": "classified", "post_types": ["other"]}},
        "untracked_brand_promotions": ["general"],
        "promoted_subjects": [{"name": "B.AI", "evidence": "B.AI"}],
    }
    result = {
        "valid": True,
        "by_brand": expected["by_brand"],
        "untracked_brand_promotions": expected["untracked_brand_promotions"],
        "promoted_subjects": expected["promoted_subjects"],
        "classification_trace": {
            "content": {"role_revision": "stage1-content-0731-v6"},
            "brand_interpretation": {"role_revision": "stage1-brand-interpretation-0731-v5"},
            "final": {
                "role_revision": "stage1-two-role-merge-0731-v6",
                "input_context_fingerprint": "abc",
                "by_brand": expected["by_brand"],
            },
        },
    }
    assert _repair_result_matches_manifest(result, expected)
    assert not _repair_result_matches_manifest(
        {**result, "by_brand": {"glm": {"outcome": "classified", "post_types": ["advertising_marketing"]}}},
        expected,
    )
    assert not _repair_result_matches_manifest(
        {**result, "classification_trace": {**result["classification_trace"], "final": {"role_revision": "stage1-two-role-merge-0731-v5", "input_context_fingerprint": "abc"}}},
        expected,
    )


def test_repair_transport_allows_only_one_retry_per_role():
    from x_monitor.deepinfra import DeepInfraPermanentError

    class Fake:
        def __init__(self):
            self.calls = []

        def messages_create(self, **kwargs):
            self.calls.append(kwargs["system"])
            return {}

    fake = Fake()
    limited = _RepairRetryLimitedClient(fake)
    for role in ("CONTENT ROLE:", "BRAND INTERPRETATION ROLE:"):
        limited.messages_create(system=role)
        limited.messages_create(system=role)
        with pytest.raises(DeepInfraPermanentError, match="repair_transport_attempt_cap"):
            limited.messages_create(system=role)
    assert len(fake.calls) == 4


def _manifest(post_ids):
    return {
        "schema_version": 1,
        "selected_content_revision": "stage1-content-0731-v6",
        "selected_brand_revision": "stage1-brand-interpretation-0731-v5",
        "selected_merge_revision": "stage1-two-role-merge-0731-v6",
        "posts": {
            post_id: {
                "input_context_fingerprint": "a" * 64,
                "by_brand": {"glm": {
                    "outcome": "classified", "post_types": ["other"],
                    "audience_topics": [], "audience_topics_state": "none",
                    "product_labels": [], "sentiment": "neutral",
                    "geopolitical_modes": [], "geopolitical_modes_state": "none",
                    "china_national_stance": "none", "us_national_stance": "none",
                }},
                "untracked_brand_promotions": [],
                "promoted_subjects": [],
            }
            for post_id in post_ids
        },
    }


def test_preview_is_exact_id_and_never_acquires_a_writer_or_provider(tmp_path, monkeypatch, capsys):
    manifest_path = tmp_path / "reviewed.json"
    manifest_path.write_text(json.dumps(_manifest(["123"])), encoding="utf-8")
    inspected = []
    monkeypatch.setattr(reclassify_posts, "_preflight", lambda ids, rows: inspected.append(ids))
    monkeypatch.setattr(
        reclassify_posts, "harvest_writer_lock",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("preview acquired writer lock")),
    )
    fake_cfg = type("Cfg", (), {"llm": type("Llm", (), {"literal_translation_v2_enabled": True})()})()
    from x_monitor import config
    monkeypatch.setattr(config, "load_config", lambda path: fake_cfg)

    reclassify_posts.Command().handle(post_id=["123"], manifest=manifest_path, apply=False)

    assert inspected == [["123"]]
    assert json.loads(capsys.readouterr().out)["status"] == "preview"


def test_manifest_rejects_unapproved_lineage_or_incomplete_row(tmp_path):
    payload = _manifest(["123"])
    payload["selected_brand_revision"] = "stage1-brand-interpretation-0731-v4"
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CommandError, match="repair_manifest_invalid"):
        reclassify_posts._load_manifest(path)
    payload["selected_brand_revision"] = "stage1-brand-interpretation-0731-v5"
    payload["posts"]["123"].pop("promoted_subjects")
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CommandError, match="repair_manifest_invalid_row"):
        reclassify_posts._load_manifest(path)


def test_apply_stops_at_contended_writer_before_any_reopen(tmp_path, monkeypatch):
    manifest_path = tmp_path / "reviewed.json"
    manifest_path.write_text(json.dumps(_manifest(["123"])), encoding="utf-8")
    monkeypatch.setattr(reclassify_posts, "_preflight", lambda ids, rows: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused.invalid/pushinweight_staging")
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    from x_monitor import config
    monkeypatch.setattr(
        config, "load_config",
        lambda path: SimpleNamespace(llm=SimpleNamespace(literal_translation_v2_enabled=True)),
    )

    @contextmanager
    def coordination(*args, **kwargs):
        yield

    @contextmanager
    def contended_writer(**kwargs):
        yield SimpleNamespace(acquired=False)

    monkeypatch.setattr(reclassify_posts, "acquire_harvest_coordination_lock", coordination)
    monkeypatch.setattr(reclassify_posts, "harvest_writer_lock", contended_writer)
    with pytest.raises(CommandError, match="repair_writer_lock_unavailable"):
        reclassify_posts.Command().handle(post_id=["123"], manifest=manifest_path, apply=True)


@pytest.mark.parametrize("database_url,environment,error", [
    ("postgresql://db/pushinweight_shadow", "production", "repair_requires_staging_environment"),
    ("postgresql://db/pushinweight_shadow", "staging", "repair_requires_staging_database"),
    ("postgresql://db/pushinweight_staging", "production", "repair_requires_staging_environment"),
])
def test_apply_target_rejects_production(database_url, environment, error):
    with pytest.raises(CommandError, match=error):
        reclassify_posts._require_staging_target(database_url, environment)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_rejected_repair_restores_completed_queue_state_before_cron_can_retry():
    from core.models import Post, PostEnrichmentState
    from django.utils import timezone

    post = Post.objects.create(tweet_id="123", text="source")
    state = PostEnrichmentState.objects.create(
        post=post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_attempts=2,
    )
    snapshot = {field: getattr(state, field) for field in reclassify_posts._QUEUE_FIELDS}
    state.classification_status = PostEnrichmentState.Status.PENDING
    state.classification_attempts = 1
    state.classification_next_attempt_at = timezone.now()
    state.claim_run_id = "rejected-repair"
    state.save()

    reclassify_posts._restore_unpublished_queue_states({"123": snapshot})

    state.refresh_from_db()
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_attempts == 2
    assert state.classification_next_attempt_at is None
    assert state.claim_run_id == ""


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_apply_incomplete_restores_queue_before_releasing_locks(tmp_path, monkeypatch):
    from core.models import Post, PostEnrichmentState
    from x_monitor import config

    post = Post.objects.create(tweet_id="123", text="source")
    PostEnrichmentState.objects.create(
        post=post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    manifest_path = tmp_path / "reviewed.json"
    manifest_path.write_text(json.dumps(_manifest(["123"])), encoding="utf-8")
    monkeypatch.setattr(reclassify_posts, "_preflight", lambda ids, rows: None)
    monkeypatch.setattr(config, "load_config", lambda path: SimpleNamespace(
        llm=SimpleNamespace(literal_translation_v2_enabled=True),
    ))
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused.invalid/pushinweight_staging")
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")

    @contextmanager
    def coordination(*args, **kwargs):
        yield

    @contextmanager
    def writer(**kwargs):
        yield SimpleNamespace(acquired=True)

    class RejectedRunner:
        _errors = ["post_fetch.repair_manifest_mismatch"]

        def __init__(self, **kwargs):
            pass

        def _run_post_fetch(self, *args, **kwargs):
            state = PostEnrichmentState.objects.get(post_id="123")
            assert state.classification_status == PostEnrichmentState.Status.PENDING
            state.classification_error_code = "repair_manifest_mismatch"
            state.classification_next_attempt_at = None
            state.save()
            return {"n_classifications_published": 0}

    monkeypatch.setattr(reclassify_posts, "acquire_harvest_coordination_lock", coordination)
    monkeypatch.setattr(reclassify_posts, "harvest_writer_lock", writer)
    monkeypatch.setattr(reclassify_posts, "CycleRunner", RejectedRunner)
    with pytest.raises(CommandError, match="repair_incomplete"):
        reclassify_posts.Command().handle(post_id=["123"], manifest=manifest_path, apply=True)

    state = PostEnrichmentState.objects.get(post_id="123")
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_next_attempt_at is None
    assert state.classification_error_code == ""


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_real_preview_reads_complete_exact_row_without_writing(tmp_path, monkeypatch, capsys):
    from core.models import (
        Brand, Post, PostBrand, PostBrandClassificationState,
        PostEnrichmentState, PostTranslationArtifact, PostTranslationText,
    )
    from monitor.post_artifacts import source_content_fingerprint
    from django.utils import timezone

    post = Post.objects.create(tweet_id="123", text="Token Machine Day 1", lang_detected="en")
    brand, _ = Brand.objects.get_or_create(
        nickname="glm", defaults={"display_name": "GLM"},
    )
    PostBrand.objects.create(post=post, brand=brand)
    state = PostEnrichmentState.objects.create(
        post=post, translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    fingerprint = "a" * 64
    PostBrandClassificationState.objects.create(
        post=post, brand=brand, contract_version="stage1-v1",
        taxonomy_version="stage1-taxonomy-v4", prompt_version="stage1-two-role-merge-0731-v5",
        model="fixture", source_language="en", input_context_fingerprint=fingerprint,
        outcome="classified",
    )
    artifact = PostTranslationArtifact.objects.create(
        post=post, source_content_fingerprint=source_content_fingerprint(post),
        source_language="en", prompt_version="fixture", model="fixture",
        provider_role="literal_translation", state=PostTranslationArtifact.State.SUCCEEDED,
        is_current=True, started_at=timezone.now(), completed_at=timezone.now(),
    )
    for locale in ("en", "zh-cn", "ja"):
        PostTranslationText.objects.create(artifact=artifact, locale=locale, text="Token Machine Day 1")
    manifest_path = tmp_path / "reviewed.json"
    manifest_path.write_text(json.dumps(_manifest(["123"])), encoding="utf-8")
    from x_monitor import config
    monkeypatch.setattr(
        config, "load_config",
        lambda path: SimpleNamespace(llm=SimpleNamespace(literal_translation_v2_enabled=True)),
    )
    reclassify_posts.Command().handle(post_id=["123"], manifest=manifest_path, apply=False)

    state.refresh_from_db()
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert json.loads(capsys.readouterr().out)["status"] == "preview"

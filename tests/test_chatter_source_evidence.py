"""Regression proofs for attributable, bounded and recoverable ranked evidence."""

import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from core.models import (
    CollectionObservation,
    CollectionRequest,
    CollectionRun,
    OriginalContent,
    OriginalContentRun,
    Post,
    SearchQuery,
)
from monitor.editorial.chatter_gathering import gather_trends
from tests.test_chatter_gathering import (
    ranked as ranked,  # noqa: PLC0414 -- shared parametrized fixture
)
from tests.test_chatter_gathering import source_response
from x_monitor.x_client import XClient

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def saved(run, identity, text="Original headline 1", **values):
    return Post.objects.create(tweet_id=identity, text=text, author_handle="reporter",
                               created_at=run.facts_as_of - timedelta(minutes=1), **values)


def transport(run, monkeypatch, rows, **pagination):
    client = XClient(api_key="fixture-only", max_retries=0)
    send = Mock(return_value=source_response(rows, **pagination))
    monkeypatch.setattr(client, "_get_bounded", send)
    return client, send


def wire(run, identity, text="Original headline 1"):
    return {"id": identity, "text": text,
            "createdAt": (run.facts_as_of - timedelta(minutes=1)).isoformat(),
            "author": {"id": "991", "userName": "verified_source"}}


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_unverified_saved_quote_does_not_suppress_source_gathering(ranked, monkeypatch):
    run, cfg = ranked
    carrier = saved(run, "82001", "An unrelated comment", quoted_text="Original headline 1")
    client, send = transport(run, monkeypatch, [wire(run, "82002")])
    assert gather_trends(run.pk, cfg=cfg, x_client=client)["status"] == "discovered"
    send.assert_called_once()
    run.refresh_from_db()
    entry = run.outcome["gathering"]["leads"][0]
    assert entry["existing_ids"] == [carrier.pk]
    assert entry["qualified_ids"] == ["82002"]
    assert {gap["code"] for gap in entry["source_gaps"]} >= {"quote_clock_missing", "quote_author_missing"}
    assert list(OriginalContent.objects.get(run=run).consideration_sources.values_list("post_id", flat=True)) == ["82002"]


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_fresh_carrier_can_support_a_verified_older_quote_without_new_request(ranked):
    run, cfg = ranked
    quote = Post.objects.create(tweet_id="82011", text="Original headline 1", author_handle="maker",
                                created_at=run.facts_as_of - timedelta(days=7))
    saved(run, "82012", "Fresh reactions to this old meme", quoted_text=quote.text, quoted_status_id=quote)
    client = Mock()
    assert gather_trends(run.pk, cfg=cfg, x_client=client)["status"] == "discovered"
    client.run_search_pages.assert_not_called()
    row = OriginalContent.objects.get(run=run)
    assert row.consideration_sources.get(post_id=quote.pk).usage == "background"


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_gather_completion_is_one_state_write_and_selection_waits_for_commit(
    ranked, monkeypatch, django_capture_on_commit_callbacks
):
    run, cfg = ranked
    saved(run, "82021")
    original = OriginalContentRun.save

    def save(row, *args, **kwargs):
        if row.pk == run.pk and row.outcome.get("phase") == "discovered":
            assert row.discovery_state == "complete"
            assert row.execution_state == "running"
        return original(row, *args, **kwargs)

    monkeypatch.setattr(OriginalContentRun, "save", save)
    queued = Mock()
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert gather_trends(run.pk, cfg=cfg, enqueue=queued)["status"] == "discovered"
        queued.assert_not_called()
    assert len(callbacks) == 1
    queued.assert_called_once_with("select", run.pk)


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_saved_split_gather_completion_is_repaired_without_source_calls(ranked):
    run, cfg = ranked
    saved(run, "82031")
    assert gather_trends(run.pk, cfg=cfg)["status"] == "discovered"
    OriginalContentRun.objects.filter(pk=run.pk).update(discovery_state="pending")
    client = Mock(side_effect=AssertionError("saved completion must not need providers"))
    assert gather_trends(run.pk, cfg=cfg, x_client=client)["status"] == "already_discovered"
    run.refresh_from_db()
    assert run.discovery_state == "complete"
    client.assert_not_called()


@pytest.mark.parametrize("ranked", [1], indirect=True)
@pytest.mark.parametrize("pagination", [{"more": True}, {"more": True, "cursor": "repeated"}])
def test_partial_pagination_keeps_usable_support_but_never_reports_complete(ranked, monkeypatch, pagination):
    run, cfg = ranked
    client, send = transport(run, monkeypatch, [wire(run, "82041")], **pagination)
    assert gather_trends(run.pk, cfg=cfg, x_client=client)["status"] == "discovered"
    assert OriginalContent.objects.filter(run=run, appearance_kind="personalized_trend").count() == 1
    run.refresh_from_db()
    assert run.outcome["gathering_incomplete"] is True
    assert run.outcome["gathering"]["leads"][0]["query_state"] == "partial"
    assert CollectionRun.objects.get(content_run=run, job__job_key__startswith="chatter-search:").status != "success"
    assert send.call_count in (1, 2)


def test_broad_saved_lead_is_sampled_before_a_supported_sibling_is_admitted(ranked):
    run, cfg = ranked
    Post.objects.bulk_create([Post(tweet_id=str(83000 + n), text="Original headline 1", author_handle="reporter",
                                    created_at=run.facts_as_of - timedelta(minutes=1)) for n in range(201)])
    saved(run, "83999", "Original headline 2")
    assert gather_trends(run.pk, cfg=cfg)["status"] == "discovered"
    rows = list(OriginalContent.objects.filter(run=run, appearance_kind="personalized_trend"))
    assert len(rows) == 2
    assert any(row.consideration_sources.filter(post_id="83999").exists() for row in rows)
    run.refresh_from_db()
    first = run.outcome["gathering"]["leads"][0]
    assert len(first["qualified_ids"]) == first["qualified_count"] == 201
    assert first["matched_count"] == 201
    assert first["context_clipped"] and first["context_omitted_count"] > 0
    assert len(run.snapshot["sources"]) <= 200
    assert len(json.dumps(run.snapshot, ensure_ascii=False, allow_nan=False).encode()) <= 240000


def test_long_saved_sources_obey_the_existing_packet_byte_bound(ranked):
    run, cfg = ranked
    Post.objects.bulk_create([Post(tweet_id=str(84000 + n), text="Original headline 1 " + "漢" * 5900,
                                    author_handle="reporter", created_at=run.facts_as_of - timedelta(minutes=1)) for n in range(30)])
    saved(run, "84999", "Original headline 2")
    assert gather_trends(run.pk, cfg=cfg)["status"] == "discovered"
    assert OriginalContent.objects.filter(run=run, appearance_kind="personalized_trend").count() == 2
    run.refresh_from_db()
    assert len(json.dumps(run.snapshot, ensure_ascii=False, allow_nan=False).encode()) <= 240000
    assert run.outcome["gathering"]["leads"][0]["context_clipped"] is True


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_provider_retrieval_and_receipts_are_not_truncated_to_the_context_sample(ranked, monkeypatch):
    run, cfg = ranked
    client, send = transport(run, monkeypatch, [wire(run, str(85000 + n)) for n in range(201)])
    assert gather_trends(run.pk, cfg=cfg, x_client=client)["status"] == "discovered"
    send.assert_called_once()
    assert Post.objects.filter(pk__gte="85000", pk__lte="85200").count() == 201
    request = CollectionRequest.objects.get(attempt__run__content_run=run, endpoint_url__contains="advanced_search")
    assert request.raw_count == 201 and CollectionObservation.objects.filter(request=request).count() == 201
    run.refresh_from_db()
    entry = run.outcome["gathering"]["leads"][0]
    assert len(entry["raw_ids"]) == len(entry["qualified_ids"]) == 201
    assert entry["context_clipped"] and len(entry["context_ids"]) < 201


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_fresh_evidence_is_reserved_before_cumulative_history(ranked, monkeypatch):
    from monitor.editorial.chatter_history import (
        attach_sources,
        freeze_sources,
        project_post,
    )
    from tests.test_original_content_consideration import consideration

    run, cfg = ranked
    previous = {}
    for index in range(3):
        prior = consideration()
        prior.run.facts_as_of = run.facts_as_of - timedelta(hours=2)
        prior.run.save(update_fields=["facts_as_of"])
        posts = [Post.objects.create(tweet_id=str(86000 + index * 100 + n), text="Old context",
                                     author_handle="historian", created_at=run.facts_as_of - timedelta(days=3)) for n in range(75)]
        freeze_sources(prior.run, [project_post(post) for post in posts], fence=prior.run.fence)
        attach_sources(prior, [post.pk for post in posts], fence=prior.run.fence)
        previous[str(prior.development_id)] = prior
    monkeypatch.setattr("monitor.editorial.chatter_chain._history", lambda *args, **kwargs: (
        previous, {}, {"board_may_be_capped": False}))
    saved(run, "86999")
    assert gather_trends(run.pk, cfg=cfg)["status"] == "discovered"
    assert OriginalContent.objects.get(run=run, appearance_kind="personalized_trend").consideration_sources.filter(post_id="86999").exists()
    run.refresh_from_db()
    assert len(run.snapshot["sources"]) + len(run.snapshot.get("source_refs", {})) <= 200
    assert run.outcome["history_context"]["clipped"] is True


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_ranked_recipe_is_saved_without_redundant_development_query(ranked):
    run, cfg = ranked
    saved(run, "87001")
    assert gather_trends(run.pk, cfg=cfg)["status"] == "discovered"
    row = OriginalContent.objects.get(run=run)
    run.refresh_from_db()
    assert run.outcome["gathering"]["leads"][0]["recipe"]["query"]
    assert row.selection["query_sha256"] == run.outcome["gathering"]["leads"][0]["recipe"]["query_sha256"]
    assert not SearchQuery.objects.filter(development=row.development).exists()


@pytest.mark.parametrize("ranked", [1], indirect=True)
@pytest.mark.parametrize("legacy_checkpoint", [False, True])
def test_expired_captured_prefix_resumes_without_repeating_physical_requests(ranked, monkeypatch, legacy_checkpoint):
    import monitor.editorial.chatter_gathering as gathering
    from monitor.editorial.chatter_sources import source_resume_is_safe

    run, cfg = ranked
    client, send = transport(run, monkeypatch, [wire(run, "88001")], more=True, cursor="next")
    save_checkpoint = gathering._save
    stopped = False

    def worker_loss(current, value):
        nonlocal stopped
        save_checkpoint(current, value)
        if value["leads"][0]["raw_ids"] and not stopped:
            stopped = True
            raise SystemExit("fixture worker loss after saved first-page prefix")

    monkeypatch.setattr(gathering, "_save", worker_loss)
    with pytest.raises(SystemExit):
        gather_trends(run.pk, cfg=cfg, x_client=client)
    send.assert_called_once()
    execution = CollectionRun.objects.get(content_run=run, job__job_key__startswith="chatter-search:")
    CollectionRun.objects.filter(pk=execution.pk).update(
        completed_at=None, status="running", execution_state="running",
        lease_expires_at=timezone.now() - timedelta(seconds=1))
    run.refresh_from_db()
    if legacy_checkpoint:
        del run.outcome["gathering"]["leads"][0]["captured_request_ids"]
        run.save(update_fields=["outcome"])
    assert source_resume_is_safe(run) is True
    monkeypatch.setattr(gathering, "_save", save_checkpoint)
    second_client, second_send = transport(run, monkeypatch, [wire(run, "88001"), wire(run, "88002")])
    assert gather_trends(run.pk, cfg=cfg, x_client=second_client, resume=True)["status"] == "discovered"
    second_send.assert_called_once()
    assert second_send.call_args.args[1]["cursor"] == "next"
    run.refresh_from_db()
    entry = run.outcome["gathering"]["leads"][0]
    assert entry["raw_ids"] == ["88001", "88001", "88002"]
    assert entry["qualified_ids"] == ["88001", "88002"]
    assert entry["query_state"] == "drained"
    assert CollectionRequest.objects.filter(attempt__run=execution).count() == 2
    assert execution.attempts.count() == 2


@pytest.mark.parametrize("ranked", [1], indirect=True)
@pytest.mark.parametrize("fault", ["active_lease", "unknown_send", "archive_checksum"])
def test_source_recovery_rejects_live_or_unverifiable_captures(ranked, monkeypatch, fault):
    from monitor.editorial.chatter_gathering import compile_recipe
    from monitor.editorial.chatter_sources import SourceSession, source_resume_is_safe
    from monitor.editorial.chatter_trends import read_ranked_batch
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import SEARCH_PATH

    run, cfg = ranked
    recipe = compile_recipe(read_ranked_batch(run.pk)["leads"][0], run.facts_as_of)
    session = SourceSession(run, cfg, purpose=TwitterApiCredentialPurpose.ON_DEMAND, client=XClient(api_key="fixture-only"))
    request = session.start(SEARCH_PATH, {"query": recipe["query"], "queryType": "Latest", "limit": 20})
    if fault != "unknown_send":
        session.finish(request, {"outcome": "received", "status_code": 200,
                                "body": json.dumps({"tweets": [wire(run, "88011")], "has_next_page": False}).encode()})
    if fault != "active_lease":
        CollectionRun.objects.filter(pk=session.claim.run_id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    if fault == "archive_checksum":
        monkeypatch.setattr("monitor.editorial.chatter_sources.read_document", Mock(side_effect=ValueError("capture checksum mismatch")))
    assert source_resume_is_safe(run) is False
    never = Mock(side_effect=AssertionError("unreconciled physical request must not be resent"))
    monkeypatch.setattr(session.client, "_get_bounded", never)
    with pytest.raises(ValueError):
        SourceSession(run, cfg, purpose=TwitterApiCredentialPurpose.ON_DEMAND, client=session.client, resume=True)
    never.assert_not_called()


def test_saved_empty_split_completion_is_repaired_without_any_provider(monkeypatch):
    from tests.test_chatter_trends import (
        discover,
        official_response,
        start,
        trends_config,
    )

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = trends_config()
    run = start(cfg)
    assert discover(run, cfg, official_response(0))[0]["status"] == "empty"
    assert gather_trends(run.pk, cfg=cfg)["status"] == "empty"
    OriginalContentRun.objects.filter(pk=run.pk).update(discovery_state="pending", execution_state="running")
    assert gather_trends(run.pk, cfg=cfg)["status"] == "already_discovered"
    run.refresh_from_db()
    assert run.discovery_state == "complete" and run.execution_state == "completed"
    assert run.provider_calls.count() == 0


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_gathered_quote_identity_reaches_actual_c1_and_used_publication(ranked):
    from pathlib import Path

    from monitor.cycle import persist_x_post
    from monitor.editorial.chatter_history import read_sources
    from monitor.editorial.config import load_editorial_config
    from monitor.editorial.graphics_entry import prepare_selected_story
    from monitor.editorial.graphics_packages import materialize_package
    from monitor.editorial.graphics_pipeline import advance_step
    from monitor.editorial.voices import load_bound_voices
    from monitor.original_content import digest
    from tests.test_graphics_chatter_adapter import copy_result, decode_handoff

    run, cfg = ranked
    quote, _ = persist_x_post({"id": "89001", "text": "Original headline 1 announced",
        "author_id": "99871", "author_handle": "maker",
        "created_at": (run.facts_as_of - timedelta(days=7)).isoformat()})
    carrier = saved(run, "89002", "Fresh response to this old announcement", quoted_text=quote.text, quoted_status_id=quote)
    assert gather_trends(run.pk, cfg=cfg)["status"] == "discovered"
    row = OriginalContent.objects.get(run=run)
    row.consideration_state, row.source_locale_id, row.editorial_group = "selected", "en", "rest"
    row.save(update_fields=["consideration_state", "source_locale", "editorial_group"])
    config = load_editorial_config(Path(__file__).resolve().parents[1] / "config/editorial-chatter-staging.yaml")
    run.config_snapshot = {"schema_version": 1, "editorial": config.model_dump(mode="json"),
                           "voices": {key: value.model_dump(mode="json") for key, value in load_bound_voices(config).items()}}
    run.save(update_fields=["config_snapshot"])
    Post.objects.filter(pk=quote.pk).update(text="A later mutable edit", author_handle="wrong_live_name")
    request = prepare_selected_story(content_id=row.pk, run_id=run.pk, locale="en")
    facts = request["handoff"]["fact_items"]
    quoted = next(fact for fact in facts if fact["source_role"] == "quoted")
    original = next(source for source in read_sources(row) if source["id"] == quote.pk)
    assert quoted["source_post_id"] == quote.pk and quoted["source_post_id"] != carrier.pk
    assert quoted["created_at"] == original["created_at"]
    assert quoted["speaker"] == "maker" and quoted["source_usage"] == "background"
    assert quoted["speaker_id"] == original["author_id"] == "99871"
    assert quoted["snapshot_hash"] == digest(original) and quoted["source_refs"] == [original["url"]]
    producing, output = materialize_package(request)
    route = request["writer_route"]
    bodies = []

    def provider(endpoint, key, body, **kwargs):
        bodies.append(body)
        return 200, json.dumps({"model": route["model"], "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(copy_result(used=(quoted["fact_id"],)))}}]}).encode()

    assert advance_step(producing.pk, keys={route["key_env"]: "fixture-only"}, transport=provider)["state"] == "completed"
    actual = next(fact for fact in decode_handoff(bodies[0])["fact_items"] if fact["fact_id"] == quoted["fact_id"])
    assert actual == quoted
    text = output.localized_texts.get(locale="en")
    assert list(text.sources.values_list("post_id", "source_hash")) == [(quote.pk, digest(original))]

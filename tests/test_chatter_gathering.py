"""Ranked trends gather actual sources before the existing editorial selector."""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from core.models import OriginalContent, Post
from tests.test_chatter_trends import (
    discover,
    official_response,
    rank_wire,
    start,
    trends_config,
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture
def ranked(monkeypatch, request):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-only")
    from core.models import Language, Locale

    for code in ("en", "ja", "zh-CN"):
        Language.objects.get_or_create(pk=code.split("-")[0])
        Locale.objects.get_or_create(
            pk=code, defaults={"language_id": code.split("-")[0]}
        )
    cfg = trends_config()
    run = start(cfg)
    count = getattr(request, "param", 2)
    result, _, _ = discover(
        run, cfg, official_response(count), Mock(return_value=rank_wire(count))
    )
    assert result["status"] == "ranked"
    run.refresh_from_db()
    return run, cfg


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_saved_source_satisfies_lead_without_constructing_network_client(
    ranked, monkeypatch, django_capture_on_commit_callbacks
):
    def fail(run, stage, exc):
        raise exc

    monkeypatch.setattr("monitor.editorial.chatter_chain._failure", fail)
    from monitor.editorial.chatter_gathering import gather_trends
    from monitor.editorial.chatter_history import read_sources

    run, cfg = ranked
    source = Post.objects.create(
        tweet_id="7001",
        text="Original headline 1 confirmed by the lab.",
        author_handle="reporter",
        lang="en",
        created_at=run.facts_as_of - timedelta(hours=1),
    )
    client = Mock()
    queued = []
    with django_capture_on_commit_callbacks(execute=True):
        result = gather_trends(
            run.pk, cfg=cfg, x_client=client, enqueue=lambda *args: queued.append(args)
        )
    assert result["status"] == "discovered", result
    row = OriginalContent.objects.get(run=run, appearance_kind="personalized_trend")
    assert row.discovery_call_id == run.outcome["trends"]["rank_call_id"]
    assert row.shortlist_position == 1
    assert read_sources(row)[0]["id"] == source.pk
    client.run_search_pages.assert_not_called()
    run.refresh_from_db()
    leads = run.outcome["gathering"]["leads"]
    assert leads[0]["existing_ids"] == [source.pk]
    assert leads[0]["coverage"] == "saved_support"
    assert queued == [("select", run.pk)]


def test_recipe_uses_original_members_and_freezes_exact_window(ranked):
    from monitor.editorial.chatter_gathering import compile_recipe, recipe_predicate
    from monitor.editorial.chatter_trends import read_ranked_batch

    run, _ = ranked
    lead = read_ranked_batch(run.pk)["leads"][0]
    lead["title"] = "from:invented Benchmark scores 999"
    recipe = compile_recipe(lead, run.facts_as_of)
    assert recipe["schema_version"] == 1
    assert recipe["original_headlines"] == ["Original headline 1"]
    assert "invented" not in recipe["query"] and "999" not in recipe["query"]
    assert recipe["query"].endswith(
        f" since_time:{int((run.facts_as_of - timedelta(hours=24)).timestamp())} until_time:{int(run.facts_as_of.timestamp())}"
    )
    assert len(recipe["query"].encode("utf-8")) <= 512
    good = Post.objects.create(
        tweet_id="7002",
        text="Original headline 1",
        created_at=run.facts_as_of - timedelta(seconds=1),
    )
    Post.objects.create(
        tweet_id="7003", text="Original headline 1", created_at=run.facts_as_of
    )
    Post.objects.create(
        tweet_id="7004", text="Original headline 2", created_at=good.created_at
    )
    assert list(
        Post.objects.filter(recipe_predicate(recipe)).values_list("pk", flat=True)
    ) == [good.pk]


def test_recipe_fails_before_io_when_final_utf8_query_exceeds_cap():
    from monitor.editorial.chatter_gathering import compile_recipe

    with pytest.raises(ValueError, match="512"):
        compile_recipe({"headlines": [{"trend_name": "漢" * 200}]}, timezone.now())


def source_response(rows, *, more=False, cursor=None):
    import json
    from types import SimpleNamespace

    body = {"tweets": rows, "has_next_page": more, "next_cursor": cursor}
    return SimpleNamespace(
        status_code=200,
        headers={},
        content=json.dumps(body).encode(),
        json=lambda: body,
    )


def test_shared_pagination_partial_prefix_quotes_and_saved_sibling(ranked, monkeypatch):
    from core.models import CollectionRequest
    from monitor.editorial.chatter_gathering import gather_trends
    from monitor.editorial.chatter_history import read_source_memberships
    from x_monitor.x_client import XClient

    run, cfg = ranked
    Post.objects.create(
        tweet_id="7112",
        text="Original headline 2 confirmed",
        author_handle="saved",
        lang="ja",
        created_at=run.facts_as_of - timedelta(minutes=30),
    )
    quote_time = run.facts_as_of - timedelta(days=2)
    raw = {
        "id": "7110",
        "text": "A reporter quotes the primary source.",
        "createdAt": (run.facts_as_of - timedelta(minutes=10)).isoformat(),
        "lang": "en",
        "author": {"id": "981", "userName": "reporter"},
        "quoted_tweet": {
            "id": "7111",
            "text": "Original headline 1 announced",
            "createdAt": quote_time.isoformat(),
            "author": {"id": "982", "userName": "actual_author"},
        },
    }
    client = XClient(api_key="fixture-only", max_retries=0)
    seen = []

    def response(url, params, timeout):
        seen.append(params)
        if len(seen) == 1:
            # All recipes are durably saved before the source request starts.
            run.refresh_from_db()
            assert len(run.outcome["gathering"]["leads"]) == 2
            return source_response([raw], more=True, cursor="next")
        raise TimeoutError("fixture dropped second page")

    monkeypatch.setattr(client, "_get_bounded", response)
    result = gather_trends(run.pk, cfg=cfg, x_client=client)
    assert result["status"] == "discovered", result
    assert len(seen) == 2 and seen[1]["cursor"] == "next"
    assert "since_time:" in seen[0]["query"] and "until_time:" in seen[0]["query"]
    assert len(seen[0]["query"].encode()) <= 512
    rows = list(OriginalContent.objects.filter(run=run).order_by("shortlist_position"))
    assert len(rows) == 2
    memberships = read_source_memberships(rows[0])
    quote = next(
        (membership, source)
        for membership, source in memberships
        if source["id"] == "7111"
    )
    assert quote[0].usage == "background"
    assert (
        quote[1]["author_id"] == "982" and quote[1]["author_handle"] == "actual_author"
    )
    assert datetime.fromisoformat(quote[1]["created_at"]) == quote_time
    run.refresh_from_db()
    assert run.outcome["gathering"]["leads"][0]["coverage"] == "partial"
    assert run.outcome["gathering"]["leads"][1]["coverage"] == "saved_support"
    assert (
        CollectionRequest.objects.filter(
            attempt__run__content_run=run, endpoint_url__contains="advanced_search"
        ).count()
        == 2
    )
    assert (
        rows[0].selection["source_identities"][0]["release_evidence"]["state"]
        == "pending"
    )


def test_pending_and_completed_empty_release_evidence_remain_distinct(monkeypatch):
    from types import SimpleNamespace

    from monitor.editorial.chatter_gathering import publication_evidence

    reader = Mock(return_value=None)
    monkeypatch.setattr(
        "monitor.editorial.chatter_gathering.importlib.import_module",
        lambda name: SimpleNamespace(read_publication_findings=reader),
    )
    assert publication_evidence("123")["state"] == "pending"
    reader.return_value = ()
    assert publication_evidence("123")["state"] == "completed_no_release"
    reader.return_value = (
        {"claim_id": 12, "finding": {"observed_name": "actual saved finding"}},
    )
    assert publication_evidence("123")["findings"][0]["claim_id"] == 12


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_captured_source_replays_shared_paginator_without_credentials_or_new_send(
    ranked, monkeypatch
):
    import json

    from monitor.editorial.chatter_gathering import compile_recipe
    from monitor.editorial.chatter_sources import SourceSession
    from monitor.editorial.chatter_trends import read_ranked_batch
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import SEARCH_PATH, XClient

    run, cfg = ranked
    recipe = compile_recipe(read_ranked_batch(run.pk)["leads"][0], run.facts_as_of)
    first = SourceSession(
        run,
        cfg,
        purpose=TwitterApiCredentialPurpose.ON_DEMAND,
        client=XClient(api_key="fixture-only"),
    )
    token = first.start(
        SEARCH_PATH, {"query": recipe["query"], "queryType": "Latest", "limit": 20}
    )
    first.finish(
        token,
        {
            "outcome": "received",
            "status_code": 200,
            "body": json.dumps(
                {
                    "tweets": [
                        {
                            "id": "7220",
                            "text": "Original headline 1",
                            "createdAt": (
                                run.facts_as_of - timedelta(minutes=1)
                            ).isoformat(),
                            "author": {"id": "991", "userName": "saved_reporter"},
                        }
                    ],
                    "has_next_page": False,
                }
            ).encode(),
        },
    )
    first.close(success=False)
    monkeypatch.delenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", raising=False)
    resumed = SourceSession(
        run, cfg, purpose=TwitterApiCredentialPurpose.ON_DEMAND, resume=True
    )
    never = Mock(side_effect=AssertionError("a captured source must not be sent again"))
    monkeypatch.setattr(resumed.client, "_get_bounded", never)
    pages = list(resumed.search_pages(recipe["query"]))
    assert len(pages) == 1 and pages[0].items[0]["id"] == "7220"
    resumed.ingest(pages[0].items)
    never.assert_not_called()
    assert Post.objects.get(pk="7220").author_handle == "saved_reporter"
    resumed.close(success=True)


def test_recipe_expands_saved_multiword_aliases_without_unrelated_brand_facts():
    from core.models import Brand, BrandSearchTerm
    from monitor.editorial.chatter_gathering import compile_recipe, recipe_predicate

    brand = Brand.objects.create(nickname="fixture-small-lab")
    for alias in ("Small Lab", "SLab"):
        BrandSearchTerm.objects.create(brand=brand, term=alias)
    cutoff = timezone.now().replace(microsecond=0)
    recipe = compile_recipe(
        {"headlines": [{"trend_name": "Small Lab releases Widget 3"}]}, cutoff
    )
    good = Post.objects.create(
        tweet_id="7331",
        text="SLab releases Widget 3",
        created_at=cutoff - timedelta(minutes=1),
    )
    Post.objects.create(
        tweet_id="7332", text="Other lab releases Widget 3", created_at=good.created_at
    )
    assert '"SLab"' in recipe["query"]
    assert list(
        Post.objects.filter(recipe_predicate(recipe)).values_list("pk", flat=True)
    ) == [good.pk]


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_production_entry_continues_to_existing_six_pool_selector(ranked, monkeypatch, django_capture_on_commit_callbacks):
    import json

    from monitor.editorial.chatter_chain import run_chatter, select_chatter
    from monitor.editorial.chatter_trends import envelope_for
    from tests.test_chatter_chain import wire
    from tests.test_chatter_discovery import selection

    monkeypatch.setenv("XAI_API_KEY_PW", "fixture-only")
    run, cfg = ranked
    Post.objects.create(
        tweet_id="7441",
        text="Original headline 1 confirmed.",
        author_handle="reporter",
        lang="en",
        created_at=run.facts_as_of - timedelta(minutes=1),
    )
    queued = []
    ranker = Mock(side_effect=AssertionError("completed ranking must be reused"))
    with django_capture_on_commit_callbacks(execute=True):
        result = run_chatter(
            envelope_for(run),
            cfg=cfg,
            transport=ranker,
            enqueue=lambda *args: queued.append(args),
        )
    assert result["status"] == "discovered", result
    ranker.assert_not_called()
    assert queued == [("select", run.pk)]
    requests = []

    def selector(endpoint, key, body, **kwargs):
        payload = json.loads(body["input"][1]["content"])
        requests.append(payload)
        assert len(payload["source_language_evidence"]) == 1
        assert payload["candidates"][0]["persistence"]["periods"][0]["state"] == "fresh"
        data = selection(payload["candidates"][0])
        data["candidate_tags"][0]["group_policy_ref"] = payload["giant_group_policy"][
            "policy_ref"
        ]
        data["candidate_tags"][0]["group_evidence_post_ids"] = ["7441"]
        return wire(data)

    result = select_chatter(
        run.pk, cfg=cfg, transport=selector, enqueue=lambda *args: queued.append(args)
    )
    assert result["status"] == "selected", result
    assert len(requests) == 1
    assert run.provider_calls.filter(stage="selector:0", state="completed").count() == 1
    row = OriginalContent.objects.get(run=run, appearance_kind="personalized_trend")
    assert (
        row.consideration_state == "selected"
        and row.source_locale_id == "en"
        and row.editorial_group == "rest"
    )


def test_common_roundup_does_not_merge_different_original_headlines(ranked):
    from monitor.editorial.chatter_gathering import gather_trends

    run, cfg = ranked
    Post.objects.create(
        tweet_id="7551",
        text="Original headline 1 and Original headline 2",
        author_handle="roundup",
        created_at=run.facts_as_of - timedelta(minutes=1),
    )
    assert gather_trends(run.pk, cfg=cfg)["status"] == "discovered"
    rows = list(
        OriginalContent.objects.filter(run=run, appearance_kind="personalized_trend")
    )
    assert len(rows) == 2 and rows[0].development_id != rows[1].development_id
    assert {
        tuple(row.consideration_sources.values_list("post_id", flat=True))
        for row in rows
    } == {("7551",)}


def test_empty_official_observation_is_healthy_without_fake_ranking_or_selector(
    monkeypatch,
):
    from core.models import EditorialStory
    from monitor.editorial.chatter_chain import run_chatter
    from monitor.editorial.chatter_history import appearance_history
    from monitor.editorial.chatter_trends import envelope_for

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = trends_config()
    run = start(cfg)
    result, _, ranker = discover(run, cfg, official_response(0))
    assert result["status"] == "empty"
    queued = Mock()
    assert run_chatter(envelope_for(run), cfg=cfg, enqueue=queued)["status"] == "empty"
    ranker.assert_not_called()
    queued.assert_not_called()
    run.refresh_from_db()
    assert run.discovery_state == "complete" and run.outcome["healthy_at"]
    assert run.provider_calls.count() == 0
    story = EditorialStory.objects.create(development_key="empty-history-fixture")
    history = appearance_history(
        story,
        run.facts_as_of,
        observed_at=timezone.now(),
        lane="personalized-trends-v1",
    )
    assert history["periods"][0]["state"] == "not_rediscovered"


def test_frozen_real_trend_controls_separate_lexical_support_and_window_eligibility():
    import json
    from pathlib import Path

    from core.models import Brand, BrandSearchTerm
    from monitor.editorial.chatter_gathering import (
        _matches,
        compile_recipe,
        recipe_predicate,
    )

    saved = json.loads(
        (
            Path(__file__).parent / "fixtures/chatter_trend_source_controls_v1.json"
        ).read_text()
    )
    # Fixture aliases are from the existing harvest policy's company entries.
    for key, aliases in (
        ("nvidia", ["NVIDIA", "英伟达", "輝達", "英偉達", "エヌビディア"]),
        ("anthropic", ["Anthropic"]),
    ):
        brand = Brand.objects.create(nickname=key)
        for alias in aliases:
            BrandSearchTerm.objects.create(brand=brand, term=alias)
    cutoff = datetime.fromisoformat(saved["cutoff"])
    sources = {post["tweet_id"]: post for post in saved["posts"]}
    lexical, eligible = [], []
    for lead in saved["leads"]:
        if str(lead["rank"]) not in saved["positive_post_ids"]:
            continue
        source = sources[saved["positive_post_ids"][str(lead["rank"])]]
        recipe = compile_recipe(lead, cutoff, context_leads=saved["leads"])
        assert recipe["query_bytes"] <= 512
        actual = {**source, "id": source["tweet_id"]}
        # Clock shift is a lexical-only control, explicitly not current support.
        lexical_source = {
            **actual,
            "created_at": (cutoff - timedelta(hours=1)).isoformat(),
        }
        if _matches(lexical_source, recipe):
            lexical.append(lead["rank"])
        if _matches(actual, recipe):
            eligible.append(lead["rank"])
        post = Post.objects.create(
            tweet_id=actual["id"],
            text=actual["text"],
            quoted_text=actual["quoted_text"],
            created_at=actual["created_at"],
        )
        assert Post.objects.filter(pk=post.pk).filter(
            recipe_predicate(recipe)
        ).exists() == _matches(actual, recipe)
    assert lexical == saved["lexical_expected_ranks"]
    assert eligible == saved["eligible_expected_ranks"]


def test_episode_and_exact_version_controls_reject_same_actor_other_developments():
    from core.models import Brand, BrandSearchTerm
    from monitor.editorial.chatter_gathering import (
        _matches,
        compile_recipe,
        recipe_predicate,
    )

    brand = Brand.objects.create(nickname="grok")
    BrandSearchTerm.objects.create(brand=brand, term="Grok")
    cutoff = timezone.now().replace(microsecond=0)
    recipe = compile_recipe(
        {"headlines": [{"trend_name": "Grok 4.8 skeleton meme wait"}]}, cutoff
    )
    for identity, text, expected in (
        ("7661", "Grok 4.8 skeleton meme", True),
        ("7662", "Grok 4.7 skeleton meme", False),
        ("7663", "Grok 4.80 skeleton meme", False),
        ("7664", "Grok 4.8 benchmark performance release", False),
    ):
        item = {
            "id": identity,
            "text": text,
            "created_at": (cutoff - timedelta(minutes=1)).isoformat(),
        }
        post = Post.objects.create(
            tweet_id=identity, text=text, created_at=item["created_at"]
        )
        assert _matches(item, recipe) is expected
        assert (
            Post.objects.filter(pk=post.pk).filter(recipe_predicate(recipe)).exists()
            is expected
        )


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_source_quote_after_cutoff_is_a_gap_without_fabricated_support(
    ranked, monkeypatch
):
    from monitor.editorial.chatter_gathering import gather_trends
    from x_monitor.x_client import XClient

    run, cfg = ranked
    raw = {
        "id": "7771",
        "text": "An unrelated comment",
        "createdAt": (run.facts_as_of - timedelta(minutes=1)).isoformat(),
        "author": {"id": "901", "userName": "reporter"},
        "quoted_tweet": {
            "id": "7772",
            "text": "Original headline 1",
            "createdAt": (run.facts_as_of + timedelta(minutes=1)).isoformat(),
            "author": {"id": "902", "userName": "future"},
        },
    }
    client = XClient(api_key="fixture-only", max_retries=0)
    monkeypatch.setattr(client, "_get_bounded", lambda *args: source_response([raw]))
    assert gather_trends(run.pk, cfg=cfg, x_client=client)["status"] == "discovered"
    assert not OriginalContent.objects.filter(run=run).exists()
    run.refresh_from_db()
    assert run.outcome["gathering"]["leads"][0]["coverage"] == "held"
    assert run.outcome["gathering_incomplete"] is True
    assert {"post_id": "7771", "code": "quote_after_cutoff"} in run.outcome[
        "gathering"
    ]["leads"][0]["source_gaps"]
    assert not run.outcome.get("healthy_at")


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_ranked_source_session_continues_past_legacy_four_request_cap(
    ranked, monkeypatch
):
    from core.models import CollectionRequest, CollectionRun
    from monitor.editorial.chatter_gathering import gather_trends
    from x_monitor.x_client import XClient

    run, cfg = ranked
    assert cfg.chatter.source_request_limit == 4
    client = XClient(api_key="fixture-only", max_retries=0)
    calls = []

    def response(url, params, timeout):
        calls.append(params)
        index = len(calls)
        return source_response(
            [
                {
                    "id": str(7900 + index),
                    "text": "Original headline 1",
                    "createdAt": (
                        run.facts_as_of - timedelta(minutes=index)
                    ).isoformat(),
                    "author": {"id": "998", "userName": "source"},
                }
            ],
            more=index < 6,
            cursor=str(index) if index < 6 else None,
        )

    monkeypatch.setattr(client, "_get_bounded", response)
    result = gather_trends(run.pk, cfg=cfg, x_client=client)
    assert result["status"] == "discovered", result
    assert len(calls) == 6
    job = (
        CollectionRun.objects.filter(
            content_run=run, job__job_key__startswith="chatter-search:"
        )
        .get()
        .job
    )
    assert job.max_requests is None and job.max_items is None
    assert job.max_seconds == 600 and job.max_bytes == 8_000_000
    assert CollectionRequest.objects.filter(attempt__run__job=job).count() == 6
    run.refresh_from_db()
    assert run.outcome["gathering"]["leads"][0]["query_state"] == "drained"
    assert len(run.outcome["gathering"]["leads"][0]["qualified_ids"]) == 6


@pytest.mark.parametrize("ranked", [1], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        {"operation": "x_cycle"},
        {"source_id": "github"},
        {"purpose": "catalog"},
        {"owner_kind": "account"},
        {"definition": {"version": 2, "options": {"workflow_version": "chatter-v1"}}},
        {"definition": {"version": 2, "options": {}}},
        {"max_bytes": None},
        {"max_seconds": None},
    ],
)
def test_sql_guard_allows_only_owned_ranked_null_request_item_limits(ranked, change):
    import json
    from uuid import uuid4

    from django.db import IntegrityError, connection, transaction

    from monitor.editorial.chatter_sources import SourceSession
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient

    run, cfg = ranked
    session = SourceSession(
        run,
        cfg,
        purpose=TwitterApiCredentialPurpose.ON_DEMAND,
        client=XClient(api_key="fixture-only"),
    )
    job = session.claim.job_id
    overrides = {"id": uuid4(), "job_key": "guard-fixture:" + str(uuid4()), **change}
    if change.get("owner_kind") == "account":
        from monitor.cycle import persist_x_post

        post, _ = persist_x_post(
            {
                "id": "8991",
                "text": "fixture owner",
                "author_id": "8992",
                "author_handle": "source_owner",
            }
        )
        overrides["owner_account_id"] = post.author_id
    columns, expressions, parameters = [], [], []
    from core.models import CollectionJob

    for field in CollectionJob._meta.concrete_fields:
        columns.append('"' + field.column + '"')
        if field.attname in overrides:
            value = overrides[field.attname]
            expressions.append("%s::jsonb" if field.attname == "definition" else "%s")
            parameters.append(
                json.dumps(value) if field.attname == "definition" else value
            )
        else:
            expressions.append('"' + field.column + '"')
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "INSERT INTO collection_jobs ("
            + ",".join(columns)
            + ") SELECT "
            + ",".join(expressions)
            + " FROM collection_jobs WHERE id=%s",
            parameters + [job],
        )
    session.close(success=True)


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_resource_guard_rollback_refuses_existing_nullable_jobs(ranked):
    from importlib import import_module

    from django.db import connection, transaction

    from monitor.editorial.chatter_sources import SourceSession
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient

    run, cfg = ranked
    session = SourceSession(
        run,
        cfg,
        purpose=TwitterApiCredentialPurpose.ON_DEMAND,
        client=XClient(api_key="fixture-only"),
    )
    migration = import_module("core.migrations.0230_chatter_source_resource_admission")
    with (
        pytest.raises(RuntimeError, match="still require"),
        transaction.atomic(),
        connection.schema_editor(atomic=False) as editor,
    ):
        migration.backwards(None, editor)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_functiondef('collection_typed_instruction_guard'::regproc)"
        )
        assert "chatter-trends-sources-v1" in cursor.fetchone()[0]
    session.close(success=True)


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_fresh_trend_upgrades_carried_memory_without_promoting_background(
    ranked, monkeypatch
):
    from monitor.editorial.chatter_gathering import gather_trends
    from monitor.editorial.chatter_history import (
        attach_sources,
        freeze_sources,
        project_post,
    )

    run, cfg = ranked
    Post.objects.create(
        tweet_id="8101",
        text="Original headline 1",
        author_handle="source",
        created_at=run.facts_as_of - timedelta(minutes=10),
    )
    assert gather_trends(run.pk, cfg=cfg)["status"] == "discovered"
    first = OriginalContent.objects.get(run=run)
    run.refresh_from_db()
    background = Post.objects.create(
        tweet_id="8102",
        text="Earlier attributable context",
        author_handle="prior",
        created_at=run.facts_as_of - timedelta(days=2),
    )
    freeze_sources(run, [project_post(background)], fence=run.fence)
    attach_sources(first, [background.pk], fence=run.fence, usage="background")
    later = run.facts_as_of + timedelta(hours=1)
    monkeypatch.setattr("monitor.editorial.chatter_trends.timezone.now", lambda: later)
    from monitor.editorial.chatter_trends import reserve_due_slot

    second = reserve_due_slot("second-memory-fixture", later, cfg=cfg, purpose="on-demand")[0]
    assert (
        discover(second, cfg, official_response(1), Mock(return_value=rank_wire(1)))[0][
            "status"
        ]
        == "ranked"
    )
    assert gather_trends(second.pk, cfg=cfg)["status"] == "discovered"
    fresh = OriginalContent.objects.get(run=second)
    assert fresh.development_id == first.development_id
    assert (
        fresh.appearance_kind == "personalized_trend" and fresh.shortlist_position == 1
    )
    assert (
        fresh.discovery_call.stage == "trends-ranking-v1"
        and fresh.discovery_call.run_id == second.pk
    )
    assert fresh.consideration_sources.get(post_id="8102").usage == "background"
    assert fresh.consideration_sources.get(post_id="8101").usage == "consideration"

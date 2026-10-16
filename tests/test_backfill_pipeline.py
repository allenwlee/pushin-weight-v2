"""Command → shared runner → real pagination/ORM, with captured transports."""
from __future__ import annotations

import json
from dataclasses import replace
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def pipeline(monkeypatch, tmp_path, seeded_policy_keywords):
    from monitor import cycle
    from monitor.management.commands import backfill
    from x_monitor.apify import TwitterApiClient

    responses = []
    requests = []
    purposes = []
    cohorts = []
    post_fetch_method = cycle.CycleRunner._run_post_fetch
    monkeypatch.setattr(backfill, "_seconds_to_next_slot", lambda: 900)
    monkeypatch.setattr(backfill, "_STATE_DIR", tmp_path)
    monkeypatch.setattr("x_monitor.reattribute.build_relevancy_client_from_env", lambda cfg, **kwargs: None)
    monkeypatch.setattr(cycle.CycleRunner, "_run_post_fetch",
                        lambda self, items, **kwargs: cohorts.append(kwargs["post_ids"]) or {})
    def forbidden(*args, **kwargs):
        raise AssertionError("historical recovery drained an unrelated optional lane")
    monkeypatch.setattr(cycle.CycleRunner, "_drain_rare_type_hits", forbidden)
    monkeypatch.setattr(cycle.CycleRunner, "_request_synthesis_prewarm", forbidden)
    def factory(cls, purpose):
        purposes.append(purpose)
        return TwitterApiClient(api_key="test-only")
    monkeypatch.setattr(TwitterApiClient, "from_env", classmethod(factory))
    def get(*args, **kwargs):
        requests.append(kwargs["params"])
        body = responses.pop(0)
        if isinstance(body, Exception):
            raise body
        return SimpleNamespace(status_code=200, content=json.dumps(body).encode(),
                               json=lambda: body, text=json.dumps(body))
    monkeypatch.setattr("x_monitor.apify.requests.get", get)
    def run(**kwargs):
        call_command("backfill", since="2026-08-09T00:00:00Z", until="2026-08-09T00:15:00Z",
                     brands="qwen", call_ids="B1", max_results=20, max_pages=1,
                     pause=0, stdout=StringIO(), stderr=StringIO(), **kwargs)
        return json.loads(next(tmp_path.glob("*.json")).read_text())
    return SimpleNamespace(responses=responses, requests=requests, purposes=purposes,
                           cohorts=cohorts, run=run, directory=tmp_path,
                           post_fetch_method=post_fetch_method)


def page(tweet_id, *, cursor=None):
    return {"tweets": [{"id": tweet_id, "text": "Qwen model release", "lang": "en",
                        "createdAt": "Sun Aug 09 00:10:00 +0000 2026",
                        "author": {"id": "author-" + tweet_id, "userName": "user" + tweet_id}}],
            "has_next_page": cursor is not None, "next_cursor": cursor or ""}


def test_capped_command_resumes_cursor_and_preserves_live_state(pipeline):
    from core.models import CallState, HarvestBacklogWindow, Post, PostEnrichmentState
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    unrelated = Post.objects.create(tweet_id="outside", text="unrelated queue work")
    PostEnrichmentState.objects.create(post=unrelated)
    pipeline.responses.append(page("1", cursor="same-second-continuation"))
    partial = pipeline.run()
    assert not partial["finished"]
    assert partial["units"][0]["cursor"] == "same-second-continuation"
    assert partial["last_invocation_usage"]["api_requests"] == 1
    pipeline.responses.append(page("2"))
    drained = pipeline.run()
    assert pipeline.requests[1]["cursor"] == "same-second-continuation"
    assert pipeline.requests[0]["query"] == pipeline.requests[1]["query"]
    assert "since_time:1786233600 until_time:1786234500" in pipeline.requests[0]["query"]
    assert drained["finished"] and drained["total_inserted"] == 2
    assert not drained["enrichment_complete"]
    assert set(drained["enrichment_pending_post_ids"]) == {"1", "2"}
    assert Post.objects.filter(pk__in=["1", "2"]).count() == 2
    assert pipeline.cohorts == [["1"], ["1"]]
    assert pipeline.purposes == [TwitterApiCredentialPurpose.ON_DEMAND] * 2
    assert not CallState.objects.exists()
    assert not HarvestBacklogWindow.objects.exists()
    assert PostEnrichmentState.objects.get(pk="outside").claim_run_id == ""


def test_page_after_first_failure_retains_received_posts(pipeline):
    import requests

    from core.models import Post

    pipeline.responses.extend([page("1", cursor="after-first"), requests.Timeout("provider timeout")])
    # A two-page unit starts exactly two physical requests, and retains page 1.
    with pytest.raises(CommandError, match="attempt failed"):
        call_command("backfill", since="2026-08-09T00:00Z", until="2026-08-09T00:15Z",
                     brands="qwen", call_ids="B1", max_results=40, max_pages=2,
                     pause=0, stdout=StringIO(), stderr=StringIO())
    state = json.loads(next(pipeline.directory.glob("*.json")).read_text())
    assert Post.objects.filter(pk="1").exists()
    assert state["units"][0]["cursor"] == "after-first"
    assert state["last_invocation_usage"]["api_requests"] == 2
    assert not state["finished"]
    assert state["runs"][0]["summary"]["calls"][0]["backfill_progress"]["reason"] == "Timeout"


def test_changed_query_cannot_inherit_checkpoint(pipeline, monkeypatch):
    from monitor import cycle

    pipeline.responses.append(page("1", cursor="resume"))
    pipeline.run()
    plan = cycle.plan_calls_for_cycle
    monkeypatch.setattr(cycle, "plan_calls_for_cycle", lambda cfg: [
        replace(call, query_string=call.query_string + " -changed") for call in plan(cfg)
    ])
    with pytest.raises(CommandError, match="identity changed"):
        pipeline.run()
    assert len(pipeline.requests) == 1


def test_repeated_cursor_is_pending_and_not_committed_past_page(pipeline):
    pipeline.responses.append(page("1", cursor="repeat"))
    pipeline.run()
    pipeline.responses.append(page("2", cursor="repeat"))
    with pytest.raises(CommandError, match="attempt failed"):
        pipeline.run()
    state = json.loads(next(pipeline.directory.glob("*.json")).read_text())
    assert not state["finished"]
    assert state["units"][0]["cursor"] == "repeat"
    assert state["runs"][-1]["summary"]["calls"][0]["backfill_progress"]["reason"] == "nonprogressing_cursor"
    with pytest.raises(CommandError):
        pipeline.run()
    assert len(pipeline.requests) == 2


def test_persistence_failure_keeps_previous_cursor(pipeline, monkeypatch):
    from core.models import Post

    save = Post.save
    def fail(self, *args, **kwargs):
        if str(self.pk) == "1":
            raise RuntimeError("injected storage failure")
        return save(self, *args, **kwargs)
    monkeypatch.setattr(Post, "save", fail)
    pipeline.responses.append(page("1", cursor="must-not-commit"))
    with pytest.raises(CommandError, match="attempt failed"):
        pipeline.run()
    state = json.loads(next(pipeline.directory.glob("*.json")).read_text())
    assert state["units"][0]["cursor"] is None
    assert state["units"][0]["seen_cursors"] == []
    assert not state["finished"]


def test_next_slot_reserve_defers_before_provider(pipeline, monkeypatch):
    from monitor.management.commands import backfill

    monkeypatch.setattr(backfill, "_seconds_to_next_slot", lambda: 100)
    state = pipeline.run()
    assert not pipeline.requests and not pipeline.purposes
    assert not state["runs"] and not state["finished"]


def test_batch_searches_whole_month_and_checkpoints_each_page(pipeline, monkeypatch):
    from core.models import CallState, HarvestBacklogWindow, Post
    from monitor.management.commands import backfill

    def forbidden(*args, **kwargs):
        raise AssertionError("one-time collection used harvest timing or model setup")
    monkeypatch.setattr(backfill, "_seconds_to_next_slot", forbidden)
    monkeypatch.setattr(backfill._time, "sleep", forbidden)
    monkeypatch.setattr("x_monitor.reattribute.build_relevancy_client_from_env", forbidden)
    checkpoints = []
    save = backfill._save_state
    def captured_save(path, state):
        if state["runs"]:
            checkpoints.append((state["units"][0]["cursor"], Post.objects.count()))
        return save(path, state)
    monkeypatch.setattr(backfill, "_save_state", captured_save)
    pipeline.responses.extend(page(str(n), cursor=f"page-{n}" if n < 7 else None)
                              for n in range(1, 8))
    call_command("backfill", batch=True, since="2026-08-01", until="2026-08-31",
                 brands="qwen", call_ids="B1", run_seconds=3600, pause=900,
                 stdout=StringIO(), stderr=StringIO())
    state = json.loads(next(pipeline.directory.glob("*.json")).read_text())
    assert len(state["units"]) == 1 and state["finished"]
    assert len(pipeline.requests) == 7  # No five-page query ceiling.
    assert all("since_time:1785542400 until_time:1788134400" in r["query"]
               for r in pipeline.requests)
    assert [r.get("cursor", "") for r in pipeline.requests] == ["", *[f"page-{n}" for n in range(1, 7)]]
    assert checkpoints == [(f"page-{n}" if n < 7 else None, n) for n in range(1, 8)]
    assert state["last_invocation_usage"]["llm_requests"] == 0
    assert pipeline.cohorts == [[]] * 7
    assert not CallState.objects.exists() and not HarvestBacklogWindow.objects.exists()


def test_batch_invocation_budget_resumes_committed_page_without_restarting(pipeline):
    pipeline.responses.extend([page("1", cursor="page-1"), page("2", cursor="page-2")])
    partial = pipeline.run(batch=True, max_api_requests=2)
    assert not partial["finished"] and partial["total_inserted"] == 2
    assert partial["units"][0]["cursor"] == "page-2"
    pipeline.responses.append(page("3"))
    drained = pipeline.run(batch=True, max_api_requests=2)
    assert drained["finished"] and drained["total_inserted"] == 3
    assert pipeline.requests[-1]["cursor"] == "page-2"


def test_batch_later_timeout_preserves_earlier_page_checkpoint(pipeline):
    import requests

    from core.models import Post

    pipeline.responses.extend([page("1", cursor="stored-page"), requests.ReadTimeout("timeout")])
    with pytest.raises(CommandError, match="attempt failed"):
        pipeline.run(batch=True)
    state = json.loads(next(pipeline.directory.glob("*.json")).read_text())
    assert Post.objects.filter(pk="1").exists()
    assert state["units"][0]["cursor"] == "stored-page"
    assert state["units"][0]["post_ids"] == ["1"]
    assert state["last_invocation_usage"]["api_requests"] == 2
    pipeline.responses.append(page("2"))
    assert pipeline.run(batch=True)["finished"]
    assert pipeline.requests[-1]["cursor"] == "stored-page"


def test_drained_collection_retries_only_its_enrichment(pipeline):
    pipeline.responses.append(page("1"))
    collected = pipeline.run()
    assert collected["finished"] and not collected["enrichment_complete"]
    repeated = pipeline.run()
    assert len(pipeline.requests) == 1
    assert repeated["total_inserted"] == 1
    assert repeated["runs"][-1]["summary"]["phase"] == "enrichment"
    assert repeated["last_invocation_usage"]["api_requests"] == 0
    assert pipeline.cohorts == [["1"], ["1"]]


def test_enrichment_resume_visits_other_units_before_retrying_pending_unit(pipeline):
    first, second = page("1"), page("2")
    second["tweets"][0]["createdAt"] = "Sun Aug 09 00:20:00 +0000 2026"
    pipeline.responses.extend([first, second])
    options = {"since": "2026-08-09T00:00Z", "until": "2026-08-09T00:30Z",
               "brands": "qwen", "call_ids": "B1", "max_results": 20, "max_pages": 1,
               "batch_size": 3, "pause": 0, "stdout": StringIO(), "stderr": StringIO()}
    call_command("backfill", **{**options, "batch_size": 2})
    pipeline.cohorts.clear()
    call_command("backfill", **options)
    assert pipeline.cohorts == [["1"], ["2"]]
    assert len(pipeline.requests) == 2


def test_manual_long_translation_and_cache_use_same_smaller_chunks(pipeline, monkeypatch):
    from pathlib import Path

    from core.models import Post, PostEnrichmentState
    from monitor import cycle
    from monitor.management.commands import backfill
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml"))
    cfg.llm.literal_translation_v2_enabled = True
    monkeypatch.setattr(backfill, "load_config", lambda path: cfg)
    pipeline.responses.append(page("1"))
    pipeline.run()
    Post.objects.filter(pk="1").update(text="word " * 1_200, lang="en")
    PostEnrichmentState.objects.filter(pk="1").update(classification_status="succeeded")
    monkeypatch.setattr(cycle.CycleRunner, "_run_post_fetch", pipeline.post_fetch_method)
    monkeypatch.setattr("x_monitor.reattribute.build_translator_client_from_env", lambda cfg, **kwargs: object())
    seen = []
    def cached(tweets, **kwargs):
        seen.append(("cache", kwargs.get("chunk_size")))
        return {}
    def translated(tweets, client, **kwargs):
        seen.append(("translation", kwargs.get("chunk_size")))
        return []
    monkeypatch.setattr("monitor.post_artifacts.load_literal_translation_chunks", cached)
    monkeypatch.setattr("x_monitor.literal_translation.translate_batch_literal_plaintext", translated)
    pipeline.run()
    assert seen == [("cache", 2_000), ("translation", 2_000)]
    seen.clear()
    runner = cycle.CycleRunner(cfg=cfg)
    pipeline.post_fetch_method(runner, [], run_id="scheduled-control", post_ids=["1"])
    assert seen == [("cache", None), ("translation", None)]


def test_manual_chunk_layout_can_coexist_with_scheduled_cache_rows():
    from datetime import timedelta

    from django.utils import timezone

    from core.models import Post, PostEnrichmentState, PostTranslationChunk
    from monitor.post_artifacts import (
        load_literal_translation_chunks,
        persist_literal_translation_chunk,
        source_text_fingerprint,
    )
    from x_monitor.literal_translation import (
        CHUNK_TRANSLATION_PROMPT_VERSION,
        _split_translation_chunks,
        chunk_translation_prompt_version,
    )

    source = "word " * 1_200
    post = Post.objects.create(tweet_id="chunk-layout", text=source)
    PostEnrichmentState.objects.create(post=post, claim_run_id="manual-layout",
                                      claim_expires_at=timezone.now() + timedelta(seconds=180))
    old = _split_translation_chunks(source)[0]
    PostTranslationChunk.objects.create(
        post=post, source_content_fingerprint=source_text_fingerprint(source),
        source_chunk_fingerprint=source_text_fingerprint(old), source_language="en",
        prompt_version=CHUNK_TRANSLATION_PROMPT_VERSION, model="test", target_language="zh-Hans",
        chunk_index=0, translated_text="旧" * 1_000,
    )
    tweet = {"tweet_id": post.pk, "text": source}
    version = chunk_translation_prompt_version(2_000)
    assert version != CHUNK_TRANSLATION_PROMPT_VERSION
    assert persist_literal_translation_chunk(
        tweet=tweet, source_language="en", target_language="zh-Hans", chunk_index=0,
        source_chunk=_split_translation_chunks(source, chunk_size=2_000)[0], translated_text="新" * 500,
        model="test", prompt_version=version, usage={}, expected_claim_run_id="manual-layout",
    )
    assert PostTranslationChunk.objects.filter(post=post).count() == 2
    cached = load_literal_translation_chunks([tweet], model="test", prompt_version=version, chunk_size=2_000)
    assert cached[str(post.pk)]["en"]["zh-Hans"][0] == "新" * 500


def test_provider_ignoring_time_bounds_cannot_finish_or_store_outside_post(pipeline):
    from core.models import Post

    escaped = page("outside-window")
    escaped["tweets"][0]["createdAt"] = "Sun Aug 09 00:20:00 +0000 2026"
    pipeline.responses.append(escaped)
    with pytest.raises(CommandError, match="attempt failed"):
        pipeline.run()
    state = json.loads(next(pipeline.directory.glob("*.json")).read_text())
    assert not state["finished"]
    assert not Post.objects.filter(pk="outside-window").exists()
    assert state["runs"][0]["summary"]["calls"][0]["backfill_progress"]["reason"] == "invalid_primary_window"
    assert state["units"][0]["status"] == "blocked"
    with pytest.raises(CommandError):
        pipeline.run()
    assert len(pipeline.requests) == 1


def test_missing_persistence_receipt_cannot_commit_cursor(pipeline, monkeypatch):
    from monitor.cycle import CycleRunner

    run = CycleRunner.run
    def incomplete_receipt(self):
        stats = run(self)
        stats["calls"][0].pop("n_persist_failed")
        return stats
    monkeypatch.setattr(CycleRunner, "run", incomplete_receipt)
    pipeline.responses.append(page("1", cursor="unverified"))
    state = pipeline.run()
    assert state["units"][0]["cursor"] is None
    assert state["units"][0]["seen_cursors"] == []
    assert not state["finished"]


def test_historical_query_is_frozen_and_reaches_shared_transport(pipeline):
    query = '(Qwen OR Qwen3 OR "Qwen3.8" OR 通义千问) min_faves:0'
    pipeline.responses.append(page("1", cursor="historical-model-cursor"))
    state = pipeline.run(query=query)
    assert pipeline.requests[0]["query"].startswith(query + " since_time:")
    assert state["identity"]["query_override"] == query
    assert state["identity"]["queries"] == {"B1": query}
    with pytest.raises(CommandError, match="identity changed"):
        pipeline.run(query='"Qwen3.8"')
    assert len(pipeline.requests) == 1


def test_historical_query_cannot_replace_fixed_time_bounds(pipeline):
    with pytest.raises(CommandError, match="omit time operators"):
        pipeline.run(query="Qwen since_time:1")
    assert not pipeline.requests


def test_zero_model_allowance_defers_before_claim_or_client_construction(pipeline, monkeypatch):
    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner

    monkeypatch.setattr(CycleRunner, "_run_post_fetch", pipeline.post_fetch_method)
    def forbidden(cfg):
        raise AssertionError("zero model allowance constructed an enrichment client")
    monkeypatch.setattr("x_monitor.reattribute.build_translator_client_from_env", forbidden)
    monkeypatch.setattr("x_monitor.reattribute.build_classifier_client_from_env", forbidden)
    pipeline.responses.append(page("1"))
    state = pipeline.run(max_llm_calls=0)
    work = PostEnrichmentState.objects.get(pk="1")
    assert work.translation_attempts == work.classification_attempts == 0
    assert work.claim_run_id == ""
    assert state["finished"] and not state["enrichment_cohort_complete"]
    assert state["last_invocation_usage"]["llm_requests"] == 0


def test_pause_releases_writer_lock_to_another_connection(pipeline, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from monitor.management.commands import backfill
    from monitor.run_lock import harvest_writer_lock

    pipeline.responses.extend([page("1", cursor="resume"), page("2")])
    acquisitions = []
    def compete():
        with harvest_writer_lock(execution_mode="live", entrypoint="test.pause") as lease:
            return lease.acquired
    def pause(_seconds):
        with ThreadPoolExecutor(max_workers=1) as pool:
            acquisitions.append(pool.submit(compete).result())
    monkeypatch.setattr(backfill._time, "sleep", pause)
    call_command("backfill", since="2026-08-09T00:00Z", until="2026-08-09T00:15Z",
                 brands="qwen", call_ids="B1", max_results=20, max_pages=1,
                 batch_size=2, pause=1, stdout=StringIO(), stderr=StringIO())
    assert acquisitions == [True]


def test_continuation_flag_without_cursor_cannot_finish(pipeline):
    pipeline.responses.append({"tweets": [], "has_next_page": True, "next_cursor": ""})
    with pytest.raises(CommandError, match="attempt failed"):
        pipeline.run()
    state = json.loads(next(pipeline.directory.glob("*.json")).read_text())
    assert not state["finished"]
    assert state["units"][0]["status"] == "blocked"
    assert state["units"][0]["blocked_reason"] == "invalid_continuation"
    with pytest.raises(CommandError):
        pipeline.run()
    assert len(pipeline.requests) == 1


def test_enrichment_failure_keeps_collection_complete_and_exits_failed(pipeline, monkeypatch):
    from monitor.cycle import CycleRunner

    pipeline.responses.append(page("1"))
    pipeline.run()
    def failed(self, items, **kwargs):
        self._errors.append("post_fetch.injected_failure")
        return {}
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", failed)
    with pytest.raises(CommandError, match="attempt failed"):
        pipeline.run()
    state = json.loads(next(pipeline.directory.glob("*.json")).read_text())
    assert state["finished"]
    assert state["units"][0]["status"] == "completed"
    assert state["runs"][-1]["call_status"] == "enrichment_failed"
    assert len(pipeline.requests) == 1


def test_real_post_fetch_claims_only_frozen_new_cohort(pipeline, monkeypatch):
    from core.models import Post, PostEnrichmentState
    from monitor.cycle import CycleRunner

    outside = Post.objects.create(tweet_id="global-pending", text="Qwen outside campaign")
    PostEnrichmentState.objects.create(post=outside)
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", pipeline.post_fetch_method)
    monkeypatch.setattr("x_monitor.reattribute.build_translator_client_from_env", lambda cfg: None)
    monkeypatch.setattr("x_monitor.reattribute.build_classifier_client_from_env", lambda cfg: None)
    pipeline.responses.append(page("1"))
    with pytest.raises(CommandError, match="attempt failed"):
        pipeline.run()
    claimed = PostEnrichmentState.objects.get(pk="1")
    unrelated = PostEnrichmentState.objects.get(pk="global-pending")
    assert claimed.translation_attempts > 0
    assert claimed.classification_attempts > 0
    assert unrelated.translation_attempts == unrelated.classification_attempts == 0
    assert unrelated.claim_run_id == ""

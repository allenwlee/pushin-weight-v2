"""Campaign → collector → real PostgreSQL priority lock and saved rare inbox."""
from contextlib import ExitStack
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone

from core.collection_capture import run_report_document
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    Post,
    RareTypeSearchHit,
)
from monitor import backfill_collection as collection
from scripts import backfill_campaign as campaign
from tests.test_backfill_collection import live_writer as captured_live_writer
from tests.test_backfill_collection import pipeline as captured_pipeline
from tests.test_backfill_collection import policy_job
from tests.test_backfill_pipeline import page
from x_monitor.jev_decisions import (
    QUESTION_SET,
    JevDecisionError,
    JevDecisionsClient,
    JevResponse,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
live_writer = pytest.fixture(name="live_writer")(captured_live_writer.__wrapped__)
pipeline = pytest.fixture(name="pipeline")(captured_pipeline.__wrapped__)


@pytest.fixture
def rare_campaign(pipeline, monkeypatch, tmp_path):
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-on-demand")
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "fixture-on-demand")
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-only")
    template = policy_job(monkeypatch, tmp_path, calls={"RARE_EXTRA"}, rare=True,
                          selected_calls=["RARE_EXTRA"])
    cfg = collection.load_config(Path("config.yaml"))
    frozen = {"campaign": "rare-handoff", "instruction_format": "x-backfill-campaign/v2",
              "deadline": (timezone.now() + timedelta(hours=1)).isoformat()}
    window = {"index": 1, "maximum_api_requests": 20, "collection_definition": template.definition}
    pipeline.responses.append(page("rare-handoff"))
    return cfg, frozen, window


@pytest.mark.parametrize("mode", ["pending", "published_before_report", "deadline"])
def test_campaign_retries_rare_writer_handoff_without_repaying(
    rare_campaign, pipeline, live_writer, monkeypatch, mode,
):
    cfg, frozen, window = rare_campaign
    model_calls, waits, releases, partial_runs = [], [], [], []
    real_report = collection._report
    clock = [timezone.now()]
    monkeypatch.setattr(campaign.timezone, "now", lambda: clock[0])

    with ExitStack() as stack:
        def decide(self, request_bytes, **kwargs):
            model_calls.append(request_bytes)
            # Live harvesting arrives after search, while its model reply is in flight.
            releases.append(stack.enter_context(live_writer()))
            probabilities = dict.fromkeys(QUESTION_SET, .1)
            probabilities.update(ai_related=.95, role_opening=.95)
            return JevResponse("approved", probabilities, 1200, 0, Decimal("0.00005"))

        monkeypatch.setattr(JevDecisionsClient, "submit", decide)

        def report(job, run_id):
            if mode == "published_before_report" and not Post.objects.exists():
                # Another writer publishes the hit before the collector snapshots it.
                # The collector still owes its own membership/checkpoint bookkeeping.
                from monitor.cycle import (
                    CycleRunner,
                    _build_brand_index,
                    _load_brand_search_terms,
                )
                from monitor.run_lock import harvest_writer_lock

                releases[0]()
                with harvest_writer_lock(execution_mode="live", entrypoint="test.rare.publish") as lease:
                    assert lease.acquired
                    result = CycleRunner(cfg=cfg)._ingest_kept_rare_type_hits(
                        run_id="test-live-publish", hit_ids=list(RareTypeSearchHit.objects.values_list("pk", flat=True)),
                        index=_build_brand_index(["qwen"]), search_terms=_load_brand_search_terms(),
                    )
                    assert result["failed"] == 0 and Post.objects.count() == 1
                assert not CollectionObservation.objects.filter(run__job=job, post_id="rare-handoff").exists()
            return real_report(job, run_id)

        monkeypatch.setattr(collection, "_report", report)

        def wait(seconds):
            waits.append(seconds)
            assert waits == [15], "handoff should resume on its first retry"
            job = CollectionJob.objects.get(job_key="rare-handoff/1")
            attempt = job.last_attempt
            partial_runs.append(attempt.pk)
            assert job.state != "completed" and job.active_run_id is None
            assert attempt.status == "partial"
            saved = run_report_document(attempt)
            assert saved["collection_drained"]
            assert saved["state"] == "waiting_for_live_writer"
            assert saved["rare_gate_pending"] == (0 if mode == "published_before_report" else 1)
            assert RareTypeSearchHit.objects.get().gate_state == "kept"
            assert len(model_calls) == len(pipeline.requests) == 1
            releases[0]()
            if mode == "deadline":
                clock[0] += timedelta(hours=2)

        monkeypatch.setattr(campaign, "_wait", wait)
        if mode == "deadline":
            with pytest.raises(RuntimeError, match="campaign_deadline_exhausted"):
                campaign.collect_window(window, frozen=frozen, cfg=cfg)
            assert not Post.objects.exists()
        else:
            result = campaign.collect_window(window, frozen=frozen, cfg=cfg)
            assert result["status"] == "verified"
            job = CollectionJob.objects.get(job_key="rare-handoff/1")
            assert job.state == "completed"
            # The fixture freezes timezone.now globally, so both runs have the
            # same timestamp. Verify the observed handoff identities instead of
            # relying on PostgreSQL's arbitrary order for equal timestamps.
            assert len(partial_runs) == 1 and partial_runs[0] != job.last_success_id
            assert dict(job.runs.values_list("pk", "status")) == {
                partial_runs[0]: "partial", job.last_success_id: "success",
            }
            assert CollectionObservation.objects.filter(run__job=job, post_id="rare-handoff").count() == 1
            saved = run_report_document(job.last_success)
            assert saved["recovered_post_ids"] == ["rare-handoff"]
            assert "state" not in saved
            assert result["phase_usage"]["twitterapi_requests"] == 1
            assert result["phase_usage"]["collection_gate"]["requests_started"] == 1
            assert result["phase_usage"]["post_enrichment"]["requests_sent"] == 0
    assert waits == [15]
    assert len(model_calls) == len(pipeline.requests) == 1


def test_unknown_rare_model_outcome_remains_a_stop_not_a_writer_wait(rare_campaign, pipeline, monkeypatch):
    cfg, frozen, window = rare_campaign
    calls = []

    def timeout(self, request_bytes, **kwargs):
        calls.append(request_bytes)
        raise JevDecisionError("timeout")

    monkeypatch.setattr(JevDecisionsClient, "submit", timeout)
    monkeypatch.setattr(campaign, "_wait", lambda seconds: pytest.fail("unknown outcome was retried"))
    with pytest.raises(RuntimeError, match="collection_rare_gate_pending"):
        campaign.collect_window(window, frozen=frozen, cfg=cfg)
    assert len(calls) == len(pipeline.requests) == 1
    assert not Post.objects.exists()
    assert CollectionRun.objects.get().status == "partial"

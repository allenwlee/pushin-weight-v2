from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.models import (
    Brand,
    Post,
    PostBrand,
    PostEnrichmentState,
    RareTypeSearchHit,
    SearchQuery,
)
from core.rare_type_search import (
    mark_search_dispatched,
    persist_hit_batch,
    reconcile_classified_hits,
    reserve_search_run,
)
from monitor.cycle import CycleRunner
from x_monitor.config import load_config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


def _hit(*, tweet_id="rare-kept", gate_state=RareTypeSearchHit.GateState.KEPT):
    query = SearchQuery.objects.create(query_id=f"query-{tweet_id}")
    reservation = reserve_search_run(
        lane="rare_types",
        slot_start=NOW,
        source_query=query,
        query_string="rare query",
        query_hash="a" * 64,
        query_version="rare-v3",
        environment="test",
        release_sha="sha",
        now=NOW,
    )
    mark_search_dispatched(reservation.run.pk, now=NOW)
    hit = persist_hit_batch(
        reservation.run.pk,
        [
            {
                "id": tweet_id,
                "text": "I joined Unknown AI",
                "created_at": "2026-09-24T08:59:00Z",
                "author_id": "author-1",
                "author_handle": "researcher",
            }
        ],
        now=NOW,
        raw_count=1,
        normalized_count=1,
    )[0]
    hit.gate_state = gate_state
    hit.gate_completed_at = NOW
    hit.save(update_fields=["gate_state", "gate_completed_at", "updated_at"])
    return hit


def _runner():
    cfg = load_config(Path("config.yaml"))
    cfg.discovery.rare_types.enabled = True
    return CycleRunner(cfg=cfg, _clock=lambda: NOW)


def test_kept_unknown_company_enters_normal_post_queue_and_links_hit():
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    hit = _hit()
    runner = _runner()
    result = runner._ingest_kept_rare_type_hits(run_id="cycle-1")
    assert result == {"selected": 1, "persisted": 1, "failed": 0}
    hit.refresh_from_db()
    assert hit.post_id == "rare-kept"
    assert hit.post_persisted_at is not None
    post = Post.objects.get(pk="rare-kept")
    assert post.source_query_id == "RARE_EXTRA"
    assert PostBrand.objects.filter(post=post, brand_id="_unattributed").exists()
    enrichment = PostEnrichmentState.objects.get(post=post)
    assert enrichment.classification_status == "pending"


def test_existing_post_is_linked_not_duplicated_and_junk_never_persists():
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    Post.objects.create(tweet_id="duplicate", text="already here")
    kept = _hit(tweet_id="duplicate")
    junk = _hit(tweet_id="junk", gate_state=RareTypeSearchHit.GateState.JUNK)
    result = _runner()._ingest_kept_rare_type_hits(run_id="cycle-2")
    assert result["persisted"] == 1
    assert Post.objects.filter(pk="duplicate").count() == 1
    kept.refresh_from_db()
    junk.refresh_from_db()
    assert kept.post_id == "duplicate"
    assert junk.post_id is None
    assert not Post.objects.filter(pk="junk").exists()


def test_persistence_failure_remains_replayable_without_search(monkeypatch):
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    hit = _hit(tweet_id="retry-local")
    runner = _runner()
    original = runner._persist_items
    monkeypatch.setattr(runner, "_persist_items", lambda _items: (0, 0, 0, 1))
    assert runner._ingest_kept_rare_type_hits(run_id="first")["failed"] == 1
    hit.refresh_from_db()
    assert hit.post_id is None and hit.last_error_code == "post_persistence_failed"
    monkeypatch.setattr(runner, "_persist_items", original)
    assert runner._ingest_kept_rare_type_hits(run_id="second")["persisted"] == 1
    hit.refresh_from_db()
    assert hit.post_id == "retry-local" and hit.last_error_code == ""


def test_jev_unavailable_still_ingests_already_kept_hit(monkeypatch):
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    hit = _hit(tweet_id="kept-before-outage")
    monkeypatch.setattr(
        "monitor.cycle.build_jev_decision_gate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no credential")),
    )
    result = _runner()._drain_rare_type_hits(
        run_id="local-replay", index=(None, {}), search_terms={}
    )
    assert result["ingestion_persisted"] == 1
    hit.refresh_from_db()
    assert hit.post_id == "kept-before-outage"


def test_pending_hit_gate_then_local_ingestion_uses_shared_deadline(monkeypatch):
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    hit = _hit(
        tweet_id="pending-local",
        gate_state=RareTypeSearchHit.GateState.DECISION_PENDING,
    )
    observed = {}

    class Gate:
        def process_hit(self, hit_id, **kwargs):
            observed.update(kwargs)
            RareTypeSearchHit.objects.filter(pk=hit_id).update(
                gate_state=RareTypeSearchHit.GateState.KEPT
            )
            return SimpleNamespace(outcome="kept")

    monkeypatch.setattr(
        "monitor.cycle.build_jev_decision_gate", lambda *_a, **_kw: Gate()
    )
    result = _runner()._drain_rare_type_hits(
        run_id="cycle-gate",
        index=(None, {}),
        search_terms={},
        deadline=SimpleNamespace(deadline_at=123.5),
    )
    assert result["kept"] == 1 and result["ingestion_persisted"] == 1
    assert observed == {
        "owner": "cycle-gate",
        "shared_deadline_monotonic": 123.5,
    }
    hit.refresh_from_db()
    assert hit.post_id == "pending-local"


def test_staging_cutoff_does_not_drain_kept_carryover():
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    hit = _hit(tweet_id="old-staging-keeper")
    result = _runner()._ingest_kept_rare_type_hits(
        run_id="staging", fetched_since=NOW + timedelta(seconds=1)
    )
    assert result == {"selected": 0, "persisted": 0, "failed": 0}
    hit.refresh_from_db()
    assert hit.post_id is None


def test_rejected_duplicate_does_not_change_existing_post_or_attribution():
    brand = Brand.objects.create(nickname="known", display_name="Known")
    post = Post.objects.create(tweet_id="rejected-existing", text="original")
    PostBrand.objects.create(post=post, brand=brand)
    hit = _hit(
        tweet_id="rejected-existing", gate_state=RareTypeSearchHit.GateState.JUNK
    )
    assert _runner()._ingest_kept_rare_type_hits(run_id="junk") == {
        "selected": 0,
        "persisted": 0,
        "failed": 0,
    }
    post.refresh_from_db()
    hit.refresh_from_db()
    assert post.text == "original"
    assert list(post.brands.values_list("brand_id", flat=True)) == ["known"]
    assert hit.post_id is None


def test_completed_normal_classification_reconciles_to_hit():
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    hit = _hit(tweet_id="classified-keeper")
    _runner()._ingest_kept_rare_type_hits(run_id="classification")
    PostEnrichmentState.objects.filter(post_id="classified-keeper").update(
        classification_status=PostEnrichmentState.Status.SUCCEEDED
    )
    assert reconcile_classified_hits(now=NOW + timedelta(minutes=1), limit=20) == 1
    hit.refresh_from_db()
    assert hit.classified_at == NOW + timedelta(minutes=1)


def test_staging_reconciliation_does_not_touch_carryover():
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    hit = _hit(tweet_id="old-classified")
    _runner()._ingest_kept_rare_type_hits(run_id="old")
    PostEnrichmentState.objects.filter(post_id="old-classified").update(
        classification_status=PostEnrichmentState.Status.SUCCEEDED
    )
    assert (
        reconcile_classified_hits(
            now=NOW + timedelta(minutes=1),
            limit=5,
            fetched_since=NOW + timedelta(seconds=1),
        )
        == 0
    )
    hit.refresh_from_db()
    assert hit.classified_at is None

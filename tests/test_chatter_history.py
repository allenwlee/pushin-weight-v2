"""History must come from frozen sources and actual fresh discovery periods."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import OriginalContent, OriginalContentCall, OriginalContentRun, Post
from tests.test_original_content_consideration import consideration

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_history_reuses_physical_source_text_and_pins_its_hash_without_reference_chains():
    from monitor.editorial import chatter_history as history

    first, second, third = consideration(), consideration(), consideration()
    post = Post.objects.create(tweet_id="882099", text="Retained original evidence.", created_at=first.run.facts_as_of)
    history.freeze_sources(first.run, [history.project_post(post)], fence=first.run.fence)
    history.attach_sources(first, [post.pk], fence=first.run.fence)
    for previous, current in ((first, second), (second, third)):
        history.reference_sources(current.run, previous, fence=current.run.fence)
        history.attach_sources(current, [post.pk], fence=current.run.fence)
        current.run.refresh_from_db()
        assert current.run.snapshot["sources"] == {}
        assert current.run.snapshot["source_refs"][post.pk]["run_id"] == first.run_id
        assert current.consideration_sources.get().snapshot_run_id == first.run_id
        assert history.read_sources(current)[0]["original_text"] == post.text
    from django.db.models.deletion import ProtectedError
    with pytest.raises(ProtectedError):
        first.run.delete()
    third.run.snapshot["source_refs"][post.pk]["sha256"] = "0"*64
    third.run.save(update_fields=["snapshot"])
    with pytest.raises(ValueError, match="reference mismatch"):
        history.read_sources(third)


def test_consideration_reads_frozen_source_after_the_post_changes():
    from monitor.editorial import chatter_history as history

    row = consideration()
    post = Post.objects.create(tweet_id="882001", text="A publisher announces a model.",
                               created_at=row.run.facts_as_of - timedelta(minutes=1))
    source = history.project_post(post)
    history.freeze_sources(row.run, [source], fence=row.run.fence)
    history.attach_sources(row, [post.pk], fence=row.run.fence)
    history.attach_sources(row, [post.pk], fence=row.run.fence)
    assert row.consideration_sources.count() == 1
    post.text = "The source was edited later."
    post.save(update_fields=["text"])
    assert history.read_sources(row)[0]["original_text"] == "A publisher announces a model."
    assert history.uses_for_post(post.pk, timezone.now())[0].pk == row.pk
    assert history.development_history(row.development, timezone.now())[0].pk == row.pk
    assert not row.localized_texts.exists() and row.published_at is None
    with pytest.raises(ValueError, match="immutable"):
        history.freeze_sources(row.run, [history.project_post(post)], fence=row.run.fence)


@pytest.mark.parametrize("fault", ["extra", "wrong_type", "missing", "version"])
def test_snapshot_rejects_unknown_payload_and_schema_changes(fault):
    from monitor.editorial import chatter_history as history

    row = consideration()
    post = Post.objects.create(tweet_id="882002", text="A source report.",
                               created_at=row.run.facts_as_of - timedelta(minutes=1))
    source = history.project_post(post)
    if fault == "extra":
        source["encrypted_reasoning"] = "must not be saved"
    elif fault == "wrong_type":
        source["is_quote"] = "false"
    elif fault == "missing":
        source.pop("original_text")
    else:
        row.run.snapshot = {"schema_version": 99, "sources": {}}
        row.run.save(update_fields=["snapshot"])
    with pytest.raises(ValueError):
        history.freeze_sources(row.run, [source], fence=row.run.fence)
    assert not row.consideration_sources.exists()


def test_stale_source_writer_cannot_change_the_new_run():
    from monitor.editorial import chatter_history as history

    row = consideration()
    post = Post.objects.create(tweet_id="882003", text="An attributed source report.",
                               created_at=row.run.facts_as_of - timedelta(minutes=1))
    history.freeze_sources(row.run, [history.project_post(post)], fence=row.run.fence)
    row.run.fence += 1
    row.run.save(update_fields=["fence"])
    with pytest.raises(ValueError, match="stale"):
        history.attach_sources(row, [post.pk], fence=row.run.fence - 1)
    assert not row.consideration_sources.exists()
    other = consideration()
    history.freeze_sources(other.run, [history.project_post(post)], fence=other.run.fence)
    row.run_id = other.run_id
    with pytest.raises(ValueError, match="stale"):
        history.attach_sources(row, [post.pk], fence=other.run.fence)


def test_query_wording_can_return_without_rewriting_its_prior_version():
    from monitor.editorial import chatter_history as history

    story = consideration().development
    a = history.save_query("original query", development=story)
    b = history.save_query("revised query", development=story)
    c = history.save_query("original query", development=story)
    assert (b.previous_version_id, c.previous_version_id) == (a.pk, b.pk)
    assert c.pk != a.pk and c.query_text == a.query_text
    assert history.save_query("original query", development=story).pk == c.pk
    a.refresh_from_db()
    assert a.query_text == "original query" and a.previous_version_id is None


def test_first_storage_time_does_not_become_a_counter_measurement_time():
    from monitor.editorial import chatter_history as history

    post = Post.objects.create(tweet_id="882004", text="A source report.",
                               created_at=timezone.now() - timedelta(days=1), like_count=42)
    saved = history.project_post(post)
    assert saved["counters"]["observed_at"] is None
    assert saved["verification_basis"] == "saved_record"
    received_at = timezone.now()
    fresh = history.project_post(post, receipt_at=received_at)
    assert fresh["verification_basis"] == "provider_receipt"
    assert fresh["counters"]["observed_at"] == received_at.isoformat().replace("+00:00", "Z")


def test_source_membership_does_not_interpret_a_string_as_a_list_of_ids():
    from monitor.editorial import chatter_history as history

    row = consideration()
    post = Post.objects.create(tweet_id="1", text="A source report.", created_at=timezone.now())
    history.freeze_sources(row.run, [history.project_post(post)], fence=row.run.fence)
    with pytest.raises(ValueError, match="source list"):
        history.attach_sources(row, post.pk, fence=row.run.fence)
    assert not row.consideration_sources.exists()


def test_rank_does_not_change_fresh_appearance_and_unknown_period_is_not_absence():
    from monitor.editorial import chatter_history as history

    template = consideration()
    story = template.development
    start = timezone.now().replace(minute=0, second=0, microsecond=0)
    for index, (kind, rank, discovery_state) in enumerate([
        ("semantic_shortlist", 1, "complete"),
        ("semantic_shortlist", 10, "complete"),
        ("keyword_only", 1, "failed"),
        ("memory_only", 1, "complete"),
    ]):
        cutoff = start + timedelta(minutes=15 * index)
        run = OriginalContentRun.objects.create(
            source_cycle_id=str(uuid4()), workflow_key="chatter-discovery", scope_key="chatter:v1",
            interval=cutoff, facts_as_of=cutoff, cycle_started_at=cutoff,
            discovery_state=discovery_state, packet_schema_version=1, snapshot={},
        )
        call = OriginalContentCall.objects.create(
            run=run, workflow_key="chatter-discovery", stage="discovery", state="completed",
            request_identity=str(uuid4()), request_hash="b" * 64, response_hash="c" * 64,
            reserved_at=cutoff, sent_at=cutoff, completed_at=cutoff,
        )
        OriginalContent.objects.create(
            run=run, workflow_key="social-brief", output_key=str(uuid4()),
            brand_key_snapshot="", status="prepared", attempted_at=cutoff,
            development=story, story_id=story.pk, source_locale_id="en", editorial_group="rest",
            consideration_state="passed_over", appearance_kind=kind, discovery_call=call,
            shortlist_position=rank,
        )
    consecutive = history.appearance_history(story, start + timedelta(minutes=15), periods=2)
    assert consecutive["consecutive_lower_bound"] == 2
    assert consecutive["fresh_periods"] == 2
    unknown = history.appearance_history(story, start + timedelta(minutes=30), periods=3)
    assert unknown["unknown_periods"] == 1 and unknown["fresh_periods"] == 2
    carried = history.appearance_history(story, start + timedelta(minutes=45), periods=4)
    assert carried["fresh_periods"] == 2  # Neither keyword confirmation nor memory adds an appearance.
    OriginalContentCall.objects.filter(
        run__interval=start + timedelta(minutes=15), run__scope_key=history.SCOPE,
    ).update(completed_at=start + timedelta(minutes=16))
    late = history.appearance_history(story, start + timedelta(minutes=15), periods=2)
    assert late["unknown_periods"] == 1 and late["fresh_periods"] == 1


def test_carried_memory_does_not_renew_the_two_hour_competition_board():
    from monitor.editorial import chatter_history as history
    from monitor.editorial.contracts import interval_start

    cutoff = timezone.now()
    old = consideration()
    old.run.scope_key = history.SCOPE
    old.run.facts_as_of = cutoff - timedelta(hours=3)
    old.run.interval = interval_start(old.run.facts_as_of)
    old.run.save(update_fields=["scope_key", "facts_as_of", "interval"])
    memory = consideration(development=old.development, story_id=old.story_id, appearance_kind="memory_only")
    memory.run.scope_key = history.SCOPE
    memory.run.interval = interval_start(memory.run.facts_as_of)
    memory.run.save(update_fields=["scope_key", "interval"])
    assert history.competition_board(timezone.now()) == []
    assert OriginalContent.objects.filter(development=old.development).count() == 2
    assert history.development_history(old.development, timezone.now())


def test_history_does_not_reveal_a_consideration_saved_after_the_requested_cutoff():
    from monitor.editorial import chatter_history as history

    row = consideration()
    row.run.scope_key = history.SCOPE
    row.run.save(update_fields=["scope_key"])
    post = Post.objects.create(tweet_id="882005", text="A source report.", created_at=timezone.now())
    history.freeze_sources(row.run, [history.project_post(post)], fence=row.run.fence)
    history.attach_sources(row, [post.pk], fence=row.run.fence)
    cutoff = timezone.now()
    OriginalContent.objects.filter(pk=row.pk).update(attempted_at=cutoff + timedelta(minutes=1))
    assert history.development_history(row.development, cutoff) == []
    assert history.uses_for_post(post.pk, cutoff) == []
    assert history.competition_board(cutoff) == []


def test_competition_board_does_not_join_large_run_packets():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from monitor.editorial import chatter_history as history

    row = consideration()
    row.run.scope_key = history.SCOPE
    row.run.save(update_fields=["scope_key"])
    with CaptureQueriesContext(connection) as queries:
        board = history.competition_board(timezone.now())
        assert board[0].run.facts_as_of == row.run.facts_as_of
        assert board[0].development.pk == row.development_id
    assert len(queries) == 1
    assert '"snapshot"' not in queries[0]["sql"]

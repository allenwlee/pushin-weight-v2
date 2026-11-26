from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import Event, EventEvidence, Opportunity, OpportunityType
from monitor.general_readers import general_feed, temporal_facts
from tests.general_helpers import NOW, classified_post

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def event(post, start=0, end=1, **overrides):
    values = {
        "brand_id": "qwen",
        "source_post": post,
        "title": "Developer workshop",
        "organizer_name": "Qwen",
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "event_identity": f"{post.pk}-{Event.objects.count()}",
        "review_status": "confirmed",
        "start_value": (NOW + timedelta(hours=start)).isoformat(),
        "start_precision": "datetime",
        "end_value": (NOW + timedelta(hours=end)).isoformat(),
        "end_precision": "datetime",
    }
    return Event.objects.create(**(values | overrides))


@pytest.mark.parametrize("section", ["calendar", "free"])
def test_timezone_evidence_reads_remain_batched_as_more_facts_are_displayed(section):
    posts = []

    def add_fact(index):
        post = classified_post(str(2600 + index), "events" if section == "calendar" else "opportunities")
        posts.append(post.pk)
        if section == "calendar":
            event(post, raw_payload={"source_timezone": "GMT+8"})
        else:
            Opportunity.objects.create(
                brand_id="qwen", source_post=post, sponsor_name="Qwen",
                opportunity_type_reference=OpportunityType.objects.get(code="free_credits"),
                action_type="apply", benefit_type="credits",
                first_seen_at=NOW, last_seen_at=NOW, opportunity_identity=post.pk,
                raw_payload={"source_timezone": "GMT+8"},
            )

    add_fact(0)
    with CaptureQueriesContext(connection) as one:
        temporal_facts(posts, section, as_of=NOW)
    for index in range(1, 20):
        add_fact(index)
    with CaptureQueriesContext(connection) as many:
        facts = temporal_facts(posts, section, as_of=NOW)
    assert len(many) == len(one)
    assert len(facts) == 20
    assert all(facts[post_id][0]["timezone"] == "GMT+8" for post_id in posts)


def test_lifecycle_order_is_independent_of_when_the_announcement_was_fetched():
    past = classified_post("2001", "events")
    future = classified_post("2002", "events", age=3000)
    live = classified_post("2003", "events", age=100)
    unknown = classified_post("2004", "events")
    event(past, -2, -1)
    event(future, 2, 3)
    event(live, -1, 1)
    page = general_feed("calendar", as_of=NOW)
    assert [item["id"] for item in page["items"]] == [live.pk, future.pk, unknown.pk]
    assert [item["timing"]["state"] for item in page["items"]] == [
        "live",
        "upcoming",
        "unknown",
    ]
    assert (
        page["items"][0]["timing"]["target"] == (NOW + timedelta(hours=1)).isoformat()
    )


@pytest.mark.parametrize(
    "offset,state,included",
    [
        (-1, "upcoming", True),
        (0, "live", True),
        (0.999, "live", True),
        (1, "past", False),
    ],
)
def test_exact_start_and_end_boundaries(offset, state, included):
    post = classified_post("2101", "events", age=20)
    event(post)
    page = general_feed("calendar", as_of=NOW + timedelta(hours=offset))
    assert bool(page["items"]) == included
    if included:
        assert page["items"][0]["timing"]["state"] == state


@pytest.mark.parametrize(
    "start,precision,status",
    [
        ("2026-10-08", "day", "scheduled"),
        ("2026-10", "month", "scheduled"),
        (None, "unknown", "unknown"),
    ],
)
def test_partial_or_missing_dates_never_create_an_exact_timer(start, precision, status):
    post = classified_post("2201", "events")
    event(
        post,
        start_value=start,
        start_precision=precision,
        end_value=None,
        end_precision="unknown",
        source_status=status,
    )
    item = general_feed("calendar", as_of=NOW)["items"][0]
    assert item["timing"]["target"] is None
    assert item["facts"][0]["start"] == {"value": start, "precision": precision}


@pytest.mark.django_db(transaction=True)
def test_multiple_events_and_evidence_only_links_choose_live_anchor_and_keep_facts():
    post = classified_post("2301", "events")
    event(post, 3, 4)
    live = event(post, -1, 1, source_post=None, source_url="https://example.org/event")
    EventEvidence.objects.create(
        event=live,
        source_post=post,
        observed_title="Workshop",
        observed_at=NOW,
        evidence_hash="a" * 64,
    )
    event(post, -2, 2, review_status="rejected")
    item = general_feed("calendar", as_of=NOW)["items"][0]
    assert len(item["facts"]) == 2
    assert item["timing"]["fact_id"] == live.pk


def test_continuation_freezes_lifecycle_clock_and_fetch_cutoff():
    for index in range(3):
        event(classified_post(str(2400 + index), "events"), index + 1, index + 2)
    first = general_feed("calendar", as_of=NOW, limit=1)
    event(classified_post("2404", "events", age=-1), 1, 5)
    later = general_feed(
        "calendar", cursor=first["next_cursor"], as_of=NOW + timedelta(hours=3)
    )
    assert [item["id"] for item in later["items"]] == ["2401", "2402"]
    assert later["as_of"] == NOW.isoformat()
    assert all(item["timing"]["state"] == "upcoming" for item in later["items"])
    refreshed = general_feed("calendar", as_of=NOW + timedelta(hours=3))
    assert {item["id"] for item in refreshed["items"]} == {"2402", "2404"}


@pytest.mark.django_db(transaction=True)
def test_calendar_pages_bound_unknown_posts_without_losing_dated_items(monkeypatch):
    from monitor import general_readers

    for index in range(60):
        classified_post(f"bounded-{index:02d}", "events", age=index + 1)
    upcoming = classified_post("bounded-upcoming", "events", age=1000)
    event(upcoming, 2, 3)
    past = classified_post("bounded-past", "events", age=1001)
    event(past, -2, -1)

    sizes = []
    original = general_readers.temporal_facts

    def count_candidates(post_ids, section, *, as_of):
        sizes.append(len(post_ids))
        return original(post_ids, section, as_of=as_of)

    monkeypatch.setattr(general_readers, "temporal_facts", count_candidates)
    seen = []
    cursor = None
    while True:
        page = general_feed("calendar", as_of=NOW, limit=7, cursor=cursor)
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [upcoming.pk, *[f"bounded-{index:02d}" for index in range(60)]]
    # The reader must examine linked events plus at most one extra page of
    # undated posts; reading the full history defeats the bounded lookup.
    assert sizes and max(sizes) <= 10


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("section", ["calendar", "free"])
def test_linked_candidate_lookup_drives_from_fact_ids_and_deduplicates(section):
    post = classified_post("linked-fact-first", "events" if section == "calendar" else "opportunities", age=1000)
    if section == "calendar":
        event(post, 2, 3)
        event(post, 3, 4)
    else:
        for index in range(2):
            Opportunity.objects.create(
                brand_id="qwen", source_post=post, sponsor_name="Qwen",
                opportunity_type_reference=OpportunityType.objects.get(code="free_credits"),
                action_type="apply", benefit_type="credits", first_seen_at=NOW,
                last_seen_at=NOW, opportunity_identity=f"linked-{index}",
            )
    classified_post("unrelated-classification", "job_listings")
    with CaptureQueriesContext(connection) as queries:
        page = general_feed(section, as_of=NOW, limit=7)
    assert [item["id"] for item in page["items"]] == [post.pk]
    linked_queries = [query["sql"] for query in queries if "WITH linked AS MATERIALIZED" in query["sql"]]
    assert len(linked_queries) == 1
    assert "CROSS JOIN LATERAL" in linked_queries[0]
    assert "SELECT DISTINCT source_post_id" in linked_queries[0]


@pytest.mark.django_db(transaction=True)
def test_calendar_sparse_recent_window_falls_back_to_older_matches():
    from core.models import Post

    older = classified_post("sparse-older", "events", age=2000)
    Post.objects.bulk_create(
        [Post(tweet_id=f"unrelated-{index:05d}") for index in range(5000)]
    )
    Post.objects.filter(tweet_id__startswith="unrelated-").update(
        fetched_at=NOW - timedelta(hours=1)
    )
    page = general_feed("calendar", as_of=NOW, limit=7)
    assert [item["id"] for item in page["items"]] == [older.pk]
    assert page["next_cursor"] is None


@pytest.mark.django_db(transaction=True)
def test_calendar_candidate_reads_share_snapshot_during_new_event():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    post = classified_post("snapshot-new-event", "events")
    inserted = False

    def write_event():
        try:
            event(post, 2, 3)
        finally:
            connections.close_all()

    def insert_after_recent_window(execute, sql, params, many, context):
        nonlocal inserted
        result = execute(sql, params, many, context)
        if not inserted and sql.lstrip().startswith("WITH recent AS MATERIALIZED"):
            inserted = True
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(write_event).result(timeout=10)
        return result

    with connection.execute_wrapper(insert_after_recent_window):
        old_page = general_feed("calendar", as_of=NOW)
    assert inserted
    assert old_page["items"][0]["timing"]["state"] == "unknown"
    new_page = general_feed("calendar", as_of=NOW)
    assert new_page["items"][0]["timing"]["state"] == "upcoming"


@pytest.mark.django_db(transaction=True)
def test_calendar_caller_owned_read_committed_transaction_uses_complete_reader():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections, transaction

    post = classified_post("caller-owned-snapshot", "events")
    inserted = False

    def add_event():
        try:
            event(post, 2, 3)
        finally:
            connections.close_all()

    def insert_after_candidates(execute, sql, params, many, context):
        nonlocal inserted
        result = execute(sql, params, many, context)
        if not inserted and 'AS "fetched_at"' in sql and 'FROM "posts"' in sql:
            inserted = True
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(add_event).result(timeout=10)
        return result

    with transaction.atomic(), CaptureQueriesContext(connection) as queries, connection.execute_wrapper(insert_after_candidates):
        page = general_feed("calendar", as_of=NOW)
    assert inserted
    assert [item["id"] for item in page["items"]] == [post.pk]
    assert page["items"][0]["timing"]["state"] == "upcoming"
    assert not any("WITH recent AS MATERIALIZED" in query["sql"] for query in queries)


@pytest.mark.django_db(transaction=True)
def test_calendar_respects_caller_disabled_autocommit():
    post = classified_post("caller-disabled-autocommit", "events")
    connection.set_autocommit(False)
    try:
        with CaptureQueriesContext(connection) as queries:
            page = general_feed("calendar", as_of=NOW)
        assert [item["id"] for item in page["items"]] == [post.pk]
        assert not any("SET TRANSACTION ISOLATION" in query["sql"] for query in queries)
        assert not any("WITH recent AS MATERIALIZED" in query["sql"] for query in queries)
    finally:
        connection.rollback()
        connection.set_autocommit(True)


@pytest.mark.django_db(transaction=True)
def test_bounded_calendar_respects_shared_public_post_and_signal_readers(monkeypatch):
    from monitor import general_readers

    kept = classified_post("policy-kept", "events", brand="qwen")
    hidden = classified_post("policy-hidden", "events", brand="qwen")
    excluded_brand = classified_post("policy-excluded-brand", "events", brand="mistral")
    original_posts, original_signals = general_readers.public_posts, general_readers.current_signals
    monkeypatch.setattr(general_readers, "public_posts", lambda: original_posts().exclude(pk=hidden.pk))
    monkeypatch.setattr(
        general_readers, "current_signals", lambda: original_signals().exclude(brand_id="mistral")
    )
    page = general_feed("calendar", as_of=NOW)
    assert [item["id"] for item in page["items"]] == [kept.pk]
    assert hidden.pk != excluded_brand.pk


@pytest.mark.django_db(transaction=True)
def test_bounded_calendar_handles_empty_shared_public_reader(monkeypatch):
    from monitor import general_readers

    classified_post("policy-hidden-all", "events")
    original = general_readers.public_posts
    monkeypatch.setattr(general_readers, "public_posts", lambda: original().none())
    assert general_feed("calendar", as_of=NOW)["items"] == []


@pytest.mark.django_db(transaction=True)
def test_free_pagination_preserves_brands_dated_order_and_exact_classification():
    from core.models import PostBrandClassificationState

    for index in range(24):
        classified_post(f"free-qwen-{index:02d}", "opportunities", age=index + 1)
    classified_post("free-other-brand", "opportunities", brand="mistral")
    failed = classified_post("free-failed", "opportunities")
    PostBrandClassificationState.objects.filter(post=failed).update(outcome="context_missing")
    open_post = classified_post("free-open", "opportunities", age=1000)
    Opportunity.objects.create(
        brand_id="qwen", source_post=open_post, sponsor_name="Qwen",
        opportunity_type_reference=OpportunityType.objects.get(code="free_credits"),
        action_type="apply", benefit_type="credits", first_seen_at=NOW,
        last_seen_at=NOW, opportunity_identity="free-open", source_status="open",
        review_status="confirmed", open_value=(NOW - timedelta(hours=1)).isoformat(),
        open_precision="datetime", close_value=(NOW + timedelta(hours=1)).isoformat(),
        close_precision="datetime",
    )
    seen, cursor = [], None
    while True:
        page = general_feed("free", brands=["qwen"], as_of=NOW, limit=7, cursor=cursor)
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [open_post.pk, *[f"free-qwen-{index:02d}" for index in range(24)]]


@pytest.mark.django_db(transaction=True)
def test_calendar_pagination_preserves_exact_id_order_on_tied_fetch_times(monkeypatch):
    from monitor import general_readers

    ids = ["tie-2", "tie-A", "tie-10", "tie-a", "tie-01", "tie-Z", "tie-3"]
    for post_id in ids:
        classified_post(post_id, "events", age=1)
    original = general_readers._bounded_temporal_candidates

    def all_pages():
        items, cursor = [], None
        while True:
            page = general_feed("calendar", as_of=NOW, limit=2, cursor=cursor)
            items.extend(item["id"] for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                return items

    monkeypatch.setattr(general_readers, "_bounded_temporal_candidates", lambda *a, **kw: None)
    expected = all_pages()
    monkeypatch.setattr(general_readers, "_bounded_temporal_candidates", original)
    assert expected == sorted(ids)
    assert all_pages() == expected


def test_free_stuff_uses_its_own_opening_closing_and_excludes_closed_offers():
    for index, status in enumerate(("open", "upcoming", "closed")):
        post = classified_post(str(2500 + index), "opportunities")
        Opportunity.objects.create(
            brand_id="qwen",
            source_post=post,
            sponsor_name="Qwen",
            opportunity_type_reference=OpportunityType.objects.get(code="free_credits"),
            action_type="apply",
            benefit_type="credits",
            benefit_text="100 credits",
            first_seen_at=NOW,
            last_seen_at=NOW,
            opportunity_identity=post.pk,
            source_status=status,
            review_status="confirmed",
            open_value=(
                NOW + timedelta(hours=2 if status == "upcoming" else -1)
            ).isoformat(),
            open_precision="datetime",
            close_value=(NOW + timedelta(hours=4)).isoformat(),
            close_precision="datetime",
        )
    items = general_feed("free", as_of=NOW)["items"]
    assert [item["id"] for item in items] == ["2500", "2501"]
    assert [item["timing"]["state"] for item in items] == ["open", "upcoming"]

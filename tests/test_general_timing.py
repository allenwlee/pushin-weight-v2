from datetime import timedelta

import pytest

from core.models import Event, EventEvidence, Opportunity
from monitor.general_readers import general_feed
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


def test_free_stuff_uses_its_own_opening_closing_and_excludes_closed_offers():
    for index, status in enumerate(("open", "upcoming", "closed")):
        post = classified_post(str(2500 + index), "opportunities")
        Opportunity.objects.create(
            brand_id="qwen",
            source_post=post,
            sponsor_name="Qwen",
            opportunity_type="free_credits",
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

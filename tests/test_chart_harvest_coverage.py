"""Chart tails reflect completed scheduled query coverage, including empty searches."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.models import Brand, CollectionRun, Post, PostBrand
from core.x_cycle_lineage import ScheduledCycleLineage
from monitor.views import _clear_home_pulse_cache

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
NOW = datetime(2026, 10, 27, 8, 42, 17, tzinfo=UTC)


@pytest.mark.parametrize("window", [7, 30, 365])
def test_long_window_cache_reused_across_request_times(window):
    from monitor.views import _build_home_chart_payload, _build_home_pulse_payload

    _clear_home_pulse_cache()
    with patch(
        "monitor.views._build_home_pulse_payload", wraps=_build_home_pulse_payload
    ) as build_pulse:
        with patch("monitor.views._dashboard_now", return_value=NOW):
            first = _build_home_chart_payload(window, {})
        with patch(
            "monitor.views._dashboard_now", return_value=NOW + timedelta(seconds=1)
        ):
            second = _build_home_chart_payload(window, {})
    assert build_pulse.call_count == 1
    assert first["series"] == second["series"]


def record_harvest(
    end,
    *,
    incomplete=None,
    missing=None,
    optional=False,
    running=False,
    finished_at=None,
    staggered=True,
):
    calls = [
        SimpleNamespace(call_id=key, query_string=f"coverage {key}")
        for key in ("A", "B1")
    ]
    if optional:
        calls.append(
            SimpleNamespace(call_id="SPECIALEVENTS1", query_string="optional search")
        )
    with patch("django.utils.timezone.now", return_value=end):
        lineage = ScheduledCycleLineage.start(
            calls,
            limits={"requests": 10, "bytes": 100000, "seconds": 300, "items": 100},
            invocation_id=uuid.uuid4().hex,
        )
        for index, call in enumerate(calls):
            if call.call_id == missing:
                continue
            scope = lineage.begin_call(
                call,
                since_epoch=int((end - timedelta(minutes=15)).timestamp()),
                until_epoch=int(
                    (
                        end + timedelta(seconds=index * 20 if staggered else 0)
                    ).timestamp()
                ),
            )
            complete = call.call_id != incomplete and call.call_id != "SPECIALEVENTS1"
            lineage.finish_call(
                scope,
                post_ids=[],
                raw_count=0,
                outcome="ok" if complete else "truncated",
                complete=complete,
            )
    if not running:
        with patch(
            "django.utils.timezone.now",
            return_value=finished_at or end + timedelta(minutes=1),
        ):
            lineage.finish(success=not incomplete and not optional)
    return CollectionRun.objects.get(pk=lineage.claim.run_id)


@pytest.mark.parametrize("locale", ["en", "zh_cn", "zh_hans", "ja"])
def test_both_chart_routes_end_at_latest_closed_boundary(client, locale):
    brand = Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    run = record_harvest(NOW.replace(minute=31, second=43), optional=True)
    for tweet_id, minutes in (("covered", 13), ("too-new", 1)):
        post = Post.objects.create(
            tweet_id=tweet_id, created_at=NOW - timedelta(minutes=minutes)
        )
        PostBrand.objects.create(post=post, brand=brand)
    _clear_home_pulse_cache()
    with patch("monitor.views._dashboard_now", return_value=NOW):
        for route in ("/chart/", "/dashboard/each/chart/"):
            response = client.get(
                route, {"brand": "deepseek", "window": 1, "locale": locale}, secure=True
            )
            assert response.status_code == 200
            data = response.json()
            assert data["harvest_coverage"]["run_id"] == str(run.pk)
            assert (
                data["harvest_coverage"]["searched_through"]
                == "2026-10-27T08:31:43+00:00"
            )
            # Coverage ended at 08:30, but the axis follows the request clock
            # (08:42 -> last closed bucket start 08:35). The 08:41 post is still
            # past that closed boundary, so it stays off the chart.
            assert data["days"][-1] == "2026-10-27T08:35:00+00:00"
            assert len(data["days"]) == 288
            totals = data["totals"]
            assert sum(totals.values() if isinstance(totals, dict) else totals) == 1


@pytest.mark.parametrize("failure", ["incomplete", "missing", "running"])
def test_failed_or_partial_cycle_does_not_advance_chart_coverage(failure):
    from monitor.harvest_coverage import latest_scheduled_coverage

    earlier = record_harvest(NOW - timedelta(minutes=20))
    record_harvest(
        NOW - timedelta(minutes=5),
        **({failure: "B1"} if failure != "running" else {"running": True}),
    )
    assert latest_scheduled_coverage(NOW)["run_id"] == str(earlier.pk)


def test_empty_search_is_coverage_and_missing_coverage_still_fills_the_axis(client):
    Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    with patch("monitor.views._dashboard_now", return_value=NOW):
        _clear_home_pulse_cache()
        unknown = client.get("/chart/", {"window": 1}, secure=True).json()
        assert unknown["harvest_coverage"] is None
        assert unknown["days"][-1] == "2026-10-27T08:35:00+00:00"
        assert len(unknown["days"]) == 288
        assert all(unknown["partial_buckets"])
        assert all(value is None for value in unknown["series"]["deepseek"])
        run = record_harvest(NOW - timedelta(minutes=5))
        known = client.get("/chart/", {"window": 1}, secure=True).json()
        assert known["harvest_coverage"]["run_id"] == str(run.pk)
        assert known["days"][-1] == unknown["days"][-1]
        assert not any(known["series"]["deepseek"])


@pytest.mark.parametrize(
    ("minute", "second", "expected_minute"), [(29, 59, 25), (30, 0, 30), (30, 1, 30)]
)
def test_cutoff_is_a_utc_closed_boundary_in_any_request_timezone(
    minute, second, expected_minute
):
    from zoneinfo import ZoneInfo

    from monitor.harvest_coverage import latest_scheduled_coverage

    record_harvest(NOW.replace(minute=minute, second=second))
    assert latest_scheduled_coverage(NOW.astimezone(ZoneInfo("Asia/Tokyo")))[
        "chart_end_at"
    ] == (NOW.replace(minute=expected_minute, second=0).isoformat())


def test_new_complete_run_invalidates_cached_chart_without_changing_request_time(
    client,
):
    Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    record_harvest(NOW - timedelta(minutes=20))
    _clear_home_pulse_cache()
    with patch("monitor.views._dashboard_now", return_value=NOW):
        first = client.get("/chart/", {"window": 1}, secure=True).json()
        latest = record_harvest(NOW - timedelta(minutes=5))
        second = client.get("/chart/", {"window": 1}, secure=True).json()
    assert first["computed_at"] == second["computed_at"]
    assert first["days"][-1] == "2026-10-27T08:35:00+00:00"
    assert second["days"] == first["days"]
    assert second["harvest_coverage"]["run_id"] == str(latest.pk)
    assert first["harvest_coverage"]["run_id"] != second["harvest_coverage"]["run_id"]
    assert any(first["partial_buckets"])
    # A 5-minute-old cycle can still leave the newest displayed bucket unsearched.
    assert first["partial_buckets"].count(True) > second["partial_buckets"].count(True)


def test_stale_coverage_cycle_does_not_freeze_chart_end(client):
    Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    stale = record_harvest(NOW - timedelta(hours=18))
    post = Post.objects.create(
        tweet_id="after-coverage", created_at=NOW - timedelta(minutes=8)
    )
    PostBrand.objects.create(post=post, brand=Brand.objects.get(nickname="deepseek"))
    _clear_home_pulse_cache()
    with patch("monitor.views._dashboard_now", return_value=NOW):
        data = client.get("/chart/", {"window": 1}, secure=True).json()
    assert data["harvest_coverage"]["run_id"] == str(stale.pk)
    assert data["days"][-1] == "2026-10-27T08:35:00+00:00"
    assert len(data["days"]) == 288
    # The stale cycle ended ~18 hours ago; a later post still appears on the axis.
    assert data["series"]["deepseek"][-2] == 1
    assert sum(value or 0 for value in data["series"]["deepseek"]) == 1
    assert any(data["partial_buckets"])


def test_stale_coverage_marks_unsearched_tail_without_freezing_the_axis(client):
    Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    record_harvest(NOW - timedelta(minutes=47))
    _clear_home_pulse_cache()
    with patch("monitor.views._dashboard_now", return_value=NOW):
        data = client.get("/chart/", {"window": 1}, secure=True).json()
    from monitor.harvest_coverage import closed_five_minute_boundary
    assert data["days"][-1] == (closed_five_minute_boundary(NOW) - timedelta(minutes=5)).isoformat()
    assert len(data["days"]) == 288
    partial = data["partial_buckets"]
    assert any(partial) and not all(partial)
    assert all(value is None for value, is_partial in zip(data["series"]["deepseek"], partial) if is_partial)


def test_stale_tail_keeps_observed_posts_but_does_not_invent_empty_counts(client):
    brand = Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    record_harvest(NOW - timedelta(minutes=47))
    post = Post.objects.create(tweet_id="observed-partial", created_at=NOW - timedelta(minutes=12))
    PostBrand.objects.create(post=post, brand=brand)
    _clear_home_pulse_cache()
    with patch("monitor.views._dashboard_now", return_value=NOW):
        data = client.get("/chart/", {"window": 1}, secure=True).json()
    partial_values = [value for value, partial in zip(data["series"]["deepseek"], data["partial_buckets"]) if partial]
    assert 1 in partial_values and None in partial_values
    assert 0 not in partial_values

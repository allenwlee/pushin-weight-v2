"""Caller-level contracts for daily comparisons and live homepage charts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from unittest.mock import patch

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from core.models import Account, Brand, MaterializationState, Post, PostBrand
from monitor.views import _clear_home_pulse_cache

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

NOW = datetime(2026, 10, 17, 12, 30, tzinfo=UTC)
DAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)


class _ChartPayload(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.payload = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "canvas" and "data-home" in values:
            self.payload = json.loads(values["data-home"])


@pytest.fixture
def chart_context():
    MaterializationState.objects.get_or_create(pk="home.brand_time_counts.v1")
    brand = Brand.objects.create(
        nickname="materialized-test",
        display_name="Count fixture",
        display_name_en="Count fixture",
        display_name_zh_cn="计数样本",
        accent_color="#123456",
    )
    _clear_home_pulse_cache()
    with (
        override_settings(
            OLLIJA_STAGING_MODE=False,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            },
        ),
        patch("monitor.views._tracked_home_brand_nicknames", return_value=(brand.pk,)),
        patch("monitor.views._dashboard_now", return_value=NOW),
    ):
        yield Client(HTTP_HOST="127.0.0.1"), brand
    _clear_home_pulse_cache()


def _post(brand, key, at, *, author=None):
    post = Post.objects.create(tweet_id=key, created_at=at, author=author)
    PostBrand.objects.create(post=post, brand=brand)
    return post


def _payload(response):
    assert response.status_code == 200
    if response.headers.get("Content-Type", "").startswith("application/json"):
        return response.json()
    parser = _ChartPayload()
    parser.feed(response.content.decode())
    assert parser.payload is not None, "real response must contain its chart payload"
    return parser.payload


@pytest.mark.parametrize("window", [30, 365])
@pytest.mark.parametrize("path", ["/", "/chart.html", "/chart/"])
@pytest.mark.parametrize("materialized", [False, True])
def test_long_comparison_uses_midnight_but_chart_clock_stays_live(
    chart_context, window, path, materialized
):
    client, brand = chart_context
    dates = [
        DAY - timedelta(days=window) + timedelta(hours=1),
        DAY - timedelta(days=1),
        DAY - timedelta(days=2 * window) + timedelta(hours=1),
        DAY + timedelta(hours=1),
        DAY + timedelta(hours=3),
    ]
    for index, at in enumerate(dates):
        _post(brand, f"daily-{window}-{index}", at)

    if materialized:
        from monitor.home_count_summary import refresh_home_counts

        assert refresh_home_counts()["status"] == "refreshed"
    with CaptureQueriesContext(connection) as queries:
        payload = _payload(
            client.get(
                path,
                {"window": window, "locale": "en", "timezone": "UTC"},
                secure=True,
            )
        )
    if materialized:
        assert any(
            "FROM home_brand_time_counts" in row["sql"]
            for row in queries.captured_queries
        )
    entry = next(
        row for row in payload["pulse"]["entries"] if row["nickname"] == brand.pk
    )
    assert (entry["current_count"], entry["prior_count"]) == (2, 1)
    assert entry["delta_percent"] == 100
    assert payload["pulse"]["comparison_as_of"] == DAY.isoformat()
    assert payload["computed_at"] == payload["pulse"]["computed_at"] == NOW.isoformat()
    assert payload["series"][brand.pk][-1] == 2
    assert payload["totals"][brand.pk] == 3


@pytest.mark.parametrize("window", [1, 7])
def test_short_comparison_keeps_exact_rolling_boundaries(chart_context, window):
    client, brand = chart_context
    dates = [
        NOW - timedelta(days=2 * window, microseconds=1),
        NOW - timedelta(days=2 * window),
        NOW - timedelta(days=window, microseconds=1),
        NOW - timedelta(days=window),
        NOW - timedelta(microseconds=1),
        NOW,
        NOW + timedelta(microseconds=1),
    ]
    for index, at in enumerate(dates):
        _post(brand, f"rolling-{window}-{index}", at)
    payload = _payload(
        client.get("/chart.html", {"window": window, "locale": "en"}, secure=True)
    )
    entry = next(
        row for row in payload["pulse"]["entries"] if row["nickname"] == brand.pk
    )
    assert (entry["current_count"], entry["prior_count"]) == (2, 2)
    assert payload["computed_at"] == NOW.isoformat()


@pytest.mark.parametrize("path", ["/", "/chart.html", "/chart/"])
@pytest.mark.parametrize("correct_history", [False, True])
def test_seven_day_comparison_reuses_history_at_exact_partial_bucket_boundaries(
    chart_context, path, correct_history
):
    from monitor.home_count_summary import read_home_counts, refresh_home_counts

    client, brand = chart_context
    anchor = NOW + timedelta(minutes=7, seconds=33, microseconds=123456)
    start = anchor - timedelta(days=14)
    midpoint = anchor - timedelta(days=7)
    dates = [
        start - timedelta(microseconds=1), start,
        midpoint - timedelta(microseconds=1), midpoint,
        anchor - timedelta(microseconds=1), anchor,
    ]
    posts = [_post(brand, f"partial-{i}", at) for i, at in enumerate(dates)]
    assert refresh_home_counts()["status"] == "refreshed"
    if correct_history:
        posts[2].created_at = midpoint + timedelta(seconds=1)
        posts[2].save(update_fields=["created_at"])
    params = {"window": 7, "locale": "en", "timezone": "Asia/Tokyo"}
    with (
        patch("monitor.views._dashboard_now", return_value=anchor),
        patch("monitor.home_count_summary.read_home_counts", wraps=read_home_counts) as reader,
    ):
        summary = _payload(client.get(path, params, secure=True))
    assert any(
        call.kwargs.get("midpoint") == midpoint for call in reader.call_args_list
    ), "the rolling Pulse comparison must reuse saved history, not rescan fourteen days"
    _clear_home_pulse_cache()
    with (
        patch("monitor.views._dashboard_now", return_value=anchor),
        patch("monitor.home_count_summary.read_home_counts", return_value=None),
    ):
        exact = _payload(client.get(path, params, secure=True))
    for key in ("days", "series", "totals", "pulse"):
        assert summary[key] == exact[key], (path, correct_history, key)
    entry = next(row for row in summary["pulse"]["entries"] if row["nickname"] == brand.pk)
    assert (entry["current_count"], entry["prior_count"]) == (
        (3, 1) if correct_history else (2, 2)
    )


@pytest.mark.parametrize("midpoint", [None, DAY - timedelta(days=30)])
def test_aligned_summary_keeps_source_scan_after_publication_boundary(chart_context, midpoint):
    from monitor.home_count_summary import read_home_counts, refresh_home_counts

    _, brand = chart_context
    _post(brand, "saved-prefix-only", DAY - timedelta(days=5))
    assert refresh_home_counts()["status"] == "refreshed"
    source_lower_bounds = []

    def observe(execute, sql, params, many, context):
        if "FROM home_brand_time_counts" in sql:
            before_source_bound = sql.split("AND p.created_at >= %s", 1)[0]
            source_lower_bounds.append(params[before_source_bound.count("%s")])
        return execute(sql, params, many, context)

    with connection.execute_wrapper(observe):
        counts = read_home_counts(
            start=DAY - timedelta(days=60), end=NOW, midpoint=midpoint,
            brand_ids=[brand.pk],
        )
    assert counts is not None
    assert sum(row["count"] for row in counts) == 1
    assert source_lower_bounds == [DAY], "aligned reads must not rescan saved history"


@pytest.mark.parametrize("locale", ["en", "zh_cn", "ja"])
def test_real_home_and_chart_requests_do_not_rank_or_render_top_voices(
    chart_context, locale
):
    client, brand = chart_context
    account = Account.objects.create(
        author_id="count-voice", handle="count_voice", followers_count=100_000
    )
    _post(brand, "voice-fixture", NOW - timedelta(hours=1), author=account)
    for path in ("/", "/chart.html"):
        _clear_home_pulse_cache()
        with CaptureQueriesContext(connection) as queries:
            response = client.get(path, {"window": 365, "locale": locale}, secure=True)
        payload = _payload(response)
        ranking = [
            row["sql"]
            for row in queries.captured_queries
            if "GROUP BY" in row["sql"].upper()
            and "ACCOUNTS" in row["sql"].upper()
            and "FOLLOWERS_COUNT" in row["sql"].upper()
        ]
        assert ranking == [], "page requests must not calculate a global author ranking"
        assert "data-pw-headline-voices" not in response.content.decode()
        assert payload.get("top_voices", {}).get("entries", []) == []
        assert "trend_narrative" in payload


@pytest.mark.parametrize("window", [7, 30, 365])
@pytest.mark.parametrize(
    "zone",
    ["UTC", "Asia/Tokyo", "America/Los_Angeles", "Asia/Kathmandu", "Pacific/Chatham"],
)
@pytest.mark.parametrize(
    "modes",
    [
        ({}, None, False),
        ({"unsanctioned": "only"}, True, None),
        ({"untracked_brand_promotions": "only"}, None, True),
    ],
)
def test_real_chart_summary_equals_exact_source_for_local_days_and_eligibility(
    chart_context, window, zone, modes
):
    from core.models import PostUnsanctionedFlag, PostUntrackedBrandPromotion
    from monitor.home_count_summary import refresh_home_counts

    client, brand = chart_context
    filters, _, _ = modes
    dates = [
        DAY - timedelta(days=window, microseconds=1),
        DAY - timedelta(days=window),
        DAY - timedelta(days=window - 1, hours=9),
        DAY - timedelta(days=2, hours=1),
        DAY - timedelta(microseconds=1),
        DAY,
        NOW - timedelta(microseconds=1),
        NOW,
        NOW + timedelta(days=1),
        None,
        datetime(2026, 3, 8, 9, 59, tzinfo=UTC),
        datetime(2026, 3, 8, 10, 1, tzinfo=UTC),
    ]
    for i, at in enumerate(dates):
        post = _post(brand, f"parity-{i}", at)
        if i % 3 == 0:
            PostUnsanctionedFlag.objects.create(post=post, flags='["test"]')
        if i % 4 == 0:
            PostUntrackedBrandPromotion.objects.create(
                post=post, promotion_keys=["ads_spam"]
            )
    # An equivalent raw FK must still project the canonical Brand identity.
    PostBrand.objects.filter(brand=brand).update(brand_id=brand.pk.upper())
    assert refresh_home_counts()["status"] == "refreshed"
    params = {
        "window": window,
        "locale": "en",
        "timezone": zone,
        "filters": json.dumps(filters),
    }
    with CaptureQueriesContext(connection) as queries:
        summary = _payload(client.get("/chart.html", params, secure=True))
    assert any(
        "FROM home_brand_time_counts" in row["sql"] for row in queries.captured_queries
    )
    _clear_home_pulse_cache()
    with patch("monitor.home_count_summary.read_home_counts", return_value=None):
        exact = _payload(client.get("/chart.html", params, secure=True))
    for key in ("days", "series", "totals", "stacked", "pulse"):
        assert summary[key] == exact[key], (window, zone, filters, key)


@pytest.mark.parametrize("window", [7, 30, 365])
@pytest.mark.parametrize("path", ["/", "/chart.html", "/chart/"])
@pytest.mark.parametrize("zone", ["UTC", "Asia/Tokyo"])
def test_historical_correction_recounts_its_whole_bucket_and_reuses_earlier_history(
    chart_context, window, path, zone,
):
    from monitor.home_count_summary import refresh_home_counts

    client, brand = chart_context
    _post(brand, "correction-prefix", DAY - timedelta(days=5))
    # Both this existing row and the later insert belong to the same saved
    # quarter hour. Splitting at the exact dirty timestamp would double-count
    # this existing row when the raw tail is added.
    bucket_day = DAY - timedelta(days=2)
    _post(brand, "correction-original", bucket_day + timedelta(hours=13, minutes=27))
    assert refresh_home_counts()["status"] == "refreshed"
    params = {"window": window, "locale": "en", "timezone": zone}
    before = _payload(client.get(path, params, secure=True))
    _post(brand, "correction-late", bucket_day + timedelta(hours=13, minutes=24))
    with CaptureQueriesContext(connection) as queries:
        dirty = _payload(client.get(path, params, secure=True))
    assert dirty["totals"][brand.pk] == before["totals"][brand.pk] + 1
    assert any(
        "FROM home_brand_time_counts" in row["sql"] for row in queries.captured_queries
    ), "a bounded historical correction must not force a complete year recount"
    if window == 7:
        # Short Pulse comparisons retain their existing one-minute cache.
        assert dirty["pulse"] == before["pulse"]
    _clear_home_pulse_cache()
    uncached_dirty = _payload(client.get(path, params, secure=True))
    assert dirty["series"] == uncached_dirty["series"]
    if window != 7:
        assert dirty["pulse"] == uncached_dirty["pulse"]
    _clear_home_pulse_cache()
    with patch("monitor.home_count_summary.read_home_counts", return_value=None):
        exact = _payload(client.get(path, params, secure=True))
    for key in ("days", "series", "totals", "stacked", "pulse"):
        assert uncached_dirty[key] == exact[key], (window, path, zone, key)
    assert refresh_home_counts()["status"] == "refreshed"
    recovered = _payload(client.get(path, params, secure=True))
    assert recovered["series"] == dirty["series"]


@pytest.mark.parametrize(
    "unavailable",
    ["missing_state", "missing_view", "timeout", "unknown_boundary", "global_change"],
)
def test_real_chart_falls_back_without_broken_transaction_when_summary_is_unavailable(
    chart_context, unavailable
):
    from django.db import transaction

    from core.models import MaterializationState
    from monitor.home_count_summary import refresh_home_counts

    client, brand = chart_context
    _post(brand, "fallback-history", DAY - timedelta(days=2))
    assert refresh_home_counts()["status"] == "refreshed"
    params = {"window": 30, "locale": "en"}
    expected = _payload(client.get("/chart.html", params, secure=True))
    _clear_home_pulse_cache()

    def cancel_summary(execute, sql, params, many, context):
        if "FROM home_brand_time_counts" in sql:
            execute("SET LOCAL statement_timeout = '1ms'", None, False, context)
            execute("SELECT pg_sleep(0.05)", None, False, context)
        return execute(sql, params, many, context)

    # Roll back the deliberately missing objects even if the assertion fails.
    class RestoreFixture(Exception):
        pass

    with pytest.raises(RestoreFixture), transaction.atomic():
        if unavailable == "missing_state":
            MaterializationState.objects.all().delete()
        elif unavailable == "missing_view":
            with connection.cursor() as cursor:
                cursor.execute("DROP MATERIALIZED VIEW home_brand_time_counts")
        elif unavailable in {"unknown_boundary", "global_change"}:
            from django.db.models import F

            MaterializationState.objects.update(
                source_generation=F("source_generation") + 1,
                dirty_since=(
                    datetime.min.replace(tzinfo=UTC)
                    if unavailable == "global_change" else None
                ),
            )
        if unavailable == "timeout":
            with connection.execute_wrapper(cancel_summary):
                actual = _payload(client.get("/chart.html", params, secure=True))
        else:
            actual = _payload(client.get("/chart.html", params, secure=True))
        assert actual["series"] == expected["series"]
        assert actual["pulse"] == expected["pulse"]
        assert Post.objects.filter(pk="fallback-history").exists()
        raise RestoreFixture


@pytest.mark.parametrize("mutation", ["move_earlier", "move_later", "flag", "delete"])
def test_dirty_prefix_matches_exact_chart_after_existing_history_changes(
    chart_context, mutation
):
    from core.models import PostUntrackedBrandPromotion
    from monitor.home_count_summary import refresh_home_counts

    client, brand = chart_context
    _post(brand, "mutation-prefix", DAY - timedelta(days=20))
    changed = _post(brand, "mutation-original", DAY - timedelta(days=5, hours=1))
    assert refresh_home_counts()["status"] == "refreshed"
    if mutation == "move_earlier":
        Post.objects.filter(pk=changed.pk).update(created_at=DAY - timedelta(days=10))
    elif mutation == "move_later":
        Post.objects.filter(pk=changed.pk).update(created_at=DAY - timedelta(days=2))
    elif mutation == "flag":
        PostUntrackedBrandPromotion.objects.create(post=changed, promotion_keys=["ads_spam"])
    else:
        PostBrand.objects.filter(post=changed).delete()
    params = {"window": 365, "locale": "en", "timezone": "Asia/Tokyo"}
    with CaptureQueriesContext(connection) as queries:
        actual = _payload(client.get("/chart.html", params, secure=True))
    assert any("FROM home_brand_time_counts" in row["sql"] for row in queries)
    _clear_home_pulse_cache()
    with patch("monitor.home_count_summary.read_home_counts", return_value=None):
        expected = _payload(client.get("/chart.html", params, secure=True))
    for key in ("days", "series", "totals", "stacked", "pulse"):
        assert actual[key] == expected[key], (mutation, key)


@pytest.mark.django_db(transaction=True)
def test_new_older_correction_between_preflight_and_count_uses_new_snapshot(chart_context):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from monitor.home_count_summary import refresh_home_counts

    client, brand = chart_context
    _post(brand, "race-prefix", DAY - timedelta(days=20))
    assert refresh_home_counts()["status"] == "refreshed"
    _post(brand, "race-first-dirty", DAY - timedelta(days=2))
    changed = False

    def write_older_correction():
        try:
            _post(brand, "race-earlier-dirty", DAY - timedelta(days=10))
        finally:
            connections.close_all()

    def race(execute, sql, params, many, context):
        nonlocal changed
        if "FROM home_brand_time_counts" in sql and not changed:
            changed = True
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(write_older_correction).result(timeout=5)
        return execute(sql, params, many, context)

    params = {"window": 365, "locale": "en", "timezone": "Asia/Tokyo"}
    with connection.execute_wrapper(race):
        actual = _payload(client.get("/chart.html", params, secure=True))
    assert changed, "the real chart must read the usable native prefix"
    assert actual["totals"][brand.pk] == 3
    _clear_home_pulse_cache()
    with patch("monitor.home_count_summary.read_home_counts", return_value=None):
        expected = _payload(client.get("/chart.html", params, secure=True))
    for key in ("days", "series", "totals", "stacked", "pulse"):
        assert actual[key] == expected[key], key


@pytest.mark.parametrize("window", [30, 365])
def test_old_fixed_request_clock_uses_full_history_without_future_leakage(
    chart_context, window
):
    from monitor.home_count_summary import refresh_home_counts

    client, brand = chart_context
    historical_now = datetime(2024, 2, 29, 12, 30, tzinfo=UTC)
    for index, at in enumerate(
        (
            historical_now - timedelta(days=2 * window - 1),
            historical_now - timedelta(days=window - 1),
            historical_now - timedelta(hours=1),
            historical_now + timedelta(hours=1),
            NOW - timedelta(days=2),
        )
    ):
        _post(brand, f"old-clock-{index}", at)
    assert refresh_home_counts()["status"] == "refreshed"
    params = {"window": window, "timezone": "Asia/Tokyo"}
    with patch("monitor.views._dashboard_now", return_value=historical_now):
        summary = _payload(client.get("/chart.html", params, secure=True))
        _clear_home_pulse_cache()
        with patch("monitor.home_count_summary.read_home_counts", return_value=None):
            exact = _payload(client.get("/chart.html", params, secure=True))
    assert summary["series"] == exact["series"]
    assert summary["pulse"] == exact["pulse"]
    entry = next(
        row for row in summary["pulse"]["entries"] if row["nickname"] == brand.pk
    )
    assert (entry["current_count"], entry["prior_count"]) == (1, 1)

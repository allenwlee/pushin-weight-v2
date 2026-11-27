"""Exercise the General page's bounded database readers on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock, get_ident

import pytest
from django.db import connection, connections
from django.utils import translation

from monitor import general_views
from tests.general_helpers import NOW, classified_post, saved_commentary


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_parallel_panels_are_bounded_and_preserve_request_context(monkeypatch):
    barrier = Barrier(2, timeout=10)
    lock = Lock()
    active = 0
    peak = 0
    calls = []

    def fake_feed(section, **options):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append((section, options, translation.get_language(), get_ident()))
        barrier.wait()
        with lock:
            active -= 1
        return section

    monkeypatch.setattr(general_views, "general_feed", fake_feed)
    result = general_views._general_panel_feeds(locale="zh-cn", brands=["qwen"], as_of=NOW)

    assert list(result) == list(general_views.SECTIONS)
    assert result == {section: section for section in general_views.SECTIONS}
    assert peak == 2
    assert len({call[3] for call in calls}) == 2
    assert all(
        options == {"locale": "zh-cn", "brands": ["qwen"], "as_of": NOW}
        and language == "zh-hans"
        for _, options, language, _ in calls
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_simultaneous_requests_share_the_worker_reader_limit(monkeypatch):
    lock = Lock()
    two_readers = Event()
    third_attempt = Event()
    release = Event()
    exceeded = Event()
    active = 0
    attempts = 0
    slots = general_views._GENERAL_FEED_SLOTS

    class TrackedSlots:
        def acquire(self, *args, **kwargs):
            nonlocal attempts
            with lock:
                attempts += 1
                if attempts == 3:
                    third_attempt.set()
            return slots.acquire(*args, **kwargs)

        def release(self):
            return slots.release()

    def fake_feed(section, **options):
        nonlocal active
        with lock:
            active += 1
            if active == 2:
                two_readers.set()
            if active > 2:
                exceeded.set()
        try:
            assert release.wait(10)
            return section
        finally:
            with lock:
                active -= 1

    def request():
        try:
            return general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)
        finally:
            connections.close_all()

    monkeypatch.setattr(general_views, "general_feed", fake_feed)
    monkeypatch.setattr(general_views, "_GENERAL_FEED_SLOTS", TrackedSlots())
    with ThreadPoolExecutor(max_workers=2) as callers:
        futures = [callers.submit(request) for _ in range(2)]
        try:
            assert two_readers.wait(10)
            assert third_attempt.wait(10)
            acquired = slots.acquire(blocking=False)
            if acquired:
                slots.release()
            assert not acquired
            assert not exceeded.is_set()
        finally:
            release.set()
        for future in futures:
            assert len(future.result()) == len(general_views.SECTIONS)
    assert not exceeded.is_set()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_panel_failure_does_not_start_later_reads(monkeypatch):
    both_started = Barrier(2, timeout=10)
    release = Event()
    finished = Event()
    called = []

    def fake_feed(section, **options):
        called.append(section)
        if section in ("calendar", "free"):
            both_started.wait()
        if section == "free":
            raise ValueError("panel failed")
        if section == "calendar":
            try:
                assert release.wait(10)
            finally:
                finished.set()
        return section

    def request():
        try:
            return general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)
        finally:
            connections.close_all()

    monkeypatch.setattr(general_views, "general_feed", fake_feed)
    with ThreadPoolExecutor(max_workers=1) as caller:
        future = caller.submit(request)
        try:
            with pytest.raises(ValueError, match="panel failed"):
                future.result(timeout=5)
        finally:
            release.set()
        assert finished.wait(10)
        slots = general_views._GENERAL_FEED_SLOTS
        assert slots.acquire(timeout=10)
        try:
            assert slots.acquire(timeout=10)
            slots.release()
        finally:
            slots.release()
    assert set(called) == {"calendar", "free"}


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("fail", [False, True])
def test_reader_connections_close_on_success_and_failure(monkeypatch, fail):
    closed = []
    opened = []
    close_all = connections.close_all

    def fake_feed(section, **options):
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
            opened.append(connections["default"].connection)
        if fail and section == "calendar":
            raise ValueError("panel failed")
        return section

    def track_close():
        close_all()
        closed.append(connections["default"].connection is None)

    monkeypatch.setattr(general_views, "general_feed", fake_feed)
    monkeypatch.setattr(connections, "close_all", track_close)
    if fail:
        with pytest.raises(ValueError, match="panel failed"):
            general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)
        slots = general_views._GENERAL_FEED_SLOTS
        assert slots.acquire(timeout=10)
        try:
            assert slots.acquire(timeout=10)
            slots.release()
        finally:
            slots.release()
        fail = False
        assert len(general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)) == 4
    else:
        assert len(general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)) == 4
    assert opened and len(opened) == len(closed)
    assert all(closed) and all(raw.closed for raw in opened)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_reader_statement_deadline_cancels_a_stalled_query(monkeypatch):
    def stalled_feed(section, **options):
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT pg_sleep(1)")
        return section

    monkeypatch.setattr(general_views, "_GENERAL_READ_BUDGET_SECONDS", 0.1)
    monkeypatch.setattr(general_views, "general_feed", stalled_feed)
    with pytest.raises(general_views.GeneralReadTimeout, match="deadline"):
        general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)
    slots = general_views._GENERAL_FEED_SLOTS
    assert slots.acquire(timeout=10)
    try:
        assert slots.acquire(timeout=10)
        slots.release()
    finally:
        slots.release()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_parallel_page_renders_real_committed_panel_results(client, monkeypatch):
    for key, category in (("75101", "job_listings"), ("75102", "personnel_changes")):
        saved_commentary(classified_post(key, category))
    monkeypatch.setattr(general_views.timezone, "now", lambda: NOW)

    response = client.get("/general/?lang=en", secure=True)

    assert response.status_code == 200
    for section, key in (("jobs", "75101"), ("moving", "75102")):
        payload = client.get(f"/general/feed/?section={section}&lang=en", secure=True).json()
        assert [item["id"] for item in payload["items"]] == [key]
        assert payload["items"][0]["url"] in response.content.decode()


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_atomic_caller_keeps_reads_on_its_connection(monkeypatch):
    caller = get_ident()
    monkeypatch.setattr(general_views, "general_feed", lambda section, **kwargs: get_ident())
    result = general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)
    assert set(result.values()) == {caller}


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_manual_transaction_keeps_reads_on_its_connection(monkeypatch):
    caller = get_ident()
    monkeypatch.setattr(general_views, "general_feed", lambda section, **kwargs: get_ident())
    connection.set_autocommit(False)
    try:
        result = general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)
        assert set(result.values()) == {caller}
    finally:
        connection.rollback()
        connection.set_autocommit(True)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_fragment_admission_uses_same_slots_and_returns_retryable_failure(client, monkeypatch):
    monkeypatch.setattr(general_views, "_GENERAL_READ_BUDGET_SECONDS", 0.05, raising=False)
    slots = general_views._GENERAL_FEED_SLOTS
    assert slots.acquire(timeout=1)
    assert slots.acquire(timeout=1)
    try:
        response = client.get("/general/feed/?section=jobs&lang=en", secure=True)
    finally:
        slots.release()
        slots.release()
    assert response.status_code == 503
    assert response["Retry-After"] == "1"
    assert "private" in response["Cache-Control"]
    assert "no-store" in response["Cache-Control"]


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_fragment_timeout_preserves_caller_transaction_and_connection_settings(client, monkeypatch):
    def stalled_feed(section, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(0.2)")
        return {"section": section, "locale": options["locale"], "as_of": NOW.isoformat(), "items": [], "next_cursor": None}

    monkeypatch.setattr(general_views, "_GENERAL_READ_BUDGET_SECONDS", 0.05, raising=False)
    monkeypatch.setattr(general_views, "general_feed", stalled_feed)
    original = connection.connection
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        original_timeout = cursor.fetchone()[0]
    response = client.get("/general/feed/?section=jobs&lang=en", secure=True)
    assert response.status_code == 503
    assert connection.connection is original
    assert connection.in_atomic_block and not connection.needs_rollback
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == original_timeout
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_initial_selection_uses_the_request_deadline(client, monkeypatch):
    select = general_views.selection

    def slow_selection(request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(0.2)")
        return select(request)

    monkeypatch.setattr(general_views, "selection", slow_selection)
    monkeypatch.setattr(general_views, "_GENERAL_READ_BUDGET_SECONDS", 0.05, raising=False)
    response = client.get("/general/?lang=ja", secure=True)
    assert response.status_code == 503
    assert response["Retry-After"] == "1"


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_request_deadline_is_cumulative_and_restores_connection_timeout():
    from monitor.general_budget import GeneralReadBudget, GeneralReadTimeout
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        original = cursor.fetchone()[0]
    with pytest.raises(GeneralReadTimeout), GeneralReadBudget(0.12).on_connection(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_sleep(0.08)")
        cursor.execute("SELECT pg_sleep(0.08)")
    assert connection.get_autocommit() and not connection.needs_rollback
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == original
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


@pytest.mark.parametrize("locale,expected", [("en", "Retry"), ("ja", "再試行"), ("zh_hans", "重试")])
@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_expired_initial_page_returns_localized_retry(client, monkeypatch, locale, expected):
    monkeypatch.setattr(general_views, "_GENERAL_READ_BUDGET_SECONDS", 0)
    response = client.get(f"/general/?lang={locale}", secure=True)
    assert response.status_code == 503
    assert expected in response.content.decode()
    assert response["Retry-After"] == "1"
    assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]

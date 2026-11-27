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
        def __enter__(self):
            nonlocal attempts
            with lock:
                attempts += 1
                if attempts == 3:
                    third_attempt.set()
            return slots.__enter__()

        def __exit__(self, *args):
            return slots.__exit__(*args)

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
    failed = Event()
    third_attempt = Event()
    release = Event()
    called = []
    lock = Lock()
    attempts = 0
    slots = general_views._GENERAL_FEED_SLOTS

    class TrackedSlots:
        def __enter__(self):
            nonlocal attempts
            with lock:
                attempts += 1
                if attempts == 3:
                    third_attempt.set()
            return slots.__enter__()

        def __exit__(self, *args):
            return slots.__exit__(*args)

    def fake_feed(section, **options):
        called.append(section)
        if section in ("calendar", "free"):
            both_started.wait()
        if section == "free":
            failed.set()
            raise ValueError("panel failed")
        if section == "calendar":
            assert release.wait(10)
        return section

    def request():
        try:
            return general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)
        finally:
            connections.close_all()

    monkeypatch.setattr(general_views, "general_feed", fake_feed)
    monkeypatch.setattr(general_views, "_GENERAL_FEED_SLOTS", TrackedSlots())
    with ThreadPoolExecutor(max_workers=1) as caller:
        future = caller.submit(request)
        try:
            assert failed.wait(10)
            assert third_attempt.wait(10)
        finally:
            release.set()
        with pytest.raises(ValueError, match="panel failed"):
            future.result()
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
        fail = False
        assert len(general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)) == 4
    else:
        assert len(general_views._general_panel_feeds(locale="en", brands=[], as_of=NOW)) == 4
    assert opened and len(opened) == len(closed)
    assert all(closed) and all(raw.closed for raw in opened)


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

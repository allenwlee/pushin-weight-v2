from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from django.db import connection, connections, transaction

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_lock_keys_use_database_equivalence():
    from core.organization_identity_locks import organization_lock_keys

    assert organization_lock_keys(name="i", nickname="Foo") == organization_lock_keys(
        name="ı", nickname="foo"
    )
    assert organization_lock_keys(
        name="Different", nickname="other"
    ) != organization_lock_keys(name="i", nickname="Foo")


def test_unrelated_writer_proceeds_while_matching_writer_waits():
    from core.organization_identity_locks import (
        acquire_ingestion_identity_locks,
        acquire_writer_identity_locks,
        organization_lock_keys,
    )

    target = organization_lock_keys(name="Shared Lab", nickname="shared-lab")
    unrelated = organization_lock_keys(name="Other Lab", nickname="other-lab")
    held, release, started, done = Event(), Event(), Event(), Event()
    backend = []

    def ingestion():
        try:
            with transaction.atomic():
                assert acquire_ingestion_identity_locks(target)
                held.set()
                assert release.wait(5)
        finally:
            connections.close_all()

    def writer():
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend.append(cursor.fetchone()[0])
                started.set()
                acquire_writer_identity_locks(target)
                done.set()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ingestion_future = pool.submit(ingestion)
        assert held.wait(5)
        writer_future = pool.submit(writer)
        assert started.wait(5)
        try:
            with transaction.atomic():
                acquire_writer_identity_locks(unrelated)
            deadline = monotonic() + 3
            waited = False
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = %s",
                        [backend[0]],
                    )
                    row = cursor.fetchone()
                if row and row[0]:
                    waited = True
                    break
                if done.is_set():
                    break
                Event().wait(0.02)
            assert waited and not done.is_set()
        finally:
            release.set()
        ingestion_future.result(timeout=5)
        writer_future.result(timeout=5)
    assert done.is_set()


def test_scheduled_registration_waits_for_matching_organization_then_rechecks():
    from core.models import Account, OfficialCompanyAccountState
    from core.official_company_accounts import register_account
    from core.organization_identity_locks import (
        acquire_ingestion_identity_locks,
        organization_lock_keys,
    )
    from x_monitor.config import OfficialCompanyConfig

    account = Account.objects.create(author_id="982291", handle="lock_lab")
    state = OfficialCompanyAccountState.objects.create(
        account=account,
        evidence_hash="a" * 64,
        status="accepted",
        decision={"outcome": "accepted", "organization_name": "Matching Writer Lab"},
    )
    keys = organization_lock_keys(
        name="Matching Writer Lab", nickname="matching-writer-lab"
    )
    held, release, started = Event(), Event(), Event()
    backend = []
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)

    def ingestion_lock():
        try:
            with transaction.atomic():
                assert acquire_ingestion_identity_locks(keys)
                held.set()
                assert release.wait(5)
        finally:
            connections.close_all()

    def scheduled():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                backend.append(cursor.fetchone()[0])
            started.set()
            return register_account(state.pk, cfg=cfg)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ingestion = pool.submit(ingestion_lock)
        assert held.wait(5)
        scheduled_result = pool.submit(scheduled)
        assert started.wait(5)
        try:
            deadline = monotonic() + 3
            waited = False
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = %s",
                        [backend[0]],
                    )
                    row = cursor.fetchone()
                if row and row[0]:
                    waited = True
                    break
                if scheduled_result.done():
                    break
                Event().wait(0.02)
            assert waited, (
                "scheduled registration did not wait for the matching organization"
            )
        finally:
            release.set()
        ingestion.result(timeout=5)
        assert scheduled_result.result(timeout=5) == state.pk

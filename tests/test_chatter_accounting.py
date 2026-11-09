"""The new chain spends through shared calls, retaining uncertainty and trial limits."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import connection

from core.models import EditorialCall, OriginalContentCall
from monitor.editorial.config import ChatterTrial, ChatterWorkflow
from monitor.editorial.persistence import BudgetHeld
from tests.test_original_content_consideration import consideration

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def policy(limit=None):
    trial = (
        None
        if limit is None
        else ChatterTrial(scope="chatter-test", limit_usd=limit, carry_usd=0)
    )
    return SimpleNamespace(
        chatter=ChatterWorkflow(trial=trial, max_call_usd=5, max_calls_per_run=40)
    )


def metadata(identity="a"):
    return {
        "request_hash": identity * 64,
        "request_packet": {"model": "fixture"},
        "provider": "fixture",
        "model": "fixture",
        "workflow_version": "fixture",
        "rates": {"input_usd_per_million": 1, "output_usd_per_million": 1},
    }


def test_shared_call_is_replayed_without_a_second_transport_or_legacy_rows():
    from monitor.editorial.chatter_accounting import call_once

    run = consideration().run
    sends = []

    def send():
        # pytest owns a test transaction; the call must not retain its reservation's savepoint.
        sends.append(len(connection.savepoint_ids))
        return {"data": {"stories": []}, "usage": {"estimated_cost": "0.01"}}

    result = call_once(
        run, "discovery", "text", 1, policy(), send, request_metadata=metadata()
    )
    assert (
        call_once(
            run, "discovery", "text", 1, policy(), send, request_metadata=metadata()
        )
        == result
    )
    assert len(sends) == 1 and sends[0] == 0
    assert OriginalContentCall.objects.filter(run=run).count() == 1
    assert not EditorialCall.objects.exists()
    with pytest.raises(BudgetHeld, match="identity"):
        call_once(
            run, "discovery", "text", 1, policy(), send, request_metadata=metadata("b")
        )


def test_live_graphics_reservation_blocks_chatter_before_provider_send():
    from monitor.editorial.chatter_accounting import call_once
    from tests.test_graphics_accounting import make_run, reserve

    call, claimed = reserve(make_run())
    assert claimed and call.state == 'reserved'
    with pytest.raises(BudgetHeld, match='already in flight'):
        call_once(consideration().run, 'discovery', 'text', 1, policy(),
                  lambda: pytest.fail('must not overlap Graphics'), request_metadata=metadata())


def test_trial_is_aggregate_across_runs_and_actual_cost_is_never_clipped():
    from monitor.editorial.chatter_accounting import call_once, spent

    first = consideration().run
    cfg = policy(1)
    call_once(
        first,
        "discovery",
        "text",
        Decimal("0.5"),
        cfg,
        lambda: {"data": {}, "usage": {"estimated_cost": "1.1"}},
        request_metadata=metadata(),
    )
    assert spent(cfg) == Decimal("1.100000")
    saved = OriginalContentCall.objects.get(run=first)
    assert saved.reserved_usd == Decimal("0.5") and saved.actual_usd == Decimal("1.1")
    other = consideration().run
    with pytest.raises(BudgetHeld, match="budget"):
        call_once(
            other,
            "discovery",
            "text",
            Decimal("0.1"),
            cfg,
            lambda: pytest.fail("trial overspend dispatched"),
            request_metadata=metadata(),
        )


def test_ambiguous_transport_keeps_its_reservation_and_is_not_retried():
    from monitor.editorial.chatter_accounting import call_once, spent

    run = consideration().run
    cfg = policy(2)

    def send():
        raise TimeoutError("untrusted provider text must not be stored")

    with pytest.raises(TimeoutError):
        call_once(run, "discovery", "text", 1, cfg, send, request_metadata=metadata())
    call = OriginalContentCall.objects.get(run=run)
    assert call.state == "ambiguous" and call.error_code == "TimeoutError"
    assert spent(cfg) == Decimal(1)
    assert "untrusted" not in str(call.response_payload)
    with pytest.raises(BudgetHeld):
        call_once(run, "discovery", "text", 1, cfg, send, request_metadata=metadata())


def test_routine_chatter_has_no_daily_spending_cutoff():
    from monitor.editorial.chatter_accounting import call_once

    for index in range(3):
        call_once(
            consideration().run,
            "discovery",
            "text",
            4,
            policy(),
            lambda: {"data": {}, "usage": {"estimated_cost": "4"}},
            request_metadata=metadata(str(index)),
        )
    assert OriginalContentCall.objects.filter(state="completed").count() == 3

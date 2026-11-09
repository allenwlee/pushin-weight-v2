from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import EditorialBudget, OriginalContentCall, OriginalContentRun
from monitor.editorial.persistence import BudgetHeld
from monitor.original_content import digest

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def make_run():
    now = timezone.now()
    return OriginalContentRun.objects.create(
        source_cycle_id=str(uuid4()), workflow_key='editorial-dispatch',
        scope_key=str(uuid4()), facts_as_of=now, packet_schema_version=1,
        snapshot={}, execution_state='running', lease_until=now + timedelta(minutes=5),
    )


def reserve(run, stage='C1', **kwargs):
    from monitor.editorial.persistence import reserve_graphics_call

    return reserve_graphics_call(
        run=run, stage=stage, kind='text', request_hash=sha256(b'{}').hexdigest(),
        request_packet={'schema_version': 'graphics-request/v1', 'request_json': '{}'},
        provider='fake', model='fake', ceiling=Decimal('0.2'), owner='worker',
        lease_seconds=120, workflow_key='social-brief', **kwargs,
    )


def test_duplicate_and_run_capacity_are_independent_of_review():
    run = make_run()
    call, claimed = reserve(run)
    assert claimed and call.state == 'reserved'
    same, claimed = reserve(run)
    assert same.pk == call.pk and not claimed
    with pytest.raises(BudgetHeld, match='run.*in flight'):
        reserve(run, 'G0')
    review, claimed = reserve(run, 'E1', review=True)
    assert claimed and review.pk != call.pk


def test_two_creation_slots_and_expired_unknown_charge_retained():
    from monitor.trend_narrative_lifecycle import (
        mark_trend_narrative_provider_call_sent,
    )

    first, _ = reserve(make_run())
    second, _ = reserve(make_run())
    with pytest.raises(BudgetHeld, match='capacity'):
        reserve(make_run())
    now = timezone.now()
    assert mark_trend_narrative_provider_call_sent(first.pk, owner='worker', fence=first.claim_fence, now=now)
    OriginalContentCall.objects.filter(pk=first.pk).update(claimed_at=now - timedelta(seconds=3), claim_expires_at=now - timedelta(seconds=1))
    third, claimed = reserve(make_run())
    assert claimed and third.pk != second.pk
    first.refresh_from_db()
    assert first.state == 'ambiguous' and first.reserved_usd == Decimal('0.2')
    assert EditorialBudget.objects.get(day=now.date()).reserved_usd == Decimal('0.6')


def test_existing_legacy_budget_and_stricter_caller_limit_apply():
    today = timezone.now().date()
    EditorialBudget.objects.create(day=today, reserved_usd=Decimal('4.9'), calls=1)
    with pytest.raises(BudgetHeld, match='budget'):
        reserve(make_run(), daily_limit=Decimal(5))
    with pytest.raises(BudgetHeld, match='budget'):
        reserve(make_run(), per_run_limit=Decimal('0.1'))


def test_same_identity_with_changed_request_cannot_be_reused():
    from monitor.editorial.persistence import reserve_graphics_call

    run = make_run()
    reserve(run)
    with pytest.raises(BudgetHeld, match='identity'):
        reserve_graphics_call(
            run=run, stage='C1', kind='text', request_hash=sha256(b'{"x":1}').hexdigest(),
            request_packet={'schema_version': 'graphics-request/v1', 'request_json': '{"x":1}'},
            provider='fake', model='fake', ceiling='0.2', owner='other', lease_seconds=120, workflow_key='social-brief',
        )


def test_competing_runs_cannot_exceed_two_live_reservations():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    runs = [make_run() for _ in range(3)]
    barrier = Barrier(3)

    def attempt(run):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return reserve(run)[1]
        except BudgetHeld as exc:
            assert 'capacity' in str(exc)
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(attempt, runs))
    assert results.count(True) == 2
    assert results.count(False) == 1
    assert OriginalContentCall.objects.filter(state='reserved').count() == 2


@pytest.mark.parametrize('mode', ['legacy', 'shared'])
def test_old_call_path_counts_graphics_against_the_same_budget(monkeypatch, mode):
    from monitor.editorial.config import EditorialConfig
    from monitor.editorial.persistence import call_once, claim_assessment

    monkeypatch.setenv('ORIGINAL_CONTENT_STORAGE', mode)
    reserve(make_run())
    assessment = claim_assessment(timezone.now(), 'legacy-graphics-budget')
    cfg = EditorialConfig(daily_usd=0.3, assessment_usd=1, daily_calls=10)
    metadata = {'workflow_version': 'test/v1', 'request_hash': 'b' * 64}
    with pytest.raises(BudgetHeld, match='budget'):
        call_once(assessment, 'editor', 'text', '.2', cfg,
                  lambda: pytest.fail('budget must block send'), request_metadata=metadata)


def test_completion_records_actual_and_refunds_original_budget_only_once():
    from monitor.editorial.persistence import complete_graphics_call
    from monitor.trend_narrative_lifecycle import (
        mark_trend_narrative_provider_call_sent,
    )

    now = timezone.now()
    call, _ = reserve(make_run())
    assert mark_trend_narrative_provider_call_sent(call.pk, owner='worker', fence=call.claim_fence, now=now)
    args = {'owner': 'worker', 'fence': call.claim_fence, 'response_hash': digest({'ok': True}),
            'response_payload': {'ok': True}, 'actual_usd': Decimal('0.05'), 'now': now + timedelta(days=1)}
    assert complete_graphics_call(call.pk, **args)
    assert complete_graphics_call(call.pk, **args)
    call.refresh_from_db()
    assert call.actual_usd == call.reserved_usd == Decimal('0.05')
    assert EditorialBudget.objects.get(day=call.budget_day).reserved_usd == Decimal('0.05')
    assert EditorialBudget.objects.count() == 1


def test_unknown_completion_cost_keeps_full_budget_reservation():
    from monitor.editorial.persistence import complete_graphics_call
    from monitor.trend_narrative_lifecycle import (
        mark_trend_narrative_provider_call_sent,
    )

    now = timezone.now()
    call, _ = reserve(make_run())
    assert mark_trend_narrative_provider_call_sent(call.pk, owner='worker', fence=call.claim_fence, now=now)
    assert complete_graphics_call(call.pk, owner='worker', fence=call.claim_fence,
                                  response_hash=digest({'ok': True}), response_payload={'ok': True}, now=now)
    call.refresh_from_db()
    assert call.actual_usd is None and call.reserved_usd == Decimal('0.2')
    assert EditorialBudget.objects.get(day=call.budget_day).reserved_usd == Decimal('0.2')

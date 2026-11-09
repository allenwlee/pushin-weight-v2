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


def test_v2_recipe_validated_before_reservation_and_without_embedded_images():
    import base64
    import json

    from monitor.editorial.graphics_generation import create_request_recipe
    from monitor.editorial.persistence import reserve_graphics_call

    data = b'a' * 240000
    body = {'model': 'fake', 'image': {'url': 'data:image/jpeg;base64,' + base64.b64encode(data).decode()}}
    reference = {'storage_alias': 'staff_media', 'storage_name': 'images/fixture.jpg', 'mime': 'image/jpeg', 'sha256': sha256(data).hexdigest()}
    loader = lambda alias, name: data
    packet, request_hash = create_request_recipe(body, [reference], load_bytes=loader)
    assert len(json.dumps(body).encode()) > 300000
    assert 'data:image/' not in json.dumps(packet)
    run = make_run()
    kwargs = {'run': run, 'stage': 'I-A', 'kind': 'media', 'request_hash': request_hash,
              'request_packet': packet, 'provider': 'fake', 'model': 'fake', 'ceiling': '.2',
              'owner': 'worker', 'lease_seconds': 120, 'workflow_key': 'social-brief'}
    with pytest.raises(ValueError, match='hash'):
        reserve_graphics_call(**kwargs, load_bytes=lambda _alias, _name: b'tampered')
    assert not OriginalContentCall.objects.filter(run=run).exists()
    call, claimed = reserve_graphics_call(**kwargs, load_bytes=loader)
    assert claimed and call.request_packet == packet and call.request_hash == request_hash


def test_pre_send_failure_is_fenced_terminal_and_refunds_reservation():
    from monitor.editorial.persistence import fail_graphics_presend_call
    from monitor.trend_narrative_lifecycle import (
        mark_trend_narrative_provider_call_sent,
    )

    call, _ = reserve(make_run())
    now = timezone.now()
    assert not fail_graphics_presend_call(call.pk, owner='other', fence=call.claim_fence,
                                         error_code='pre_send:request_reconstruction', now=now)
    assert not fail_graphics_presend_call(call.pk, owner='worker', fence=call.claim_fence + 1,
                                         error_code='pre_send:request_reconstruction', now=now)
    assert fail_graphics_presend_call(call.pk, owner='worker', fence=call.claim_fence,
                                     error_code='pre_send:request_reconstruction', now=now)
    assert fail_graphics_presend_call(call.pk, owner='worker', fence=call.claim_fence,
                                     error_code='pre_send:request_reconstruction', now=now)
    call.refresh_from_db()
    assert call.state == 'failed' and call.sent_at is None
    assert call.reserved_usd == Decimal(0)
    assert EditorialBudget.objects.get(day=call.budget_day).reserved_usd == Decimal(0)
    assert not mark_trend_narrative_provider_call_sent(call.pk, owner='worker', fence=call.claim_fence, now=now)
    _, should_send = reserve(call.run)
    assert not should_send


def test_pre_send_failure_rejects_expired_claim_and_sent_call():
    from monitor.editorial.persistence import fail_graphics_presend_call
    from monitor.trend_narrative_lifecycle import (
        mark_trend_narrative_provider_call_sent,
    )

    call, _ = reserve(make_run())
    now = timezone.now()
    assert not fail_graphics_presend_call(call.pk, owner='worker', fence=call.claim_fence,
                                         error_code='pre_send:request_reconstruction',
                                         now=call.claim_expires_at)
    assert mark_trend_narrative_provider_call_sent(call.pk, owner='worker', fence=call.claim_fence, now=now)
    assert not fail_graphics_presend_call(call.pk, owner='worker', fence=call.claim_fence,
                                         error_code='pre_send:request_reconstruction', now=now)
    call.refresh_from_db()
    assert call.state == 'sent' and call.sent_at is not None


def test_v1_packet_rejects_embedded_image_data_at_reservation_boundary():
    import json

    from monitor.editorial.persistence import reserve_graphics_call

    run = make_run()
    raw = json.dumps({'image': {'url': 'data:image/jpeg;base64,YQ=='}})
    with pytest.raises(ValueError, match='asset|data|packet'):
        reserve_graphics_call(run=run, stage='I-A', kind='media', request_hash=sha256(raw.encode()).hexdigest(),
            request_packet={'schema_version': 'graphics-request/v1', 'request_json': raw},
            provider='fake', model='fake', ceiling='.2', owner='worker', lease_seconds=120,
            workflow_key='social-brief')
    assert not OriginalContentCall.objects.filter(run=run).exists()


def test_changed_asset_after_reservation_never_sends_and_is_terminal():
    from pathlib import Path

    from monitor.editorial.graphics_contracts import load_pack
    from monitor.editorial.graphics_generation import (
        build_image_request,
        create_request_recipe,
        submit_once,
    )
    from monitor.editorial.persistence import (
        fail_graphics_presend_call,
        reserve_graphics_call,
    )
    from monitor.trend_narrative_lifecycle import (
        mark_trend_narrative_provider_call_sent,
    )

    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    data = b'fixture image'
    sha = sha256(data).hexdigest()
    asset = {'asset_ref': 'person:1', 'role': 'identity_reference', 'data': data, 'sha256': sha, 'mime': 'image/jpeg'}
    treatment = {'candidate_id': 'A', 'still_prompt': 'Draw headline.', 'aspect_ratio': '3:4',
                 'input_asset_refs': [{'asset_ref': 'person:1', 'role': 'identity_reference'}]}
    request = build_image_request(pack, 'I-A', treatment, [asset])
    reference = {'storage_alias': 'staff_media', 'storage_name': 'images/fixture.jpg', 'mime': 'image/jpeg', 'sha256': sha}
    packet, request_hash = create_request_recipe(request['body'], [reference], load_bytes=lambda *_: data)
    reads = []
    def load_bytes(*_):
        reads.append('read')
        return data if len(reads) <= 2 else b'changed'
    run = make_run()
    def reserve_call(saved_packet, saved_hash):
        return reserve_graphics_call(run=run, stage='I-A', kind='media', request_hash=saved_hash,
             request_packet=saved_packet, provider='fake', model='fake', ceiling='.2', owner='worker',
             lease_seconds=120, workflow_key='social-brief', load_bytes=load_bytes)
    def mark_sent(call):
        return mark_trend_narrative_provider_call_sent(call.pk, owner='worker', fence=call.claim_fence, now=timezone.now())
    def fail(call, error_code):
        return fail_graphics_presend_call(call.pk, owner='worker', fence=call.claim_fence, error_code=error_code)
    def forbidden(*_args, **_kwargs):
        pytest.fail('provider must not be called or response recorded')
    result = submit_once('I-A', request, packet, request_hash, 'fake', pack, reserve=reserve_call,
                         mark_sent=mark_sent, complete=forbidden, ambiguous=forbidden, fail=fail,
                         transport=forbidden, load_bytes=load_bytes)
    call = OriginalContentCall.objects.get(run=run)
    assert result['state'] == call.state == 'failed'
    assert call.error_code == 'pre_send:request_reconstruction' and call.sent_at is None
    assert call.reserved_usd == Decimal(0) and len(reads) == 3


def test_recipe_is_snapshotted_before_external_loader_can_mutate_caller_packet():
    import base64
    from copy import deepcopy

    from monitor.editorial.graphics_generation import create_request_recipe
    from monitor.editorial.persistence import reserve_graphics_call

    data = b'image'
    body = {'image': {'url': 'data:image/jpeg;base64,' + base64.b64encode(data).decode()}}
    reference = {'storage_alias': 'staff_media', 'storage_name': 'images/a.jpg', 'mime': 'image/jpeg', 'sha256': sha256(data).hexdigest()}
    packet, request_hash = create_request_recipe(body, [reference], load_bytes=lambda *_: data)
    original = deepcopy(packet)
    def mutate_original(*_):
        packet['assets'][0]['storage_name'] = 'images/changed.jpg'
        return data
    call, claimed = reserve_graphics_call(
        run=make_run(), stage='I-A', kind='media', request_hash=request_hash,
        request_packet=packet, provider='fake', model='fake', ceiling='.2',
        owner='worker', lease_seconds=120, workflow_key='social-brief', load_bytes=mutate_original,
    )
    assert claimed and call.request_packet == original
    assert packet != original


@pytest.mark.parametrize('mode', ['legacy', 'shared'])
def test_search_dollars_count_against_old_budget_without_counting_model_calls(monkeypatch, mode):
    from monitor.editorial.config import EditorialConfig
    from monitor.editorial.persistence import (
        call_once,
        claim_assessment,
        reserve_graphics_call,
    )
    from monitor.original_content import budget_totals

    monkeypatch.setenv('ORIGINAL_CONTENT_STORAGE', mode)
    run = make_run()
    call, _ = reserve_graphics_call(run=run, stage='S1', kind='text',
        request_hash=sha256(b'{}').hexdigest(),
        request_packet={'schema_version': 'graphics-request/v1', 'request_json': '{}'},
        provider='exa', model='exa-auto', ceiling='0.02', owner='worker',
        lease_seconds=120, workflow_key='social-brief')
    budget = EditorialBudget.objects.get(day=call.budget_day)
    assert budget.reserved_usd == Decimal('0.02') and budget.calls == budget.media_calls == 0
    totals = budget_totals('editorial', call.budget_day)
    assert totals['reserved_usd'] == Decimal('0.02') and totals['calls'] == totals['media_calls'] == 0
    assessment = claim_assessment(timezone.now(), 'search-budget')
    config = EditorialConfig(daily_usd=0.2, assessment_usd=1, daily_calls=10)
    with pytest.raises(BudgetHeld, match='budget'):
        call_once(assessment, 'editor', 'text', '.2', config,
            lambda: pytest.fail('search reserve must count against the daily budget'),
            request_metadata={'workflow_version': 'test/v1', 'request_hash': 'b' * 64})

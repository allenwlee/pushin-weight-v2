from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import EditorialAssessment, EditorialCall
from monitor.editorial.config import EditorialConfig
from monitor.editorial.persistence import BudgetHeld, call_once, claim_assessment

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_interval_claim_is_unique_and_stale_fence_cannot_send():
    now = timezone.now()
    row = claim_assessment(now, "cycle-1")
    assert claim_assessment(now, "cycle-2") is None
    EditorialAssessment.objects.filter(pk=row.pk).update(
        lease_until=now - timedelta(seconds=1)
    )
    replacement = claim_assessment(now, "cycle-3")
    assert replacement.fence > row.fence
    with pytest.raises(BudgetHeld):
        call_once(
            row,
            "editor",
            "text",
            Decimal("0.01"),
            EditorialConfig(daily_usd=1, assessment_usd=1, daily_calls=5),
            lambda: {"ok": True},
        )


def test_unknown_send_stays_reserved_and_cannot_be_repeated():
    row = claim_assessment(timezone.now(), "cycle")
    cfg = EditorialConfig(daily_usd=1, assessment_usd=1, daily_calls=5)
    calls = []

    def send():
        calls.append(1)
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        call_once(row, "editor", "text", Decimal("0.2"), cfg, send)
    with pytest.raises(BudgetHeld):
        call_once(row, "editor", "text", Decimal("0.2"), cfg, send)
    assert calls == [1]
    assert EditorialCall.objects.get().state == "ambiguous"


def test_completed_stage_reuses_output_and_enforces_shared_budget():
    now = timezone.now()
    cfg = EditorialConfig(daily_usd=0.3, assessment_usd=1, daily_calls=10)
    row = claim_assessment(now, "cycle")
    assert call_once(
        row, "editor", "text", Decimal("0.2"), cfg, lambda: {"result": 1}
    ) == {"result": 1}
    assert call_once(
        row,
        "editor",
        "text",
        Decimal("0.2"),
        cfg,
        lambda: pytest.fail("duplicate send"),
    ) == {"result": 1}
    with pytest.raises(BudgetHeld):
        call_once(
            row,
            "writer",
            "text",
            Decimal("0.2"),
            cfg,
            lambda: pytest.fail("over budget"),
        )


def test_launch_text_and_media_share_the_five_dollar_daily_ceiling(monkeypatch):
    from core.models import EditorialBudget
    from monitor.editorial.config import load_editorial_config

    monkeypatch.setenv("EDITORIAL_CONFIG_PATH", "config/editorial-english-launch.yaml")
    cfg = load_editorial_config()
    now = timezone.now()
    costs = [
        ("text", "1.8"),
        ("media", "0.6"),
        ("text", "1.8"),
        ("media", "0.6"),
        ("text", "0.2"),
    ]
    sent = []
    for index, (kind, cost) in enumerate(costs):
        row = claim_assessment(now - timedelta(minutes=15 * index), f"cycle-{index}")
        call_once(
            row,
            f"stage-{index}",
            kind,
            Decimal(cost),
            cfg,
            lambda kind=kind: sent.append(kind) or {"ok": True},
        )
    assert EditorialBudget.objects.get(day=now.date()).reserved_usd == Decimal(5)
    for kind in ("text", "media"):
        with pytest.raises(BudgetHeld, match="budget exhausted"):
            call_once(
                row,
                f"over-{kind}",
                kind,
                Decimal("0.01"),
                cfg,
                lambda: pytest.fail("send beyond combined ceiling"),
            )
    assert len(sent) == 5 and EditorialCall.objects.count() == 5


@pytest.mark.parametrize(
    "status,model,reason,code",
    [
        (503, "expected", "stop", "provider_http_503"),
        (200, "different", "stop", "served_model_mismatch"),
        (200, "expected", "length", "incomplete_model_response"),
    ],
)
def test_rejected_provider_reply_keeps_safe_diagnostics_and_cannot_resubmit(
    monkeypatch, status, model, reason, code
):
    import json

    from monitor.editorial.config import Route
    from monitor.editorial.contracts import ProviderReplyError
    from monitor.editorial.providers import json_call

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-private-key")
    cfg = EditorialConfig(daily_usd=1, assessment_usd=1, daily_calls=10)
    route = Route(
        model="expected",
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        key_env="OPENROUTER_API_KEY",
        input_usd_per_million=1,
        output_usd_per_million=1,
    )
    row = claim_assessment(timezone.now(), "diagnostics")
    sends = []

    def transport(*args, **kwargs):
        sends.append(1)
        return status, json.dumps(
            {
                "model": model,
                "choices": [
                    {
                        "finish_reason": reason,
                        "message": {"content": "PRIVATE PROVIDER TEXT"},
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 34},
            }
        ).encode()

    request = {"system": "Return JSON", "user": "A source"}
    with pytest.raises(ProviderReplyError):
        json_call(row, "editor", route, request, cfg, transport=transport)
    receipt = row.calls.get()
    assert receipt.state == "ambiguous" and receipt.error_code == code
    assert receipt.response["failure"]["http_status"] == status
    saved = json.dumps(receipt.response)
    assert "PRIVATE PROVIDER TEXT" not in saved and "test-only-private-key" not in saved
    with pytest.raises(BudgetHeld):
        json_call(row, "editor", route, request, cfg, transport=transport)
    assert len(sends) == 1


def test_concurrent_workers_share_one_daily_reservation_limit():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    now = timezone.now()
    rows = [claim_assessment(now - timedelta(minutes=15 * i), str(i)) for i in range(2)]
    barrier = Barrier(2)
    cfg = EditorialConfig(daily_usd=0.3, assessment_usd=1, daily_calls=10)

    def work(row):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            call_once(row, "editor", "text", Decimal("0.2"), cfg, lambda: {"ok": True})
            return "sent"
        except BudgetHeld:
            return "held"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(work, rows))
    assert sorted(results) == ["held", "sent"]
    assert EditorialCall.objects.count() == 1


def test_dead_workers_do_not_block_other_intervals_forever():
    now = timezone.now()
    old = claim_assessment(now - timedelta(minutes=30), "old")
    EditorialCall.objects.create(
        assessment=old,
        stage="editor",
        kind="text",
        state="sent",
        reserved_usd="0.1",
        budget_day=now.date(),
    )
    EditorialAssessment.objects.filter(pk=old.pk).update(
        lease_until=now - timedelta(seconds=1)
    )
    new = claim_assessment(now, "new")
    cfg = EditorialConfig(daily_usd=1, assessment_usd=1, daily_calls=4)
    assert call_once(
        new, "editor", "text", Decimal("0.1"), cfg, lambda: {"ok": True}
    ) == {"ok": True}
    assert old.calls.get().state == "ambiguous"


def test_media_receipt_survives_assessment_change_without_second_send():
    now = timezone.now()
    first = claim_assessment(now - timedelta(minutes=30), "first")
    second = claim_assessment(now, "second")
    cfg = EditorialConfig(
        daily_usd=1, assessment_usd=1, daily_calls=4, media_daily_calls=2
    )
    receipt = call_once(
        first,
        "media:picture-id",
        "media",
        Decimal("0.1"),
        cfg,
        lambda: {"task_id": "123"},
    )
    assert (
        call_once(
            second,
            "media:picture-id",
            "media",
            Decimal("0.1"),
            cfg,
            lambda: pytest.fail("duplicate media send"),
        )
        == receipt
    )
    assert EditorialCall.objects.count() == 1

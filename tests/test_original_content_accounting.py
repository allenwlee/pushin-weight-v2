"""Exercise real compatible reservation paths, their caps and no-resend contract."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.utils import timezone

from core.models import OriginalContentCall
from monitor.editorial.config import EditorialConfig
from monitor.editorial.persistence import BudgetHeld, call_once, claim_assessment
from monitor.original_content import budget_totals

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def metadata():
    return {
        "request_hash": "b" * 64,
        "request_packet": {"test_request": "actual fake transport input"},
        "workflow_version": "c" * 64,
        "provider": "test",
        "model": "test-model",
    }


def test_shared_completed_call_has_strict_provenance_and_is_charged_once(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    row = claim_assessment(timezone.now(), "shared-accounting")
    cfg = EditorialConfig(daily_usd=1, assessment_usd=1, daily_calls=4)
    sent = []
    assert call_once(
        row,
        "editor",
        "text",
        ".2",
        cfg,
        lambda: sent.append(1) or {"ok": True},
        request_metadata=metadata(),
    ) == {"ok": True}
    assert call_once(
        row,
        "editor",
        "text",
        ".2",
        cfg,
        lambda: pytest.fail("resend"),
        request_metadata=metadata(),
    ) == {"ok": True}
    call = OriginalContentCall.objects.get()
    assert not call.legacy_import and call.completed_at and call.sent_at
    assert call.request_hash == "b" * 64
    assert budget_totals("editorial", call.budget_day) == {
        "reserved_usd": Decimal(".2"),
        "calls": 1,
        "media_calls": 0,
    }
    assert sent == [1]


def test_shared_timeout_remains_charged_without_another_send(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    row = claim_assessment(timezone.now(), "shared-timeout")
    cfg = EditorialConfig(daily_usd=1, assessment_usd=1, daily_calls=4)

    def fail():
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        call_once(row, "editor", "text", ".2", cfg, fail, request_metadata=metadata())
    with pytest.raises(BudgetHeld):
        call_once(
            row,
            "editor",
            "text",
            ".2",
            cfg,
            lambda: pytest.fail("resend"),
            request_metadata=metadata(),
        )
    call = OriginalContentCall.objects.get()
    assert call.state == "ambiguous" and call.reserved_usd == Decimal(".2")


def test_shared_concurrent_calls_admit_only_the_affordable_request(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    now = timezone.now()
    rows = [claim_assessment(now - timedelta(minutes=15 * i), str(i)) for i in range(2)]
    cfg = EditorialConfig(daily_usd=0.3, assessment_usd=1, daily_calls=5)
    barrier = Barrier(2)

    def reserve(row):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            call_once(
                row,
                "editor",
                "text",
                ".2",
                cfg,
                lambda: {"ok": True},
                request_metadata=metadata(),
            )
            return "sent"
        except BudgetHeld:
            return "held"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, rows)) == ["held", "sent"]
    assert OriginalContentCall.objects.count() == 1


def test_provider_caller_persists_actual_wire_hash_and_model(monkeypatch):
    import hashlib
    import json

    from monitor.editorial.config import Route
    from monitor.editorial.providers import json_call

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-transport-only")
    cfg = EditorialConfig(daily_usd=1, assessment_usd=1, daily_calls=4)
    route = Route(
        model="fixture-model",
        endpoint="https://api.openai.com/v1/chat/completions",
        key_env="OPENAI_API_KEY",
        input_usd_per_million=1,
        output_usd_per_million=1,
    )
    row = claim_assessment(timezone.now(), "actual-wire")
    captured = []

    def transport(endpoint, key, body, **kwargs):
        captured.append(body)
        return 200, json.dumps(
            {
                "model": route.model,
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"ok": true}'}}
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            }
        )

    json_call(
        row,
        "editor",
        route,
        {"system": "Return JSON", "user": "Source evidence"},
        cfg,
        transport=transport,
    )
    call = OriginalContentCall.objects.get()
    assert (
        call.request_hash
        == hashlib.sha256(
            json.dumps(captured[0], ensure_ascii=False).encode()
        ).hexdigest()
    )
    assert call.request_packet == captured[0]
    assert call.provider == "api.openai.com" and call.model == route.model
    assert len(captured) == 1 and not call.legacy_import

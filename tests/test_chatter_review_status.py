"""Read-only Chatter reports count physical calls and preserve charge uncertainty."""

import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import CollectionRequest, OriginalContentCall
from monitor.editorial.chatter_accounting import call_once
from monitor.editorial.chatter_sources import SourceSession
from tests.test_chatter_accounting import metadata
from tests.test_chatter_review_recovery import selected_package
from tests.test_chatter_trends import configured as configured  # noqa: PLC0414
from tests.test_original_content_consideration import producer
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_status_links_reused_completed_unknown_reserved_source_and_graphics_calls(configured, monkeypatch):
    run, _, package, output, cfg = selected_package(configured, 0)
    # A saved successful observation reports two separate credential HTTP calls.
    run.refresh_from_db()
    run.outcome["trends"]["observation"]["credential_refresh_requests"] = 2
    run.lease_until = timezone.now() + timedelta(minutes=10)
    run.save(update_fields=["outcome", "lease_until"])
    send = Mock(return_value={"data": {}, "usage": {"estimated_cost": "0.012"}})
    for _ in range(2):
        call_once(run, "selector:0", "text", 1, cfg, send, request_metadata=metadata())
    assert send.call_count == 1
    with pytest.raises(TimeoutError):
        call_once(run, "selector:1", "text", 2, cfg, Mock(side_effect=TimeoutError()),
                  request_metadata=metadata("b"))
    reserved = OriginalContentCall.objects.create(run=run, stage="selector:2", request_identity="reserved-report",
        request_hash="c" * 64, reserved_at=timezone.now(), reserved_usd="0.5")
    graphic = producer(output, "en")
    graphic.provider = "openrouter"
    graphic.actual_usd = "0.250001"
    graphic.provenance = {"graphics_billing_receipt": {"schema_version": "graphics-billing-receipt/v1",
        "provider": "openrouter", "unit": "usd", "amount": "0.2500000001"}}
    graphic.save(update_fields=["provider", "actual_usd", "provenance"])
    # One uncertain TwitterAPI send is a physical call, not a known invoice.
    session = SourceSession(run, cfg, purpose=TwitterApiCredentialPurpose.ON_DEMAND)
    session.start("/twitter/tweet/advanced_search", {"query": '"Original headline 1"', "queryType": "Latest"})
    request = CollectionRequest.objects.filter(attempt__run__content_run=run).exclude(
        endpoint_url="https://api.x.com/2/users/personalized_trends").get()
    monkeypatch.setattr("monitor.management.commands.editorial.load_editorial_config", lambda: cfg)
    stdout = StringIO()
    call_command("editorial", "status", chatter_run=run.pk, stdout=stdout)
    report = json.loads(stdout.getvalue())["chatter"][0]
    assert report["run_id"] == run.pk and report["graphics_run_ids"] == [package.pk]
    assert report["physical_calls"] == {
        "official_x": 1, "official_x_refresh": 2, "source": 1,
        "ranker": 1, "selector": 2, "graphics": 1, "total": 8,
    }
    assert Decimal(report["charges"]["billed_usd"]) == Decimal("0.3033010001")
    assert Decimal(report["charges"]["estimated_usd"]) == Decimal("0.012")
    assert report["charges"]["unknown_charge_calls"] == 6
    assert report["charges"]["reserved_only_calls"] == 1
    assert Decimal(report["charges"]["reserved_only_usd"]) == Decimal("0.5")
    calls = {row["identity"]: row for row in report["calls"]}
    assert calls[f"model:{reserved.pk}"]["physical"] is False
    assert calls[f"collection:{request.pk}"]["billing_state"] == "unknown"
    assert next(row for row in calls.values() if row["category"] == "official_x")["estimated_usd"] is None
    assert OriginalContentCall.objects.count() == 5


def test_status_refuses_a_forged_producing_link(configured):
    from monitor.editorial.chatter_accounting import chatter_call_report

    run, _, package, _, _ = selected_package(configured, 0)
    package.snapshot["request"]["chatter"]["source_locale"] = "ja"
    package.save(update_fields=["snapshot"])
    with pytest.raises(ValueError):
        chatter_call_report(run.pk)

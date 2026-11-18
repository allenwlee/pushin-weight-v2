"""Explicit saved-reply recovery preserves physical requests and finite limits."""

from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import CollectionRequest, OriginalContentRun
from monitor.editorial.chatter_chain import resume_chatter_discovery, run_chatter
from monitor.editorial.contracts import ProviderReplyError
from tests.test_chatter_chain import chain_config, wire

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture
def held_discovery(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY_PW", "fixture-only")
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-only")
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg, now = chain_config(), timezone.now()
    transport = Mock(
        return_value=wire(
            {
                "stories": [],
                "keyword_query": "",
                "search_notes": [],
                "history_requests": [],
            },
            search=True,
        )
    )
    with patch(
        "monitor.editorial.chatter_chain.validate_semantic",
        side_effect=ProviderReplyError("ambiguous_semantic_identity", {}),
    ):
        result = run_chatter(
            {
                "schema_version": 1,
                "source_cycle_id": str(uuid4()),
                "cycle_started_at": now.isoformat(),
                "cutoff": now.isoformat(),
                "dry_run": False,
                "credential_purpose": "on-demand",
            },
            cfg=cfg,
            transport=transport,
            enqueue=Mock(),
        )
    assert result["status"] == "held"
    return OriginalContentRun.objects.get(pk=result["run_id"]), cfg, transport


@pytest.mark.parametrize(
    "problem",
    [
        "ambiguous_call",
        "unknown_receipt",
        "changed_input",
        "changed_hash",
        "source_already_sent",
        "expired_lease",
        "unfinished",
    ],
)
def test_unsafe_discovery_recovery_makes_no_request_or_new_attempt(
    held_discovery, problem
):
    run, cfg, transport = held_discovery
    execution = run.collection_runs.get()
    request = CollectionRequest.objects.get(attempt__run=execution)
    call = run.provider_calls.get()
    if problem == "ambiguous_call":
        call.state = "ambiguous"
        call.completed_at = None
        call.response_hash, call.response_payload = "", {}
        call.save(
            update_fields=["state", "completed_at", "response_hash", "response_payload"]
        )
    elif problem == "unknown_receipt":
        request.transport_outcome = "unknown"
        request.save(update_fields=["transport_outcome"])
    elif problem == "changed_input":
        call.request_packet = {**call.request_packet, "max_turns": 1}
        call.save(update_fields=["request_packet"])
    elif problem == "changed_hash":
        call.request_hash = "0" * 64
        call.save(update_fields=["request_hash"])
    elif problem == "source_already_sent":
        CollectionRequest.objects.create(
            attempt=request.attempt,
            scope_run=request.scope_run,
            ordinal=2,
            endpoint_url="https://api.twitterapi.io/twitter/tweets",
            transport_outcome="received",
            http_status=200,
        )
    elif problem == "expired_lease":
        run.lease_until = timezone.now() - timedelta(seconds=1)
        run.save(update_fields=["lease_until"])
    else:
        execution.status, execution.completed_at = "running", None
        execution.save(update_fields=["status", "completed_at"])
    before = CollectionRequest.objects.count()
    with patch("x_monitor.x_client.XClient._get_bounded") as source_get:
        result = resume_chatter_discovery(
            run.pk, cfg=cfg, transport=transport, enqueue=Mock()
        )
    assert result["status"] in {"held", "stale"}
    assert transport.call_count == 1 and source_get.call_count == 0
    assert CollectionRequest.objects.count() == before
    assert execution.attempts.count() == 1
    run.refresh_from_db()
    assert "discovery_recovery" not in run.outcome


def test_request_ceiling_and_fence_survive_source_continuation(held_discovery):
    from monitor.editorial.chatter_history import freeze_sources
    from monitor.editorial.chatter_sources import SourceSession
    from monitor.editorial.persistence import BudgetHeld
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    run, cfg, _ = held_discovery
    cfg = cfg.model_copy(
        update={"chatter": cfg.chatter.model_copy(update={"source_request_limit": 2})}
    )
    # Job instructions are immutable: use the original configuration to claim,
    # then lower the in-process ceiling to exercise the cross-attempt guard.
    original_cfg = chain_config()
    stale_fence, original_start = run.fence, run.cycle_started_at
    session = SourceSession(
        run, original_cfg, purpose=TwitterApiCredentialPurpose.ON_DEMAND, resume=True
    )
    session.cfg = cfg
    with pytest.raises(ValueError, match="stale"):
        freeze_sources(run, [], fence=stale_fence)
    request = session.start("/twitter/tweets", {"tweet_ids": "123"})
    session.finish(
        request, {"outcome": "received", "status_code": 200, "body": b'{"tweets":[]}'}
    )
    with pytest.raises(BudgetHeld, match="request limit"):
        session.start("/twitter/tweets", {"tweet_ids": "124"})
    session.close(success=False)
    execution = run.collection_runs.get()
    assert execution.request_count == 2 and execution.attempts.count() == 2
    assert list(
        execution.attempts.order_by("ordinal").values_list("actual_requests", flat=True)
    ) == [1, 1]
    assert (
        resume_chatter_discovery(run.pk, cfg=original_cfg)["status"]
        == "already_dispatched"
    )
    run.refresh_from_db()
    assert run.cycle_started_at == original_start

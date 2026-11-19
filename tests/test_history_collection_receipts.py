"""History pages use the existing leased request and evidence owners."""

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from core.collection_jobs import register_job, set_job_state
from core.collection_state import checkpoint_scope, claim_job
from core.models import CollectionRequest, CollectionScopeRun
from core.staff_assets.job_history_collection import (
    CollectionRequestHistoryJournal,
    build_history_plan,
    collect_history_pages,
    lookup_history_posts,
)
from tests.test_backfill_collection import ready_job
from tests.test_record_job_history_collection import (
    FakeHistoryClient,
    history_item,
    history_page,
)
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
from x_monitor.x_client import XClient

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def history_job(monkeypatch):
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "test-only")
    plan = build_history_plan(
        people=[{"native_id": "123", "handle": "example"}],
        cutoff=datetime(2026, 11, 9, tzinfo=ZoneInfo("Asia/Tokyo")),
    )
    seed = ready_job(requests=4)
    definition = deepcopy(seed.definition)
    scope = definition["scope"]
    ids = [str(i) for i in range(1, 52)]
    scope["save_person_job_lookup"] = {
        "schema": "save-person-job-lookup/v1",
        "post_ids": ids,
        "expected_authors": {item: "123" for item in ids},
        "deadline": datetime(2030, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")).isoformat(),
    }
    scope["since_epoch"], scope["until_epoch"] = plan["since_time"], plan["until_time"]
    scope["units"][0]["ownership"].update(
        query=plan["queries"][0]["query"],
        since_epoch=plan["since_time"],
        until_epoch=plan["until_time"],
    )
    job = register_job(
        job_key="saved-person-history-test",
        source=seed.source,
        purpose="content",
        operation="x_backfill",
        mode="historical",
        definition=definition,
    )
    job = set_job_state(job.pk, "ready")
    claim = claim_job(
        job.pk, invocation_id="saved-person-history", manual_authorized=True
    )
    unit = job.scope["units"][0]
    checkpoint_scope(
        claim,
        scope_kind="x_query",
        scope_key=unit["scope_key"],
        ownership=unit["ownership"],
        typed=True,
    )
    scoped = CollectionScopeRun.objects.get(run_id=claim.run_id, scope_kind="x_query")
    return plan, claim, scoped


def _run(plan, client, journal, **changes):
    args = {
        "request": plan["queries"][0],
        "since_time": plan["since_time"],
        "until_time": plan["until_time"],
        "client": client,
        "journal": journal,
        "authorized": True,
        "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND,
        "max_requests": 3,
        "max_pages": 3,
        "max_posts": 100,
        "deadline": datetime(2030, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")),
    }
    args.update(changes)
    return collect_history_pages(**args)


def test_fenced_history_receipts_replay_without_another_request(history_job):
    plan, claim, scope = history_job
    journal = CollectionRequestHistoryJournal(claim, scope)

    class FakeClient(FakeHistoryClient):
        def run_search_pages(self, *args, **kwargs):
            pages = super().run_search_pages(*args, **kwargs)
            journal.record_transport(status_code=200, response_bytes=456)
            return pages

    client = FakeClient(
        {
            None: history_page([history_item("1")], next_cursor="x", more=True),
            "x": history_page([history_item("2")]),
        }
    )
    result = _run(plan, client, journal)
    assert result["status"] == "complete" and result["requests_made"] == 2
    receipts = CollectionRequest.objects.filter(
        scope_run=scope, request_category=journal.category
    ).order_by("ordinal")
    assert list(receipts.values_list("cursor_before", "response_bytes")) == [
        (None, 456),
        ("x", 456),
    ]
    assert all(r.archive.encoding == "selected-json-canonical-v1" for r in receipts)
    replay = _run(plan, client, CollectionRequestHistoryJournal(claim, scope))
    assert replay["status"] == "complete" and replay["requests_made"] == 0
    assert len(client.calls) == 2


def test_unknown_send_remains_reserved_and_cannot_be_retried(history_job):
    plan, claim, scope = history_job
    journal = CollectionRequestHistoryJournal(claim, scope)
    client = FakeHistoryClient({None: TimeoutError()})
    assert _run(plan, client, journal)["reason"] == "request_failed_or_unknown"
    assert (
        _run(plan, client, CollectionRequestHistoryJournal(claim, scope))["reason"]
        == "unknown_request_outcome"
    )
    assert (
        CollectionRequest.objects.get(
            scope_run=scope, request_category=journal.category
        ).transport_outcome
        == "pending"
    )
    assert len(client.calls) == 1


def test_frozen_query_and_transport_metadata_cannot_be_forged(history_job):
    plan, claim, scope = history_job
    journal = CollectionRequestHistoryJournal(claim, scope)
    changed = deepcopy(plan["queries"][0])
    changed["query"] += " extra"
    with pytest.raises(ValueError, match="frozen collection scope"):
        _run(plan, FakeHistoryClient({}), journal, request=changed)
    token = journal.reserve("a" * 64, None)
    with pytest.raises(ValueError, match="metadata"):
        journal.finish(token, {"items": []})
    assert CollectionRequest.objects.get(pk=token).transport_outcome == "pending"


def test_real_client_uses_mock_transport_and_durable_bounded_receipts(
    history_job, monkeypatch
):
    import json

    import requests

    plan, claim, scope = history_job
    journal = CollectionRequestHistoryJournal(
        claim, scope, max_spend_usd="0.000002", max_request_usd="0.000001"
    )
    calls = []

    def fake_transport(self, url, params, timeout):
        calls.append(params.get("cursor"))
        body = {
            "tweets": [
                {
                    "id": "1" if not params.get("cursor") else "2",
                    "text": "Joined",
                    "createdAt": "2026-08-01T00:00:00Z",
                    "author": {"id": "123", "userName": "example"},
                }
            ],
            "has_next_page": not params.get("cursor"),
            "next_cursor": "next" if not params.get("cursor") else None,
        }
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode()
        return response

    monkeypatch.setattr(XClient, "_get_bounded", fake_transport)
    client = XClient(
        api_key="test-only", max_retries=0, max_response_bytes=4096, timeout_s=10
    )
    result = _run(plan, client, journal)
    assert result["status"] == "complete" and calls == [None, "next"]
    receipts = list(
        CollectionRequest.objects.filter(
            scope_run=scope, request_category=journal.category
        ).order_by("ordinal")
    )
    assert len(receipts) == 2
    assert all(row.request_group == journal._budget_pin for row in receipts)
    assert all(row.response_bytes > 0 and row.archive_id for row in receipts)
    assert (
        _run(
            plan,
            client,
            CollectionRequestHistoryJournal(
                claim, scope, max_spend_usd="0.000002", max_request_usd="0.000001"
            ),
        )["requests_made"]
        == 0
    )
    assert len(calls) == 2


def test_live_client_requires_on_demand_key_and_finite_spend(history_job, monkeypatch):
    plan, claim, scope = history_job
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "scheduled-test")
    client = XClient(api_key="scheduled-test", max_retries=0, max_response_bytes=4096)
    journal = CollectionRequestHistoryJournal(
        claim, scope, max_spend_usd="0.01", max_request_usd="0.001"
    )
    with pytest.raises(ValueError, match="on-demand credential"):
        _run(plan, client, journal)
    client.api_key = "test-only"
    with pytest.raises(ValueError, match="dollar ceiling"):
        _run(plan, client, CollectionRequestHistoryJournal(claim, scope))
    assert not CollectionRequest.objects.filter(
        scope_run=scope, request_category=journal.category
    ).exists()


def test_live_client_stops_at_dollar_cap_without_refetch(history_job, monkeypatch):
    import json

    import requests

    plan, claim, scope = history_job
    journal = CollectionRequestHistoryJournal(
        claim, scope, max_spend_usd="0.000001", max_request_usd="0.000001"
    )
    calls = []

    def fake_transport(self, url, params, timeout):
        calls.append(params)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            {
                "tweets": [
                    {
                        "id": "1",
                        "text": "Joined",
                        "createdAt": "2026-08-01T00:00:00Z",
                        "author": {"id": "123", "userName": "example"},
                    }
                ],
                "has_next_page": True,
                "next_cursor": "next",
            }
        ).encode()
        return response

    monkeypatch.setattr(XClient, "_get_bounded", fake_transport)
    client = XClient(
        api_key="test-only", max_retries=0, max_response_bytes=4096, timeout_s=10
    )
    result = _run(plan, client, journal)
    assert result["reason"] == "budget_exhausted" and len(result["records"]) == 1
    assert len(calls) == 1
    replay = CollectionRequestHistoryJournal(
        claim, scope, max_spend_usd="0.000001", max_request_usd="0.000001"
    )
    assert _run(plan, client, replay)["reason"] == "budget_exhausted"
    assert len(calls) == 1
    with pytest.raises(ValueError, match="budget changed"):
        _run(
            plan,
            client,
            CollectionRequestHistoryJournal(
                claim, scope, max_spend_usd="0.000002", max_request_usd="0.000001"
            ),
        )
    with pytest.raises(ValueError, match="request identity changed"):
        _run(
            plan,
            client,
            CollectionRequestHistoryJournal(
                claim, scope, max_spend_usd="0.000001", max_request_usd="0.000001"
            ),
            max_pages=4,
        )
    assert len(calls) == 1


def test_rate_limit_is_recorded_and_never_automatically_retried(
    history_job, monkeypatch
):
    import requests

    plan, claim, scope = history_job
    journal = CollectionRequestHistoryJournal(
        claim, scope, max_spend_usd="0.01", max_request_usd="0.001"
    )
    calls = []

    def fake_transport(self, url, params, timeout):
        calls.append(params)
        response = requests.Response()
        response.status_code = 429
        response._content = b"{}"
        return response

    monkeypatch.setattr(XClient, "_get_bounded", fake_transport)
    client = XClient(
        api_key="test-only", max_retries=0, max_response_bytes=4096, timeout_s=10
    )
    assert _run(plan, client, journal)["reason"] == "rate_limited"
    receipt = CollectionRequest.objects.get(
        scope_run=scope, request_category=journal.category
    )
    assert receipt.http_status == 429 and receipt.transport_outcome == "received"
    replay = CollectionRequestHistoryJournal(
        claim, scope, max_spend_usd="0.01", max_request_usd="0.001"
    )
    assert _run(plan, client, replay)["reason"] == "rate_limited" and len(calls) == 1


def test_real_lookup_uses_frozen_ids_and_records_requests_without_network(
    history_job, monkeypatch
):
    import json

    import requests

    _plan, claim, scope = history_job
    frozen = scope.run.job.scope["save_person_job_lookup"]
    journal = CollectionRequestHistoryJournal(
        claim, scope, endpoint="lookup", max_spend_usd="0.002", max_request_usd="0.001"
    )
    calls = []

    def fake_transport(self, url, params, timeout):
        ids = params["tweet_ids"].split(",")
        calls.append(ids)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            {
                "tweets": [
                    {
                        "id": item,
                        "text": "Joined",
                        "createdAt": "2026-08-01T00:00:00Z",
                        "author": {"id": "123", "userName": "example"},
                    }
                    for item in ids
                    if item != "51"
                ]
            }
        ).encode()
        return response

    monkeypatch.setattr(XClient, "_get_bounded", fake_transport)
    client = XClient(
        api_key="test-only", max_retries=0, max_response_bytes=100000, timeout_s=10
    )
    kwargs = {
        "post_ids": frozen["post_ids"],
        "expected_authors": frozen["expected_authors"],
        "client": client,
        "journal": journal,
        "authorized": True,
        "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND,
        "max_requests": 2,
        "deadline": datetime.fromisoformat(frozen["deadline"]),
    }
    result = lookup_history_posts(**kwargs)
    assert result["reason"] == "unresolved_posts" and len(result["records"]) == 50
    assert result["provider_appearances_complete"] is True
    assert len(result["provider_returned_ids"]) == 50
    assert result["unresolved"][0]["reason"] == "missing_or_unavailable"
    assert [len(batch) for batch in calls] == [50, 1]
    receipts = list(
        CollectionRequest.objects.filter(
            scope_run=scope, request_category=journal.category
        ).order_by("ordinal")
    )
    assert len(receipts) == 2 and all(
        "tweet_ids=" in row.endpoint_url and row.archive_id for row in receipts
    )
    kwargs["journal"] = CollectionRequestHistoryJournal(
        claim, scope, endpoint="lookup", max_spend_usd="0.002", max_request_usd="0.001"
    )
    assert lookup_history_posts(**kwargs)["requests_made"] == 0 and len(calls) == 2
    kwargs["post_ids"] = ["999"]
    kwargs["expected_authors"] = {"999": "123"}
    with pytest.raises(ValueError, match="differ from the frozen job"):
        lookup_history_posts(**kwargs)
    assert len(calls) == 2


def test_real_lookup_keeps_duplicate_and_foreign_provider_appearances(
    history_job, monkeypatch
):
    import json

    import requests

    _plan, claim, scope = history_job
    frozen = scope.run.job.scope["save_person_job_lookup"]
    journal = CollectionRequestHistoryJournal(
        claim, scope, endpoint="lookup", max_spend_usd="0.002", max_request_usd="0.001"
    )

    def fake_transport(self, url, params, timeout):
        rows = []
        if "1" in params["tweet_ids"].split(","):
            for identifier, body in [
                ("1", "First"),
                ("1", "Changed"),
                ("999", "Foreign"),
            ]:
                rows.append(
                    {
                        "id": identifier,
                        "text": body,
                        "createdAt": "2026-08-01T00:00:00Z",
                        "author": {"id": "123", "userName": "example"},
                    }
                )
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"tweets": rows}).encode()
        return response

    monkeypatch.setattr(XClient, "_get_bounded", fake_transport)
    client = XClient(
        api_key="test-only", max_retries=0, max_response_bytes=100000, timeout_s=10
    )
    result = lookup_history_posts(
        post_ids=frozen["post_ids"],
        expected_authors=frozen["expected_authors"],
        client=client,
        journal=journal,
        authorized=True,
        credential_purpose=TwitterApiCredentialPurpose.ON_DEMAND,
        max_requests=2,
        deadline=datetime.fromisoformat(frozen["deadline"]),
    )
    assert result["provider_returned_ids"] == ["1", "1", "999"]
    assert any(
        row["id"] == "999" and row["reason"] == "unrequested_post_id"
        for row in result["unresolved"]
    )
    conflict = next(row for row in result["unresolved"] if row["id"] == "1")
    assert (
        conflict["reason"] == "conflicting_post_content"
        and len(conflict["source_versions"]) == 2
    )
    assert not result["records"]


@pytest.mark.parametrize("body", [b"not-json", b'{"tweets":"invalid"}'])
def test_malformed_lookup_keeps_received_transport_accounting_and_never_retries(history_job, monkeypatch, body):
    import requests

    from core.models import CollectionAttempt

    _plan, claim, scope = history_job
    frozen = scope.run.job.scope["save_person_job_lookup"]
    calls = []
    def transport(self, url, params, timeout):
        calls.append(params)
        response = requests.Response()
        response.status_code = 200
        response._content = body
        return response
    monkeypatch.setattr(XClient, "_get_bounded", transport)
    client = XClient(api_key="test-only", max_retries=0, max_response_bytes=100000, timeout_s=10)
    def run():
        journal = CollectionRequestHistoryJournal(claim, scope, endpoint="lookup", max_spend_usd="0.002", max_request_usd="0.001")
        return lookup_history_posts(post_ids=frozen["post_ids"], expected_authors=frozen["expected_authors"], client=client,
            journal=journal, authorized=True, credential_purpose=TwitterApiCredentialPurpose.ON_DEMAND,
            max_requests=2, deadline=datetime.fromisoformat(frozen["deadline"]))
    assert run()["reason"] == "request_failed_or_unknown"
    request = CollectionRequest.objects.get(scope_run=scope)
    assert (request.transport_outcome, request.http_status, request.response_bytes) == ("received", 200, len(body))
    attempt = CollectionAttempt.objects.get(pk=claim.attempt_id)
    assert (attempt.actual_requests, attempt.actual_response_bytes) == (1, len(body))
    assert run()["reason"] == "unknown_request_outcome"
    assert len(calls) == 1

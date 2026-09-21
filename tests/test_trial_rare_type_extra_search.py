"""U2: the bounded on-demand trial emits decision-grade evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import MagicMock

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError

from monitor.management.commands.trial_rare_type_extra_search import Command
from x_monitor.twitterapi_credentials import (
    TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV,
    TwitterApiCredentialPurpose,
)

pytestmark = [pytest.mark.django_db]


def _payload(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _response(status: int, body: dict | str) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = json.dumps(body) if isinstance(body, dict) else body
    response.content = response.text.encode()
    response.json.return_value = body
    return response


def test_preview_needs_no_database_provider_or_credentials(monkeypatch, capsys) -> None:
    monkeypatch.delenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, raising=False)
    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        lambda *_: pytest.fail("preview constructed a provider client"),
    )
    call_command("trial_rare_type_extra_search", "--preview", "--json")
    payload = _payload(capsys)
    assert payload["mode"] == "preview"
    assert payload["query_version"]
    assert payload["planner_query_sha256"]
    assert payload["rendered_query_sha256"]
    assert payload["request_kwargs"] == {
        "max_results": 20,
        "max_pages": 1,
        "max_per_page": 20,
        "since_time": payload["since_time"],
        "until_time": payload["until_time"],
    }


def test_planner_hash_is_stable_across_time_windows(monkeypatch, capsys) -> None:
    times = iter(
        [
            datetime(2026, 9, 22, 0, 0, tzinfo=UTC),
            datetime(2026, 9, 22, 1, 0, tzinfo=UTC),
        ]
    )

    class Clock:
        @classmethod
        def now(cls, tz):
            return next(times)

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.datetime", Clock
    )
    call_command("trial_rare_type_extra_search", "--preview", "--json")
    first = _payload(capsys)
    call_command("trial_rare_type_extra_search", "--preview", "--json")
    second = _payload(capsys)

    assert first["planner_query"] == second["planner_query"]
    assert first["planner_query_sha256"] == second["planner_query_sha256"]
    assert first["rendered_query_sha256"] != second["rendered_query_sha256"]


def test_trial_uses_on_demand_one_page_and_zero_retries(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        max_retries = 2
        _request_log: ClassVar[list[dict]] = [
            {"path": "/twitter/tweet/advanced_search", "n_results": 0}
        ]

        @classmethod
        def from_env(cls, purpose):
            captured["purpose"] = purpose
            return cls()

        def run_search(self, query, max_results, **kwargs):
            captured.update(query=query, max_results=max_results, kwargs=kwargs)
            captured["max_retries_at_send"] = self.max_retries
            return [], False

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    call_command("trial_rare_type_extra_search", "--window", "15m", "--json")
    payload = _payload(capsys)
    assert captured["purpose"] is TwitterApiCredentialPurpose.ON_DEMAND
    assert captured["max_retries_at_send"] == 0
    assert captured["max_results"] == 20
    assert captured["kwargs"] == {
        "max_pages": 1,
        "max_per_page": 20,
        "since_time": payload["since_time"],
        "until_time": payload["until_time"],
    }
    assert payload["credential_purpose"] == TwitterApiCredentialPurpose.ON_DEMAND.value


def test_direct_handle_rejects_invalid_options_before_client(monkeypatch) -> None:
    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        lambda *_: pytest.fail("invalid direct options reached client construction"),
    )
    with pytest.raises(CommandError, match="max-pages"):
        Command().handle(window="15m", max_pages=2, json=True, preview=False)
    with pytest.raises(CommandError, match="window"):
        Command().handle(window="24h", max_pages=1, json=True, preview=False)


def test_call_command_rejects_more_than_one_page_before_client(monkeypatch) -> None:
    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        lambda *_: pytest.fail("invalid argparse options reached client"),
    )
    with pytest.raises(CommandError, match="invalid choice"):
        call_command("trial_rare_type_extra_search", "--max-pages", "2")


def test_missing_key_names_only_on_demand_env(monkeypatch) -> None:
    def boom(purpose):
        assert purpose is TwitterApiCredentialPurpose.ON_DEMAND
        raise RuntimeError(f"{TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV} not in environment")

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        boom,
    )
    with pytest.raises(CommandError, match=TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV) as exc:
        call_command("trial_rare_type_extra_search")
    assert "SCHEDULED" not in str(exc.value)


def test_raw_paid_count_is_distinct_from_normalized_rows(monkeypatch, capsys) -> None:
    long_text = "full evidence " + ("x" * 400)

    class FakeClient:
        max_retries = 2
        _request_log: ClassVar[list[dict]] = [
            {"path": "/twitter/tweet/advanced_search", "n_results": 20}
        ]

        @classmethod
        def from_env(cls, purpose):
            return cls()

        def run_search(self, query, max_results, **kwargs):
            return (
                [
                    {
                        "id": str(i),
                        "created_at": datetime(2026, 9, 21, tzinfo=UTC),
                        "author_handle": "example",
                        "author_name": "Example",
                        "lang": "en",
                        "text": long_text if i == 0 else f"post {i}",
                        "quoted_text": "quoted source",
                    }
                    for i in range(4)
                ],
                False,
            )

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    call_command("trial_rare_type_extra_search", "--json")
    payload = _payload(capsys)
    assert payload["raw_paid_result_count"] == 20
    assert payload["normalized_result_count"] == 4
    assert payload["credits"]["reserved"] == 300
    assert payload["credits"]["estimated"] == 300
    assert payload["credits"]["confirmed"] is None
    assert payload["tweets"][0]["text"] == long_text
    assert payload["tweets"][0]["quoted_text"] == "quoted source"


def test_empty_success_uses_fifteen_credit_floor(monkeypatch, capsys) -> None:
    class FakeClient:
        max_retries = 2
        _request_log: ClassVar[list[dict]] = [
            {"path": "/twitter/tweet/advanced_search", "n_results": 0}
        ]

        @classmethod
        def from_env(cls, purpose):
            return cls()

        def run_search(self, *args, **kwargs):
            return [], False

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    call_command("trial_rare_type_extra_search", "--json")
    payload = _payload(capsys)
    assert payload["raw_paid_result_count"] == 0
    assert payload["credits"]["estimated"] == 15
    assert payload["credits"]["basis"] == "provider_raw_empty_floor"


def test_unavailable_usage_keeps_conservative_reservation(monkeypatch, capsys) -> None:
    class FakeClient:
        max_retries = 2
        _request_log: ClassVar[list[dict]] = []

        @classmethod
        def from_env(cls, purpose):
            return cls()

        def run_search(self, *args, **kwargs):
            return [], False

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    call_command("trial_rare_type_extra_search", "--json")
    payload = _payload(capsys)
    assert payload["raw_paid_result_count"] is None
    assert payload["credits"] == {
        "reserved": 300,
        "estimated": 300,
        "confirmed": None,
        "basis": "provider_usage_unavailable",
    }


def test_missing_database_reports_unknown_overlap_without_error_text(
    monkeypatch, capsys
) -> None:
    from django.db.utils import OperationalError

    class FakeClient:
        max_retries = 2
        _request_log: ClassVar[list[dict]] = [
            {"path": "/twitter/tweet/advanced_search", "n_results": 1}
        ]

        @classmethod
        def from_env(cls, purpose):
            return cls()

        def run_search(self, *args, **kwargs):
            return [{"id": "1", "text": "keeper"}], False

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    monkeypatch.setattr(
        "core.models.Post.objects.filter",
        MagicMock(side_effect=OperationalError("postgres://secret@host/db")),
    )
    call_command("trial_rare_type_extra_search", "--json")
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["db_overlap"] == {"status": "unavailable", "count": None}
    assert payload["tweets"][0]["already_in_db"] is None
    assert "secret" not in out


@pytest.mark.parametrize(
    ("effect", "match"),
    [
        (requests.Timeout("slow"), "request failed"),
        (_response(401, "unauthorized"), "auth failed"),
        (_response(429, "limited"), "rate limit"),
        (_response(503, "down"), "5xx"),
    ],
)
def test_transport_failures_make_one_physical_attempt(
    monkeypatch, effect, match
) -> None:
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "test-secret")
    get = MagicMock(side_effect=effect if isinstance(effect, Exception) else None)
    if not isinstance(effect, Exception):
        get.return_value = effect
    monkeypatch.setattr("x_monitor.apify.requests.get", get)

    with pytest.raises(CommandError, match=match):
        call_command("trial_rare_type_extra_search", "--json")
    assert get.call_count == 1


def test_generic_provider_failure_emits_sanitized_conservative_evidence(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "test-secret")
    get = MagicMock(return_value=_response(400, "postgres://secret@host/db"))
    monkeypatch.setattr("x_monitor.apify.requests.get", get)

    with pytest.raises(CommandError, match="request failed") as exc:
        call_command("trial_rare_type_extra_search", "--json")
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "failed"
    assert payload["error_code"] == "provider_error"
    assert payload["provider_request_attempts"] == 1
    assert payload["raw_paid_result_count"] is None
    assert payload["credits"]["estimated"] == 300
    assert "secret" not in out
    assert "secret" not in str(exc.value)
    assert get.call_count == 1


def test_trial_never_inserts_posts(monkeypatch, capsys) -> None:
    class FakeClient:
        max_retries = 2
        _request_log: ClassVar[list[dict]] = [
            {"path": "/twitter/tweet/advanced_search", "n_results": 1}
        ]

        @classmethod
        def from_env(cls, purpose):
            return cls()

        def run_search(self, *args, **kwargs):
            return [{"id": "trial-only", "text": "I've joined an AI lab"}], False

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    call_command("trial_rare_type_extra_search", "--json")
    _payload(capsys)

    from core.models import Post

    assert not Post.objects.filter(tweet_id="trial-only").exists()

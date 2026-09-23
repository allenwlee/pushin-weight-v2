"""U2: the bounded on-demand trial emits decision-grade evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
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


def _write_windows(path: Path, windows: list[dict[str, str]]) -> None:
    path.write_text(json.dumps(windows), encoding="utf-8")


def test_volume_preview_validates_exact_nonoverlapping_windows_without_provider(
    monkeypatch, tmp_path, capsys
) -> None:
    windows = tmp_path / "windows.json"
    output = tmp_path / "evidence"
    _write_windows(
        windows,
        [
            {"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:15:00Z"},
            {"start": "2026-09-19T00:15:00Z", "end": "2026-09-19T00:30:00Z"},
        ],
    )
    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        lambda *_: pytest.fail("preview constructed a provider client"),
    )

    call_command(
        "trial_rare_type_extra_search",
        "--volume-windows",
        str(windows),
        "--output-dir",
        str(output),
        "--max-calls",
        "2",
        "--credit-budget",
        "600",
        "--preview",
        "--json",
    )

    payload = _payload(capsys)
    assert payload["mode"] == "volume_preview"
    assert payload["planned_physical_calls"] == 2
    assert payload["reserved_credits"] == 600
    assert payload["windows"][0]["duration_seconds"] == 900
    assert not output.exists()


@pytest.mark.parametrize(
    "windows",
    [
        [{"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:14:59Z"}],
        [
            {"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:15:00Z"},
            {"start": "2026-09-19T00:14:00Z", "end": "2026-09-19T00:29:00Z"},
        ],
    ],
)
def test_volume_probe_rejects_invalid_windows_before_http(
    monkeypatch, tmp_path, windows
) -> None:
    source = tmp_path / "windows.json"
    _write_windows(source, windows)
    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        lambda *_: pytest.fail("invalid windows reached provider"),
    )
    with pytest.raises(CommandError, match="15-minute|overlap"):
        call_command(
            "trial_rare_type_extra_search",
            "--volume-windows",
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--max-calls",
            "2",
            "--credit-budget",
            "600",
        )


@pytest.mark.parametrize(
    "windows",
    [
        [{"start": "2026-09-19T00:01:00Z", "end": "2026-09-19T00:16:00Z"}],
        [{"start": "2999-09-19T00:00:00Z", "end": "2999-09-19T00:15:00Z"}],
    ],
)
def test_volume_probe_rejects_unaligned_or_future_windows_before_http(
    monkeypatch, tmp_path, windows
) -> None:
    source = tmp_path / "windows.json"
    _write_windows(source, windows)
    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        lambda *_: pytest.fail("invalid windows reached provider"),
    )
    with pytest.raises(CommandError, match="quarter-hour|completed"):
        call_command(
            "trial_rare_type_extra_search", "--volume-windows", str(source),
            "--output-dir", str(tmp_path / "out"), "--max-calls", "1",
            "--credit-budget", "300",
        )


def test_volume_probe_renders_every_window_before_client(monkeypatch, tmp_path) -> None:
    source = tmp_path / "windows.json"
    _write_windows(source, [
        {"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:15:00Z"},
        {"start": "2026-09-19T00:15:00Z", "end": "2026-09-19T00:30:00Z"},
    ])
    calls = 0

    def render(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("bad rendered query")
        return "rendered"

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.render_rare_type_extra_search_query",
        render,
    )
    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        lambda *_: pytest.fail("render failure reached provider"),
    )
    with pytest.raises(CommandError, match="bad rendered query"):
        call_command(
            "trial_rare_type_extra_search", "--volume-windows", str(source),
            "--output-dir", str(tmp_path / "out"), "--max-calls", "2",
            "--credit-budget", "600",
        )


@pytest.mark.parametrize(
    ("max_calls", "budget", "match"),
    [(1, 600, "physical-call"), (2, 599, "credit")],
)
def test_volume_probe_reserves_all_calls_before_http(
    monkeypatch, tmp_path, max_calls, budget, match
) -> None:
    source = tmp_path / "windows.json"
    _write_windows(
        source,
        [
            {"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:15:00Z"},
            {"start": "2026-09-19T00:15:00Z", "end": "2026-09-19T00:30:00Z"},
        ],
    )
    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient.from_env",
        lambda *_: pytest.fail("unreserved batch reached provider"),
    )
    with pytest.raises(CommandError, match=match):
        call_command(
            "trial_rare_type_extra_search",
            "--volume-windows",
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--max-calls",
            str(max_calls),
            "--credit-budget",
            str(budget),
        )


def test_volume_probe_captures_raw_before_next_call_and_reconciles_counts(
    monkeypatch, tmp_path
) -> None:
    source = tmp_path / "windows.json"
    output = tmp_path / "evidence"
    _write_windows(
        source,
        [
            {"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:15:00Z"},
            {"start": "2026-09-19T00:15:00Z", "end": "2026-09-19T00:30:00Z"},
        ],
    )

    class FakeClient:
        max_retries = 2
        calls = 0

        @classmethod
        def from_env(cls, purpose):
            assert purpose is TwitterApiCredentialPurpose.ON_DEMAND
            return cls()

        def run_search_page_with_raw(self, query, receipt_sink, **kwargs):
            if self.calls:
                assert (output / "raw" / "request-0001.json").exists()
                assert (output / "requests.jsonl").read_text(encoding="utf-8")
            self.calls += 1
            raw = {
                "tweets": [
                    {
                        "id": "duplicate-id",
                        "text": "verbatim\ntext" if self.calls == 1 else "again",
                        "createdAt": "2026-09-19T00:01:00Z",
                        "author": {"userName": "tester"},
                    },
                    {"text": "missing id"},
                ]
                if self.calls == 1
                else [],
                "has_next_page": self.calls == 1,
                "next_cursor": "cursor-secret" if self.calls == 1 else None,
            }
            normalized = (
                [
                    {"id": "duplicate-id", "text": "verbatim\ntext"},
                    {"id": "", "text": "missing id"},
                ]
                if self.calls == 1
                else []
            )
            raw_body = json.dumps(raw).encode()
            receipt_sink(raw_body)
            return raw_body, raw, normalized, self.calls == 1, 0

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    call_command(
        "trial_rare_type_extra_search",
        "--volume-windows",
        str(source),
        "--output-dir",
        str(output),
        "--max-calls",
        "2",
        "--credit-budget",
        "600",
    )

    requests_rows = [json.loads(line) for line in (output / "requests.jsonl").read_text().splitlines()]
    hit_rows = [json.loads(line) for line in (output / "hits.jsonl").read_text().splitlines()]
    assert len(requests_rows) == 2
    assert requests_rows[0]["raw_count"] == 2
    assert requests_rows[0]["normalized_count"] == 2
    assert requests_rows[0]["continuation"] is True
    assert requests_rows[0]["coverage"] == "capped_or_unfinished_lower_bound"
    assert requests_rows[1]["raw_count"] == 0
    assert requests_rows[1]["estimated_credits"] == 15
    assert requests_rows[0]["arguments"]["max_pages"] == 1
    assert requests_rows[0]["http_arguments"] == {
        "query": requests_rows[0]["rendered_query"],
        "queryType": "Latest",
        "limit": 20,
    }
    assert requests_rows[0]["run_search_kwargs"] == requests_rows[0]["arguments"]
    assert requests_rows[0]["query_version"]
    assert requests_rows[0]["query_sha256"]
    assert requests_rows[0]["capture_format"] == "exact_provider_response_bytes_json"
    assert len(hit_rows) == 2
    assert hit_rows[0]["tweet_id"] == "duplicate-id"
    assert hit_rows[0]["text"] == "verbatim\ntext"
    assert hit_rows[1]["tweet_id"] is None
    assert "missing_tweet_id" in hit_rows[1]["record_issues"]
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "Raw top-level slots: 2" in report
    assert "Normalized rows: 2" in report
    assert "Unique nonempty tweet IDs: 1" in report
    assert "Unknown-ID slots: 1" in report
    assert "Capped/unfinished windows: 1" in report
    assert "Provider-confirmed credits: unavailable" in report
    assert "Creation-time distribution (UTC hour)" in report
    assert "Sampled raw posts/hour" in report
    assert "Weekday sampled windows" in report
    assert "20 posts/hour" in report and "50 posts/hour" in report
    assert "UTC coverage" in report


def test_volume_probe_error_keeps_raw_receipt_status_and_stops_on_overage(
    monkeypatch, tmp_path
) -> None:
    source = tmp_path / "windows.json"
    output = tmp_path / "evidence"
    _write_windows(source, [
        {"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:15:00Z"},
        {"start": "2026-09-19T00:15:00Z", "end": "2026-09-19T00:30:00Z"},
    ])
    calls = []

    class FakeClient:
        max_retries = 2

        @classmethod
        def from_env(cls, purpose):
            return cls()

        def run_search_page_with_raw(self, query, receipt_sink, **kwargs):
            calls.append(kwargs)
            body = json.dumps({"tweets": [{}] * 21}).encode()
            receipt_sink(body)
            exc = TypeError("schema failure")
            exc.response_status_code = 200
            raise exc

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    call_command(
        "trial_rare_type_extra_search", "--volume-windows", str(source),
        "--output-dir", str(output), "--max-calls", "2", "--credit-budget", "600",
    )
    rows = [json.loads(line) for line in (output / "requests.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["raw_count"] == 21
    assert rows[0]["raw_response_path"] == "raw/request-0001.json"
    assert (output / rows[0]["raw_response_path"]).exists()
    assert rows[0]["capture_format"] == "exact_provider_response_bytes_json"
    assert rows[0]["http_status"] == 200
    assert rows[0]["stop_reason"] == "reservation_undermined_raw_slots_over_20"


def test_volume_probe_stops_after_first_request_error_and_reports_unattempted(
    monkeypatch, tmp_path
) -> None:
    source = tmp_path / "windows.json"
    output = tmp_path / "evidence"
    _write_windows(source, [
        {"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:15:00Z"},
        {"start": "2026-09-19T00:15:00Z", "end": "2026-09-19T00:30:00Z"},
    ])
    calls = []

    class FakeClient:
        max_retries = 2

        @classmethod
        def from_env(cls, purpose):
            return cls()

        def run_search_page_with_raw(self, query, receipt_sink, **kwargs):
            calls.append(kwargs)
            raise requests.Timeout("do not retry later windows")

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    call_command(
        "trial_rare_type_extra_search", "--volume-windows", str(source),
        "--output-dir", str(output), "--max-calls", "2", "--credit-budget", "600",
    )

    rows = [json.loads(line) for line in (output / "requests.jsonl").read_text().splitlines()]
    assert len(calls) == 1
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert rows[0]["stop_reason"] == "request_error"
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "Completion: incomplete (1 of 2 planned windows attempted)" in report
    assert "2026-09-19T00:15:00Z" in report


@pytest.mark.parametrize(
    ("raw, expected_reason"),
    [
        ({"tweets": [{"id": str(index)} for index in range(21)]},
         "reservation_undermined_raw_slots_over_20"),
        ({"tweets": [{"id": "over-credit"}], "usage": {"credits": 301}},
         "reservation_undermined_actual_credits_over_300"),
    ],
)
def test_volume_probe_overage_appends_final_row_without_rewriting_prior_ledger(
    monkeypatch, tmp_path, raw, expected_reason
) -> None:
    source = tmp_path / "windows.json"
    output = tmp_path / "evidence"
    _write_windows(source, [
        {"start": "2026-09-19T00:00:00Z", "end": "2026-09-19T00:15:00Z"},
        {"start": "2026-09-19T00:15:00Z", "end": "2026-09-19T00:30:00Z"},
        {"start": "2026-09-19T00:30:00Z", "end": "2026-09-19T00:45:00Z"},
    ])
    first_line = None
    calls = 0

    class FakeClient:
        max_retries = 2

        @classmethod
        def from_env(cls, purpose):
            return cls()

        def run_search_page_with_raw(self, query, receipt_sink, **kwargs):
            nonlocal calls, first_line
            calls += 1
            if calls == 2:
                first_line = (output / "requests.jsonl").read_bytes()
            body = {"tweets": []} if calls == 1 else raw
            raw_body = json.dumps(body).encode()
            receipt_sink(raw_body)
            return raw_body, body, [], False, 0

    monkeypatch.setattr(
        "monitor.management.commands.trial_rare_type_extra_search.TwitterApiClient",
        FakeClient,
    )
    monkeypatch.setattr(
        Command, "_rewrite_last_jsonl_row",
        lambda *_: pytest.fail("durable request ledger was rewritten"),
        raising=False,
    )
    call_command(
        "trial_rare_type_extra_search", "--volume-windows", str(source),
        "--output-dir", str(output), "--max-calls", "3", "--credit-budget", "900",
    )

    ledger = (output / "requests.jsonl").read_bytes()
    rows = [json.loads(line) for line in ledger.splitlines()]
    assert calls == 2
    assert ledger.startswith(first_line)
    assert rows[1]["stop_reason"] == expected_reason


def test_volume_report_labels_complete_96_window_day() -> None:
    start = datetime(2026, 9, 19, tzinfo=UTC)
    windows = []
    for index in range(96):
        window_start = start + timedelta(minutes=15 * index)
        windows.append({
            "start_utc": window_start.isoformat().replace("+00:00", "Z"),
            "end_utc": (window_start + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
        })
    preview = {
        "query_version": "test", "planner_query_sha256": "sha",
        "credential_purpose": "on_demand", "planned_physical_calls": 96,
        "reserved_credits": 28800, "windows": windows,
    }
    rows = [
        {
            "request_id": f"request-{index + 1:04d}",
            "window_start_utc": window["start_utc"], "window_end_utc": window["end_utc"],
            "raw_count": 0, "normalized_count": 0, "actual_credits": 0,
            "estimated_credits": 15, "coverage": "provider_exhausted_within_window",
            "status": "success",
        }
        for index, window in enumerate(windows)
    ]
    report = Command._volume_report(preview, rows, [])
    assert "Completion: complete 96-window UTC day" in report
    assert "not a complete-period sample" not in report
    assert "Missing/unattempted windows: none" in report


def _volume_report_fixture(*starts: datetime) -> tuple[dict, list[dict]]:
    windows = []
    for start in starts:
        for index in range(96):
            window_start = start + timedelta(minutes=15 * index)
            windows.append(
                {
                    "start_utc": window_start.isoformat().replace("+00:00", "Z"),
                    "end_utc": (window_start + timedelta(minutes=15))
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
    preview = {
        "query_version": "test",
        "planner_query_sha256": "sha",
        "credential_purpose": "on_demand",
        "planned_physical_calls": len(windows),
        "reserved_credits": 300 * len(windows),
        "windows": windows,
    }
    rows = [
        {
            "request_id": f"request-{index + 1:04d}",
            "window_start_utc": window["start_utc"],
            "window_end_utc": window["end_utc"],
            "raw_count": 0,
            "normalized_count": 0,
            "actual_credits": 0,
            "estimated_credits": 15,
            "coverage": "provider_exhausted_within_window",
            "status": "success",
        }
        for index, window in enumerate(windows)
    ]
    return preview, rows


def test_volume_report_labels_two_nonconsecutive_complete_utc_days() -> None:
    preview, rows = _volume_report_fixture(
        datetime(2026, 9, 18, tzinfo=UTC),
        datetime(2026, 9, 20, tzinfo=UTC),
    )

    report = Command._volume_report(preview, rows, [])

    assert "Completion: complete 2-day sample (192 successful planned windows)" in report
    assert "not a complete-period sample" not in report
    assert "Missing/unattempted windows: none" in report


def test_volume_report_keeps_two_day_sample_incomplete_when_a_window_is_missing() -> None:
    preview, rows = _volume_report_fixture(
        datetime(2026, 9, 18, tzinfo=UTC),
        datetime(2026, 9, 20, tzinfo=UTC),
    )

    report = Command._volume_report(preview, rows[:-1], [])

    assert "Completion: incomplete (191 of 192 planned windows attempted)" in report
    assert "This is an incomplete prespecified sample" in report


def test_volume_report_counts_known_error_receipts_and_capped_windows_separately() -> None:
    preview, rows = _volume_report_fixture(
        datetime(2026, 9, 18, tzinfo=UTC),
        datetime(2026, 9, 20, tzinfo=UTC),
    )
    rows[0].update(status="error", raw_count=3, normalized_count=None)
    rows[1]["coverage"] = "capped_or_unfinished_lower_bound"

    report = Command._volume_report(preview, rows, [])

    assert "Completion: incomplete (191 successful of 192 planned windows)" in report
    assert "Capped/unfinished windows: 1" in report
    assert "Error windows: 1 (known raw count: 1; unknown raw count: 0)" in report
    assert "Error receipts with known raw counts are included in raw-slot totals" in report
    assert "Provider coverage: exhaustive for every planned window" not in report

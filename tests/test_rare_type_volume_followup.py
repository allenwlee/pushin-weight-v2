import json
from pathlib import Path

import pytest

from scripts.rare_type_volume_followup import EvidenceError, load_first_pages, run_followup


def write_first_pages(root: Path, pages: list[dict]) -> None:
    (root / "raw").mkdir(parents=True)
    rows = []
    for index, raw in enumerate(pages, 1):
        request_id = f"request-{index:04d}"
        (root / "raw" / f"{request_id}.json").write_text(json.dumps(raw))
        rows.append({"request_id": request_id, "query_id": f"q-{index}",
                     "status": "success", "rendered_query": f"query {index} since_time:1 until_time:2",
                     "window_start_utc": "2026-09-20T00:00:00Z",
                     "window_end_utc": "2026-09-20T00:15:00Z",
                     "raw_response_path": f"raw/{request_id}.json",
                     "raw_count": len(raw.get("tweets", [])),
                     "continuation": bool(raw.get("has_next_page") or raw.get("next_cursor"))})
    (root / "requests.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def _get(self, path, params, *, capture_raw, raw_sink):
        self.calls.append((path, params.copy()))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        body = json.dumps(value, separators=(",", ":")).encode()
        raw_sink(body)
        return body, value


class RawThenErrorClient(FakeClient):
    def _get(self, path, params, *, capture_raw, raw_sink):
        self.calls.append((path, params.copy()))
        raw_sink(b'{"error":"rate limited"}')
        error = RuntimeError("HTTP 429")
        error.response_status_code = 429
        raise error


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def tweet(number: int, created="2026-09-20T00:05:00Z"):
    return {"id": str(number), "text": f"tweet {number}", "created_at": created}


def test_validates_first_page_count_and_raw_count(tmp_path):
    write_first_pages(tmp_path, [{"tweets": [tweet(1)], "next_cursor": "c1"}])
    with pytest.raises(EvidenceError, match="expected 2"):
        load_first_pages(tmp_path, expected_windows=2)
    row = json.loads((tmp_path / "requests.jsonl").read_text())
    row["raw_count"] = 9
    (tmp_path / "requests.jsonl").write_text(json.dumps(row) + "\n")
    with pytest.raises(EvidenceError, match="raw-count mismatch"):
        load_first_pages(tmp_path, expected_windows=1)


def test_walks_cursor_chain_including_underfilled_page_without_rebuying_first(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    write_first_pages(source, [{"tweets": [tweet(1)], "has_next_page": True, "next_cursor": "c1"}])
    client = FakeClient([
        {"tweets": [tweet(2)], "has_next_page": True, "next_cursor": "c2"},
        {"tweets": [tweet(3)], "has_next_page": False, "next_cursor": None},
    ])
    result = run_followup(source, output, client, expected_windows=1)
    assert result["status"] == "definitive_provider_exhaustion"
    assert result["combined_raw_slots"] == 3
    assert result["first_pages_rebought"] == 0
    assert [call[1]["cursor"] for call in client.calls] == ["c1", "c2"]
    assert all("cursor" in call[1] for call in client.calls)
    rows = read_jsonl(output / "requests.jsonl")
    assert rows[0]["stop_reason"] == "continue_underfilled"
    assert rows[1]["stop_reason"] == "cursor_exhausted"


def test_repeated_cursor_stops_incomplete(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    write_first_pages(source, [{"tweets": [tweet(1)], "next_cursor": "same"}])
    client = FakeClient([{"tweets": [tweet(2)], "next_cursor": "same"}])
    result = run_followup(source, output, client, expected_windows=1)
    assert result["status"] == "incomplete"
    assert result["stop_reason"] == "repeated_cursor_no_progress"


def test_error_keeps_dispatch_and_stops_fail_closed(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    write_first_pages(source, [{"tweets": [tweet(1)], "next_cursor": "c1"}])
    result = run_followup(source, output, FakeClient([requests_error()]), expected_windows=1)
    assert result["status"] == "incomplete"
    assert result["stop_reason"] == "request_error_fail_closed"
    assert len(read_jsonl(output / "dispatches.jsonl")) == 1
    error = read_jsonl(output / "requests.jsonl")[0]
    assert error["status"] == "error"
    assert error["raw_count"] is None


def test_error_response_bytes_are_durable_and_linked(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    write_first_pages(source, [{"tweets": [tweet(1)], "next_cursor": "c1"}])
    result = run_followup(source, output, RawThenErrorClient([]), expected_windows=1)
    assert result["status"] == "incomplete"
    row = read_jsonl(output / "requests.jsonl")[0]
    assert row["http_status"] == 429
    assert (output / row["raw_response_path"]).read_bytes() == b'{"error":"rate limited"}'


def requests_error():
    return RuntimeError("network ambiguous")


def test_budget_reserves_300_before_each_call(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    write_first_pages(source, [{"tweets": [tweet(1)], "next_cursor": "c1"}])
    client = FakeClient([{"tweets": [tweet(number) for number in range(2, 22)], "next_cursor": "c2"}])
    result = run_followup(source, output, client, expected_windows=1, credit_budget=300)
    assert result["physical_followup_calls"] == 1
    assert result["committed_or_reserved_credits"] == 300
    assert result["stop_reason"] == "global_credit_budget_exhausted"
    assert result["status"] == "incomplete"


def test_reconciles_duplicates_dates_and_first_page_complete_window(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    write_first_pages(source, [
        {"tweets": [tweet(1)], "next_cursor": "c1"},
        {"tweets": [tweet(9)], "has_next_page": False},
    ])
    client = FakeClient([{"tweets": [tweet(1), tweet(2, "Sun Sep 21 00:00:00 +0000 2026")],
                          "has_next_page": False}])
    result = run_followup(source, output, client, expected_windows=2)
    assert result["status"] == "definitive_provider_exhaustion"
    assert result["complete_windows"] == 2
    assert result["combined_raw_slots"] == 4
    assert result["combined_unique_tweet_ids"] == 3
    row = read_jsonl(output / "requests.jsonl")[0]
    assert row["duplicate_count"] == 1
    assert row["outside_window_count"] == 1
    assert row["unknown_or_unparseable_date_count"] == 0


def test_empty_page_with_cursor_is_incomplete_no_progress(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    write_first_pages(source, [{"tweets": [tweet(1)], "next_cursor": "c1"}])
    result = run_followup(source, output,
                          FakeClient([{"tweets": [], "next_cursor": "c2"}]),
                          expected_windows=1)
    assert result["status"] == "incomplete"
    assert result["stop_reason"] == "empty_page_no_progress"


def test_refuses_existing_output_so_ambiguous_call_is_not_retried(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    write_first_pages(source, [{"tweets": [], "next_cursor": "c1"}])
    output.mkdir()
    with pytest.raises(EvidenceError, match="fresh"):
        run_followup(source, output, FakeClient([]), expected_windows=1)

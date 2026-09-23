"""Exhaust saved rare-type volume-probe cursor chains without buying page 1 again.

This is an on-demand diagnostic. It writes an append-only pre-dispatch ledger so
an interruption is deliberately not auto-resumed: use a fresh output directory
and reconcile the ambiguous dispatched call before trying again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import requests

from x_monitor.apify import SEARCH_PATH, TwitterApiClient
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

PAGE_LIMIT = 20
RESERVATION_PER_CALL = 300
CREDITS_PER_SLOT = 15
DEFAULT_MAX_CALLS = 2_000
DEFAULT_CREDIT_BUDGET = 300_000


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class Window:
    first: dict[str, Any]
    first_raw: dict[str, Any]
    cursor: str


def _append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_bytes(path: Path, body: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, value: Any) -> None:
    body = (json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n").encode()
    _write_bytes(path, body)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvidenceError(f"cannot read {path}") from exc
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"invalid JSON at {path}:{number}") from exc
        if not isinstance(row, dict):
            raise EvidenceError(f"non-object row at {path}:{number}")
        rows.append(row)
    return rows


def load_first_pages(source: Path, expected_windows: int = 192) -> list[Window]:
    rows = _load_jsonl(source / "requests.jsonl")
    if len(rows) != expected_windows:
        raise EvidenceError(f"expected {expected_windows} first-page rows, found {len(rows)}")
    request_ids: set[str] = set()
    query_ids: set[str] = set()
    windows: list[Window] = []
    for row in rows:
        request_id = row.get("request_id")
        query_id = row.get("query_id")
        if not isinstance(request_id, str) or request_id in request_ids:
            raise EvidenceError("first-page request IDs must be unique strings")
        if not isinstance(query_id, str) or query_id in query_ids:
            raise EvidenceError("first-page query IDs must be unique strings")
        request_ids.add(request_id)
        query_ids.add(query_id)
        required = ("rendered_query", "window_start_utc", "window_end_utc")
        if any(not isinstance(row.get(key), str) for key in required):
            raise EvidenceError(f"{request_id} lacks exact query/window evidence")
        if row.get("status") not in {"success", "success_with_normalization_errors"}:
            raise EvidenceError(f"{request_id} was not a successful first page")
        raw_rel = row.get("raw_response_path")
        if not isinstance(raw_rel, str):
            raise EvidenceError(f"{request_id} lacks raw_response_path")
        raw_path = source / raw_rel
        try:
            raw = json.loads(raw_path.read_bytes())
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EvidenceError(f"invalid raw response for {request_id}") from exc
        if not isinstance(raw, dict):
            raise EvidenceError(f"raw response for {request_id} is not an object")
        items = raw.get("tweets") or raw.get("data") or []
        if not isinstance(items, list) or len(items) != row.get("raw_count"):
            raise EvidenceError(f"raw-count mismatch for {request_id}")
        cursor = raw.get("next_cursor")
        signaled = bool(raw.get("has_next_page") or cursor)
        if bool(row.get("continuation")) != signaled:
            raise EvidenceError(f"continuation mismatch for {request_id}")
        if signaled and not isinstance(cursor, str):
            raise EvidenceError(f"{request_id} signals continuation without a cursor")
        if cursor:
            windows.append(Window(row, raw, cursor))
    return windows


def _items(raw: dict[str, Any]) -> list[Any]:
    value = raw.get("tweets") or raw.get("data") or []
    if not isinstance(value, list):
        raise EvidenceError("provider search results are not a list")
    return value


def _tweet_id(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get("id") or item.get("id_str")
    return str(value) if value else None


def _created(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get("createdAt") or item.get("created_at")
    return value if isinstance(value, str) else None


def _parse_created(value: str) -> datetime | None:
    for parser in (
        lambda: datetime.fromisoformat(value.replace("Z", "+00:00")),
        lambda: datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y"),
    ):
        try:
            return parser()
        except ValueError:
            pass
    return None


def _hit(request_id: str, index: int, item: Any, duplicate: bool) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"request_id": request_id, "response_index": index, "tweet_id": None,
                "created_at_utc": None, "author_handle": None, "text": None,
                "source_url": None, "duplicate_in_window": False,
                "record_issues": ["non_object_slot"]}
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    issues = []
    if _tweet_id(item) is None:
        issues.append("missing_tweet_id")
    if item.get("text") is None:
        issues.append("missing_text")
    return {"request_id": request_id, "response_index": index,
            "tweet_id": _tweet_id(item), "created_at_utc": _created(item),
            "author_handle": item.get("author_handle") or author.get("userName") or author.get("username"),
            "text": item.get("text"), "source_url": item.get("tweet_url") or item.get("url"),
            "duplicate_in_window": duplicate, "record_issues": issues}


def run_followup(
    source: Path,
    output: Path,
    client: TwitterApiClient,
    *,
    max_calls: int = DEFAULT_MAX_CALLS,
    credit_budget: int = DEFAULT_CREDIT_BUDGET,
    expected_windows: int = 192,
) -> dict[str, Any]:
    if max_calls <= 0 or credit_budget < RESERVATION_PER_CALL:
        raise EvidenceError("max_calls and credit_budget must permit at least one reserved call")
    client.max_retries = 0
    windows = load_first_pages(source, expected_windows)
    if output.exists():
        raise EvidenceError("output directory must be fresh; automatic resume is fail-closed")
    output.mkdir(parents=True)
    raw_dir = output / "raw"
    raw_dir.mkdir()
    dispatches = output / "dispatches.jsonl"
    requests_path = output / "requests.jsonl"
    hits_path = output / "hits.jsonl"
    for path in (dispatches, requests_path, hits_path):
        path.touch()

    calls = committed = estimated = followup_raw = duplicates = 0
    complete_windows = sum(not (raw.get("has_next_page") or raw.get("next_cursor")) for raw in
                           [json.loads((source / row["raw_response_path"]).read_bytes())
                            for row in _load_jsonl(source / "requests.jsonl")])
    stop_reason: str | None = None
    processed: set[str] = set()

    for window in windows:
        first = window.first
        query_id = first["query_id"]
        cursor = window.cursor
        page = 2
        seen_cursors = {cursor}
        seen_ids = {_tweet_id(item) for item in _items(window.first_raw) if _tweet_id(item)}
        seen_pages: set[str] = set()
        window_complete = False
        while cursor:
            if calls >= max_calls:
                stop_reason = "global_max_calls_exhausted"
                break
            if committed + RESERVATION_PER_CALL > credit_budget:
                stop_reason = "global_credit_budget_exhausted"
                break
            request_id = f"followup-{calls + 1:04d}"
            raw_path = raw_dir / f"{request_id}.json"
            issued = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            params = {"query": first["rendered_query"], "queryType": "Latest",
                      "limit": PAGE_LIMIT, "cursor": cursor}
            _append(dispatches, {"request_id": request_id, "query_id": query_id,
                    "page": page, "cursor_sha256": hashlib.sha256(cursor.encode()).hexdigest(),
                    "issued_at_utc": issued, "state": "dispatching_no_automatic_retry"})
            calls += 1
            committed += RESERVATION_PER_CALL
            try:
                _, raw = client._get(SEARCH_PATH, params, capture_raw=True,
                                     raw_sink=lambda body, path=raw_path: _write_bytes(path, body))
                if not isinstance(raw, dict):
                    raise EvidenceError("provider response is not an object")
                items = _items(raw)
                raw_count = len(items)
                page_fingerprint = hashlib.sha256(
                    json.dumps([_tweet_id(item) for item in items], separators=(",", ":")).encode()
                ).hexdigest()
                next_cursor = raw.get("next_cursor")
                continuation = bool(raw.get("has_next_page") or next_cursor)
                outside = unknown_dates = 0
                page_duplicates = 0
                created_values: list[str] = []
                for index, item in enumerate(items):
                    tweet_id = _tweet_id(item)
                    duplicate = bool(tweet_id and tweet_id in seen_ids)
                    page_duplicates += int(duplicate)
                    if tweet_id:
                        seen_ids.add(tweet_id)
                    created = _created(item)
                    if created:
                        created_values.append(created)
                        dt = _parse_created(created)
                        if dt is None:
                            unknown_dates += 1
                        else:
                            start = datetime.fromisoformat(first["window_start_utc"].replace("Z", "+00:00"))
                            end = datetime.fromisoformat(first["window_end_utc"].replace("Z", "+00:00"))
                            outside += int(not (start <= dt < end))
                    else:
                        unknown_dates += 1
                    _append(hits_path, _hit(request_id, index, item, duplicate))
                estimated_call = CREDITS_PER_SLOT * max(1, raw_count)
                estimated += estimated_call
                followup_raw += raw_count
                duplicates += page_duplicates
                if raw_count > PAGE_LIMIT:
                    page_stop = "raw_slots_over_20"
                elif continuation and raw_count == 0:
                    page_stop = "empty_page_no_progress"
                elif page_fingerprint in seen_pages:
                    page_stop = "repeated_page_no_progress"
                elif continuation and not isinstance(next_cursor, str):
                    page_stop = "continuation_without_cursor"
                elif next_cursor in seen_cursors:
                    page_stop = "repeated_cursor_no_progress"
                elif continuation:
                    page_stop = "continue_underfilled" if raw_count < PAGE_LIMIT else "continue"
                else:
                    page_stop = "cursor_exhausted"
                if raw_count <= PAGE_LIMIT:
                    committed += estimated_call - RESERVATION_PER_CALL
                _append(requests_path, {"request_id": request_id, "query_id": query_id,
                        "provider": "twitterapi.io", "tool_or_endpoint": SEARCH_PATH,
                        "credential_purpose": "on-demand", "issued_at_utc": issued,
                        "page": page, "cursor_sha256": hashlib.sha256(cursor.encode()).hexdigest(),
                        "rendered_query": first["rendered_query"],
                        "window_start_utc": first["window_start_utc"], "window_end_utc": first["window_end_utc"],
                        "requested_limit": PAGE_LIMIT, "raw_count": raw_count, "status": "success",
                        "raw_response_path": str(raw_path.relative_to(output)),
                        "capture_format": "exact_provider_response_bytes_json",
                        "continuation": continuation, "next_cursor_present": bool(next_cursor),
                        "created_at_min": min(created_values) if created_values else None,
                        "created_at_max": max(created_values) if created_values else None,
                        "outside_window_count": outside, "unknown_or_unparseable_date_count": unknown_dates,
                        "duplicate_count": page_duplicates,
                        "reserved_credits": RESERVATION_PER_CALL, "estimated_credits": estimated_call,
                        "stop_reason": page_stop})
                if page_stop == "cursor_exhausted":
                    window_complete = True
                    break
                if page_stop not in {"continue", "continue_underfilled"}:
                    stop_reason = page_stop
                    break
                seen_pages.add(page_fingerprint)
                seen_cursors.add(next_cursor)
                cursor = next_cursor
                page += 1
            except Exception as exc:
                # The raw sink runs before HTTP/JSON validation, when a response exists.
                _append(requests_path, {"request_id": request_id, "query_id": query_id,
                        "provider": "twitterapi.io", "tool_or_endpoint": SEARCH_PATH,
                        "credential_purpose": "on-demand", "issued_at_utc": issued, "page": page,
                        "cursor_sha256": hashlib.sha256(cursor.encode()).hexdigest(),
                        "window_start_utc": first["window_start_utc"], "window_end_utc": first["window_end_utc"],
                        "raw_count": None, "status": "error", "error_type": type(exc).__name__,
                        "http_status": getattr(exc, "response_status_code", None),
                        "raw_response_path": str(raw_path.relative_to(output)) if raw_path.exists() else None,
                        "reserved_credits": RESERVATION_PER_CALL, "estimated_credits": RESERVATION_PER_CALL,
                        "stop_reason": "request_error_fail_closed"})
                estimated += RESERVATION_PER_CALL
                stop_reason = "request_error_fail_closed"
                break
        if window_complete:
            complete_windows += 1
            processed.add(query_id)
        if stop_reason:
            break

    first_rows = _load_jsonl(source / "requests.jsonl")
    first_raw = sum(row["raw_count"] for row in first_rows)
    first_ids: list[str] = []
    for row in first_rows:
        raw = json.loads((source / row["raw_response_path"]).read_bytes())
        first_ids.extend(filter(None, (_tweet_id(item) for item in _items(raw))))
    new_hits = _load_jsonl(hits_path)
    all_ids = first_ids + [row["tweet_id"] for row in new_hits if row.get("tweet_id")]
    definitive = complete_windows == expected_windows and stop_reason is None
    summary = {"status": "definitive_provider_exhaustion" if definitive else "incomplete",
               "expected_windows": expected_windows, "complete_windows": complete_windows,
               "followup_windows_completed": len(processed), "physical_followup_calls": calls,
               "committed_or_reserved_credits": committed, "estimated_credits": estimated,
               "credit_budget": credit_budget, "max_calls": max_calls,
               "first_page_raw_slots": first_raw, "followup_raw_slots": followup_raw,
               "combined_raw_slots": first_raw + followup_raw,
               "combined_unique_tweet_ids": len(set(all_ids)),
               "combined_duplicate_identified_slots": len(all_ids) - len(set(all_ids)),
               "followup_duplicate_slots": duplicates, "stop_reason": stop_reason,
               "first_pages_rebought": 0,
               "resume_policy": "fail_closed_no_automatic_resume; reconcile dispatches.jsonl against requests.jsonl"}
    _write_json(output / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--credit-budget", type=int, default=DEFAULT_CREDIT_BUDGET)
    args = parser.parse_args(argv)
    client = TwitterApiClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    client.max_retries = 0
    summary = run_followup(args.input_dir, args.output_dir, client,
                           max_calls=args.max_calls, credit_budget=args.credit_budget)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "definitive_provider_exhaustion" else 2


if __name__ == "__main__":
    raise SystemExit(main())

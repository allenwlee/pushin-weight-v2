"""On-demand TwitterAPI.io trial of the rare-type extra-search exhibit.

Uses TWITTERAPI_IO_ON_DEMAND_API_KEY only. Does not insert posts.
Does not enable extra search on run_cycle.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, NoReturn

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from x_monitor.apify import (
    SEARCH_PATH,
    TwitterApiAuthError,
    TwitterApiClient,
    TwitterApiRateLimitError,
    TwitterApiServerError,
)
from x_monitor.rare_type_extra_search import (
    QUERY_VERSION,
    planned_query_string,
    render_rare_type_extra_search_query,
)
from x_monitor.twitterapi_credentials import (
    TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV,
    TwitterApiCredentialPurpose,
)

_WINDOWS = {
    "15m": timedelta(minutes=15),
    "7d": timedelta(days=7),
}
_MAX_RESULTS = 20
_MAX_PAGES = 1
_RESERVED_CREDITS = 300
_CREDITS_PER_RESULT = 15

_SAFE_TWEET_FIELDS = (
    "id",
    "created_at",
    "author_handle",
    "author_name",
    "lang",
    "text",
    "quoted_text",
    "quoted_author_handle",
    "tweet_url",
    "tweet_twitter_url",
)


class Command(BaseCommand):
    help = (
        "Run the combined rare-type extra-search exhibit against TwitterAPI.io "
        "with the on-demand key. Does not write posts."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--window",
            choices=sorted(_WINDOWS),
            default="15m",
            help="Lookback window for since_time (default 15m).",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            choices=(1,),
            default=1,
            help="Safety cap: this bounded trial is limited to one page.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print a JSON object instead of a table.",
        )
        parser.add_argument(
            "--preview",
            action="store_true",
            help="Render evidence without credentials, provider calls, or DB access.",
        )
        parser.add_argument(
            "--volume-windows",
            type=Path,
            help="JSON array of prespecified exact UTC 15-minute windows.",
        )
        parser.add_argument(
            "--output-dir",
            type=Path,
            help="Durable destination for volume-probe receipts.",
        )
        parser.add_argument("--max-calls", type=int, help="Physical HTTP call ceiling.")
        parser.add_argument(
            "--credit-budget", type=int, help="Reserved TwitterAPI credit ceiling."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options.get("volume_windows") is not None:
            self._handle_volume_probe(options)
            return
        window = options.get("window", "15m")
        max_pages = options.get("max_pages", _MAX_PAGES)
        if window not in _WINDOWS:
            raise CommandError(f"window must be one of: {', '.join(sorted(_WINDOWS))}")
        if isinstance(max_pages, bool) or max_pages != _MAX_PAGES:
            raise CommandError("--max-pages must be exactly 1")

        now = datetime.now(UTC)
        until_time = int(now.timestamp())
        since_time = int((now - _WINDOWS[window]).timestamp())
        query_string = planned_query_string()
        try:
            query = render_rare_type_extra_search_query(
                since_time=since_time,
                until_time=until_time,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        request_kwargs = {
            "max_results": _MAX_RESULTS,
            "max_pages": _MAX_PAGES,
            "max_per_page": _MAX_RESULTS,
            "since_time": since_time,
            "until_time": until_time,
        }
        payload: dict[str, Any] = {
            "mode": "preview" if options.get("preview", False) else "trial",
            "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND.value,
            "window": window,
            "since_time": since_time,
            "until_time": until_time,
            "query_version": QUERY_VERSION,
            "planner_query": query_string,
            "planner_query_sha256": hashlib.sha256(
                query_string.encode("utf-8")
            ).hexdigest(),
            "rendered_query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "query": query,
            "query_length": len(query),
            "request_kwargs": request_kwargs,
        }
        if options.get("preview", False):
            self._write_payload(payload, as_json=bool(options.get("json", False)))
            return

        try:
            client = TwitterApiClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
        except RuntimeError as exc:
            raise CommandError(
                f"{exc}. Set {TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV}."
            ) from exc

        # This explicit trial gets one physical HTTP attempt. Ordinary clients
        # retain their default retry policy.
        client.max_retries = 0

        # Same injection path as CycleRunner._fetch_tweets: planner string
        # plus since_time/until_time kwargs (not a pre-baked query).
        try:
            tweets, truncated = client.run_search(query_string, **request_kwargs)
        except TwitterApiAuthError as exc:
            self._fail_paid_attempt(payload, "auth_failed", exc)
        except TwitterApiRateLimitError as exc:
            self._fail_paid_attempt(payload, "rate_limited", exc)
        except TwitterApiServerError as exc:
            self._fail_paid_attempt(payload, "server_error", exc)
        except requests.RequestException as exc:
            self._fail_paid_attempt(payload, "transport_error", exc)
        except json.JSONDecodeError as exc:
            self._fail_paid_attempt(payload, "invalid_provider_response", exc)
        except RuntimeError as exc:
            self._fail_paid_attempt(payload, "provider_error", exc)

        known: set[str] = set()
        overlap_available = True
        tweet_ids = [str(t.get("id") or "") for t in tweets if t.get("id")]
        if tweet_ids:
            try:
                from core.models import Post

                known = set(
                    Post.objects.filter(tweet_id__in=tweet_ids).values_list(
                        "tweet_id", flat=True
                    )
                )
            except DatabaseError:
                # Database exception text can contain a DSN; evidence records
                # only the categorical unavailable state.
                overlap_available = False

        rows = []
        for tweet in tweets:
            tid = str(tweet.get("id") or "")
            row = {field: tweet.get(field) for field in _SAFE_TWEET_FIELDS}
            row["id"] = tid
            row["already_in_db"] = (tid in known) if overlap_available else None
            rows.append(row)

        raw_paid_count = self._raw_paid_result_count(client)
        credits = self._credit_evidence(raw_paid_count)
        payload.update(
            {
                "truncated": truncated,
                "raw_paid_result_count": raw_paid_count,
                "normalized_result_count": len(rows),
                "db_overlap": {
                    "status": "known" if overlap_available else "unavailable",
                    "count": (
                        sum(1 for row in rows if row["already_in_db"])
                        if overlap_available
                        else None
                    ),
                },
                "credits": credits,
                "tweets": rows,
            }
        )
        self._write_payload(payload, as_json=bool(options.get("json", False)))

    def _handle_volume_probe(self, options: dict[str, Any]) -> None:
        source = options["volume_windows"]
        output_dir = options.get("output_dir")
        max_calls = options.get("max_calls")
        credit_budget = options.get("credit_budget")
        if output_dir is None:
            raise CommandError("--output-dir is required with --volume-windows")
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 1:
            raise CommandError("--max-calls must be a positive physical-call ceiling")
        if (
            isinstance(credit_budget, bool)
            or not isinstance(credit_budget, int)
            or credit_budget < 1
        ):
            raise CommandError("--credit-budget must be a positive credit ceiling")
        windows = self._load_volume_windows(source)
        try:
            rendered_queries = [
                render_rare_type_extra_search_query(
                    since_time=window["since_time"], until_time=window["until_time"]
                )
                for window in windows
            ]
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        planned_calls = len(windows)
        reserved_credits = planned_calls * _RESERVED_CREDITS
        if planned_calls > max_calls:
            raise CommandError(
                f"planned windows exceed physical-call ceiling ({planned_calls} > {max_calls})"
            )
        if reserved_credits > credit_budget:
            raise CommandError(
                "300-credit/page reservation exceeds credit budget "
                f"({reserved_credits} > {credit_budget})"
            )

        preview = {
            "mode": "volume_preview" if options.get("preview") else "volume_probe",
            "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND.value,
            "planned_physical_calls": planned_calls,
            "physical_call_ceiling": max_calls,
            "reserved_credits": reserved_credits,
            "credit_budget": credit_budget,
            "query_version": QUERY_VERSION,
            "planner_query": planned_query_string(),
            "planner_query_sha256": hashlib.sha256(
                planned_query_string().encode("utf-8")
            ).hexdigest(),
            "windows": windows,
        }
        if options.get("preview"):
            self._write_payload(preview, as_json=bool(options.get("json")))
            return
        if output_dir.exists():
            raise CommandError("--output-dir must not already exist")

        try:
            client = TwitterApiClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
        except RuntimeError as exc:
            raise CommandError(
                f"{exc}. Set {TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV}."
            ) from exc
        client.max_retries = 0
        output_dir.mkdir(parents=True)
        raw_dir = output_dir / "raw"
        raw_dir.mkdir()
        requests_path = output_dir / "requests.jsonl"
        hits_path = output_dir / "hits.jsonl"
        requests_path.touch()
        hits_path.touch()

        request_rows: list[dict[str, Any]] = []
        hit_rows: list[dict[str, Any]] = []
        query_string = planned_query_string()
        for index, (window, rendered_query) in enumerate(
            zip(windows, rendered_queries, strict=True), start=1
        ):
            request_id = f"request-{index:04d}"
            since_time = window["since_time"]
            until_time = window["until_time"]
            arguments = {
                "max_results": _MAX_RESULTS,
                "max_pages": 1,
                "max_per_page": _MAX_RESULTS,
                "since_time": since_time,
                "until_time": until_time,
            }
            issued_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            raw_path = raw_dir / f"{request_id}.json"
            try:
                _, raw, normalized, continuation, normalization_errors = client.run_search_page_with_raw(
                    query_string,
                    **arguments,
                    receipt_sink=lambda body, path=raw_path: self._write_bytes_durable(
                        path, body
                    ),
                )
                raw_items = raw.get("tweets") or raw.get("data") or []
                raw_count = len(raw_items) if isinstance(raw_items, list) else None
                actual_credits = self._actual_credits(raw)
                if raw_count is not None and raw_count > _MAX_RESULTS:
                    stop_reason = "reservation_undermined_raw_slots_over_20"
                elif actual_credits is not None and actual_credits > _RESERVED_CREDITS:
                    stop_reason = "reservation_undermined_actual_credits_over_300"
                else:
                    stop_reason = "one_page_cap" if continuation else "page_complete"
                row = {
                    "request_id": request_id,
                    "query_id": f"{QUERY_VERSION}:{window['start_utc']}/{window['end_utc']}",
                    "query_version": QUERY_VERSION,
                    "query_sha256": hashlib.sha256(rendered_query.encode("utf-8")).hexdigest(),
                    "provider": "twitterapi.io",
                    "tool_or_endpoint": SEARCH_PATH,
                    "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND.value,
                    "issued_at_utc": issued_at,
                    "arguments": arguments,
                    "run_search_kwargs": arguments,
                    "http_arguments": {
                        "query": rendered_query,
                        "queryType": "Latest",
                        "limit": _MAX_RESULTS,
                    },
                    "rendered_query": rendered_query,
                    "window_start_utc": window["start_utc"],
                    "window_end_utc": window["end_utc"],
                    "requested_limit": _MAX_RESULTS,
                    "raw_count": raw_count,
                    "normalized_count": len(normalized),
                    "status": (
                        "success_with_normalization_errors"
                        if normalization_errors
                        else "success"
                    ),
                    "normalization_error_count": normalization_errors,
                    "raw_response_path": str(raw_path.relative_to(output_dir)),
                    "capture_format": "exact_provider_response_bytes_json",
                    "continuation": continuation,
                    "coverage": (
                        "capped_or_unfinished_lower_bound"
                        if continuation or raw_count == _MAX_RESULTS
                        else "provider_exhausted_within_window"
                    ),
                    "stop_reason": stop_reason,
                    "reserved_credits": _RESERVED_CREDITS,
                    "estimated_credits": (
                        max(_CREDITS_PER_RESULT, raw_count * _CREDITS_PER_RESULT)
                        if raw_count is not None
                        else _RESERVED_CREDITS
                    ),
                    "actual_credits": actual_credits,
                }
                self._append_jsonl_durable(requests_path, row)
                request_rows.append(row)
                for response_index, item in enumerate(raw_items if isinstance(raw_items, list) else []):
                    hit = self._raw_hit_row(request_id, response_index, item)
                    self._append_jsonl_durable(hits_path, hit)
                    hit_rows.append(hit)
                if stop_reason.startswith("reservation_undermined_"):
                    break
            except (TwitterApiAuthError, TwitterApiRateLimitError, TwitterApiServerError,
                    requests.RequestException, json.JSONDecodeError, RuntimeError,
                    TypeError, ValueError) as exc:
                captured = raw_path.exists()
                raw_count = self._raw_count_from_receipt(raw_path) if captured else None
                stop_reason = (
                    "reservation_undermined_raw_slots_over_20"
                    if raw_count is not None and raw_count > _MAX_RESULTS
                    else "request_error"
                )
                error_row = {
                    "request_id": request_id,
                    "query_id": f"{QUERY_VERSION}:{window['start_utc']}/{window['end_utc']}",
                    "query_version": QUERY_VERSION,
                    "query_sha256": hashlib.sha256(rendered_query.encode("utf-8")).hexdigest(),
                    "provider": "twitterapi.io",
                    "tool_or_endpoint": SEARCH_PATH,
                    "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND.value,
                    "issued_at_utc": issued_at,
                    "arguments": arguments,
                    "run_search_kwargs": arguments,
                    "http_arguments": {
                        "query": rendered_query,
                        "queryType": "Latest",
                        "limit": _MAX_RESULTS,
                    },
                    "rendered_query": rendered_query,
                    "window_start_utc": window["start_utc"],
                    "window_end_utc": window["end_utc"],
                    "requested_limit": _MAX_RESULTS,
                    "raw_count": raw_count,
                    "normalized_count": None,
                    "status": "error",
                    "normalization_error_count": None,
                    "error_type": type(exc).__name__,
                    "raw_response_path": str(raw_path.relative_to(output_dir)) if captured else None,
                    "capture_format": "exact_provider_response_bytes_json" if captured else None,
                    "http_status": getattr(exc, "response_status_code", None),
                    "continuation": None,
                    "coverage": "failed_unknown",
                    "stop_reason": stop_reason,
                    "reserved_credits": _RESERVED_CREDITS,
                    "estimated_credits": _RESERVED_CREDITS,
                    "actual_credits": None,
                }
                self._append_jsonl_durable(requests_path, error_row)
                request_rows.append(error_row)
                for response_index, item in enumerate(
                    self._raw_items_from_receipt(raw_path) if captured else []
                ):
                    hit = self._raw_hit_row(request_id, response_index, item)
                    self._append_jsonl_durable(hits_path, hit)
                    hit_rows.append(hit)
                break

        self._write_text_durable(
            output_dir / "report.md",
            self._volume_report(preview, request_rows, hit_rows),
        )

    @staticmethod
    def _parse_utc(value: Any, field: str) -> datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise CommandError(f"{field} must be an exact UTC timestamp ending in Z")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise CommandError(f"invalid {field}") from exc
        if parsed.microsecond:
            raise CommandError(f"{field} must use whole seconds")
        return parsed

    def _load_volume_windows(self, source: Path) -> list[dict[str, Any]]:
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError("unable to read --volume-windows JSON") from exc
        if not isinstance(raw, list) or not raw:
            raise CommandError("--volume-windows must contain a nonempty JSON array")
        windows = []
        now = datetime.now(UTC)
        for item in raw:
            if not isinstance(item, dict):
                raise CommandError("each volume window must be an object")
            start = self._parse_utc(item.get("start"), "start")
            end = self._parse_utc(item.get("end"), "end")
            if end - start != timedelta(minutes=15):
                raise CommandError("every volume window must be exactly 15-minute")
            windows.append({
                "start_utc": start.isoformat().replace("+00:00", "Z"),
                "end_utc": end.isoformat().replace("+00:00", "Z"),
                "since_time": int(start.timestamp()),
                "until_time": int(end.timestamp()),
                "duration_seconds": 900,
                "_start": start,
                "_end": end,
            })
        ordered = sorted(windows, key=lambda item: item["_start"])
        for previous, current in pairwise(ordered):
            if current["_start"] < previous["_end"]:
                raise CommandError("volume windows must not overlap")
        for window in windows:
            if (
                window["_start"].second
                or window["_end"].second
                or window["_start"].minute % 15
                or window["_end"].minute % 15
            ):
                raise CommandError(
                    "volume windows must align to whole-second UTC quarter-hours"
                )
            if window["_end"] > now:
                raise CommandError("volume windows must be completed, not future")
        for window in windows:
            window.pop("_start")
            window.pop("_end")
        return windows

    @staticmethod
    def _raw_count_from_receipt(path: Path) -> int | None:
        items = Command._raw_items_from_receipt(path)
        return len(items) if items is not None else None

    @staticmethod
    def _raw_items_from_receipt(path: Path) -> list[Any] | None:
        try:
            value = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        items = value.get("tweets") or value.get("data") or []
        return items if isinstance(items, list) else None

    @staticmethod
    def _write_bytes_durable(path: Path, value: bytes) -> None:
        with path.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _append_jsonl_durable(path: Path, value: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _write_text_durable(path: Path, value: str) -> None:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _raw_hit_row(request_id: str, index: int, item: Any) -> dict[str, Any]:
        issues = []
        if not isinstance(item, dict):
            return {"request_id": request_id, "response_index": index, "tweet_id": None,
                    "created_at_utc": None, "author_handle": None, "text": None,
                    "source_url": None, "record_issues": ["non_object_slot"]}
        tweet_id = item.get("id") or item.get("id_str")
        if not tweet_id:
            issues.append("missing_tweet_id")
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        text = item.get("text")
        if text is None:
            issues.append("missing_text")
        return {
            "request_id": request_id,
            "response_index": index,
            "tweet_id": str(tweet_id) if tweet_id else None,
            "created_at_utc": item.get("createdAt") or item.get("created_at"),
            "author_handle": item.get("author_handle") or author.get("userName") or author.get("username"),
            "text": text,
            "source_url": item.get("tweet_url") or item.get("url"),
            "record_issues": issues,
        }

    @staticmethod
    def _actual_credits(raw: dict[str, Any]) -> int | None:
        usage = raw.get("usage")
        if isinstance(usage, dict):
            value = usage.get("credits")
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None

    @staticmethod
    def _volume_report(preview, requests_rows, hit_rows) -> str:
        raw_known = [row["raw_count"] for row in requests_rows if row["raw_count"] is not None]
        normalized_known = [
            row["normalized_count"]
            for row in requests_rows
            if row["normalized_count"] is not None
        ]
        ids = [row["tweet_id"] for row in hit_rows if row["tweet_id"]]
        unknown_ids = sum(row["tweet_id"] is None for row in hit_rows)
        capped = sum(row.get("coverage") == "capped_or_unfinished_lower_bound" for row in requests_rows)
        errors = sum(row["status"] == "error" for row in requests_rows)
        zeros = sum(value == 0 for value in raw_known)
        sorted_counts = sorted(raw_known)
        upper_index = max(0, int(0.95 * len(sorted_counts) + 0.999999) - 1)
        upper_tail = sorted_counts[upper_index] if sorted_counts else "unknown"
        estimated_credits = sum(row["estimated_credits"] for row in requests_rows)
        actual_values = [row["actual_credits"] for row in requests_rows]
        actual_credits = (
            sum(actual_values) if actual_values and all(value is not None for value in actual_values)
            else "unavailable"
        )
        creation_counts: dict[str, int] = {}
        unknown_creation = 0
        for hit in hit_rows:
            created = hit.get("created_at_utc")
            if isinstance(created, str) and len(created) >= 13:
                hour = created[:13] + ":00Z"
                creation_counts[hour] = creation_counts.get(hour, 0) + 1
            else:
                unknown_creation += 1
        creation_lines = [
            f"  - `{hour}`: {count}" for hour, count in sorted(creation_counts.items())
        ] or ["  - No known creation timestamps"]
        successful = [row for row in requests_rows if row["status"] != "error"]
        weekday = [row for row in successful if datetime.fromisoformat(row["window_start_utc"]).weekday() < 5]
        weekend = [row for row in successful if datetime.fromisoformat(row["window_start_utc"]).weekday() >= 5]
        attempted_starts = {row["window_start_utc"] for row in requests_rows}
        missing_windows = [
            window for window in preview["windows"]
            if window["start_utc"] not in attempted_starts
        ]
        planned_by_day: dict[date, list[dict[str, Any]]] = {}
        for window in preview["windows"]:
            start = datetime.fromisoformat(window["start_utc"])
            planned_by_day.setdefault(start.date(), []).append(window)

        def is_complete_utc_day(windows: list[dict[str, Any]]) -> bool:
            ordered = sorted(windows, key=lambda window: window["start_utc"])
            first = datetime.fromisoformat(ordered[0]["start_utc"])
            last = datetime.fromisoformat(ordered[-1]["end_utc"])
            return (
                len(ordered) == 96
                and first.hour == 0
                and first.minute == 0
                and last - first == timedelta(days=1)
                and all(
                    datetime.fromisoformat(window["start_utc"])
                    == first + timedelta(minutes=15 * index)
                    for index, window in enumerate(ordered)
                )
            )

        complete_days = len(planned_by_day) in {1, 2} and all(
            is_complete_utc_day(windows) for windows in planned_by_day.values()
        )
        complete_sample = complete_days and not errors and not missing_windows
        if complete_sample and len(planned_by_day) == 1:
            completion = "complete 96-window UTC day"
        elif complete_sample:
            completion = "complete 2-day sample (192 successful planned windows)"
        elif errors and not missing_windows:
            completion = (
                f"incomplete ({len(successful)} successful of "
                f"{len(preview['windows'])} planned windows)"
            )
        else:
            completion = (
                f"incomplete ({len(requests_rows)} of "
                f"{len(preview['windows'])} planned windows attempted)"
            )
        known_error_counts = sum(
            row["status"] == "error" and row["raw_count"] is not None
            for row in requests_rows
        )
        unknown_error_counts = errors - known_error_counts
        provider_exhaustive = complete_sample and not capped and all(
            row.get("coverage") == "provider_exhausted_within_window"
            for row in requests_rows
        )
        hits_by_request: dict[str, int] = {}
        for hit in hit_rows:
            request_id = hit["request_id"]
            hits_by_request[request_id] = hits_by_request.get(request_id, 0) + 1

        def sampled_hour_rate(rows):
            counts = [row["raw_count"] * 4 for row in rows if row["raw_count"] is not None]
            return statistics.mean(counts) if counts else "unknown"

        coverage = (
            f"{min(row['start_utc'] for row in preview['windows'])} to "
            f"{max(row['end_utc'] for row in preview['windows'])}"
            if preview["windows"] else "none"
        )
        return "\n".join([
            "# Rare-type extra-search volume probe", "",
            f"- Query version: `{preview['query_version']}`",
            f"- Query SHA-256: `{preview['planner_query_sha256']}`",
            f"- Credential purpose: `{preview['credential_purpose']}`",
            f"- Planned/used physical calls: {preview['planned_physical_calls']}/{len(requests_rows)}",
            f"- Completion: {completion}",
            f"- UTC coverage (planned): `{coverage}`",
            f"- Reserved credits: {preview['reserved_credits']}",
            f"- Estimated credits: {estimated_credits}",
            f"- Provider-confirmed credits: {actual_credits}",
            f"- Raw top-level slots: {sum(raw_known)}",
            f"- Normalized rows: {sum(normalized_known)}",
            f"- Unique nonempty tweet IDs: {len(set(ids))}",
            f"- Duplicate identified slots: {len(ids) - len(set(ids))}",
            f"- Unknown-ID slots: {unknown_ids}",
            f"- Capped/unfinished windows: {capped}",
            f"- Error windows: {errors} (known raw count: {known_error_counts}; unknown raw count: {unknown_error_counts})",
            f"- Successful zero-result windows: {zeros}",
            f"- Median raw slots per known window: {statistics.median(raw_known) if raw_known else 'unknown'}",
            f"- P95 raw slots per known window: {upper_tail}",
            f"- Sampled raw posts/hour (successful windows only): {sampled_hour_rate(successful)}",
            f"- Weekday sampled windows: {len(weekday)}; sampled raw posts/hour: {sampled_hour_rate(weekday)}",
            f"- Weekend sampled windows: {len(weekend)}; sampled raw posts/hour: {sampled_hour_rate(weekend)}",
            "- Missing/unattempted windows: " + (
                ", ".join(
                    f"`{window['start_utc']}` to `{window['end_utc']}`"
                    for window in missing_windows
                )
                if missing_windows else "none"
            ),
            "- Comparison: 20 posts/hour = 5 per 15m; 50 posts/hour = 12.5 per 15m",
            "", "## Creation-time distribution (UTC hour)", "",
            *creation_lines,
            f"  - Unknown creation time: {unknown_creation}",
            "", "## Per-window status", "",
            *[
                f"- `{row['window_start_utc']}` to `{row['window_end_utc']}`: "
                f"status={row['status']}, raw={row['raw_count']}, "
                f"hits={hits_by_request.get(row['request_id'], 0)}, "
                f"normalized={row['normalized_count']}, coverage={row['coverage']}"
                for row in requests_rows
            ],
            "", "Full pages and continuation are lower bounds, not complete volume.",
            *(
                ["Provider coverage: exhaustive for every planned window."]
                if provider_exhaustive
                else []
            ),
            (
                f"All {len(preview['windows'])} prespecified UTC quarter-hour windows "
                "completed successfully."
                if complete_sample
                else "This is an incomplete prespecified sample, not a complete-period sample."
            ),
            (
                "Error receipts with known raw counts are included in raw-slot totals; "
                "errors without known raw counts are not counted as zero."
            ), ""
        ])

    def _fail_paid_attempt(
        self,
        payload: dict[str, Any],
        error_code: str,
        cause: Exception,
    ) -> NoReturn:
        payload.update(
            {
                "status": "failed",
                "error_code": error_code,
                "provider_request_attempts": 1,
                "raw_paid_result_count": None,
                "normalized_result_count": None,
                "db_overlap": {"status": "unavailable", "count": None},
                "credits": self._credit_evidence(None),
                "tweets": [],
            }
        )
        self._write_payload(payload, as_json=True)
        safe_messages = {
            "auth_failed": "TwitterAPI.io auth failed",
            "rate_limited": "TwitterAPI.io rate limit",
            "server_error": "TwitterAPI.io 5xx response",
            "transport_error": "TwitterAPI.io request failed",
            "invalid_provider_response": "TwitterAPI.io invalid response",
            "provider_error": "TwitterAPI.io request failed",
        }
        raise CommandError(safe_messages[error_code]) from cause

    def _write_payload(self, payload: dict[str, Any], *, as_json: bool) -> None:
        if as_json:
            self.stdout.write(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            )
            return
        self.stdout.write(
            f"purpose={payload['credential_purpose']} window={payload['window']} "
            f"mode={payload['mode']} query_version={payload['query_version']} "
            f"query_len={payload['query_length']}"
        )
        for row in payload.get("tweets", []):
            state = row["already_in_db"]
            flag = "unknown" if state is None else ("dup" if state else "new")
            self.stdout.write(
                f"{flag} {row['id']} @{row['author_handle']} {row['text']!r}"
            )

    @staticmethod
    def _raw_paid_result_count(client: TwitterApiClient) -> int | None:
        logs = getattr(client, "_request_log", None)
        if not isinstance(logs, list):
            return None
        matching = [
            entry
            for entry in logs
            if isinstance(entry, dict) and entry.get("path") == SEARCH_PATH
        ]
        if len(matching) != 1:
            return None
        value = matching[0].get("n_results")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    @staticmethod
    def _credit_evidence(raw_paid_count: int | None) -> dict[str, Any]:
        if raw_paid_count is None:
            return {
                "reserved": _RESERVED_CREDITS,
                "estimated": _RESERVED_CREDITS,
                "confirmed": None,
                "basis": "provider_usage_unavailable",
            }
        return {
            "reserved": _RESERVED_CREDITS,
            "estimated": max(_CREDITS_PER_RESULT, raw_paid_count * _CREDITS_PER_RESULT),
            "confirmed": None,
            "basis": (
                "provider_raw_empty_floor"
                if raw_paid_count == 0
                else "provider_raw_result_count"
            ),
        }

"""On-demand TwitterAPI.io trial of the rare-type extra-search exhibit.

Uses TWITTERAPI_IO_ON_DEMAND_API_KEY only. Does not insert posts.
Does not enable extra search on run_cycle.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
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

    def handle(self, *args: Any, **options: Any) -> None:
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

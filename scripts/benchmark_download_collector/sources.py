"""Small, bounded readers for the three fixed public-data sources."""

from __future__ import annotations

import hashlib
import json
import math
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx

from core.hf_metadata_client import HFMetadataClient

from .identity import count, day, days, require, timestamp

ARENA_URL = "https://datasets-server.huggingface.co/filter"
ARENA_DATASET = "lmarena-ai/leaderboard-dataset"
ARENA_CONFIG = "text"
ARENA_CONTRACT = "arena-overall-text-v1"
ARENA_LATEST = "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/resolve/main/text/latest-00000-of-00001.parquet"
OPENROUTER_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily"
SOURCE_URLS = {
    "arena": "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
    "hf": "https://huggingface.co/docs/hub/models-download-stats",
    "openrouter": "https://openrouter.ai/rankings",
}


class SourceError(ValueError):
    """Only fixed, non-secret error codes cross the collection boundary."""


class Budget:
    def __init__(
        self,
        client,
        *,
        max_requests=80,
        max_seconds=180,
        max_bytes=4 * 1024 * 1024,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        require(
            type(max_requests) is int and max_requests > 0,
            "max_requests must be positive",
        )
        require(
            math.isfinite(max_seconds) and max_seconds > 0,
            "max_seconds must be positive",
        )
        require(type(max_bytes) is int and max_bytes > 0, "max_bytes must be positive")
        self.client, self.clock, self.sleep = client, clock, sleep
        self.remaining = max_requests
        self.deadline = clock() + max_seconds
        self.max_bytes = max_bytes

    def check(self):
        if self.remaining <= 0:
            raise SourceError("request_cap")
        if self.clock() >= self.deadline:
            raise SourceError("time_cap")

    def get(self, url, params, *, key=None, asset=False):
        if asset:
            parsed = urlsplit(url)
            require(
                parsed.scheme == "https"
                and not parsed.username
                and parsed.port in (None, 443)
                and (
                    parsed.hostname == "huggingface.co"
                    or (parsed.hostname or "").endswith(".hf.co")
                ),
                "untrusted_arena_asset_redirect",
            )
        else:
            require(url in {ARENA_URL, OPENROUTER_URL}, "unsupported source URL")
        require(not key or url == OPENROUTER_URL, "credential host mismatch")
        require(not asset or not key, "asset_credentials_forbidden")
        for attempt in range(3):
            self.check()
            self.remaining -= 1
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            try:
                # Build independently: do not inherit client cookies/default credentials.
                request = httpx.Request(
                    "GET",
                    url,
                    params=None if asset else params,
                    headers=headers,
                    extensions={
                        "timeout": httpx.Timeout(
                            min(20, self.deadline - self.clock())
                        ).as_dict()
                    },
                )
                with closing(
                    self.client.send(
                        request, stream=True, auth=None, follow_redirects=False
                    )
                ) as response:
                    if asset and response.is_redirect:
                        return {"redirect": response.headers.get("location", "")}
                    if response.status_code != 200:
                        code = f"http_{response.status_code}"
                        retry = (
                            response.status_code == 429 or response.status_code >= 500
                        )
                        delay = HFMetadataClient._retry_delay(
                            response.headers.get("retry-after"), 2**attempt
                        )
                    else:
                        content = bytearray()
                        for chunk in response.iter_bytes(chunk_size=65536):
                            content.extend(chunk)
                            if len(content) > self.max_bytes:
                                raise SourceError("response_size_cap")
                            if self.clock() >= self.deadline:
                                raise SourceError("time_cap")
                        if asset:
                            return bytes(content)
                        try:
                            payload = json.loads(content)
                        except (ValueError, UnicodeDecodeError) as exc:
                            raise SourceError("malformed_json") from exc
                        if not isinstance(payload, dict):
                            raise SourceError("malformed_payload")
                        return payload
            except httpx.HTTPError:
                code, retry, delay = "request_error", True, 2**attempt
            if not retry or attempt == 2:
                raise SourceError(code)
            if self.clock() + delay >= self.deadline or self.remaining <= 0:
                raise SourceError(code)
            self.sleep(delay)
        raise SourceError("request_error")

    def arena_asset(self, config=ARENA_CONFIG, split="latest"):
        require(
            config in {"text", "text_style_control"} and split in {"latest", "full"},
            "unsupported Arena configuration",
        )
        url = f"https://huggingface.co/datasets/{ARENA_DATASET}/resolve/main/{config}/{split}-00000-of-00001.parquet"
        for _ in range(4):
            value = self.get(url, {}, asset=True)
            if isinstance(value, bytes):
                return value
            url = value["redirect"]
        raise SourceError("arena_redirect_cap")

    def hf_counts(self, repo_id, account_kind=None):
        self.check()
        client = HFMetadataClient(
            self.client,
            max_requests=self.remaining,
            max_seconds=self.deadline - self.clock(),
            max_bytes=self.max_bytes,
            clock=self.clock,
            sleep=self.sleep,
        )
        result = (
            client.account_counts(repo_id, account_kind)
            if account_kind
            else client.download_counts(repo_id)
        )
        self.remaining -= len(result.attempts)
        if result.outcome != "ok":
            raise SourceError(result.outcome)
        count(result.payload.get("numFollowers" if account_kind else "downloads"))
        all_time = result.payload.get("downloadsAllTime")
        if all_time is not None:
            count(all_time)
        return result.payload


def validate_arena_row(row, start_date, end_date):
    require(isinstance(row, dict), "arena_invalid_row")
    model, published = row.get("model_name"), row.get("leaderboard_publish_date")
    require(isinstance(model, str) and 0 < len(model) <= 256, "arena_invalid_model")
    require(
        row.get("category") == "overall"
        and day(start_date) <= day(published) <= day(end_date),
        "arena_scope_mismatch",
    )
    for field in ("rating", "rating_lower", "rating_upper"):
        value = row.get(field)
        require(
            type(value) in (int, float) and math.isfinite(value), "arena_invalid_rating"
        )
    require(
        row["rating_lower"] <= row["rating"] <= row["rating_upper"],
        "arena_invalid_interval",
    )
    votes = row.get("vote_count")
    require(
        type(votes) in (int, float)
        and math.isfinite(votes)
        and votes >= 0
        and int(votes) == votes,
        "arena_invalid_votes",
    )
    return published, model


def arena_latest(budget, *, config=ARENA_CONFIG):
    """The official latest artifact avoids the Dataset Viewer's cold search index."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SourceError("install_benchmark_extra_for_arena") from exc
    content = budget.arena_asset(config=config)
    try:
        parquet = pq.ParquetFile(
            pa.BufferReader(content),
            arrow_extensions_enabled=False,
            thrift_string_size_limit=1024 * 1024,
            thrift_container_size_limit=100000,
        )
        require(parquet.metadata.num_rows <= 50000, "arena_row_cap")
        require(
            sum(
                parquet.metadata.row_group(i).total_byte_size
                for i in range(parquet.metadata.num_row_groups)
            )
            <= 32 * 1024 * 1024,
            "arena_decoded_size_cap",
        )
        fields = {
            "model_name",
            "category",
            "leaderboard_publish_date",
            "rating",
            "rating_lower",
            "rating_upper",
            "vote_count",
        }
        require(fields <= set(parquet.schema.names), "arena_schema_changed")
        rows = [r for r in parquet.read().to_pylist() if r["category"] == "overall"]
    except pa.ArrowException as exc:
        raise SourceError("arena_invalid_parquet") from exc
    require(bool(rows), "arena_missing_overall")
    seen = set()
    for row in rows:
        identity = validate_arena_row(
            row, "2024-01-01", datetime.now(UTC).date().isoformat()
        )
        require(identity not in seen, "arena_duplicate_model")
        seen.add(identity)
    require(
        len({r["leaderboard_publish_date"] for r in rows}) == 1,
        "arena_latest_has_multiple_publications",
    )
    published = rows[0]["leaderboard_publish_date"]
    return {
        "status": "ok",
        "rows": rows,
        "config": config,
        "score_contract": f"arena-overall-{config}-v1",
        "as_of": published,
        "coverage": "latest_publication_only",
        "artifact_url": f"https://huggingface.co/datasets/{ARENA_DATASET}/resolve/main/{config}/latest-00000-of-00001.parquet",
        "artifact_sha256": hashlib.sha256(content).hexdigest(),
        "start_date": published,
        "end_date": published,
    }


def arena(
    budget, start_date, end_date, *, max_pages=50, history=False, config=ARENA_CONFIG
):
    """Read complete publications, including at most 30 days of carry-in history."""
    require(type(max_pages) is int and max_pages > 0, "max_pages must be positive")
    days(start_date, end_date)
    require(config in {"text", "text_style_control"}, "unsupported Arena configuration")
    if not history:
        return arena_latest(budget, config=config)
    start = (day(start_date) - timedelta(days=30)).isoformat()
    where = f"\"category\"='overall' AND \"leaderboard_publish_date\">='{start}' AND \"leaderboard_publish_date\"<='{end_date}'"
    rows, total, revision = [], None, None
    seen = set()
    for page in range(max_pages):
        payload = budget.get(
            ARENA_URL,
            {
                "dataset": ARENA_DATASET,
                "config": config,
                "split": "full",
                "where": where,
                "offset": len(rows),
                "length": 100,
            },
        )
        current_total = count(payload.get("num_rows_total"))
        current_revision = payload.get("dataset_git_revision")
        require(payload.get("partial") is not True, "arena_partial_index")
        if total is None:
            total, revision = current_total, current_revision
        require(
            total == current_total and revision == current_revision,
            "arena_changed_during_pagination",
        )
        batch = payload.get("rows")
        require(isinstance(batch, list) and len(batch) <= 100, "arena_invalid_page")
        require(bool(batch) or total == 0, "arena_incomplete_page")
        for item in batch:
            require(
                isinstance(item, dict) and not item.get("truncated_cells"),
                "arena_truncated_row",
            )
            row = item.get("row")
            identity = validate_arena_row(row, start, end_date)
            require(identity not in seen, "arena_duplicate_model")
            seen.add(identity)
            rows.append(row)
        require(len(rows) <= total, "arena_invalid_total")
        if len(rows) == total:
            return {
                "status": "ok",
                "rows": rows,
                "revision": revision,
                "config": config,
                "score_contract": f"arena-overall-{config}-v1",
                "start_date": start,
                "end_date": end_date,
                "as_of": max(
                    (r["leaderboard_publish_date"] for r in rows), default=None
                ),
                "coverage": "publication_window",
            }
    raise SourceError("arena_page_cap")


def hf(budget, products):
    rows = []
    for product in products:
        row = {
            "product_key": product["product_key"],
            **(
                {
                    "account_identifier": product["account_identifier"],
                    "account_kind": product["account_kind"],
                }
                if "account_identifier" in product
                else {"repo_id": product["repo_id"]}
            ),
            "observed_at": datetime.now(UTC).isoformat(),
        }
        try:
            row.update(
                status="ok",
                raw=(
                    budget.hf_counts(
                        product["account_identifier"], product["account_kind"]
                    )
                    if "account_identifier" in product
                    else budget.hf_counts(product["repo_id"])
                ),
            )
        except (ValueError, TypeError, KeyError) as exc:
            row.update(status="error", error=safe_error(exc))
        row["observed_at"] = datetime.now(UTC).isoformat()
        rows.append(row)
    return {
        "status": "ok"
        if rows and all(r["status"] == "ok" for r in rows)
        else "partial"
        if rows
        else "not_configured",
        "rows": rows,
    }


def openrouter(budget, start_date, end_date, *, key, today=None):
    window = set(days(start_date, end_date))
    require(day(start_date) >= day("2025-01-01"), "openrouter_history_floor")
    require(
        day(end_date) < (today or datetime.now(UTC).date()),
        "openrouter_requires_completed_utc_days",
    )
    if not key:
        raise SourceError("missing_openrouter_key")
    payload = budget.get(
        OPENROUTER_URL,
        {"start_date": start_date, "end_date": end_date, "period": "day"},
        key=key,
    )
    meta, rows = payload.get("meta"), payload.get("data")
    require(
        isinstance(meta, dict) and meta.get("version") == "v1",
        "openrouter_unknown_version",
    )
    require(
        meta.get("start_date") == start_date and meta.get("end_date") == end_date,
        "openrouter_scope_mismatch",
    )
    timestamp(meta.get("as_of"))
    require(isinstance(rows, list), "openrouter_invalid_rows")
    seen, day_counts, other = set(), {}, set()
    for row in rows:
        require(
            isinstance(row, dict) and row.get("date") in window,
            "openrouter_invalid_date",
        )
        model, tokens = row.get("model_permaslug"), row.get("total_tokens")
        require(
            isinstance(model, str)
            and 0 < len(model) <= 256
            and (model == "other" or "/" in model),
            "openrouter_invalid_model",
        )
        require(
            isinstance(tokens, str)
            and tokens.isascii()
            and tokens.isdecimal()
            and len(tokens) <= 30,
            "openrouter_invalid_tokens",
        )
        identity = row["date"], model
        require(identity not in seen, "openrouter_duplicate_model")
        seen.add(identity)
        day_counts[row["date"]] = day_counts.get(row["date"], 0) + 1
        if model == "other":
            other.add(row["date"])
    require(
        all(n - int(day in other) <= 50 for day, n in day_counts.items()),
        "openrouter_unexpected_population",
    )
    # Empty/missing dates are retained as missing data, never filled with zero.
    return {
        "status": "ok",
        "rows": rows,
        "meta": meta,
        "as_of": meta["as_of"],
        "missing_dates": sorted(window - day_counts.keys()),
        "coverage": "top_50_public_models",
    }


def safe_error(exc):
    # Never persist an HTTP response body, key, URL query, or exception repr.
    if isinstance(exc, SourceError):
        return str(exc)
    return "invalid_source_data"

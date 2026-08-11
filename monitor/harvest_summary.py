"""Canonical, redacted harvest summary envelopes.

The cycle keeps a useful in-process summary for operators and tests.  This
module is the boundary between that object and the one-line record that may
be copied into Render logs or durable evidence.  The boundary is deliberately
structural: only named fields cross it, and raw errors, queries, provider
payloads, and credentials never do.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

HARVEST_SUMMARY_PREFIX = "HARVEST_SUMMARY "
HARVEST_SUMMARY_SCHEMA_VERSION = "1"

_ENVELOPE_KEYS = {
    "schema_version",
    "service_id",
    "deploy_sha",
    "run_id",
    "summary",
    "hash",
}
_SUMMARY_KEYS = {
    "status",
    "cycle_kind",
    "dry_run",
    "started_at",
    "finished_at",
    "planned_calls",
    "calls",
    "backlog_replays",
    "totals",
    "degraded",
    "errors_count",
    "n_errors_by_type",
    "post_fetch",
    "metrics_refresh",
    "latency",
}
_CALL_KEYS = {
    "call_id",
    "call_kind",
    "brand_id",
    "bucket",
    "query_length",
    "execution_kind",
    "replay",
    "status",
    "window_since",
    "window_until",
    "n_results",
    "fetch_n",
    "n_kept",
    "n_inserted",
    "n_updated",
    "n_persist_failed",
    "n_attributed",
    "keep_rate",
    "not_include_drops",
    "llm_drops",
    "cursor_advanced",
    "request_started_at",
    "first_page_received_at",
    "cycle_start_to_first_page_ms",
    "wall_clock_ms",
    "page_receipts",
    "provider_late",
}
_PLANNED_CALL_KEYS = {
    "call_id",
    "call_kind",
    "brand_id",
    "bucket",
    "query_length",
}
_BACKLOG_KEYS = _CALL_KEYS | {
    "window_id",
    "attempt",
    "membership_run_id",
    "role_degraded",
}
_TOTAL_KEYS = {
    "n_calls_planned",
    "n_calls_run",
    "n_results",
    "n_inserted",
    "n_updated",
    "n_persist_failed",
    "n_attributed",
    "n_classifications_written",
    "keep_rate_min",
    "keep_rate_mean",
    "keep_rate_max",
}
_POST_FETCH_KEYS = {
    "n_translated",
    "n_classified",
    "n_translator_unavailable",
    "n_classifier_unavailable",
    "n_translator_failed",
    "n_classifier_failed",
    "n_enrichment_pending",
    "n_enrichment_quarantined",
    "n_flags_persisted",
    "n_flag_dead_letters",
    "completed_at",
    "wall_clock_ms",
}
_METRICS_KEYS = {"n_due", "n_refreshed", "n_missing", "wall_clock_ms"}
_LATENCY_KEYS = {
    "cycle_started_at",
    "post_fetch_completed_at",
    "tip_sweep_wall_clock_ms",
    "tip_sweep_first_page_max_ms",
    "tip_sweep_target_ms",
    "tip_sweep_within_target",
    "eligible_count",
    "api_to_db_p95_ms",
    "api_to_db_max_ms",
    "api_to_db",
}
_PAGE_RECEIPT_KEYS = {"page_number", "received_at"}
_OBSERVATION_KEYS = {
    "tweet_id",
    "api_received_at",
    "db_committed_at",
    "api_to_db_ms",
}
_PROVIDER_LATE_KEYS = {
    "eligible",
    "reason_code",
    "tweet_id",
    "prior_call_id",
    "prior_status",
    "prior_window_since",
    "prior_window_until",
    "query_bounds_match",
    "list_bounds_match",
    "time_bounds_match",
    "tweet_id_absent",
}

_SENSITIVE_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"(?:postgres(?:ql)?(?:\+[a-z0-9_-]+)?|mysql|mongodb(?:\+srv)?|redis)://"
    r"|(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)%3a%2f%2f"
    r"|(?:authorization|cookie|set-cookie|x-api-key|api[_-]?key|token|secret|password)"
    r"\s*[:=]"
    r"|\bbearer\s+[a-z0-9._~+/=-]{6,}"
    r"|\b(?:sk|ghp|github_pat|xai|AIza)[_-]?[a-z0-9_-]{8,}\b"
    r")"
)
_MULTILINE_RE = re.compile(r"[\r\n]")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.*:@+-]{1,160}$")
_SAFE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_HTTP_PATH_RE = re.compile(r"^/[A-Za-z0-9_./-]{1,200}$")


class SummaryValidationError(ValueError):
    """Raised when a canonical summary line is structurally invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_unsigned(envelope: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in envelope.items() if key != "hash"}
    return hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()


def _safe_token(value: Any, *, default: str = "unknown") -> str:
    if value is None or value == "":
        return default
    text = str(value)
    if _SENSITIVE_RE.search(text) or _MULTILINE_RE.search(text):
        return "[redacted]"
    if not _SAFE_TOKEN_RE.match(text):
        return "[redacted]"
    return text


def _safe_code(value: Any) -> str | None:
    text = _safe_token(value, default="")
    if not text or not _SAFE_CODE_RE.match(text):
        return None
    return text


def _safe_number(value: Any, *, integer: bool = False) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value) if integer else float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(float(number)) or number < 0:
        return None
    return number


def _safe_datetime(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value)
    if _SENSITIVE_RE.search(text) or _MULTILINE_RE.search(text):
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def redact_http_log(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        path = str(row.get("path") or "")
        cleaned: dict[str, Any] = {
            "path": path if _SAFE_HTTP_PATH_RE.match(path) and not _SENSITIVE_RE.search(path) else "[redacted]"
        }
        for key in ("status", "n_results", "duration_ms", "attempts"):
            if key in row:
                value = _safe_number(row.get(key), integer=True)
                if value is not None:
                    cleaned[key] = value
        if "has_next_page" in row:
            cleaned["has_next_page"] = bool(row.get("has_next_page"))
        result.append(cleaned)
    return result


def _copy_number_fields(source: Mapping[str, Any], keys: set[str]) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for key in keys:
        if key not in source:
            continue
        value = _safe_number(source.get(key), integer=key.startswith("n_") or key.endswith("_drops"))
        if value is not None:
            result[key] = value
    return result


def _normalise_page_receipts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        received = _safe_datetime(raw.get("received_at"))
        page = _safe_number(raw.get("page_number"), integer=True)
        if received is None or page is None:
            continue
        key = (page, received)
        if key in seen:
            continue
        seen.add(key)
        result.append({"page_number": page, "received_at": received})
    return sorted(result, key=lambda item: (item["page_number"], item["received_at"]))


def _normalise_call(raw: Mapping[str, Any], *, replay: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("call_id", "call_kind", "brand_id", "bucket", "status", "execution_kind"):
        if key in raw:
            result[key] = _safe_token(raw.get(key), default="")
    for key in ("query_length", "window_since", "window_until"):
        if key in raw:
            value = _safe_number(raw.get(key), integer=True)
            if value is not None:
                result[key] = value
    result["execution_kind"] = "backlog_replay" if replay else result.get("execution_kind", "live")
    result["replay"] = bool(raw.get("replay", replay))
    for key in (
        "n_results",
        "fetch_n",
        "n_kept",
        "n_inserted",
        "n_updated",
        "n_persist_failed",
        "n_attributed",
        "not_include_drops",
        "llm_drops",
    ):
        if key in raw:
            value = _safe_number(raw.get(key), integer=True)
            if value is not None:
                result[key] = value
    if "keep_rate" in raw:
        value = _safe_number(raw.get("keep_rate"))
        if value is not None:
            result["keep_rate"] = round(float(value), 4)
    if "cursor_advanced" in raw:
        result["cursor_advanced"] = bool(raw.get("cursor_advanced"))
    for key in ("request_started_at", "first_page_received_at"):
        if key in raw:
            value = _safe_datetime(raw.get(key))
            if value is not None:
                result[key] = value
    for key in ("cycle_start_to_first_page_ms", "wall_clock_ms"):
        if key in raw:
            value = _safe_number(raw.get(key), integer=True)
            if value is not None:
                result[key] = value
    page_receipts = _normalise_page_receipts(raw.get("page_receipts"))
    if page_receipts:
        result["page_receipts"] = page_receipts
    provider_late = _normalise_provider_late(raw.get("provider_late"))
    if provider_late is not None:
        result["provider_late"] = provider_late
    return result


def _normalise_provider_late(value: Any) -> dict[str, Any] | None:
    """Keep only an evidence-backed provider-late exception."""

    if not isinstance(value, Mapping) or value.get("eligible") is not True:
        return None
    required = (
        "tweet_id",
        "prior_call_id",
        "prior_status",
        "prior_window_since",
        "prior_window_until",
    )
    if any(key not in value for key in required):
        return None
    if not all(value.get(key) is True for key in (
        "query_bounds_match",
        "list_bounds_match",
        "time_bounds_match",
        "tweet_id_absent",
    )):
        return None
    since = _safe_number(value.get("prior_window_since"), integer=True)
    until = _safe_number(value.get("prior_window_until"), integer=True)
    if since is None or until is None or until < since:
        return None
    result = {
        "eligible": True,
        "reason_code": _safe_token(value.get("reason_code"), default="provider_late"),
        "tweet_id": _safe_token(value.get("tweet_id"), default=""),
        "prior_call_id": _safe_token(value.get("prior_call_id"), default=""),
        "prior_status": _safe_token(value.get("prior_status"), default=""),
        "prior_window_since": since,
        "prior_window_until": until,
        "query_bounds_match": True,
        "list_bounds_match": True,
        "time_bounds_match": True,
        "tweet_id_absent": True,
    }
    if not result["tweet_id"] or not result["prior_call_id"]:
        return None
    return result


def _normalise_planned(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        row: dict[str, Any] = {}
        for key in ("call_id", "call_kind", "brand_id", "bucket"):
            if key in item:
                row[key] = _safe_token(item.get(key), default="")
        if "query_length" in item:
            number = _safe_number(item.get("query_length"), integer=True)
            if number is not None:
                row["query_length"] = number
        if row:
            result.append(row)
    return result


def _normalise_degraded(summary: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    degraded = summary.get("degraded")
    if isinstance(degraded, Mapping):
        for raw_key, raw_value in degraded.items():
            key = _safe_code(raw_key)
            if key is None:
                continue
            if isinstance(raw_value, (list, Mapping)):
                count = len(raw_value) or 1
            elif raw_value:
                count = 1
            else:
                continue
            counts[key] = counts.get(key, 0) + count
    typed = summary.get("n_errors_by_type")
    if isinstance(typed, Mapping):
        for raw_key, raw_value in typed.items():
            count = _safe_number(raw_value, integer=True)
            if count:
                key = _safe_code(raw_key)
                if key is not None:
                    counts[key] = max(counts.get(key, 0), int(count))
    return dict(sorted(counts.items()))


def _normalise_latency(summary: Mapping[str, Any]) -> dict[str, Any]:
    latency = summary.get("latency")
    if not isinstance(latency, Mapping):
        latency = {}
    result: dict[str, Any] = {}
    for key in ("cycle_started_at", "post_fetch_completed_at"):
        value = _safe_datetime(latency.get(key))
        if value is not None:
            result[key] = value
    for key in ("tip_sweep_wall_clock_ms", "tip_sweep_first_page_max_ms", "tip_sweep_target_ms"):
        value = _safe_number(latency.get(key), integer=True)
        if value is not None:
            result[key] = value
    if "tip_sweep_within_target" in latency:
        result["tip_sweep_within_target"] = bool(latency.get("tip_sweep_within_target"))
    # ``summarize_latency`` uses ``observations`` as its in-process name;
    # the canonical envelope calls the same allowlisted evidence ``api_to_db``.
    observations = latency.get("api_to_db")
    if not isinstance(observations, list):
        observations = latency.get("observations")
    if isinstance(observations, list):
        cleaned = []
        for item in observations:
            if not isinstance(item, Mapping):
                continue
            tweet_id = _safe_token(item.get("tweet_id"), default="")
            received = _safe_datetime(item.get("api_received_at"))
            committed = _safe_datetime(item.get("db_committed_at"))
            duration = _safe_number(item.get("api_to_db_ms"), integer=True)
            if not tweet_id or received is None or committed is None or duration is None:
                continue
            cleaned.append({
                "tweet_id": tweet_id,
                "api_received_at": received,
                "db_committed_at": committed,
                "api_to_db_ms": duration,
            })
        result["api_to_db"] = cleaned
    for key in ("eligible_count", "api_to_db_p95_ms", "api_to_db_max_ms"):
        value = _safe_number(latency.get(key), integer=True)
        if value is not None:
            result[key] = value
    return result


def _normalise_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("status", "cycle_kind"):
        if key in summary:
            result[key] = _safe_token(summary.get(key), default="")
    if "dry_run" in summary:
        result["dry_run"] = bool(summary.get("dry_run"))
    for key in ("started_at", "finished_at"):
        value = _safe_datetime(summary.get(key))
        if value is not None:
            result[key] = value
    result["planned_calls"] = _normalise_planned(summary.get("planned_calls"))
    result["calls"] = [
        _normalise_call(item)
        for item in (summary.get("calls") or [])
        if isinstance(item, Mapping)
    ]
    result["backlog_replays"] = [
        _normalise_call(item, replay=True)
        for item in (summary.get("backlog_replays") or [])
        if isinstance(item, Mapping)
    ]
    totals = summary.get("totals")
    if isinstance(totals, Mapping):
        result["totals"] = _copy_number_fields(totals, _TOTAL_KEYS)
    else:
        result["totals"] = {}
    result["degraded"] = _normalise_degraded(summary)
    errors = summary.get("errors")
    result["errors_count"] = len(errors) if isinstance(errors, list) else (1 if errors else 0)
    typed = summary.get("n_errors_by_type")
    if isinstance(typed, Mapping):
        result["n_errors_by_type"] = {
            key: value
            for raw_key, raw_value in typed.items()
            if (key := _safe_code(raw_key)) is not None
            and (value := _safe_number(raw_value, integer=True)) is not None
        }
    post_fetch = summary.get("post_fetch")
    if isinstance(post_fetch, Mapping):
        result["post_fetch"] = _copy_number_fields(post_fetch, _POST_FETCH_KEYS)
        completed = _safe_datetime(post_fetch.get("completed_at"))
        if completed is not None:
            result["post_fetch"]["completed_at"] = completed
    metrics = summary.get("metrics_refresh")
    if isinstance(metrics, Mapping):
        result["metrics_refresh"] = _copy_number_fields(metrics, _METRICS_KEYS)
    result["latency"] = _normalise_latency(summary)
    return result


def build_summary_envelope(
    summary: Mapping[str, Any],
    *,
    service_id: str | None = None,
    deploy_sha: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic, redacted envelope for one cycle."""

    run_id = _safe_token(summary.get("run_id"), default="unknown")
    envelope: dict[str, Any] = {
        "schema_version": HARVEST_SUMMARY_SCHEMA_VERSION,
        "service_id": _safe_token(
            service_id if service_id is not None else os.environ.get("RENDER_SERVICE_ID"),
            default="local",
        ),
        "deploy_sha": _safe_token(
            deploy_sha if deploy_sha is not None else os.environ.get("RENDER_GIT_COMMIT"),
            default="unknown",
        ),
        "run_id": run_id,
        "summary": _normalise_summary(summary),
    }
    envelope["hash"] = _hash_unsigned(envelope)
    return envelope


def redacted_summary_payload(
    summary: Mapping[str, Any], envelope: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return a cost-tool-compatible top-level payload without raw evidence.

    ``data/runs`` still has legacy readers that expect ``run_id``/``calls`` at
    the top level. Keep that shape locally while deriving every value from the
    strict envelope. Render log synchronization uses the envelope itself.
    """

    envelope = envelope or build_summary_envelope(summary)
    payload = dict(envelope["summary"])
    payload.update(
        {
            "run_id": envelope["run_id"],
            "schema_version": envelope["schema_version"],
            "service_id": envelope["service_id"],
            "deploy_sha": envelope["deploy_sha"],
            "summary_hash": envelope["hash"],
        }
    )
    if isinstance(summary.get("http_log"), list):
        payload["http_log"] = redact_http_log(summary["http_log"])
    return payload


def serialize_summary_envelope(envelope: Mapping[str, Any]) -> str:
    """Serialize an already-built envelope as the reserved one-line record."""

    _validate_envelope(envelope, verify_hash=True)
    return HARVEST_SUMMARY_PREFIX + _canonical_json(dict(envelope))


def parse_summary_line(line: str) -> dict[str, Any]:
    if not isinstance(line, str) or not line.startswith(HARVEST_SUMMARY_PREFIX):
        raise SummaryValidationError("missing HARVEST_SUMMARY prefix")
    try:
        value = json.loads(line[len(HARVEST_SUMMARY_PREFIX):])
    except json.JSONDecodeError as exc:
        raise SummaryValidationError("invalid HARVEST_SUMMARY JSON") from exc
    if not isinstance(value, dict):
        raise SummaryValidationError("HARVEST_SUMMARY must be an object")
    _validate_envelope(value, verify_hash=True)
    return value


def _validate_envelope(envelope: Mapping[str, Any], *, verify_hash: bool) -> None:
    if set(envelope) != _ENVELOPE_KEYS:
        raise SummaryValidationError("unknown or missing envelope fields")
    if envelope.get("schema_version") != HARVEST_SUMMARY_SCHEMA_VERSION:
        raise SummaryValidationError("unsupported summary schema")
    for key in ("service_id", "deploy_sha", "run_id"):
        value = envelope.get(key)
        if not isinstance(value, str) or not value or _SENSITIVE_RE.search(value) or _MULTILINE_RE.search(value):
            raise SummaryValidationError(f"unsafe envelope field: {key}")
    if not isinstance(envelope.get("summary"), Mapping):
        raise SummaryValidationError("summary must be an object")
    if set(envelope["summary"]) - _SUMMARY_KEYS:
        raise SummaryValidationError("unknown summary fields")
    required_summary = {
        "planned_calls",
        "calls",
        "backlog_replays",
        "totals",
        "degraded",
        "errors_count",
        "latency",
    }
    if not required_summary.issubset(envelope["summary"]):
        raise SummaryValidationError("missing summary fields")
    if verify_hash and envelope.get("hash") != _hash_unsigned(envelope):
        raise SummaryValidationError("summary hash mismatch")
    summary = envelope["summary"]
    if not isinstance(summary.get("totals"), Mapping):
        raise SummaryValidationError("totals must be an object")
    if set(summary["totals"]) - _TOTAL_KEYS:
        raise SummaryValidationError("unknown totals fields")
    if not isinstance(summary.get("degraded"), Mapping):
        raise SummaryValidationError("degraded must be an object")
    for key, value in summary["degraded"].items():
        if not isinstance(key, str) or not _SAFE_CODE_RE.match(key):
            raise SummaryValidationError("unsafe degraded key")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise SummaryValidationError("degraded values must be non-negative integers")
    typed = summary.get("n_errors_by_type")
    if typed is not None and (
        not isinstance(typed, Mapping) or any(
            not isinstance(key, str) or not _SAFE_CODE_RE.match(key)
            or not isinstance(value, (int, float)) or isinstance(value, bool)
            or int(value) != value or value < 0
            for key, value in typed.items()
        )
    ):
        raise SummaryValidationError("invalid typed error counters")
    latency = summary.get("latency")
    if not isinstance(latency, Mapping) or set(latency) - _LATENCY_KEYS:
        raise SummaryValidationError("unknown latency fields")
    observations = latency.get("api_to_db", [])
    if not isinstance(observations, list):
        raise SummaryValidationError("api_to_db must be a list")
    for row in observations:
        if not isinstance(row, Mapping) or set(row) != _OBSERVATION_KEYS:
            raise SummaryValidationError("invalid api_to_db evidence")
    for key in ("post_fetch", "metrics_refresh"):
        value = summary.get(key)
        if value is None:
            continue
        allowed = _POST_FETCH_KEYS if key == "post_fetch" else _METRICS_KEYS
        if not isinstance(value, Mapping) or set(value) - allowed:
            raise SummaryValidationError(f"unknown {key} fields")
    for key in ("calls", "planned_calls", "backlog_replays"):
        rows = envelope["summary"].get(key)
        if not isinstance(rows, list):
            raise SummaryValidationError(f"{key} must be a list")
        allowed = _PLANNED_CALL_KEYS if key == "planned_calls" else (_BACKLOG_KEYS if key == "backlog_replays" else _CALL_KEYS)
        for row in rows:
            if not isinstance(row, Mapping) or set(row) - allowed:
                raise SummaryValidationError(f"unknown {key} fields")
            if key != "planned_calls" and "page_receipts" in row:
                receipts = row["page_receipts"]
                if not isinstance(receipts, list):
                    raise SummaryValidationError("page_receipts must be a list")
                for receipt in receipts:
                    if not isinstance(receipt, Mapping) or set(receipt) != _PAGE_RECEIPT_KEYS:
                        raise SummaryValidationError("invalid page receipt")
            if "provider_late" in row:
                evidence = row["provider_late"]
                if not isinstance(evidence, Mapping) or set(evidence) != _PROVIDER_LATE_KEYS:
                    raise SummaryValidationError("invalid provider-late evidence")
                if evidence.get("eligible") is not True or evidence.get("tweet_id_absent") is not True:
                    raise SummaryValidationError("provider-late evidence is not eligible")


def provider_late_evidence(
    *,
    tweet_id: Any,
    prior_call: Mapping[str, Any],
    query_bounds: Mapping[str, Any],
    query_bounds_match: bool,
    list_bounds_match: bool,
    returned_tweet_ids: Any,
) -> dict[str, Any] | None:
    """Return a provider-late claim only when R11 evidence is complete.

    A healthy, untruncated prior call must carry the same time bounds and the
    caller must explicitly prove query/list equivalence.  Missing evidence is
    represented by ``None`` rather than a permissive degradation claim.
    """

    if not isinstance(prior_call, Mapping) or not isinstance(query_bounds, Mapping):
        return None
    if prior_call.get("status") not in {"completed", "no_results"}:
        return None
    if prior_call.get("truncated") is True or prior_call.get("cursor_advanced") is False:
        return None
    if not query_bounds_match or not list_bounds_match:
        return None
    try:
        since = int(query_bounds["since"])
        until = int(query_bounds["until"])
        prior_since = int(prior_call["window_since"])
        prior_until = int(prior_call["window_until"])
    except (KeyError, TypeError, ValueError):
        return None
    if until < since or (prior_since, prior_until) != (since, until):
        return None
    safe_tweet_id = _safe_token(tweet_id, default="")
    prior_call_id = _safe_token(prior_call.get("call_id"), default="")
    if not safe_tweet_id or not prior_call_id:
        return None
    try:
        if any(str(value) == safe_tweet_id for value in returned_tweet_ids):
            return None
    except TypeError:
        return None
    return {
        "eligible": True,
        "reason_code": "provider_late",
        "tweet_id": safe_tweet_id,
        "prior_call_id": prior_call_id,
        "prior_status": _safe_token(prior_call.get("status"), default=""),
        "prior_window_since": since,
        "prior_window_until": until,
        "query_bounds_match": True,
        "list_bounds_match": True,
        "time_bounds_match": True,
        "tweet_id_absent": True,
    }


def summarize_latency(observations: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute API-receipt-to-DB-commit latency from eligible observations.

    The provider's ``created_at`` and Django's ``fetched_at`` are intentionally
    ignored.  Duplicate tweet IDs remain separate observations because each
    API page/commit pair is evidence of a distinct persistence event.
    """

    cleaned: list[dict[str, Any]] = []
    for raw in observations:
        tweet_id = _safe_token(raw.get("tweet_id"), default="")
        received = _safe_datetime(raw.get("api_received_at"))
        committed = _safe_datetime(raw.get("db_committed_at"))
        if not tweet_id or received is None or committed is None:
            continue
        start = datetime.fromisoformat(received)
        end = datetime.fromisoformat(committed)
        duration = round((end - start).total_seconds() * 1000)
        if duration < 0:
            continue
        cleaned.append({
            "tweet_id": tweet_id,
            "api_received_at": received,
            "db_committed_at": committed,
            "api_to_db_ms": duration,
        })
    durations = sorted(row["api_to_db_ms"] for row in cleaned)
    if not durations:
        p95 = maximum = 0
    else:
        p95 = durations[max(0, math.ceil(len(durations) * 0.95) - 1)]
        maximum = durations[-1]
    return {
        "eligible_count": len(cleaned),
        "api_to_db_p95_ms": p95,
        "api_to_db_max_ms": maximum,
        "observations": cleaned,
    }

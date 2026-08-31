"""Strict TwitterAPI User About parsing and bounded HTTP access."""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp
from dateutil.parser import isoparse
from dateutil.parser import parse as parse_datetime
from django.utils import timezone

from monitor.country_codes import normalize_country_code
from monitor.twitterapi.caller import USER_AGENT, CircuitBreaker, GlobalPaceGate

USER_ABOUT_URL = "https://api.twitterapi.io/twitter/user_about"


class UserAboutError(ValueError):
    """Base class for a response that cannot become an Account observation."""


class SchemaDriftError(UserAboutError):
    """The response no longer matches the documented provider schema."""


class IdentityMismatchError(UserAboutError):
    """The response belongs to a different X account."""


class ProviderResponseError(UserAboutError):
    """The provider returned a documented non-success envelope."""


@dataclass(frozen=True)
class UserAboutObservation:
    author_id: str
    candidates: dict[str, Any]
    present_fields: set[str]


@dataclass(frozen=True)
class FetchSelection:
    author_id: str
    handle: str


@dataclass(frozen=True)
class FetchOutcome:
    author_id: str
    observation: UserAboutObservation | None
    reason: str
    status_code: int | None
    latency_ms: float
    schema_diagnostic: tuple[str, ...] | None = None


@dataclass(frozen=True)
class FetchBatchResult:
    outcomes: list[FetchOutcome]
    attempts: int
    retries: int
    projected_credits: int
    latencies_ms: list[float]
    wall_seconds: float
    stop_reason: str | None


_DATA_KEYS = {
    "id",
    "name",
    "userName",
    "createdAt",
    "isVerified",
    "isBlueVerified",
    "protected",
    "profilePicture",
    "verification_info",
    "unavailable",
    "unavailableReason",
    "affiliates_highlighted_label",
    "about_profile",
    "identity_profile_labels_highlighted_label",
}
_ABOUT_KEYS = {
    "account_based_in",
    "location_accurate",
    "created_country_accurate",
    "learn_more_url",
    "affiliate_username",
    "source",
    "username_changes",
}
_USERNAME_CHANGES_KEYS = {"count", "last_changed_at_msec"}
_VERIFICATION_INFO_KEYS = {"id", "is_identity_verified", "reason"}
_VERIFICATION_REASON_KEYS = {
    "override_verified_year",
    "verified_since_msec",
}
_LABEL_KEYS = {
    "badge",
    "description",
    "url",
    "userLabelDisplayType",
    "userLabelType",
}
_LONG_DESCRIPTION_KEYS = {"text", "entities"}
_LONG_DESCRIPTION_ENTITY_KEYS = {"from_index", "to_index", "ref"}
_LONG_DESCRIPTION_REF_KEYS = {
    "__isTimelineReferenceObject",
    "__typename",
    "screen_name",
    "user_results",
}
_LABEL_SUFFIXES = {
    "badge_url",
    "description",
    "url",
    "url_type",
    "user_label_display_type",
    "user_label_type",
}
_SAFE_SCHEMA_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_MAX_SCHEMA_PATHS = 128


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unsupported"


def _redacted_schema_key(key: object, sensitive_values: set[str]) -> str:
    text = str(key)
    if text in sensitive_values or not _SAFE_SCHEMA_KEY.fullmatch(text):
        return "<redacted-key>"
    return text


def _schema_error_summary(error: SchemaDriftError) -> str:
    message = str(error)
    if message.startswith("unknown leaves at "):
        path = message.removeprefix("unknown leaves at ").split(":", 1)[0]
        return f"unknown_leaves:{path}"
    return message


def describe_json_shape(
    payload: object,
    *,
    sensitive_values: set[str] | None = None,
) -> tuple[str, ...]:
    """Return bounded JSON paths and types without retaining response values."""
    sensitive = {str(value) for value in (sensitive_values or set()) if value}
    paths: list[str] = []

    def collect_scalar_values(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                collect_scalar_values(child)
        elif isinstance(value, list):
            for child in value:
                collect_scalar_values(child)
        elif isinstance(value, (str, int, float)) and type(value) is not bool:
            text = str(value)
            if 0 < len(text) <= 64:
                sensitive.add(text)

    def walk(value: object, path: str, depth: int) -> None:
        if len(paths) >= _MAX_SCHEMA_PATHS:
            return
        paths.append(f"{path}:{_json_type(value)}")
        if depth >= 8:
            return
        if isinstance(value, dict):
            for key in sorted(value, key=str):
                safe_key = _redacted_schema_key(key, sensitive)
                walk(value[key], f"{path}.{safe_key}", depth + 1)
                if len(paths) >= _MAX_SCHEMA_PATHS:
                    return
        elif isinstance(value, list) and value:
            walk(value[0], f"{path}[]", depth + 1)

    collect_scalar_values(payload)
    walk(payload, "$", 0)
    if len(paths) >= _MAX_SCHEMA_PATHS:
        paths.append("<truncated>")
    return tuple(paths)


def _assert_keys(value: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SchemaDriftError(f"unknown leaves at {path}: {', '.join(unknown)}")


def _optional_dict(value: object, path: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SchemaDriftError(f"{path} must be an object or null")
    return value


def _strict_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaDriftError(f"{path} must be a string or null")
    return value


def _strict_bool(value: object, path: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise SchemaDriftError(f"{path} must be a boolean or null")
    return value


def _strict_datetime(value: object, path: str) -> datetime | None:
    text = _strict_string(value, path)
    if text is None:
        return None
    try:
        parsed = isoparse(text) if "T" in text else parse_datetime(text)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SchemaDriftError(f"{path} must be a documented datetime") from exc
    if parsed.tzinfo is None:
        raise SchemaDriftError(f"{path} must include a timezone")
    return parsed


def _strict_numeric_string(value: object, path: str) -> int | None:
    text = _strict_string(value, path)
    if text is None:
        return None
    if not text.isdigit():
        raise SchemaDriftError(f"{path} must be a numeric string")
    return int(text)


def _strict_nonnegative_int(value: object, path: str) -> int:
    if type(value) is not int or value < 0:
        raise SchemaDriftError(f"{path} must be a nonnegative integer")
    return value


def _validate_long_description_entities(value: object, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise SchemaDriftError(f"{path} must be an array or null")
    for index, entity_value in enumerate(value):
        entity_path = f"{path}[{index}]"
        if not isinstance(entity_value, dict):
            raise SchemaDriftError(f"{entity_path} must be an object")
        _assert_keys(entity_value, _LONG_DESCRIPTION_ENTITY_KEYS, entity_path)
        for key in ("from_index", "to_index"):
            if key in entity_value:
                _strict_nonnegative_int(entity_value[key], f"{entity_path}.{key}")
        ref = entity_value.get("ref")
        if not isinstance(ref, dict):
            raise SchemaDriftError(f"{entity_path}.ref must be an object")
        _assert_keys(ref, _LONG_DESCRIPTION_REF_KEYS, f"{entity_path}.ref")
        for key in ("__isTimelineReferenceObject", "__typename", "screen_name"):
            if key in ref:
                _strict_string(ref[key], f"{entity_path}.ref.{key}")
        if "user_results" in ref and not isinstance(ref["user_results"], dict):
            raise SchemaDriftError(f"{entity_path}.ref.user_results must be an object")


def _put(
    candidates: dict[str, Any],
    present: set[str],
    source: dict[str, Any],
    source_key: str,
    field_name: str,
    parser,
    path: str,
) -> None:
    if source_key not in source:
        return
    candidates[field_name] = parser(source[source_key], f"{path}.{source_key}")
    present.add(field_name)


def flatten_label(
    value: object,
    *,
    prefix: str,
    path: str,
    include_long_description: bool = False,
) -> tuple[dict[str, Any], set[str]]:
    """Flatten one documented highlighted-label wrapper as an atomic group."""
    wrapper = _optional_dict(value, path)
    field_names = {f"{prefix}_{suffix}" for suffix in _LABEL_SUFFIXES}
    if include_long_description:
        field_names.add(f"{prefix}_long_description")
    if wrapper is None or not wrapper:
        return ({field: None for field in field_names}, field_names)
    _assert_keys(wrapper, {"label"}, path)
    label = _optional_dict(wrapper.get("label"), f"{path}.label")
    if label is None or not label:
        return ({field: None for field in field_names}, field_names)
    label_keys = _LABEL_KEYS | (
        {"long_description"} if include_long_description else set()
    )
    _assert_keys(label, label_keys, f"{path}.label")

    candidates: dict[str, Any] = {field: None for field in field_names}
    badge = _optional_dict(label.get("badge"), f"{path}.label.badge")
    if badge is not None:
        _assert_keys(badge, {"url"}, f"{path}.label.badge")
        if "url" in badge:
            candidates[f"{prefix}_badge_url"] = _strict_string(
                badge["url"], f"{path}.label.badge.url"
            )
    if "description" in label:
        candidates[f"{prefix}_description"] = _strict_string(
            label["description"], f"{path}.label.description"
        )
    if include_long_description and "long_description" in label:
        long_description = _optional_dict(
            label["long_description"], f"{path}.label.long_description"
        )
        if long_description is not None:
            _assert_keys(
                long_description,
                _LONG_DESCRIPTION_KEYS,
                f"{path}.label.long_description",
            )
            if "text" in long_description:
                candidates[f"{prefix}_long_description"] = _strict_string(
                    long_description["text"],
                    f"{path}.label.long_description.text",
                )
            if "entities" in long_description:
                _validate_long_description_entities(
                    long_description["entities"],
                    f"{path}.label.long_description.entities",
                )
    url = _optional_dict(label.get("url"), f"{path}.label.url")
    if url is not None:
        _assert_keys(url, {"url", "urlType"}, f"{path}.label.url")
        if "url" in url:
            candidates[f"{prefix}_url"] = _strict_string(
                url["url"], f"{path}.label.url.url"
            )
        if "urlType" in url:
            candidates[f"{prefix}_url_type"] = _strict_string(
                url["urlType"], f"{path}.label.url.urlType"
            )
    if "userLabelDisplayType" in label:
        candidates[f"{prefix}_user_label_display_type"] = _strict_string(
            label["userLabelDisplayType"],
            f"{path}.label.userLabelDisplayType",
        )
    if "userLabelType" in label:
        candidates[f"{prefix}_user_label_type"] = _strict_string(
            label["userLabelType"], f"{path}.label.userLabelType"
        )
    return candidates, field_names


def parse_user_about(
    payload: object,
    *,
    expected_author_id: str,
    observed_at: datetime,
) -> UserAboutObservation:
    """Convert one documented success envelope into typed field candidates."""
    if not isinstance(payload, dict):
        raise SchemaDriftError("response envelope must be an object")
    _assert_keys(payload, {"status", "msg", "data", "errors"}, "response")
    if payload.get("status") != "success":
        raise ProviderResponseError("provider returned a non-success response")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SchemaDriftError("response.data must be an object on success")
    _assert_keys(data, _DATA_KEYS, "response.data")

    if data.get("unavailable") is True:
        _assert_keys(
            data,
            {"unavailable", "unavailableReason"},
            "response.data",
        )
        candidates: dict[str, Any] = {}
        present: set[str] = set()
        _put(
            candidates,
            present,
            data,
            "unavailable",
            "unavailable",
            _strict_bool,
            "response.data",
        )
        _put(
            candidates,
            present,
            data,
            "unavailableReason",
            "unavailable_reason",
            _strict_string,
            "response.data",
        )
        candidates["account_based_in_fetched_at"] = observed_at
        present.add("account_based_in_fetched_at")
        return UserAboutObservation(
            author_id=str(expected_author_id),
            candidates=candidates,
            present_fields=present,
        )
    if "unavailable" in data or "unavailableReason" in data:
        raise SchemaDriftError(
            "response.data unavailable variant must set unavailable=true"
        )

    returned_id = _strict_string(data.get("id"), "response.data.id")
    if not returned_id:
        raise SchemaDriftError("response.data.id must be a nonblank string")
    if returned_id != str(expected_author_id):
        raise IdentityMismatchError("returned account ID does not match selection")

    candidates: dict[str, Any] = {}
    present: set[str] = set()
    _put(
        candidates,
        present,
        data,
        "name",
        "display_name",
        _strict_string,
        "response.data",
    )
    _put(
        candidates, present, data, "userName", "handle", _strict_string, "response.data"
    )
    _put(
        candidates,
        present,
        data,
        "createdAt",
        "created_at",
        _strict_datetime,
        "response.data",
    )
    _put(
        candidates,
        present,
        data,
        "isVerified",
        "verified",
        _strict_bool,
        "response.data",
    )
    _put(
        candidates,
        present,
        data,
        "isBlueVerified",
        "is_blue_verified",
        _strict_bool,
        "response.data",
    )
    _put(
        candidates,
        present,
        data,
        "profilePicture",
        "profile_picture",
        _strict_string,
        "response.data",
    )

    if "verification_info" in data:
        verification_info = _optional_dict(
            data["verification_info"],
            "response.data.verification_info",
        )
        if verification_info is not None:
            _assert_keys(
                verification_info,
                _VERIFICATION_INFO_KEYS,
                "response.data.verification_info",
            )
            _put(
                candidates,
                present,
                verification_info,
                "id",
                "verification_info_id",
                _strict_string,
                "response.data.verification_info",
            )
            if "reason" in verification_info:
                reason = _optional_dict(
                    verification_info["reason"],
                    "response.data.verification_info.reason",
                )
                present.update(
                    {
                        "verification_info_reason_override_verified_year",
                        "verification_info_reason_verified_since_msec",
                    }
                )
                candidates["verification_info_reason_override_verified_year"] = None
                candidates["verification_info_reason_verified_since_msec"] = None
                if reason is not None:
                    _assert_keys(
                        reason,
                        _VERIFICATION_REASON_KEYS,
                        "response.data.verification_info.reason",
                    )
                    if (
                        "override_verified_year" in reason
                        and reason["override_verified_year"] is not None
                    ):
                        candidates[
                            "verification_info_reason_override_verified_year"
                        ] = _strict_nonnegative_int(
                            reason["override_verified_year"],
                            "response.data.verification_info.reason."
                            "override_verified_year",
                        )
                    if (
                        "verified_since_msec" in reason
                        and reason["verified_since_msec"] is not None
                    ):
                        candidates["verification_info_reason_verified_since_msec"] = (
                            _strict_numeric_string(
                                reason["verified_since_msec"],
                                "response.data.verification_info.reason."
                                "verified_since_msec",
                            )
                        )
            _put(
                candidates,
                present,
                verification_info,
                "is_identity_verified",
                "verification_info_is_identity_verified",
                _strict_bool,
                "response.data.verification_info",
            )
    _put(
        candidates,
        present,
        data,
        "protected",
        "protected",
        _strict_bool,
        "response.data",
    )

    if "affiliates_highlighted_label" in data:
        values, fields = flatten_label(
            data["affiliates_highlighted_label"],
            prefix="affiliate_label",
            path="response.data.affiliates_highlighted_label",
        )
        candidates.update(values)
        present.update(fields)

    if "about_profile" in data:
        about = _optional_dict(data["about_profile"], "response.data.about_profile")
        if about is not None:
            _assert_keys(about, _ABOUT_KEYS, "response.data.about_profile")
            _put(
                candidates,
                present,
                about,
                "account_based_in",
                "account_based_in",
                _strict_string,
                "response.data.about_profile",
            )
            _put(
                candidates,
                present,
                about,
                "location_accurate",
                "location_accurate",
                _strict_bool,
                "response.data.about_profile",
            )
            _put(
                candidates,
                present,
                about,
                "created_country_accurate",
                "created_country_accurate",
                _strict_bool,
                "response.data.about_profile",
            )
            _put(
                candidates,
                present,
                about,
                "learn_more_url",
                "learn_more_url",
                _strict_string,
                "response.data.about_profile",
            )
            _put(
                candidates,
                present,
                about,
                "affiliate_username",
                "affiliate_username",
                _strict_string,
                "response.data.about_profile",
            )
            _put(
                candidates,
                present,
                about,
                "source",
                "source",
                _strict_string,
                "response.data.about_profile",
            )
            if "username_changes" in about:
                changes = _optional_dict(
                    about["username_changes"],
                    "response.data.about_profile.username_changes",
                )
                present.add("username_changes_count")
                candidates["username_changes_count"] = None
                present.add("username_changes_last_changed_at_msec")
                candidates["username_changes_last_changed_at_msec"] = None
                if changes is not None:
                    _assert_keys(
                        changes,
                        _USERNAME_CHANGES_KEYS,
                        "response.data.about_profile.username_changes",
                    )
                    if "count" in changes and changes["count"] is not None:
                        candidates["username_changes_count"] = _strict_numeric_string(
                            changes["count"],
                            "response.data.about_profile.username_changes.count",
                        )
                    if (
                        "last_changed_at_msec" in changes
                        and changes["last_changed_at_msec"] is not None
                    ):
                        candidates["username_changes_last_changed_at_msec"] = (
                            _strict_numeric_string(
                                changes["last_changed_at_msec"],
                                "response.data.about_profile.username_changes."
                                "last_changed_at_msec",
                            )
                        )
            if "account_based_in" in about:
                code = normalize_country_code(candidates.get("account_based_in"))
                if code is not None:
                    candidates["country_code"] = code
                    present.add("country_code")

    if "identity_profile_labels_highlighted_label" in data:
        values, fields = flatten_label(
            data["identity_profile_labels_highlighted_label"],
            prefix="identity_profile_label",
            path="response.data.identity_profile_labels_highlighted_label",
            include_long_description=True,
        )
        candidates.update(values)
        present.update(fields)

    candidates["account_based_in_fetched_at"] = observed_at
    present.add("account_based_in_fetched_at")
    return UserAboutObservation(
        author_id=returned_id,
        candidates=candidates,
        present_fields=present,
    )


async def fetch_user_about_batch(
    selections: list[FetchSelection],
    *,
    api_key: str,
    rate_qps: float,
    concurrency: int = 1,
    max_attempts: int,
    max_credits: int,
    max_wall_seconds: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> FetchBatchResult:
    """Fetch a bounded batch with one session, strict parsing, and safe stops."""
    if not api_key:
        raise ValueError("api_key is required")
    if max_attempts <= 0 or max_credits <= 0 or max_wall_seconds <= 0:
        raise ValueError("all User About budgets must be positive")
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    started = clock()
    attempts = 0
    retries = 0
    projected_credits = 0
    outcomes: list[FetchOutcome] = []
    latencies_ms: list[float] = []
    stop_reason: str | None = None
    breaker = CircuitBreaker()
    pace = GlobalPaceGate(rate_qps=rate_qps, clock=clock, sleep=sleep)
    connector = aiohttp.TCPConnector(limit=concurrency)
    headers = {"X-API-Key": api_key, "User-Agent": USER_AGENT}
    admission_lock = asyncio.Lock()
    stopped = asyncio.Event()

    def remaining_wall() -> float:
        return max(0.0, max_wall_seconds - (clock() - started))

    def budget_stop() -> str | None:
        if remaining_wall() <= 0:
            return "wall_time_budget"
        if attempts + 1 > max_attempts:
            return "attempt_budget"
        if projected_credits + 18 > max_credits:
            return "credit_budget"
        return None

    async def stop(reason: str) -> None:
        nonlocal stop_reason
        async with admission_lock:
            if stop_reason is None:
                stop_reason = reason
            stopped.set()

    async def reserve_attempt(*, retry: bool) -> bool:
        nonlocal attempts, retries, projected_credits, stop_reason
        await pace.wait()
        async with admission_lock:
            if stopped.is_set():
                return False
            reason = budget_stop()
            if reason is not None:
                stop_reason = reason
                stopped.set()
                return False
            attempts += 1
            projected_credits += 18
            if retry:
                retries += 1
            return True

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers,
    ) as session:
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_one(
            index: int,
            selection: FetchSelection,
        ) -> tuple[int, FetchOutcome | None]:
            if stopped.is_set():
                return index, None
            if breaker.is_open:
                await stop("circuit_open")
                return index, None
            final_outcome: FetchOutcome | None = None
            for attempt_number in (1, 2):
                if not await reserve_attempt(retry=attempt_number == 2):
                    break
                request_started = clock()
                status: int | None = None
                body_text = ""
                headers_out: dict[str, str] = {}
                reason: str
                schema_diagnostic: tuple[str, ...] | None = None
                request_budget = remaining_wall()
                if request_budget <= 0:
                    await stop("wall_time_budget")
                    break
                try:
                    async with session.get(
                        USER_ABOUT_URL,
                        params={"userName": selection.handle},
                        timeout=aiohttp.ClientTimeout(
                            sock_connect=min(3.0, request_budget),
                            sock_read=min(10.0, request_budget),
                            total=min(12.0, request_budget),
                        ),
                    ) as response:
                        status = response.status
                        headers_out = dict(response.headers)
                        body_text = await response.text()
                except (TimeoutError, aiohttp.ClientError):
                    reason = (
                        "wall_time_budget"
                        if remaining_wall() <= 0
                        else "connection_error"
                    )
                else:
                    if status == 200:
                        try:
                            payload = json.loads(body_text)
                        except json.JSONDecodeError:
                            reason = "schema_drift"
                            schema_diagnostic = ("parser_error:response is not JSON",)
                        else:
                            try:
                                observation = parse_user_about(
                                    payload,
                                    expected_author_id=selection.author_id,
                                    observed_at=timezone.now(),
                                )
                            except IdentityMismatchError:
                                reason = "identity_mismatch"
                            except SchemaDriftError as exc:
                                reason = "schema_drift"
                                sensitive = {
                                    str(selection.author_id),
                                    str(selection.handle),
                                }
                                schema_diagnostic = (
                                    "parser_error:" + _schema_error_summary(exc),
                                    *describe_json_shape(
                                        payload,
                                        sensitive_values=sensitive,
                                    ),
                                )
                            except ProviderResponseError:
                                reason = "provider_error"
                            else:
                                latency = round(
                                    (clock() - request_started) * 1_000,
                                    3,
                                )
                                latencies_ms.append(latency)
                                final_outcome = FetchOutcome(
                                    author_id=selection.author_id,
                                    observation=observation,
                                    reason="success",
                                    status_code=status,
                                    latency_ms=latency,
                                )
                                breaker.record("success")
                                break
                    elif status in {401, 403}:
                        reason = "auth_invalid" if status == 401 else "auth_forbidden"
                    elif status == 429:
                        reason = "rate_limited"
                    elif status is not None and 500 <= status < 600:
                        reason = "http_5xx"
                    else:
                        reason = "provider_error"

                latency = round((clock() - request_started) * 1_000, 3)
                latencies_ms.append(latency)
                final_outcome = FetchOutcome(
                    author_id=selection.author_id,
                    observation=None,
                    reason=reason,
                    status_code=status,
                    latency_ms=latency,
                    schema_diagnostic=schema_diagnostic,
                )
                if reason in {
                    "schema_drift",
                    "identity_mismatch",
                    "auth_invalid",
                    "auth_forbidden",
                    "wall_time_budget",
                }:
                    await stop(reason)
                    break
                retryable = reason in {"rate_limited", "http_5xx", "connection_error"}
                if attempt_number == 1 and retryable:
                    if reason == "rate_limited":
                        raw_retry = headers_out.get("Retry-After", "2")
                        try:
                            retry_after = min(30.0, max(0.0, float(raw_retry)))
                        except ValueError:
                            retry_after = 2.0
                        delay = retry_after + random.uniform(0.1, 0.5)
                        remaining = remaining_wall()
                        if delay >= remaining:
                            await sleep(remaining)
                            await stop("wall_time_budget")
                            break
                        await sleep(delay)
                    continue
                breaker.record(reason)
                if breaker.is_open:
                    await stop("circuit_open")
                break

            return index, final_outcome

        async def fetch_one_bounded(
            index: int,
            selection: FetchSelection,
        ) -> tuple[int, FetchOutcome | None]:
            async with semaphore:
                return await fetch_one(index, selection)

        fetched = await asyncio.gather(
            *(
                fetch_one_bounded(index, selection)
                for index, selection in enumerate(selections)
            )
        )
        outcomes.extend(
            outcome
            for _, outcome in sorted(fetched, key=lambda item: item[0])
            if outcome is not None
        )

    return FetchBatchResult(
        outcomes=outcomes,
        attempts=attempts,
        retries=retries,
        projected_credits=projected_credits,
        latencies_ms=latencies_ms,
        wall_seconds=round(clock() - started, 3),
        stop_reason=stop_reason,
    )

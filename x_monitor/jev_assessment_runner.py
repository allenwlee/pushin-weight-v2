"""Bounded, resumable direct-TypeSafe assessment support.

The runner deliberately does not know reference labels while making requests.
Each provider result is durably journaled before it is parsed or reported.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from x_monitor.config import JevDecisionsConfig
from x_monitor.jev_decisions import (
    JevDecisionError,
    conservative_reservation_usd,
    encode_request_payload,
    parse_response,
    public_post_state,
)
from x_monitor.rare_type_quality_gate import ASSESSMENT_BUDGET_USD

MAX_PHYSICAL_CALLS = 56
DIRECT_KEY_ENV = "TYPESAFE_API_KEY"


class AssessmentRunError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _request(case: Mapping[str, Any], config: JevDecisionsConfig) -> tuple[bytes, str]:
    encoded = encode_request_payload(public_post_state(case["public_payload"]), config)
    return encoded, hashlib.sha256(encoded).hexdigest()


def preflight(corpus: Mapping[str, Any], config: JevDecisionsConfig) -> dict[str, Any]:
    cases = corpus.get("cases")
    if not isinstance(cases, list) or len(cases) != MAX_PHYSICAL_CALLS:
        raise AssessmentRunError(
            f"assessment requires exactly {MAX_PHYSICAL_CALLS} cases"
        )
    reservations = [
        conservative_reservation_usd(_request(case, config)[0], config)
        for case in cases
    ]
    reserved = sum(reservations, Decimal(0))
    if reserved > ASSESSMENT_BUDGET_USD:
        raise AssessmentRunError("conservative reservation exceeds assessment ceiling")
    return {
        "ready": bool(os.environ.get(DIRECT_KEY_ENV)),
        "credential_env": DIRECT_KEY_ENV,
        "credential_present": bool(os.environ.get(DIRECT_KEY_ENV)),
        "endpoint": config.endpoint,
        "model": config.model,
        "provider": config.provider,
        "case_count": len(cases),
        "max_physical_calls": MAX_PHYSICAL_CALLS,
        "http_retries": 0,
        "reserved_usd": format(reserved, "f"),
        "ceiling_usd": format(ASSESSMENT_BUDGET_USD, "f"),
    }


def atomic_new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise AssessmentRunError(f"refusing to overwrite evidence: {path}") from exc
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _direct_send(request_bytes: bytes, config: JevDecisionsConfig) -> dict[str, Any]:
    key = os.environ.get(DIRECT_KEY_ENV, "")
    if not key:
        raise AssessmentRunError("direct TypeSafe credential missing")
    try:
        response = httpx.post(
            config.endpoint,
            content=request_bytes,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=config.request_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise AssessmentRunError(f"transport_error:{type(exc).__name__}") from exc
    if response.status_code != 200:
        # Error payloads are not evidence inputs and can echo request/auth details.
        return {
            "http_status": response.status_code,
            "error_body_sha256": hashlib.sha256(response.content).hexdigest(),
            "error_body_bytes": len(response.content),
        }
    try:
        body = response.json()
    except ValueError:
        body = {"unparseable_body_sha256": hashlib.sha256(response.content).hexdigest()}
    return {"http_status": response.status_code, "body": body}


def run(
    *,
    corpus: Mapping[str, Any],
    config: JevDecisionsConfig,
    output_dir: Path,
    sender: Callable[[bytes, JevDecisionsConfig], Mapping[str, Any]] = _direct_send,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    check = preflight(corpus, config)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    predictions: list[dict[str, Any]] = []
    calls = 0
    errors = 0
    measured_spend = Decimal(0)
    reserved_committed = Decimal(0)
    expected_journals = {
        f"{case['id']}--{_request(case, config)[1]}.json" for case in corpus["cases"]
    }
    existing_journals = {path.name for path in (output_dir / "journal").glob("*.json")}
    if existing_journals - expected_journals:
        raise AssessmentRunError(
            "journal contains a different case or request identity"
        )
    if (
        sender is _direct_send
        and not check["credential_present"]
        and (expected_journals - existing_journals)
    ):
        raise AssessmentRunError("direct TypeSafe credential missing")
    for case in corpus["cases"]:
        case_id = case["id"]
        request_bytes, request_hash = _request(case, config)
        case_reservation = conservative_reservation_usd(request_bytes, config)
        journal = output_dir / "journal" / f"{case_id}--{request_hash}.json"
        if journal.exists():
            record = json.loads(journal.read_text())
            if (
                record.get("case_id") != case_id
                or record.get("request_sha256") != request_hash
            ):
                raise AssessmentRunError(f"journal identity mismatch: {case_id}")
        else:
            if reserved_committed + case_reservation > ASSESSMENT_BUDGET_USD:
                raise AssessmentRunError("assessment reservation ceiling exhausted")
            if calls >= MAX_PHYSICAL_CALLS:
                raise AssessmentRunError("physical call cap exhausted")
            calls += 1
            started = time.time()
            try:
                raw = dict(sender(request_bytes, config))
                record = {
                    "schema_version": "direct-jev-journal-v1",
                    "case_id": case_id,
                    "request_sha256": request_hash,
                    "captured_at_unix": started,
                    "raw_response": raw,
                }
            except Exception as exc:  # noqa: BLE001 - journal any post-dispatch failure
                record = {
                    "schema_version": "direct-jev-journal-v1",
                    "case_id": case_id,
                    "request_sha256": request_hash,
                    "captured_at_unix": started,
                    "error": {"type": type(exc).__name__},
                }
            atomic_new_json(journal, record)
        reserved_committed += case_reservation
        # Evidence exists on disk before any parse/progress operation.
        if "error" in record:
            errors += 1
            progress(f"{case_id}: error")
            continue
        raw = record["raw_response"]
        if raw.get("http_status") != 200:
            errors += 1
            progress(f"{case_id}: http_error")
            continue
        try:
            parsed = parse_response(raw.get("body"), config)
        except JevDecisionError:
            errors += 1
            progress(f"{case_id}: invalid_response")
            continue
        measured_spend += parsed.cost_usd
        if measured_spend > ASSESSMENT_BUDGET_USD:
            raise AssessmentRunError("captured usage exceeds assessment ceiling")
        predictions.append(
            {
                "case_id": case_id,
                "response_id": parsed.response_id,
                "model": config.model,
                "provider": config.provider,
                "request_sha256": request_hash,
                "probabilities": parsed.probabilities,
                "evidence_kind": "captured_real",
                "usage": {
                    "cost_usd": format(parsed.cost_usd, "f"),
                    "input_tokens": parsed.input_tokens,
                    "output_tokens": parsed.output_tokens,
                },
            }
        )
        progress(f"{case_id}: captured")
    summary = {
        "schema_version": "direct-jev-run-v1",
        "physical_calls_this_run": calls,
        "captured_predictions": len(predictions),
        "errors": errors,
        "complete": len(predictions) == len(corpus["cases"]),
        "predictions": predictions,
    }
    summary_path = (
        output_dir
        / f"run-summary-{hashlib.sha256(_canonical(summary)).hexdigest()}.json"
    )
    if not summary_path.exists():
        atomic_new_json(summary_path, summary)
    return summary


def deterministic_live_manifest(
    hits_path: Path, *, sample_size: int = 56
) -> dict[str, Any]:
    # Iterate physical JSONL records; str.splitlines() also splits valid JSON
    # strings containing Unicode NEL/line-separator characters.
    with hits_path.open() as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    unique = {str(row["tweet_id"]): row for row in rows}
    ordered = sorted(
        unique.values(),
        key=lambda row: hashlib.sha256(str(row["tweet_id"]).encode()).hexdigest(),
    )
    selected = ordered[:sample_size]
    return {
        "schema_version": "rare-type-unlabeled-live-cohort-v1",
        "selection": "ascending_sha256_tweet_id",
        "source_path": str(hits_path),
        "source_row_count": len(rows),
        "source_unique_post_count": len(unique),
        "requested_sample_size": sample_size,
        "selected_count": len(selected),
        "source_cap_state": "historical_probe_cursor_chains_exhausted",
        "human_labels_present": False,
        "posts": [
            {
                "tweet_id": str(row["tweet_id"]),
                "text": row.get("text"),
                "author_handle": row.get("author_handle"),
                "source_url": row.get("source_url"),
            }
            for row in selected
        ],
    }


def build_assessment(
    *,
    fixture_path: Path,
    predictions: list[Mapping[str, Any]],
    config: JevDecisionsConfig,
    live_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Score only after complete captured predictions and human live labels exist."""
    from x_monitor.rare_type_extra_search import QUERY_VERSION, planned_query_string
    from x_monitor.rare_type_quality_gate import (
        assessment_identity,
        complete_assessment,
    )

    corpus = json.loads(fixture_path.read_text())
    estimated = sum(
        (Decimal(str(row["usage"]["cost_usd"])) for row in predictions), Decimal(0)
    )
    reserved = sum(
        (
            conservative_reservation_usd(_request(case, config)[0], config)
            for case in corpus["cases"]
        ),
        Decimal(0),
    )
    identity = assessment_identity(
        query_version=QUERY_VERSION,
        planner_query=planned_query_string(),
        config=config,
        fixture_path=fixture_path,
    )
    return complete_assessment(
        identity=identity,
        corpus=corpus,
        predictions=predictions,
        config=config,
        live_evidence=live_evidence,
        budget={
            "reserved_usd": format(reserved, "f"),
            "confirmed_usd": None,
            "estimated_usd_from_usage": format(estimated, "f"),
            "usage_complete": len(predictions) == len(corpus["cases"]),
        },
    )

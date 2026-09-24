"""Bounded, resumable direct-TypeSafe assessment support.

The runner deliberately does not know reference labels while making requests.
Each provider result is durably journaled before it is parsed or reported.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
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
from x_monitor.rare_type_quality_gate import ASSESSMENT_BUDGET_USD, _canonical_bytes

MAX_PHYSICAL_CALLS = 56
DIRECT_KEY_ENV = "TYPESAFE_API_KEY"
BLIND_LABELS_DECLARATION = (
    "No Jev predictions, assessment journal, run summary, other-agent labels, "
    "or model outputs were read."
)


class AssessmentRunError(RuntimeError):
    pass


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
            handle.write(_canonical_bytes(value) + b"\n")
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


def atomic_new_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
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
        / f"run-summary-{hashlib.sha256(_canonical_bytes(summary)).hexdigest()}.json"
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


def _read_json_object(path: Path, *, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssessmentRunError(f"{description} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise AssessmentRunError(f"{description} must be a JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise AssessmentRunError(f"evidence file is unreadable: {path}") from exc


def _load_archived_provider_receipts(
    *,
    corpus: Mapping[str, Any],
    run_dir: Path,
    config: JevDecisionsConfig,
    accepted_http_errors: Mapping[str, int],
) -> dict[str, Any]:
    """Rebuild one provider run from its immutable per-attempt journals."""

    cases = corpus.get("cases")
    if not isinstance(cases, list) or len(cases) != MAX_PHYSICAL_CALLS:
        raise AssessmentRunError(
            f"archived run requires exactly {MAX_PHYSICAL_CALLS} cases"
        )
    case_ids = [case.get("id") for case in cases if isinstance(case, Mapping)]
    if (
        len(case_ids) != len(cases)
        or any(not isinstance(case_id, str) or not case_id for case_id in case_ids)
        or len(set(case_ids)) != len(case_ids)
    ):
        raise AssessmentRunError("archived corpus case identities are invalid")
    if not set(accepted_http_errors) <= set(case_ids):
        raise AssessmentRunError("accepted provider error IDs are outside the corpus")
    if any(
        isinstance(status, bool) or not isinstance(status, int) or status == 200
        for status in accepted_http_errors.values()
    ):
        raise AssessmentRunError("accepted provider error statuses are invalid")

    expected: dict[str, tuple[Mapping[str, Any], str]] = {}
    for case in cases:
        _request_bytes, request_hash = _request(case, config)
        filename = f"{case['id']}--{request_hash}.json"
        expected[filename] = (case, request_hash)
    journal_dir = run_dir / "journal"
    actual_paths = sorted(journal_dir.glob("*.json"))
    actual_names = {path.name for path in actual_paths}
    if actual_names != set(expected):
        missing = sorted(set(expected) - actual_names)
        unexpected = sorted(actual_names - set(expected))
        raise AssessmentRunError(
            "archived journal set mismatch: "
            f"missing={missing!r} unexpected={unexpected!r}"
        )

    predictions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    receipt_hashes: list[dict[str, str]] = []
    estimated_usage = Decimal(0)
    reservation = Decimal(0)
    for path in actual_paths:
        case, request_hash = expected[path.name]
        case_id = str(case["id"])
        request_bytes, recomputed_hash = _request(case, config)
        if recomputed_hash != request_hash:
            raise AssessmentRunError(f"request identity changed: {case_id}")
        reservation += conservative_reservation_usd(request_bytes, config)
        record = _read_json_object(path, description="provider journal")
        if (
            record.get("schema_version") != "direct-jev-journal-v1"
            or record.get("case_id") != case_id
            or record.get("request_sha256") != request_hash
        ):
            raise AssessmentRunError(f"provider journal identity mismatch: {case_id}")
        captured_at = record.get("captured_at_unix")
        if (
            isinstance(captured_at, bool)
            or not isinstance(captured_at, (int, float))
            or captured_at <= 0
        ):
            raise AssessmentRunError(f"provider capture timestamp invalid: {case_id}")
        if "error" in record:
            raise AssessmentRunError(
                f"transport/runtime error is not an accepted HTTP receipt: {case_id}"
            )
        raw = record.get("raw_response")
        if not isinstance(raw, Mapping):
            raise AssessmentRunError(f"provider response missing: {case_id}")
        status = raw.get("http_status")
        if isinstance(status, bool) or not isinstance(status, int):
            raise AssessmentRunError(f"provider HTTP status invalid: {case_id}")
        receipt_sha256 = _sha256_file(path)
        receipt_hashes.append({"filename": path.name, "sha256": receipt_sha256})
        if status != 200:
            if accepted_http_errors.get(case_id) != status:
                raise AssessmentRunError(
                    f"unapproved provider HTTP error: {case_id} status={status}"
                )
            error_hash = raw.get("error_body_sha256")
            error_bytes = raw.get("error_body_bytes")
            if (
                not isinstance(error_hash, str)
                or len(error_hash) != 64
                or any(character not in "0123456789abcdef" for character in error_hash)
                or isinstance(error_bytes, bool)
                or not isinstance(error_bytes, int)
                or error_bytes < 0
            ):
                raise AssessmentRunError(
                    f"provider HTTP error receipt invalid: {case_id}"
                )
            errors.append(
                {
                    "case_id": case_id,
                    "http_status": status,
                    "request_sha256": request_hash,
                    "error_body_sha256": error_hash,
                    "error_body_bytes": error_bytes,
                    "receipt_sha256": receipt_sha256,
                    "usage": "unknown",
                }
            )
            continue
        if case_id in accepted_http_errors:
            raise AssessmentRunError(
                f"accepted error unexpectedly has a successful receipt: {case_id}"
            )
        try:
            parsed = parse_response(raw.get("body"), config)
        except JevDecisionError as exc:
            raise AssessmentRunError(
                f"archived provider response is invalid: {case_id}"
            ) from exc
        estimated_usage += parsed.cost_usd
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
    if {row["case_id"] for row in errors} != set(accepted_http_errors):
        raise AssessmentRunError("accepted provider error set is incomplete")
    return {
        "physical_attempts": len(actual_paths),
        "successful_responses": len(predictions),
        "errors": errors,
        "predictions": predictions,
        "estimated_usage_usd": estimated_usage,
        "conservative_reservation_usd": reservation,
        "receipt_manifest_sha256": hashlib.sha256(
            _canonical_bytes(receipt_hashes)
        ).hexdigest(),
    }


def _validated_independent_labels(
    *,
    labels_path: Path,
    live_corpus: Mapping[str, Any],
    live_corpus_sha256: str,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    from x_monitor.rare_type_quality_gate import DOMAIN_TYPES

    artifact = _read_json_object(
        labels_path, description="independent source-label artifact"
    )
    if (
        artifact.get("schema_version")
        != "rare-type-live56-independent-source-labels-v1"
        or artifact.get("artifact_status")
        != "machine-reviewed source labels; not human gold"
    ):
        raise AssessmentRunError("independent label artifact identity is invalid")
    method = artifact.get("method")
    if (
        not isinstance(method, Mapping)
        or method.get("blindness") != BLIND_LABELS_DECLARATION
        or method.get("external_fact_verification") is not False
    ):
        raise AssessmentRunError("independent labels do not attest blind review")
    source = artifact.get("source")
    cases = live_corpus.get("cases")
    if not isinstance(cases, list):
        raise AssessmentRunError("live corpus cases missing")
    case_ids = [case.get("id") for case in cases if isinstance(case, Mapping)]
    if (
        not isinstance(source, Mapping)
        or source.get("corpus_sha256") != live_corpus_sha256
        or source.get("corpus_schema_version") != live_corpus.get("schema_version")
        or source.get("selection") != manifest.get("selection")
        or source.get("source_unique_post_count")
        != manifest.get("source_unique_post_count")
        or source.get("reviewed_case_count") != len(case_ids)
    ):
        raise AssessmentRunError("independent label source identity mismatch")
    labels = artifact.get("labels")
    if not isinstance(labels, list) or len(labels) != len(case_ids):
        raise AssessmentRunError("independent labels are incomplete")
    allowed_keys = {
        "index",
        "id",
        "label",
        "types",
        "candidate_types",
        "rationale",
        "noise_family",
        "recruiter_account",
        "job_mill",
        "uncertainty",
    }
    if any(not isinstance(label, Mapping) or set(label) != allowed_keys for label in labels):
        raise AssessmentRunError("independent label row schema is invalid")
    if [label.get("id") for label in labels] != case_ids or [
        label.get("index") for label in labels
    ] != list(range(len(case_ids))):
        raise AssessmentRunError("independent label IDs/order do not match corpus")
    by_id: dict[str, Mapping[str, Any]] = {}
    label_counts: Counter[str] = Counter()
    keep_type_counts: Counter[str] = Counter()
    uncertain_type_counts: Counter[str] = Counter()
    recruiter_count = 0
    job_mill_count = 0
    domain_types = set(DOMAIN_TYPES)
    for label in labels:
        case_id = str(label["id"])
        verdict = label.get("label")
        types = label.get("types")
        candidate_types = label.get("candidate_types")
        if verdict not in {"keep", "drop", "uncertain"}:
            raise AssessmentRunError(f"independent label invalid: {case_id}")
        if (
            not isinstance(types, list)
            or not isinstance(candidate_types, list)
            or len(types) != len(set(types))
            or len(candidate_types) != len(set(candidate_types))
            or not set(types) <= domain_types
            or not set(candidate_types) <= domain_types
        ):
            raise AssessmentRunError(f"independent label types invalid: {case_id}")
        if (
            (verdict == "keep" and (not types or candidate_types))
            or (verdict == "drop" and (types or candidate_types))
            or (verdict == "uncertain" and types)
        ):
            raise AssessmentRunError(f"independent label semantics invalid: {case_id}")
        if not isinstance(label.get("recruiter_account"), bool) or not isinstance(
            label.get("job_mill"), bool
        ):
            raise AssessmentRunError(f"independent label flags invalid: {case_id}")
        label_counts[verdict] += 1
        keep_type_counts.update(types)
        if verdict == "uncertain":
            if candidate_types:
                uncertain_type_counts.update(candidate_types)
            else:
                uncertain_type_counts["unresolved_no_type"] += 1
        recruiter_count += int(label["recruiter_account"])
        job_mill_count += int(label["job_mill"])
        by_id[case_id] = label
    expected_summary = {
        "keep": label_counts["keep"],
        "drop": label_counts["drop"],
        "uncertain": label_counts["uncertain"],
        "keep_type_counts": {
            type_name: keep_type_counts[type_name] for type_name in DOMAIN_TYPES
        },
        "uncertain_candidate_type_counts": {
            type_name: uncertain_type_counts[type_name]
            for type_name in (
                "events",
                "opportunities",
                "model_releases",
                "unresolved_no_type",
            )
        },
        "recruiter_or_recruiting_adjacent_accounts": recruiter_count,
        "job_mill_cases": job_mill_count,
    }
    if artifact.get("summary") != expected_summary:
        raise AssessmentRunError("independent label summary does not match rows")
    return expected_summary, by_id


def assemble_archived_sample_assessment(
    *,
    fixture_path: Path,
    frozen_run_dir: Path,
    live_manifest_path: Path,
    live_run_dir: Path,
    independent_labels_path: Path,
    config: JevDecisionsConfig,
    expected_live_corpus_sha256: str,
    accepted_live_http_errors: Mapping[str, int],
    source_window_count: int,
    source_estimated_credits: int,
) -> dict[str, Any]:
    """Assemble a gate artifact from archived evidence without provider calls."""

    from x_monitor.jev_decisions import derive_gate_outcome
    from x_monitor.rare_type_extra_search import QUERY_VERSION, planned_query_string
    from x_monitor.rare_type_quality_gate import (
        ASSESSMENT_BUDGET_USD,
        FUNCTIONAL_EXEMPLARS,
        _corpus_reasons,
        assessment_identity,
        evaluate_fixture_predictions,
    )

    if (
        isinstance(source_window_count, bool)
        or not isinstance(source_window_count, int)
        or source_window_count <= 0
        or isinstance(source_estimated_credits, bool)
        or not isinstance(source_estimated_credits, int)
        or source_estimated_credits < 0
    ):
        raise AssessmentRunError("archived source cost facts are invalid")
    fixture_corpus = _read_json_object(fixture_path, description="frozen fixture")
    live_corpus_path = live_run_dir / "corpus.json"
    live_corpus_sha256 = _sha256_file(live_corpus_path)
    if live_corpus_sha256 != expected_live_corpus_sha256:
        raise AssessmentRunError("live corpus SHA-256 mismatch")
    live_corpus = _read_json_object(live_corpus_path, description="live corpus")
    if live_corpus.get("schema_version") != "rare-type-live-direct-corpus-v1":
        raise AssessmentRunError("live corpus schema version mismatch")
    manifest = _read_json_object(
        live_manifest_path, description="unlabeled live manifest"
    )
    if (
        manifest.get("schema_version") != "rare-type-unlabeled-live-cohort-v1"
        or manifest.get("selection") != "ascending_sha256_tweet_id"
        or manifest.get("human_labels_present") is not False
        or manifest.get("source_cap_state")
        != "historical_probe_cursor_chains_exhausted"
    ):
        raise AssessmentRunError("unlabeled live manifest identity is invalid")
    manifest_posts = manifest.get("posts")
    live_cases = live_corpus.get("cases")
    if not isinstance(manifest_posts, list) or not isinstance(live_cases, list):
        raise AssessmentRunError("live sample rows are missing")
    manifest_ids = [str(post.get("tweet_id")) for post in manifest_posts]
    live_ids = [case.get("id") for case in live_cases if isinstance(case, Mapping)]
    if (
        len(manifest_ids) != MAX_PHYSICAL_CALLS
        or manifest_ids != live_ids
        or len(set(manifest_ids)) != len(manifest_ids)
        or manifest.get("requested_sample_size") != MAX_PHYSICAL_CALLS
        or manifest.get("selected_count") != MAX_PHYSICAL_CALLS
        or manifest.get("source_row_count") != manifest.get("source_unique_post_count")
        or manifest.get("source_unique_post_count", 0) < MAX_PHYSICAL_CALLS
    ):
        raise AssessmentRunError("live manifest IDs/counts do not match corpus")

    label_summary, labels_by_id = _validated_independent_labels(
        labels_path=independent_labels_path,
        live_corpus=live_corpus,
        live_corpus_sha256=live_corpus_sha256,
        manifest=manifest,
    )
    frozen = _load_archived_provider_receipts(
        corpus=fixture_corpus,
        run_dir=frozen_run_dir,
        config=config,
        accepted_http_errors={},
    )
    live = _load_archived_provider_receipts(
        corpus=live_corpus,
        run_dir=live_run_dir,
        config=config,
        accepted_http_errors=accepted_live_http_errors,
    )
    fixture_metrics = evaluate_fixture_predictions(
        corpus=fixture_corpus,
        predictions=frozen["predictions"],
        config=config,
    )
    functional_reasons = _corpus_reasons(fixture_corpus)
    if fixture_metrics["evidence_kind"] != "captured_real":
        functional_reasons.append("mock_only_evidence")
    if fixture_metrics["hard_negative_false_keeps"]:
        functional_reasons.append("hard_negative_false_keep")
    fixture_rows = {row["case_id"]: row for row in fixture_metrics["rows"]}
    for case_id, expected_types in FUNCTIONAL_EXEMPLARS.items():
        row = fixture_rows.get(case_id)
        if (
            row is None
            or row["outcome"] != "kept"
            or row["derived_types"] != list(expected_types)
        ):
            functional_reasons.append(f"functional_exemplar_failed:{case_id}")
    if functional_reasons:
        raise AssessmentRunError(
            "frozen functional evidence failed: "
            + ", ".join(dict.fromkeys(functional_reasons))
        )

    cases_by_id = {case["id"]: case for case in live_cases}
    comparison: Counter[tuple[str, str]] = Counter()
    routed_type_counts: Counter[tuple[str, str]] = Counter()
    for prediction in live["predictions"]:
        case_id = prediction["case_id"]
        outcome, routed_types = derive_gate_outcome(
            prediction["probabilities"],
            config,
            state=public_post_state(cases_by_id[case_id]["public_payload"]),
        )
        outcome_value = getattr(outcome, "value", str(outcome))
        verdict = str(labels_by_id[case_id]["label"])
        comparison[(verdict, outcome_value)] += 1
        for type_name in routed_types:
            routed_type_counts[(verdict, type_name)] += 1
    for error in live["errors"]:
        comparison[
            (str(labels_by_id[error["case_id"]]["label"]), "provider_error_accepted")
        ] += 1

    total_attempts = frozen["physical_attempts"] + live["physical_attempts"]
    total_successes = frozen["successful_responses"] + live["successful_responses"]
    total_errors = len(frozen["errors"]) + len(live["errors"])
    total_estimated_usage = (
        frozen["estimated_usage_usd"] + live["estimated_usage_usd"]
    )
    total_reservation = (
        frozen["conservative_reservation_usd"]
        + live["conservative_reservation_usd"]
    )
    if total_reservation > ASSESSMENT_BUDGET_USD:
        raise AssessmentRunError("archived all-attempt reservation exceeds ceiling")
    identity = assessment_identity(
        query_version=QUERY_VERSION,
        planner_query=planned_query_string(),
        config=config,
        fixture_path=fixture_path,
    )
    assessment: dict[str, Any] = {
        "schema_version": "rare-type-quality-assessment-v3",
        "assessment_mode": "archived_deterministic_sample",
        "identity": identity,
        "status": "pass",
        "quality_gate_passed": True,
        "enablement_eligible": False,
        "enablement_approved": False,
        "reasons": [],
        "decision_basis": {
            "numeric_quality_thresholds": None,
            "functional_fixture_required": True,
            "complete_archived_accounting_required": True,
            "owner_accepted_live_http_errors": sorted(
                accepted_live_http_errors
            ),
        },
        "fixture_metrics": fixture_metrics,
        "archived_sample_evidence": {
            "source_sample": {
                "manifest_sha256": _sha256_file(live_manifest_path),
                "live_corpus_sha256": live_corpus_sha256,
                "selection": manifest["selection"],
                "historical_window_count": source_window_count,
                "historical_raw_post_count": manifest["source_row_count"],
                "historical_unique_post_count": manifest[
                    "source_unique_post_count"
                ],
                "historical_estimated_credits": source_estimated_credits,
                "selected_post_count": len(live_ids),
                "incremental_credits_for_archived_sample": 0,
                "provider_exhaustion_scope": (
                    "captured historical window chains only; not future X coverage"
                ),
            },
            "independent_labels": {
                "artifact_sha256": _sha256_file(independent_labels_path),
                "schema_version": (
                    "rare-type-live56-independent-source-labels-v1"
                ),
                "blind_to_provider_outputs": True,
                "human_gold": False,
                "externally_fact_verified": False,
                "counts": {
                    "keep": label_summary["keep"],
                    "drop": label_summary["drop"],
                    "uncertain": label_summary["uncertain"],
                },
                "keep_type_counts": label_summary["keep_type_counts"],
                "uncertain_candidate_type_counts": label_summary[
                    "uncertain_candidate_type_counts"
                ],
                "recruiter_or_recruiting_adjacent_accounts": label_summary[
                    "recruiter_or_recruiting_adjacent_accounts"
                ],
                "job_mill_cases": label_summary["job_mill_cases"],
            },
            "provider_capture": {
                "physical_attempts": total_attempts,
                "successful_responses": total_successes,
                "accepted_http_errors": total_errors,
                "provider_capture_complete": total_errors == 0,
                "successful_usage_complete": total_successes
                == len(frozen["predictions"]) + len(live["predictions"]),
                "unknown_usage_attempts": total_errors,
                "estimated_usd_from_successful_usage": format(
                    total_estimated_usage, "f"
                ),
                "conservative_all_attempt_reservation_usd": format(
                    total_reservation, "f"
                ),
                "ceiling_usd": format(ASSESSMENT_BUDGET_USD, "f"),
                "invoice_confirmed": False,
                "http_retries": 0,
                "frozen_run": {
                    "attempts": frozen["physical_attempts"],
                    "successful_responses": frozen["successful_responses"],
                    "errors": frozen["errors"],
                    "receipt_manifest_sha256": frozen[
                        "receipt_manifest_sha256"
                    ],
                },
                "live_run": {
                    "attempts": live["physical_attempts"],
                    "successful_responses": live["successful_responses"],
                    "errors": live["errors"],
                    "receipt_manifest_sha256": live["receipt_manifest_sha256"],
                },
            },
            "live_label_route_counts": [
                {
                    "source_label": source_label,
                    "jev_outcome": outcome,
                    "count": count,
                }
                for (source_label, outcome), count in sorted(comparison.items())
            ],
            "live_routed_type_counts": [
                {
                    "source_label": source_label,
                    "routed_type": type_name,
                    "count": count,
                }
                for (source_label, type_name), count in sorted(
                    routed_type_counts.items()
                )
            ],
        },
        "budget": {
            "ceiling_usd": format(ASSESSMENT_BUDGET_USD, "f"),
            "reserved_usd": format(total_reservation, "f"),
            "confirmed_usd": None,
            "estimated_usd_from_usage": format(total_estimated_usage, "f"),
            "invoice_confirmed": False,
            "usage_complete": total_errors == 0,
            "successful_attempt_usage_complete": True,
            "unknown_usage_attempts": total_errors,
        },
        "limitations": [
            "The live provider capture contains accepted HTTP errors and is not complete.",
            "The independent source labels are blind machine review, not human gold.",
            "The frozen fixture was used to tune routing and is not prospective quality evidence.",
            "The archived live sample measures the captured historical corpus, not future X coverage.",
            "Source review included captured article context that Jev's public-state serializer did not always receive.",
        ],
    }
    assessment["assessment_digest"] = hashlib.sha256(
        _canonical_bytes(assessment)
    ).hexdigest()
    return assessment


def render_archived_assessment_report(assessment: Mapping[str, Any]) -> str:
    """Render the concise human companion to a verified archived artifact."""

    evidence = assessment["archived_sample_evidence"]
    source = evidence["source_sample"]
    labels = evidence["independent_labels"]
    provider = evidence["provider_capture"]
    live_rows = evidence["live_label_route_counts"]
    route_lines = "\n".join(
        f"| {row['source_label']} | {row['jev_outcome']} | {row['count']} |"
        for row in live_rows
    )
    return f"""---
title: Rare-Type Archived Live56 Assessment
date: 2026-09-24
topic: combined-rare-type-extra-search
status: {assessment['status']}
---

# Rare-Type Archived Live56 Assessment

This offline finalization passed the functional, identity, receipt, and budget checks for the pinned rare-type tuple. It used frozen evidence only: no retries or new provider calls were made. There is no numeric precision, recall, yield, overlap, or junk-share release bar.

## Evidence

- Source sample: {source['selected_post_count']} posts selected deterministically from {source['historical_unique_post_count']} unique rows across {source['historical_window_count']} historical quarter-hour windows. The source search estimate was {source['historical_estimated_credits']} credits; selecting and assessing the archived sample spent zero incremental TwitterAPI credits.
- Independent labels: {labels['counts']['keep']} keep, {labels['counts']['drop']} drop, and {labels['counts']['uncertain']} uncertain. These are blind machine-reviewed source labels, not human gold, and were not externally fact-verified.
- TypeSafe receipts: {provider['physical_attempts']} physical attempts, {provider['successful_responses']} successful responses, and {provider['accepted_http_errors']} owner-accepted HTTP errors with unknown usage. The capture is explicitly not represented as complete.
- Cost: successful token receipts estimate ${provider['estimated_usd_from_successful_usage']}; conservative reservation across every attempt is ${provider['conservative_all_attempt_reservation_usd']} against the ${provider['ceiling_usd']} ceiling. Neither amount is an invoice.

## Blind-label / Jev outcomes

| Source label | Jev outcome | Cases |
| --- | --- | ---: |
{route_lines}

All definite keep labels in this archived live sample are model or harness releases. The sample supplies no live-positive coverage for personnel changes, jobs, events, or opportunities. Source review could use captured article context that was not always present in Jev's public-state serializer.

The two accepted HTTP failures remain errors with unknown usage; they were not retried, relabeled from provider output, or replaced with fabricated responses. The frozen fixture was used while tuning routing, so its functional result is in-sample rather than a prospective quality estimate.

Runtime assessment digest: `{assessment['assessment_digest']}`.
"""


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

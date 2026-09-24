from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from x_monitor.config import load_config
from x_monitor.jev_decisions import QUESTION_SET

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/rare_type_extra_search/gate_cases.json"


def _corpus():
    return json.loads(FIXTURE.read_text())


def _config():
    return load_config(REPO / "config.yaml").discovery.rare_types.jev


def _sender(request_bytes, config):
    # Exact direct System One shape has no response ID.
    return {
        "http_status": 200,
        "body": {
            "model": config.model,
            "usage": {"input_tokens": 100, "output_tokens": 0},
            "answers": {name: {"type": "noul", "noul": 0.1} for name in QUESTION_SET},
        },
    }


def test_preflight_is_bounded_and_secret_free(monkeypatch):
    from x_monitor.jev_assessment_runner import preflight

    monkeypatch.setenv("TYPESAFE_API_KEY", "do-not-print-this")
    result = preflight(_corpus(), _config())
    assert result["ready"] is True
    assert result["case_count"] == result["max_physical_calls"] == 56
    assert float(result["reserved_usd"]) <= 0.25
    assert "do-not-print-this" not in json.dumps(result)


def test_direct_send_posts_exact_contract_once_without_printing_secret(
    monkeypatch, capsys
):
    from x_monitor.jev_assessment_runner import _direct_send

    secret = "direct-secret-sentinel"
    request_bytes = b'{"model":"jev-1.13.0"}'
    calls = []
    response_body = {
        "model": _config().model,
        "usage": {"input_tokens": 12, "output_tokens": 0},
        "answers": {},
    }

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=response_body)

    monkeypatch.setenv("TYPESAFE_API_KEY", secret)
    monkeypatch.setattr("x_monitor.jev_assessment_runner.httpx.post", post)

    result = _direct_send(request_bytes, _config())

    assert result == {"http_status": 200, "body": response_body}
    assert calls == [
        (
            _config().endpoint,
            {
                "content": request_bytes,
                "headers": {
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/json",
                },
                "timeout": _config().request_timeout_seconds,
            },
        )
    ]
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_direct_send_redacts_non_200_body_and_never_retries(monkeypatch):
    from x_monitor.jev_assessment_runner import _direct_send

    secret = "provider-echoed-secret"
    calls = 0

    def post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return httpx.Response(529, content=f"error echoed {secret}".encode())

    monkeypatch.setenv("TYPESAFE_API_KEY", "credential-sentinel")
    monkeypatch.setattr("x_monitor.jev_assessment_runner.httpx.post", post)

    result = _direct_send(b"{}", _config())

    assert calls == 1
    assert result["http_status"] == 529
    assert result["error_body_bytes"] == len(f"error echoed {secret}".encode())
    assert result["error_body_sha256"] == hashlib.sha256(
        f"error echoed {secret}".encode()
    ).hexdigest()
    assert secret not in json.dumps(result)
    assert "body" not in result


def test_direct_send_hashes_malformed_200_body_without_retry(monkeypatch):
    from x_monitor.jev_assessment_runner import _direct_send

    malformed = b'{"model":'
    calls = 0

    def post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=malformed)

    monkeypatch.setenv("TYPESAFE_API_KEY", "credential-sentinel")
    monkeypatch.setattr("x_monitor.jev_assessment_runner.httpx.post", post)

    assert _direct_send(b"{}", _config()) == {
        "http_status": 200,
        "body": {
            "unparseable_body_sha256": hashlib.sha256(malformed).hexdigest()
        },
    }
    assert calls == 1


def test_direct_send_sanitizes_request_error_and_never_retries(monkeypatch):
    from x_monitor.jev_assessment_runner import AssessmentRunError, _direct_send

    secret = "transport-secret-sentinel"
    calls = 0

    def post(url, **_kwargs):
        nonlocal calls
        calls += 1
        request = httpx.Request("POST", url)
        raise httpx.ConnectError(f"connection failed with {secret}", request=request)

    monkeypatch.setenv("TYPESAFE_API_KEY", "credential-sentinel")
    monkeypatch.setattr("x_monitor.jev_assessment_runner.httpx.post", post)

    with pytest.raises(AssessmentRunError) as raised:
        _direct_send(b"{}", _config())

    assert str(raised.value) == "transport_error:ConnectError"
    assert secret not in str(raised.value)
    assert calls == 1


def test_direct_send_missing_key_fails_before_transport(monkeypatch):
    from x_monitor.jev_assessment_runner import AssessmentRunError, _direct_send

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(
        "x_monitor.jev_assessment_runner.httpx.post",
        lambda *_args, **_kwargs: pytest.fail("missing key must prevent transport"),
    )

    with pytest.raises(AssessmentRunError, match="direct TypeSafe credential missing"):
        _direct_send(b"{}", _config())


def test_runner_journals_then_resumes_without_more_calls(tmp_path, monkeypatch):
    from x_monitor.jev_assessment_runner import run

    calls = []

    def sender(request, config):
        calls.append(request)
        return _sender(request, config)

    first = run(
        corpus=_corpus(),
        config=_config(),
        output_dir=tmp_path,
        sender=sender,
        progress=lambda _: None,
    )
    assert first["physical_calls_this_run"] == 56
    assert first["complete"] is True
    assert len(list((tmp_path / "journal").glob("*.json"))) == 56
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    second = run(
        corpus=_corpus(),
        config=_config(),
        output_dir=tmp_path,
        progress=lambda _: None,
    )
    assert second["physical_calls_this_run"] == 0
    assert len(calls) == 56


def test_error_is_journaled_and_never_retried(tmp_path):
    from x_monitor.jev_assessment_runner import run

    calls = 0

    def sender(request, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("sentinel")
        return _sender(request, config)

    first = run(
        corpus=_corpus(),
        config=_config(),
        output_dir=tmp_path,
        sender=sender,
        progress=lambda _: None,
    )
    assert first["errors"] == 1 and not first["complete"]
    error_record = next(
        json.loads(path.read_text())
        for path in (tmp_path / "journal").glob("*.json")
        if "error" in json.loads(path.read_text())
    )
    assert error_record["error"] == {"type": "RuntimeError"}
    run(
        corpus=_corpus(),
        config=_config(),
        output_dir=tmp_path,
        sender=sender,
        progress=lambda _: None,
    )
    assert calls == 56


def test_runner_rejects_stale_request_identity_before_any_call(tmp_path):
    import pytest

    from x_monitor.jev_assessment_runner import AssessmentRunError, run

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / "old-case--old-request.json").write_text("{}")
    calls = 0

    def sender(request, config):
        nonlocal calls
        calls += 1
        return _sender(request, config)

    with pytest.raises(AssessmentRunError, match="different case or request identity"):
        run(
            corpus=_corpus(),
            config=_config(),
            output_dir=tmp_path,
            sender=sender,
            progress=lambda _: None,
        )
    assert calls == 0


def test_runner_stops_when_attested_usage_exceeds_ceiling(tmp_path):
    import pytest

    from x_monitor.jev_assessment_runner import AssessmentRunError, run

    calls = 0

    def sender(request, config):
        nonlocal calls
        calls += 1
        response = _sender(request, config)
        response["body"]["usage"]["input_tokens"] = 6_000_000
        return response

    with pytest.raises(AssessmentRunError, match="usage exceeds"):
        run(
            corpus=_corpus(),
            config=_config(),
            output_dir=tmp_path,
            sender=sender,
            progress=lambda _: None,
        )
    assert calls == 1
    assert len(list((tmp_path / "journal").glob("*.json"))) == 1


def test_live_manifest_is_deterministic_unlabeled_and_keeps_denominator(tmp_path):
    from x_monitor.jev_assessment_runner import deterministic_live_manifest

    source = tmp_path / "hits.jsonl"
    source.write_text(
        "\n".join(
            json.dumps({"tweet_id": str(i), "text": f"post {i}"}) for i in range(80)
        )
    )
    one = deterministic_live_manifest(source)
    two = deterministic_live_manifest(source)
    assert one == two
    assert one["source_row_count"] == one["source_unique_post_count"] == 80
    assert one["selected_count"] == 56
    assert one["human_labels_present"] is False
    assert all("reference" not in post for post in one["posts"])


def test_build_assessment_uses_exact_v3_identity_and_direct_usage_estimate(tmp_path):
    from x_monitor.jev_assessment_runner import build_assessment, run
    from x_monitor.rare_type_extra_search import QUERY_VERSION

    summary = run(
        corpus=_corpus(),
        config=_config(),
        output_dir=tmp_path,
        sender=_sender,
        progress=lambda _: None,
    )
    live = {
        "overlap_source": "production_read_only_exact_ids",
        "cohorts": [
            {
                "cohort_id": "v3-human-labeled",
                "post_ids": ["1"],
                "raw_paid_result_count": 1,
                "captured_assessable_count": 1,
                "estimated_credits": 15,
                "independently_read_keepers": 0,
                "already_stored": 0,
                "mill": 0,
                "recruiter": 0,
            }
        ],
    }
    assessment = build_assessment(
        fixture_path=FIXTURE,
        predictions=summary["predictions"],
        config=_config(),
        live_evidence=live,
    )
    assert all(row["response_id"] == "" for row in summary["predictions"])
    assert assessment["identity"]["query_version"] == QUERY_VERSION
    assert assessment["budget"]["usage_complete"] is True
    assert assessment["budget"]["invoice_confirmed"] is False


def _write_archived_assessment_inputs(tmp_path: Path):
    from x_monitor.jev_assessment_runner import _request, run

    def probabilities(reference):
        values = {name: 0.1 for name in QUESTION_SET}
        if reference["types"]:
            values["ai_related"] = 0.9
        if "personnel_changes" in reference["types"]:
            values.update(person_identity=0.9, role_change=0.9)
        if "job_listings" in reference["types"]:
            values["role_opening"] = 0.9
        if "events" in reference["types"]:
            values["attendance_event"] = 0.9
        if "opportunities" in reference["types"]:
            values["bounded_opportunity"] = 0.9
        if "model_releases" in reference["types"]:
            values.update(model_release=0.9, source_announcement=0.9)
        hard_negative = reference.get("hard_negative")
        if hard_negative in {
            "mill",
            "lineup",
            "f1",
            "joke",
            "static_bio",
            "price_only",
            "conference_ad",
        }:
            values[f"junk_{hard_negative}"] = 0.9
        return values

    fixture_by_request = {
        _request(case, _config())[1]: case for case in _corpus()["cases"]
    }

    def frozen_sender(request_bytes, config):
        case = fixture_by_request[hashlib.sha256(request_bytes).hexdigest()]
        response = _sender(request_bytes, config)
        response["body"]["answers"] = {
            name: {"type": "noul", "noul": value}
            for name, value in probabilities(case["reference"]).items()
        }
        return response

    frozen_dir = tmp_path / "frozen"
    frozen_summary = run(
        corpus=_corpus(),
        config=_config(),
        output_dir=frozen_dir,
        sender=frozen_sender,
        progress=lambda _: None,
    )
    assert frozen_summary["complete"] is True

    live_cases = []
    live_reference_by_id = {}
    labels = []
    keep_type_counts = {
        "personnel_changes": 0,
        "job_listings": 0,
        "events": 0,
        "opportunities": 0,
        "model_releases": 0,
    }
    for index, fixture_case in enumerate(_corpus()["cases"]):
        case_id = f"live-{index:02d}"
        live_cases.append(
            {"id": case_id, "public_payload": fixture_case["public_payload"]}
        )
        reference = fixture_case["reference"]
        live_reference_by_id[case_id] = reference
        label = "keep" if reference["keep"] else "drop"
        for type_name in reference["types"]:
            keep_type_counts[type_name] += 1
        labels.append(
            {
                "index": index,
                "id": case_id,
                "label": label,
                "types": reference["types"],
                "candidate_types": [],
                "rationale": "independent source-only test label",
                "noise_family": None,
                "recruiter_account": False,
                "job_mill": False,
                "uncertainty": {"level": "low", "note": None},
            }
        )
    live_corpus = {
        "schema_version": "rare-type-live-direct-corpus-v1",
        "cases": live_cases,
    }
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    corpus_path = live_dir / "corpus.json"
    corpus_path.write_text(json.dumps(live_corpus, ensure_ascii=False))
    corpus_sha256 = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    accepted_errors = {"live-00": 529, "live-55": 529}
    live_id_by_request = {
        _request(case, _config())[1]: case["id"] for case in live_cases
    }

    def live_sender(request_bytes, config):
        request_hash = hashlib.sha256(request_bytes).hexdigest()
        case_id = live_id_by_request[request_hash]
        if case_id in accepted_errors:
            return {
                "http_status": 529,
                "error_body_sha256": "a" * 64,
                "error_body_bytes": 10,
            }
        response = _sender(request_bytes, config)
        response["body"]["answers"] = {
            name: {"type": "noul", "noul": value}
            for name, value in probabilities(live_reference_by_id[case_id]).items()
        }
        return response

    live_summary = run(
        corpus=live_corpus,
        config=_config(),
        output_dir=live_dir,
        sender=live_sender,
        progress=lambda _: None,
    )
    assert live_summary["captured_predictions"] == 54
    assert live_summary["errors"] == 2

    manifest_path = tmp_path / "live-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "rare-type-unlabeled-live-cohort-v1",
                "selection": "ascending_sha256_tweet_id",
                "source_path": "/archived/hits.jsonl",
                "source_row_count": 1337,
                "source_unique_post_count": 1337,
                "requested_sample_size": 56,
                "selected_count": 56,
                "source_cap_state": "historical_probe_cursor_chains_exhausted",
                "human_labels_present": False,
                "posts": [
                    {
                        "tweet_id": case["id"],
                        "text": case["public_payload"].get("text"),
                        "author_handle": None,
                        "source_url": None,
                    }
                    for case in live_cases
                ],
            }
        )
    )
    label_path = tmp_path / "labels.json"
    keep_count = sum(label["label"] == "keep" for label in labels)
    drop_count = sum(label["label"] == "drop" for label in labels)
    label_path.write_text(
        json.dumps(
            {
                "schema_version": "rare-type-live56-independent-source-labels-v1",
                "artifact_status": "machine-reviewed source labels; not human gold",
                "created_at": "2026-09-24T16:00:00+09:00",
                "method": {
                    "review_scope": "source fields only",
                    "blindness": (
                        "No Jev predictions, assessment journal, run summary, "
                        "other-agent labels, or model outputs were read."
                    ),
                    "definitions": "test",
                    "keep_policy": "test",
                    "drop_policy": "test",
                    "uncertain_policy": "test",
                    "external_fact_verification": False,
                    "provider_failure_note": "blind source labels are independent",
                },
                "source": {
                    "corpus_path": str(corpus_path),
                    "corpus_sha256": corpus_sha256,
                    "corpus_schema_version": "rare-type-live-direct-corpus-v1",
                    "selection": "ascending_sha256_tweet_id",
                    "source_unique_post_count": 1337,
                    "reviewed_case_count": 56,
                },
                "summary": {
                    "keep": keep_count,
                    "drop": drop_count,
                    "uncertain": 0,
                    "keep_type_counts": keep_type_counts,
                    "uncertain_candidate_type_counts": {
                        "events": 0,
                        "opportunities": 0,
                        "model_releases": 0,
                        "unresolved_no_type": 0,
                    },
                    "recruiter_or_recruiting_adjacent_accounts": 0,
                    "job_mill_cases": 0,
                },
                "labels": labels,
            }
        )
    )
    return {
        "frozen_dir": frozen_dir,
        "live_dir": live_dir,
        "manifest_path": manifest_path,
        "label_path": label_path,
        "corpus_sha256": corpus_sha256,
        "accepted_errors": accepted_errors,
    }


def test_archived_sample_assembles_truthful_runtime_pinnable_assessment(tmp_path):
    from x_monitor.jev_assessment_runner import (
        assemble_archived_sample_assessment,
        render_archived_assessment_report,
    )
    from x_monitor.rare_type_quality_gate import (
        QualityEvidenceError,
        validate_assessment,
    )

    inputs = _write_archived_assessment_inputs(tmp_path)
    assessment = assemble_archived_sample_assessment(
        fixture_path=FIXTURE,
        frozen_run_dir=inputs["frozen_dir"],
        live_manifest_path=inputs["manifest_path"],
        live_run_dir=inputs["live_dir"],
        independent_labels_path=inputs["label_path"],
        config=_config(),
        expected_live_corpus_sha256=inputs["corpus_sha256"],
        accepted_live_http_errors=inputs["accepted_errors"],
        source_window_count=192,
        source_estimated_credits=22935,
    )

    assert assessment["schema_version"] == "rare-type-quality-assessment-v3"
    assert assessment["assessment_mode"] == "archived_deterministic_sample"
    assert assessment["status"] == "pass"
    assert assessment["quality_gate_passed"] is True
    assert assessment["enablement_eligible"] is False
    assert assessment["enablement_approved"] is False
    source = assessment["archived_sample_evidence"]["source_sample"]
    assert source["historical_window_count"] == 192
    assert source["historical_unique_post_count"] == 1337
    assert source["historical_estimated_credits"] == 22935
    assert source["incremental_credits_for_archived_sample"] == 0
    provider = assessment["archived_sample_evidence"]["provider_capture"]
    assert provider["physical_attempts"] == 112
    assert provider["successful_responses"] == 110
    assert provider["accepted_http_errors"] == 2
    assert provider["provider_capture_complete"] is False
    assert provider["unknown_usage_attempts"] == 2
    assert provider["successful_usage_complete"] is True
    assert provider["invoice_confirmed"] is False
    assert float(provider["estimated_usd_from_successful_usage"]) > 0
    assert float(provider["conservative_all_attempt_reservation_usd"]) <= 0.25
    assert assessment["archived_sample_evidence"]["independent_labels"][
        "blind_to_provider_outputs"
    ] is True
    assert validate_assessment(
        assessment, expected_identity=assessment["identity"]
    )
    tampered = json.loads(json.dumps(assessment))
    tampered["archived_sample_evidence"]["provider_capture"][
        "provider_capture_complete"
    ] = True
    unsigned = {
        key: value for key, value in tampered.items() if key != "assessment_digest"
    }
    tampered["assessment_digest"] = hashlib.sha256(
        json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    with pytest.raises(QualityEvidenceError, match="provider accounting"):
        validate_assessment(tampered, expected_identity=assessment["identity"])
    report = render_archived_assessment_report(assessment)
    assert "no retries or new provider calls" in report.lower()
    assert "not human gold" in report.lower()
    assert assessment["assessment_digest"] in report


@pytest.mark.parametrize("tamper", ["corpus_hash", "label_id", "unapproved_error"])
def test_archived_sample_fails_closed_on_identity_or_receipt_drift(tmp_path, tamper):
    from x_monitor.jev_assessment_runner import (
        AssessmentRunError,
        assemble_archived_sample_assessment,
    )

    inputs = _write_archived_assessment_inputs(tmp_path)
    expected_hash = inputs["corpus_sha256"]
    accepted_errors = dict(inputs["accepted_errors"])
    if tamper == "corpus_hash":
        expected_hash = "0" * 64
    elif tamper == "label_id":
        labels = json.loads(inputs["label_path"].read_text())
        labels["labels"][0]["id"] = "different-id"
        inputs["label_path"].write_text(json.dumps(labels))
    else:
        accepted_errors.pop("live-00")

    with pytest.raises(AssessmentRunError):
        assemble_archived_sample_assessment(
            fixture_path=FIXTURE,
            frozen_run_dir=inputs["frozen_dir"],
            live_manifest_path=inputs["manifest_path"],
            live_run_dir=inputs["live_dir"],
            independent_labels_path=inputs["label_path"],
            config=_config(),
            expected_live_corpus_sha256=expected_hash,
            accepted_live_http_errors=accepted_errors,
            source_window_count=192,
            source_estimated_credits=22935,
        )

from __future__ import annotations

import json
from pathlib import Path

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

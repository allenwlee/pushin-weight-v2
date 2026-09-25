from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from tests.ui_assurance import gate

SOURCE = "a" * 40
BASELINE = "b" * 40


def candidate_args(mode="candidate", target=SOURCE):
    return [
        "--scope",
        "candidate",
        "--candidate-revision",
        SOURCE,
        "--performance-mode",
        mode,
        "--performance-state-home",
        "/private/tmp/state",
        "--performance-runtime",
        "/private/tmp/runtime",
        "--performance-target-revision",
        target,
        "--performance-installed-package-commit",
        "c" * 40,
        "--performance-data-source-identity",
        "environment:https://example.test",
        "--performance-data-source-kind",
        "environment",
        "--performance-declaration",
        "tests/fixtures/performance_assurance/declaration.json",
    ]


@pytest.fixture
def runners(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(gate, "EVIDENCE_PATH", tmp_path / "evidence.json")
    monkeypatch.setattr(
        gate,
        "build_evidence",
        lambda *a, **kw: SimpleNamespace(model_dump=lambda **kw: {}),
    )
    monkeypatch.setattr(gate, "_run", lambda *args, **kwargs: calls.append(args))

    def result(*args):
        calls.append(args)
        if args[1] == "performance-run":
            return {"attempt_id": "measured"}
        return {
            "attempt_id": "measured",
            "status": "clean",
            "payload": {"evidence": {"identity": {"target_revision": SOURCE}}},
        }

    monkeypatch.setattr(gate, "_run_json", result)
    return calls


def test_candidate_rejects_missing_inputs_before_any_checks(runners):
    with pytest.raises(SystemExit):
        gate.main(["--scope", "candidate", "--candidate-revision", SOURCE])
    assert runners == []


def test_old_production_cannot_count_as_candidate_performance(runners):
    with pytest.raises(SystemExit):
        gate.main(candidate_args(target=BASELINE))
    assert runners == []


def test_candidate_requires_sealed_measurement_identity(monkeypatch, runners):
    monkeypatch.setattr(
        gate,
        "_run_json",
        lambda *args: {
            "attempt_id": "measured",
            "status": "clean",
            "payload": {"evidence": {"identity": {"target_revision": BASELINE}}},
        },
    )
    with pytest.raises(RuntimeError, match="sealed performance evidence"):
        gate.main(candidate_args())


def test_candidate_reports_matching_measurement(runners, capsys):
    assert gate.main(candidate_args()) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["performance_mode"] == "candidate"
    assert (
        report["product_source_revision"]
        == report["performance_target_revision"]
        == SOURCE
    )
    assert report["performance_status"] == "clean"


def test_baseline_is_explicitly_labelled(monkeypatch, runners, capsys):
    monkeypatch.setattr(
        gate,
        "_run_json",
        lambda *args: {
            "attempt_id": "baseline",
            "status": "clean",
            "payload": {"evidence": {"identity": {"target_revision": BASELINE}}},
        },
    )
    assert (
        gate.main(
            candidate_args("baseline", BASELINE)
            + [
                "--performance-rationale",
                "Production comparison only; copy change has no performance gate.",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["performance_mode"] == "baseline"
    assert report["performance_target_revision"] == BASELINE
    assert report["product_source_revision"] == SOURCE


def test_not_required_keeps_product_checks_and_never_measures(runners, capsys):
    assert (
        gate.main(
            [
                "--scope",
                "candidate",
                "--candidate-revision",
                SOURCE,
                "--performance-mode",
                "not-required",
                "--performance-rationale",
                "Hover copy only; browser regression covers the changed behavior.",
            ]
        )
        == 0
    )
    assert any("assurance-assess" in command for command in runners)
    assert any("pytest" in command for command in runners)
    assert not any(
        any(arg.startswith("performance-") for arg in command) for command in runners
    )
    assert json.loads(capsys.readouterr().out)["performance_status"] == "not-run"


@pytest.mark.parametrize("mode", ["baseline", "not-required"])
def test_non_candidate_choice_requires_a_rationale(mode, runners):
    with pytest.raises(SystemExit):
        gate.main(
            [
                "--scope",
                "candidate",
                "--candidate-revision",
                SOURCE,
                "--performance-mode",
                mode,
            ]
        )
    assert runners == []


def test_product_failure_still_stops_candidate_without_performance(
    monkeypatch, runners
):
    def fail(*args, **kwargs):
        if "pytest" in args:
            raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(gate, "_run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        gate.main(
            [
                "--scope",
                "candidate",
                "--candidate-revision",
                SOURCE,
                "--performance-mode",
                "not-required",
                "--performance-rationale",
                "No timing-sensitive changes",
            ]
        )
    assert runners == []

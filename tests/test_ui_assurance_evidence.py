"""Evidence closure and fail-closed Bridgewright assessment tests."""

from __future__ import annotations

from pathlib import Path

from bridgewright.assurance.engine import assess_evidence, compile_obligations

from tests.ui_assurance.evidence import build_evidence, load_documents

ROOT = Path(__file__).resolve().parents[1]


def test_full_target_evidence_closes_every_bridgewright_obligation() -> None:
    declaration, _ = load_documents(ROOT)
    evidence = build_evidence(
        ROOT,
        candidate_revision=declaration.source_revision,
        browser_runtime="playwright-chromium",
    )
    assessment = assess_evidence(declaration, evidence)

    assert len(evidence.results) == len(compile_obligations(declaration)) == 2804
    assert assessment.status == "clean"
    assert assessment.coverage.passed == 2804
    assert assessment.coverage.missing == 0
    assert assessment.coverage.unknown == 0


def test_missing_or_skipped_required_result_fails_with_stable_obligation_id() -> None:
    declaration, _ = load_documents(ROOT)
    evidence = build_evidence(
        ROOT,
        candidate_revision=declaration.source_revision,
        browser_runtime="playwright-chromium",
    )
    missing_id = evidence.results.pop(0).obligation_id
    assessment = assess_evidence(declaration, evidence)

    assert assessment.status == "invalid"
    assert assessment.coverage.missing == 1
    assert assessment.findings[0].code == "required_obligation_missing"
    assert assessment.findings[0].path == f"results.{missing_id}"

    evidence = build_evidence(
        ROOT,
        candidate_revision=declaration.source_revision,
        browser_runtime="playwright-chromium-test",
    )
    evidence.results[0].status = "skipped"
    assessment = assess_evidence(declaration, evidence)
    assert assessment.status == "invalid"
    assert assessment.coverage.skipped == 1

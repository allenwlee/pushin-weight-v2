"""Pin the discourse_key spelling in evidence-report artifacts and
emit scripts.

Plan 2026-07-13-002 U7: the U3 evidence report used `discours_key`
(missing the `e`) in 10+ places. The codebase, DB schema, and
runtime column are all `discourse_key`. The typo originated in
`scripts/build_u3_evidence_live_run.py` and the legacy
`scripts/build_u3_evidence.py`. This test pins the spelling so a
future regression in either the emit code or a regenerated report
fails the test.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "tests" / "classifier_tests"
EMIT_SCRIPTS = [
    REPO_ROOT / "scripts" / "build_u3_evidence_live_run.py",
    REPO_ROOT / "scripts" / "build_u3_evidence.py",
]
# Allow-list for files where the typo is intentional (review notes
# document the bug by quoting it). Add new entries here ONLY when a
# file is documenting the typo on purpose.
TYPO_ALLOWLIST = {
    REPO_ROOT / "tests/classifier_tests/20260713T040301_0000-bbf72b83-u3-evidence-review-notes.md",
}


def _report_files() -> list[Path]:
    return sorted(REPORT_DIR.glob("*u3-evidence.md"))


def test_no_discours_key_in_emit_scripts():
    """Both emit scripts must use `discourse_key` (with the `e`).

    Pins the fix from Plan 2026-07-13-002 U7 — the typo originated
    in these emit functions and a regression in either must fail
    this test before a new typo lands in a regenerated report."""
    typo_re = re.compile(r"\bdiscours_key\b")
    for script in EMIT_SCRIPTS:
        text = script.read_text()
        matches = typo_re.findall(text)
        assert not matches, (
            f"{script.relative_to(REPO_ROOT)} contains "
            f"{len(matches)} occurrences of `discours_key` (missing "
            f"the `e`). The codebase uses `discourse_key` — fix the "
            f"emit function."
        )


def test_no_discours_key_in_evidence_reports():
    """Every `*u3-evidence.md` artifact in tests/classifier_tests/
    must use `discourse_key`. Allow-list holds only the review
    notes file, which quotes the typo on purpose."""
    typo_re = re.compile(r"\bdiscours_key\b")
    for report in _report_files():
        if report in TYPO_ALLOWLIST:
            continue
        text = report.read_text()
        matches = typo_re.findall(text)
        assert not matches, (
            f"{report.relative_to(REPO_ROOT)} contains "
            f"{len(matches)} occurrences of `discours_key`. "
            f"Regenerate the report via the fixed emit script or "
            f"sed-replace."
        )


def test_canonical_spelling_present_in_evidence_reports():
    """Companion check to the no-typo test: at least one
    `discourse_key` reference must be present in every report.
    Guards against an over-aggressive sed that removes both
    spellings."""
    canon_re = re.compile(r"\bdiscourse_key\b")
    for report in _report_files():
        text = report.read_text()
        assert canon_re.search(text), (
            f"{report.relative_to(REPO_ROOT)} contains no "
            f"`discourse_key` reference. Either the report was "
            f"regenerated against the wrong DB schema, or the "
            f"discourse section was removed entirely."
        )
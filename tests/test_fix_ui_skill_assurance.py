"""Keep fix-ui a thin, non-authoritative Bridgewright target invoker."""

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1] / ".claude/skills/fix-ui/SKILL.md"
).read_text(encoding="utf-8")


def test_fix_ui_invokes_both_target_gates_and_structural_assessment() -> None:
    assert "bridgewright assurance-validate" in SKILL
    assert "bridgewright assurance-prescribe" in SKILL
    assert "tests.ui_assurance.gate --scope affected" in SKILL
    assert "tests.ui_assurance.gate --scope candidate" in SKILL
    assert "zero failed, skipped, errored, missing, or unknown obligations" in SKILL


def test_fix_ui_does_not_grant_bridgewright_release_authority() -> None:
    assert "grants no permission to commit, push, merge, stage, deploy, or release" in SKILL
    assert "do not copy Bridgewright's generic protocol" in SKILL

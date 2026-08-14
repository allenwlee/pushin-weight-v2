from __future__ import annotations

from pathlib import Path

from scripts.ollija.config import load_project_config
from scripts.ollija.impact import assess_ui_impact

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_visible_candidate_requires_desktop_iphone_and_bridgewright() -> None:
    impact = assess_ui_impact(
        load_project_config(REPO_ROOT),
        ["monitor/templates/monitor/home.html", "scripts/ollija/status.py"],
    )

    assert impact.ui_required is True
    assert impact.required_approvals == ("desktop", "iphone")
    assert impact.required_evidence == ("bridgewright",)
    assert impact.matched_paths == ("monitor/templates/monitor/home.html",)


def test_backend_only_candidate_still_requires_desktop_owner_review() -> None:
    impact = assess_ui_impact(
        load_project_config(REPO_ROOT),
        ["scripts/ollija/status.py", "tests/ollija/test_status.py"],
    )

    assert impact.ui_required is False
    assert impact.required_approvals == ("desktop",)
    assert impact.required_evidence == ()


def test_surface_fingerprint_changes_with_applicability_or_path() -> None:
    config = load_project_config(REPO_ROOT)
    first = assess_ui_impact(config, ["project/settings.py"])
    second = assess_ui_impact(config, ["scripts/ollija/status.py"])

    assert first.surface_fingerprint != second.surface_fingerprint

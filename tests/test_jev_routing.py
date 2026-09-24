from __future__ import annotations

from pathlib import Path

from core.models import RareTypeDecision
from x_monitor.config import load_config
from x_monitor.jev_decisions import QUESTION_SET, derive_gate_outcome

REPO = Path(__file__).resolve().parents[1]


def _config():
    return load_config(REPO / "config.yaml").discovery.rare_types.jev


def _probabilities(**overrides):
    probabilities = {question_id: 0.1 for question_id in QUESTION_SET}
    probabilities.update(overrides)
    return probabilities


def test_non_personnel_routes_ignore_static_bio_veto():
    probabilities = _probabilities(
        ai_related=0.95,
        attendance_event=0.51,
        bounded_opportunity=0.91,
        model_release=0.88,
        source_announcement=0.87,
        junk_static_bio=0.91,
    )

    assert derive_gate_outcome(probabilities, _config()) == (
        RareTypeDecision.GateOutcome.KEPT,
        ("events", "opportunities", "model_releases"),
    )


def test_job_and_event_thresholds_preserve_lower_uncertainty():
    probabilities = _probabilities(
        ai_related=0.95, role_opening=0.31, attendance_event=0.51
    )
    assert derive_gate_outcome(probabilities, _config()) == (
        RareTypeDecision.GateOutcome.KEPT,
        ("job_listings", "events"),
    )

    probabilities.update(role_opening=0.29, attendance_event=0.49)
    assert derive_gate_outcome(probabilities, _config()) == (
        RareTypeDecision.GateOutcome.REVIEW_NEEDED,
        (),
    )


def test_hard_job_mill_veto_remains_route_scoped():
    probabilities = _probabilities(ai_related=0.95, role_opening=0.41, junk_mill=0.96)
    assert derive_gate_outcome(probabilities, _config()) == (
        RareTypeDecision.GateOutcome.JUNK,
        (),
    )


def test_quoted_first_person_identity_supports_personnel_route():
    probabilities = _probabilities(
        ai_related=0.87, person_identity=0.61, role_change=0.89
    )
    state = {
        "text": "Congratulations to Priya on her next chapter.",
        "author": {"id": "lab", "handle": "emberglasslab"},
        "quoted_text": "After four years, I'm leaving Emberglass Lab.",
        "quoted_author": {"id": None, "name": None, "handle": "priyamenon"},
    }

    assert derive_gate_outcome(probabilities, _config(), state=state) == (
        RareTypeDecision.GateOutcome.KEPT,
        ("personnel_changes",),
    )

"""The preview and writer must agree on an employment spell."""

from core.person_affiliations import reconcile_role


def role(**values):
    return {"id": 1, "affiliation_type": "employment", "status": "current", **values}


def test_month_to_day_precision_enriches_the_same_role():
    saved = role(start_date="2026-08", start_date_precision="month")
    incoming = role(start_date="2026-08-14", start_date_precision="day")
    decision = reconcile_role(incoming, [saved])
    assert decision["action"] == "enrich"
    assert decision["match"]["id"] == 1
    assert decision["updates"] == {
        "start_date": "2026-08-14",
        "start_date_precision": "day",
    }


def test_distinct_or_undated_spells_are_not_guessed():
    candidates = [role(id=1, start_date="2024"), role(id=2, start_date="2026")]
    result = reconcile_role(role(start_date=None), candidates)
    assert result == {"action": "review_existing", "match": None, "updates": {}}


def test_conflicting_dates_require_review_and_preserve_existing_values():
    result = reconcile_role(role(start_date="2026-11"), [role(start_date="2026-10")])
    assert result["action"] == "review_existing"
    assert result["updates"] == {}


def test_exact_replay_adds_evidence_without_changing_role():
    original = role(team="Research", start_date="2026-08", start_date_precision="month")
    result = reconcile_role(dict(original), [original])
    assert result == {"action": "add_evidence", "match": original, "updates": {}}

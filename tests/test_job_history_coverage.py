from copy import deepcopy

import pytest

from core.staff_assets.job_history_coverage import compare, coverage


def _packet():
    return {
        "input_digest": "same",
        "target_inventory_digest": "inventory",
        "people": [
            {
                "key": "person-a",
                "affiliations": [
                    {
                        "action": "hold",
                        "fields": {"status": "current", "start_date": "2026-10"},
                        "chain": {"brand_id": "brand", "company_ids": ["company"]},
                        "field_sources": {
                            "start_date": [{"basis": "source_keys_unresolved"}]
                        },
                    },
                    {
                        "action": "create",
                        "fields": {"status": "former", "end_date": "2026-09"},
                        "chain": {"brand_id": "brand", "company_ids": ["company"]},
                        "field_sources": {"end_date": [{"basis": "literal_match"}]},
                    },
                ],
            },
            {"key": "person-b", "affiliations": []},
        ],
    }


def test_coverage_counts_entries_distinct_people_holds_and_date_basis():
    result = coverage(_packet())
    assert result["people"] == 2 and result["role_entries"] == 2
    assert result["people_without_structured_roles"] == 1
    assert result["present_without_end_date"] == {"entries": 1, "people": 1}
    assert result["actions"] == {"hold": 1, "create": 1}
    assert result["fields"]["start_date"] == {
        "populated_entries": 1,
        "missing_entries": 1,
        "populated_people": 1,
        "missing_people": 1,
        "basis_entries": {"source_keys_unresolved": 1},
    }
    assert result["fields"]["end_date"]["basis_entries"] == {"literal_match": 1}
    assert result["brands"]["brand"] == {
        "entries": 2,
        "people": 1,
        "current_entries": 1,
        "current_people": 1,
    }
    assert result["statuses"] == {"current": 1, "former": 1}


def test_comparison_discloses_changed_inputs_and_rejects_different_cohort():
    before = _packet()
    after = deepcopy(before)
    after["input_digest"] = "different"
    report = compare(before, after)
    assert report["same_input_digest"] is False
    assert report["same_target_inventory"] is True
    after["people"].pop()
    with pytest.raises(ValueError, match="same person cohort"):
        compare(before, after)


def test_duplicate_people_cannot_inflate_coverage():
    packet = _packet()
    packet["people"].append(deepcopy(packet["people"][0]))
    with pytest.raises(ValueError, match="distinct"):
        coverage(packet)

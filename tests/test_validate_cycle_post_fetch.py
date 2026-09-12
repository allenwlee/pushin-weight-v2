"""Post-fetch summary vocabulary for validate_cycle."""

from monitor.management.commands.validate_cycle import _extract_post_fetch_totals


def test_stage1_publication_and_legacy_discourse_are_distinct_evidence():
    totals = _extract_post_fetch_totals({
        "post_fetch": {
            "n_translated": 4,
            "n_classifications_published": 3,
            "n_discourse": 0,
            "n_nationalism": 0,
            "n_failed_translate": 1,
        }
    })

    assert totals == {
        "n_translated": 4,
        "n_classifications_published": 3,
        "n_classified_legacy": None,
        "n_discourse_legacy": 0,
        "n_nationalism_legacy": 0,
        "n_failed_translate": 1,
    }


def test_missing_stage1_counter_is_unknown_in_legacy_summary():
    totals = _extract_post_fetch_totals({
        "post_fetch": {"n_classified": 2, "n_discourse": 2}
    })

    assert totals["n_classifications_published"] is None
    assert totals["n_classified_legacy"] == 2
    assert totals["n_discourse_legacy"] == 2

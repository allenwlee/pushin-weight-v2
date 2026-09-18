from scripts import u18_fresh40_batch20_compare as subject


def test_cohort_uses_two_production_sized_batches_and_excludes_five():
    packets = subject.sol.packets()[: subject.CASE_COUNT]
    assert [len(batch) for batch in subject.batches(packets)] == [20, 20]
    assert [row["case_id"] for row in packets] == subject.EXPECTED_CASES
    assert "L45-41" not in subject.EXPECTED_CASES


def test_semantic_issue_is_reported_without_changing_model_output():
    rows = [{
        "case_id": "L45-01",
        "by_brand": [{
            "brand_id": "deepseek",
            "geopolitical_modes": ["framework"],
            "china_national_stance": "pro",
            "us_national_stance": "none",
        }],
    }]
    issues = subject.semantic_issues(rows, "brand")
    assert issues == [{"case_id": "L45-01", "brand_id": "deepseek", "issue": "national stance without nationalistic_stance mode"}]
    assert rows[0]["by_brand"][0]["china_national_stance"] == "pro"


def test_exact_set_scoring_is_order_independent():
    assert subject.same(["events", "opportunities"], ["opportunities", "events"])
    assert not subject.same(["events"], ["events", "opportunities"])

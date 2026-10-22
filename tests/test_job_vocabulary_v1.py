from core.job_vocabulary_v1 import assignment_values, canonical_code


def test_explicit_plural_values_are_separate_without_splitting_arbitrary_prose():
    rows = assignment_values("employment_type", "Full-time/Contract")
    assert [row.category_code for row in rows] == ["full_time", "contract"]
    assert len({row.source_value_sha256 for row in rows}) == 2
    unknown = assignment_values("job_function", "research/engineering depending on team")
    assert len(unknown) == 1
    assert unknown[0].category_code is None
    assert unknown[0].reported_value == "research/engineering depending on team"


def test_unknown_wording_and_legacy_dictionary_string_survive():
    value = "{'id': 10, 'name': '产品类/Product'}"
    row, = assignment_values("job_function", value)
    assert row.reported_value == value
    assert row.category_code == "product"
    row, = assignment_values("role_ai_relationship", "The role supports an AI team")
    assert row.category_code is None
    assert row.reported_value == "The role supports an AI team"


def test_source_list_has_explicit_membership_and_period_has_no_amount_conversion():
    rows = assignment_values("workplace_type", ["Remote", "Hybrid", "Remote"])
    assert [row.category_code for row in rows] == ["remote", "hybrid"]
    assert canonical_code("salary_period", "yearly") == "year"
    assert canonical_code("salary_period", "per release") is None

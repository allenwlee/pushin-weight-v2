import pytest

from monitor.country_codes import COUNTRY_NAMES, normalize_country_code


def test_country_inventory_matches_approved_source():
    assert len(COUNTRY_NAMES) == 249
    assert COUNTRY_NAMES["CN"] == "China"
    assert COUNTRY_NAMES["US"] == "United States of America"
    assert COUNTRY_NAMES["KR"] == "Republic of Korea"
    assert COUNTRY_NAMES["TR"] == "Türkiye"
    assert COUNTRY_NAMES["RU"] == "Russian Federation"
    assert COUNTRY_NAMES["MK"] == "North Macedonia"


def test_country_normalization_is_exact_only():
    assert normalize_country_code("CN") == "CN"
    assert normalize_country_code("United States") == "US"
    assert normalize_country_code("South Korea") == "KR"
    assert normalize_country_code("Korea") is None
    assert normalize_country_code("Congo") is None
    assert normalize_country_code("us") is None
    assert normalize_country_code(" United States ") is None
    assert normalize_country_code("Seoul") is None
    assert normalize_country_code("WW") is None
    assert normalize_country_code(None) is None


@pytest.mark.parametrize(
    ("provider_name", "expected_code"),
    [
        ("Turkey", "TR"),
        ("Russian Federation", "RU"),
        ("Macedonia", "MK"),
    ],
)
def test_country_normalization_accepts_exact_provider_aliases(
    provider_name, expected_code
):
    assert normalize_country_code(provider_name) == expected_code
    assert normalize_country_code(provider_name.lower()) is None
    assert normalize_country_code(f" {provider_name} ") is None

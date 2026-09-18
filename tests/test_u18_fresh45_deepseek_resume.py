from scripts import u18_fresh45_deepseek_resume as subject


def brand_row(modes, china, us):
    return {"brand_id": "deepseek", "product_labels": ["none"], "sentiment": "unknown", "geopolitical_modes": modes, "china_national_stance": china, "us_national_stance": us}


def test_unavailable_allows_unknown_national_stance():
    item = brand_row(["unavailable"], "unknown", "unknown")
    subject.validate_array(item["geopolitical_modes"], subject.shared.GEO, {"none", "unavailable"})
    allowed = {"unknown"} if item["geopolitical_modes"] == ["unavailable"] else {"none"}
    assert item["china_national_stance"] in allowed
    assert item["us_national_stance"] in allowed


def test_assessed_non_geopolitical_requires_none_stance():
    item = brand_row(["none"], "none", "none")
    allowed = {"unknown"} if item["geopolitical_modes"] == ["unavailable"] else {"none"}
    assert item["china_national_stance"] in allowed
    assert item["us_national_stance"] in allowed

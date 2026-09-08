import json
from pathlib import Path

from x_monitor.provider_telemetry import ProviderResponse, normalize_usage


def test_usage_fixture_normalizes_without_adding_overlapping_fields():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "llm_enrichment_evaluation_v1.json").read_text()
    )
    for case in fixture["usage_cases"]:
        assert normalize_usage(case["provider_usage"]) == case["expected_normalized"]


def test_response_metadata_survives_parse_failure_without_changing_dict_output():
    response = ProviderResponse({"results": []}, usage={"input_tokens": 9})
    assert response == {"results": []}
    assert normalize_usage(response.provider_usage)["input_tokens"] == 9

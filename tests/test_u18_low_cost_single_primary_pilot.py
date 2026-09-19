"""Evidence and row-identity regressions for the offline price comparison."""
import json

import pytest

from scripts import u18_low_cost_single_primary_pilot as pilot


def test_billable_invalid_model_json_retains_raw_response_and_usage(tmp_path, monkeypatch):
    payload = {
        "model": "mistralai/mistral-nemo", "provider": "DekaLLM", "id": "generation-test",
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.0000024},
        "choices": [{"finish_reason": "stop", "message": {"content": "{broken-json"}}],
    }

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(pilot.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    candidate = pilot.CANDIDATES["mistral_nemo"]
    decoded, record = pilot.transport(pilot.request_body(candidate), "private-test-key", tmp_path, "batch")
    assert record["usage"]["cost"] == payload["usage"]["cost"]
    assert json.loads((tmp_path / "batch-raw-response.json").read_text()) == payload
    with pytest.raises(json.JSONDecodeError):
        pilot.content_and_identity(decoded, candidate)
    assert all("private-test-key" not in p.read_text() for p in tmp_path.iterdir())


def test_missing_rows_are_recorded_without_discarding_independent_valid_evidence():
    def packet(identity):
        return {"tweet_id": identity, "text": "Qwen meetup", "context": [], "brand_ids": ["qwen"], "affiliations": [], "source_language": "en"}

    row = {
        "tweet_id": "present",
        "classifications": [{"brand_id": "qwen", "outcome": "classified", "post_types": ["events"], "product_labels": [], "sentiment": "neutral", "china_nationalism": "none", "us_nationalism": "none"}],
        "unsanctioned_flags": [],
    }
    result, errors = pilot.diagnostic_rows({"results": [row]}, [packet("present"), packet("missing")], 0)
    assert len(result["merged"]) == 1
    assert errors == [{"tweet_id": "missing", "error": "missing or duplicate response ID"}]
    with pytest.raises(ValueError):
        pilot.primary.parse_primary({"results": [row]}, [packet("present"), packet("missing")])

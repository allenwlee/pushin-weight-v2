"""Pin the accepted complete requests, keeping historical/native voices intact."""

import hashlib
import json
from pathlib import Path

import pytest

from monitor.editorial.config import load_editorial_config
from monitor.editorial.contracts import Event
from monitor.editorial.providers import request_payload
from monitor.editorial.voices import load_voice
from monitor.editorial.writing import HEADLINE_ATTRIBUTION_RULE, writer_request


@pytest.mark.parametrize("case", ["wang", "mistral-first"])
def test_production_writer_reproduces_accepted_complete_request(case):
    data = json.loads(
        Path("tests/fixtures/editorial_repaired_writer_inputs.json").read_text()
    )[case]
    cfg = load_editorial_config(Path("config/editorial-english-launch.yaml"))
    voice = load_voice(cfg.voices["chatter:en"])
    request = writer_request(Event.model_validate(data["event"]), data["packet"], voice, cfg)
    body = request_payload(cfg.writer_route("chatter", "en"), request)
    encoded = json.dumps(body, ensure_ascii=False).encode()
    assert hashlib.sha256(encoded).hexdigest() == data["request_hash"]
    assert voice.id == "chatter-en-v3" and voice.version == 3
    assert body["model"] == "gpt-6-sol" and body["reasoning_effort"] == "medium"
    assert request["system"].count(HEADLINE_ATTRIBUTION_RULE) == 1
    assert "THE PRICE IS WANG" not in request["system"] + request["user"]
    assert "CHONK NOW, WEIGHTS LATER" not in request["system"] + request["user"]


def test_historical_voice_digest_and_native_editorial_instructions_are_preserved():
    old = load_voice("chatter-en-v2")
    assert old.digest == "913bccde6fa5bcb4f63804bf68d8f37d548e418d4a8b8bd9dc4f19fe79e60dc0"
    before = json.loads(Path("config/editorial_prompts/editorial-judgment-headline-v1.json").read_text())
    after = json.loads(Path("config/editorial_prompts/editorial-judgment-headline-v2.json").read_text())
    assert before["instructions"] == after["instructions"]
    for name in before["voices"]:
        if name != "en|nypost":
            assert before["voices"][name] == after["voices"][name]
    cfg = load_editorial_config(Path("config/editorial-english-launch.yaml"))
    for locale, profile in {"ja": "chatter-ja-tospo-v2", "zh-cn": "chatter-zh-cn-wemedia-v2"}.items():
        assert cfg.voices["chatter:" + locale] == profile
        voice = load_voice(profile)
        assert voice.shared_prompt == "editorial-judgment-headline-v1"
        assert voice.headline_attribution is None
        route = cfg.writer_route("chatter", locale)
        assert route.model == "gpt-6.1-sol" and route.reasoning == "high"


def test_unknown_attribution_policy_is_rejected():
    from pydantic import ValidationError

    from monitor.editorial.voices import Voice

    with pytest.raises(ValidationError):
        Voice(id="invalid", version=3, track="chatter", locale="en", headline_attribution="unattributed")

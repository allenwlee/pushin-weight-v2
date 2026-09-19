from __future__ import annotations

import json
import pytest

from scripts.model_task_profiles import (
    HY_MT2_SNAPSHOT,
    HY_MT2_SNAPSHOT_SHA256,
    LUNA_ENDPOINT_SNAPSHOT,
    LUNA_ENDPOINT_SNAPSHOT_SHA256,
    get_profile,
    profile_manifest,
    restore_translation_lines,
    translation_lines,
)
from scripts.model_task_experiment import _visible_output_limit, capture_requests


def test_luna_uses_the_openrouter_flex_endpoint_and_excludes_unsupported_samplers():
    profile = get_profile("luna_translation_v1")
    request = profile.apply({
        "model": profile.model, "max_tokens": 1061, "thinking": {"type": "disabled"},
        "temperature": 0, "top_p": 1, "seed": 2, "reasoning_effort": "high", "messages": [],
    })
    assert profile.provider_only == "openai/flex"
    assert profile.upstream_model == "openai/gpt-5.6-luna-20260709"
    assert profile.max_output_tokens == 9216
    assert request["provider"]["only"] == ["openai/flex"]
    assert request["service_tier"] == "flex"
    assert request["reasoning"] == {"effort": "low", "exclude": True}
    assert request["max_tokens"] == 2085
    assert not {"thinking", "temperature", "top_p", "seed", "reasoning_effort"} & request.keys()
    assert "response_format" not in request
    manifest = profile_manifest(profile)
    assert manifest["snapshot_path"].endswith("2026-09-17-143812-openrouter-pricing-snapshot")
    assert manifest["endpoint_snapshot"] == {"path": str(LUNA_ENDPOINT_SNAPSHOT), "sha256": LUNA_ENDPOINT_SNAPSHOT_SHA256}


def test_luna_commentary_reserves_visible_output_after_low_reasoning_and_requires_schema():
    profile = get_profile("luna_commentary_v1")
    assert profile.max_output_tokens == 5120
    assert _visible_output_limit(profile) == 4096
    request = profile.apply({"model": profile.model, "max_tokens": 4096, "temperature": 0, "messages": []})
    assert request["max_tokens"] == 5120
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["reasoning"] == {"effort": "low", "exclude": True}
    assert "temperature" not in request


def test_existing_profiles_keep_their_visible_output_limit_without_reasoning_headroom():
    profile = get_profile("qwen_commentary_v1")
    assert profile.reasoning_headroom_tokens == 0
    assert _visible_output_limit(profile) == profile.max_output_tokens


def test_luna_commentary_actual_caller_reserves_reasoning_headroom_under_the_profile_cap():
    profile = get_profile("luna_commentary_v1")
    request = capture_requests(profile, [{"post_id": "probe", "text": "A model may be cheaper, but its quality is uncertain.", "source_language": "en", "context": []}])[0]
    assert request["max_tokens"] == _visible_output_limit(profile) + profile.reasoning_headroom_tokens
    assert request["max_tokens"] == profile.max_output_tokens
    assert request["reasoning"] == {"effort": "low", "exclude": True}


def test_luna_v2_translation_uses_general_source_bound_fidelity_without_reviewed_answers():
    profile = get_profile("luna_translation_v2")
    payload = "[[PW0:001]]\nAster Nova dismisses the Delta slowdown claim.\n[[PW0:END]]"
    original = (
        "literal-translation-lines-v13. Translate one en source post into Japanese (ja). "
        "Return exactly 1 numbered blocks from [[PW0:001]] through [[PW0:001]], followed by "
        "[[PW0:END]]; keep each marker unchanged and in order. SOURCE:\n" + payload
    )
    request = profile.apply({"model": profile.model, "max_tokens": 1061, "temperature": 0, "top_p": 1, "messages": [{"role": "user", "content": original}]})
    prompt = request["messages"][0]["content"]
    assert profile.prompt_style == "luna_source_bound_translation"
    assert "Preserve grammatical relationships while using natural target-language syntax" in prompt
    assert "contextual meaning and tone" in prompt
    assert "opaque proper names" in prompt
    assert "country or currency" in prompt
    assert prompt.split("SOURCE:\n", 1)[1] == payload
    assert "temperature" not in request and "top_p" not in request


def test_luna_v2_commentary_preserves_reply_roles_without_record_metadata_prose():
    profile = get_profile("luna_commentary_v2")
    original = (
        "Write commentary. Input: "
        '{"post_id":"p1","context":{"post":"@reader I think Aster is faster",'
        '"quoted_text":"A different claim"}}'
    )
    request = profile.apply({"model": profile.model, "max_tokens": 4096, "temperature": 0, "top_p": 1, "messages": [{"role": "user", "content": original}]})
    system = request["messages"][0]["content"]
    assert profile.prompt_style == "luna_source_bound_commentary"
    assert "addressee or reply target" in system
    assert "unit or currency is unspecified" in system
    assert "data structure, record fields, or missing metadata" in system
    assert "stored_quote" not in system and "local_parent" not in system
    assert request["messages"][1]["content"] == original.split(" Input: ", 1)[1]
    assert request["response_format"]["type"] == "json_schema"
    assert "temperature" not in request and "top_p" not in request


def test_luna_v2_capture_uses_the_actual_marker_and_commentary_message_shapes():
    translation = get_profile("luna_translation_v2")
    requests = capture_requests(translation, [{"post_id": "p1", "text": "Aster compares Nova with Delta.\nNova remains uncertain.", "source_language": "en", "context": []}])
    assert len(requests) == 2
    for request in requests:
        assert request["messages"][0]["role"] == "user"
        body = request["messages"][0]["content"]
        assert "[[PW0:001]]" in body and "[[PW0:END]]" in body
        assert "response_format" not in request

    commentary = get_profile("luna_commentary_v2")
    request = capture_requests(commentary, [{"post_id": "p2", "text": "@reader Aster may be faster.", "source_language": "en", "context": []}])[0]
    assert [message["role"] for message in request["messages"]] == ["system", "user"]
    assert request["response_format"]["type"] == "json_schema"


def test_luna_v3_uses_json_lines_to_restore_markers_with_medium_reasoning_headroom():
    profile = get_profile("luna_translation_v3")
    original = (
        "literal-translation-lines-v13. Translate one en source post into Japanese (ja). "
        "SOURCE:\n[[PW0:001]]\nAster Delta is faster.\n[[PW0:002]]\nOrion is uncertain.\n[[PW0:END]]"
    )
    request = profile.apply({"model": profile.model, "max_tokens": 1061, "messages": [{"role": "user", "content": original}]})
    assert profile.prompt_style == "luna_structured_source_bound_translation"
    assert request["reasoning"] == {"effort": "medium", "exclude": True}
    assert request["max_tokens"] == 5157
    assert request["response_format"] == {"type": "json_object"}
    assert [message["role"] for message in request["messages"]] == ["system", "user"]
    assert "[[PW0:" not in request["messages"][1]["content"]
    assert "opaque proper names, product/model names" in request["messages"][0]["content"]
    assert "ordinary adjacent prose and country names" in request["messages"][0]["content"]
    captured = capture_requests(profile, [{"post_id": "p3", "text": "Aster Delta is faster.\nOrion is uncertain.", "source_language": "en", "context": []}])
    assert all(request["response_format"] == {"type": "json_object"} for request in captured)


def test_luna_commentary_v3_uses_medium_reasoning_and_general_locale_fidelity_rules():
    profile = get_profile("luna_commentary_v3")
    original = 'Write commentary. Input: {"post_id":"p4","context":{"post":"@reader Aster may be faster"}}'
    request = profile.apply({"model": profile.model, "max_tokens": _visible_output_limit(profile), "messages": [{"role": "user", "content": original}]})
    system = request["messages"][0]["content"]
    assert _visible_output_limit(profile) == 4096
    assert request["max_tokens"] == 8192
    assert request["reasoning"] == {"effort": "medium", "exclude": True}
    assert request["response_format"]["type"] == "json_schema"
    assert "account relationship" in system
    assert "all ordinary prose" in system
    assert "numerical magnitude" in system
    assert "more than one plausible referent or meaning" in system
    assert "poulet" not in system and "ox Alpha" not in system
    captured = capture_requests(profile, [{"post_id": "p4", "text": "@reader Aster may be faster.", "source_language": "en", "context": []}])[0]
    assert [message["role"] for message in captured["messages"]] == ["system", "user"]
    assert captured["max_tokens"] == 8192


def test_qwen_translation_pins_alibaba_without_unsupported_sampler_fields():
    profile = get_profile("qwen_translation_v1")
    request = profile.apply({"model": profile.model, "max_tokens": 9999, "thinking": {"type": "disabled"}, "top_p": 1, "seed": 4, "messages": []})
    assert request["provider"]["only"] == ["alibaba"]
    assert request["provider"]["allow_fallbacks"] is False
    assert request["reasoning"] == {"enabled": False, "exclude": True}
    assert "top_p" not in request and "seed" not in request
    assert "response_format" not in request


def test_gemini_flex_cannot_silently_become_standard():
    profile = get_profile("gemini_flex_commentary_v1")
    request = profile.apply({"model": profile.model, "max_tokens": 20, "messages": []})
    assert request["provider"]["only"] == ["google-ai-studio/flex"]
    assert request["service_tier"] == "flex"
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True


def test_gemini_commentary_no_reasoning_control_only_changes_reasoning():
    rows = [{"post_id": "p4", "text": "@reader Aster may be faster.", "source_language": "en", "context": []}]
    v3 = capture_requests(get_profile("gemini_flex_commentary_v3"), rows)[0]
    control = capture_requests(get_profile("gemini_flex_commentary_v4_no_reasoning"), rows)[0]
    assert control["reasoning"] == {"enabled": False, "exclude": True}
    assert v3["reasoning"] == {"enabled": True, "max_tokens": 2048, "exclude": True}
    assert {key: value for key, value in control.items() if key != "reasoning"} == {key: value for key, value in v3.items() if key != "reasoning"}


def test_profile_rejects_a_caller_model_redirect():
    profile = get_profile("qwen_commentary_v1")
    try:
        profile.apply({"model": "other", "max_tokens": 1, "messages": []})
    except ValueError as error:
        assert "caller model" in str(error)
    else:
        raise AssertionError("profile accepted a model redirect")


def test_hy_mt2_translation_uses_the_native_user_prompt_and_snapshot_route():
    profile = get_profile("hy18_translation_v1")
    payload = "[[PW-zh-Hans-0001]]\n[[PQ0:001]] https://example.com\n[[PW-zh-Hans-END]]"
    original = (
        "literal-translation-lines-v13. Translate one en source post into Simplified Chinese (zh-Hans). "
        "Return exactly 1 numbered blocks from [[PW-zh-Hans-0001]] through [[PW-zh-Hans-0001]], followed by "
        "[[PW-zh-Hans-END]]; keep each marker unchanged and in order. SOURCE:\n" + payload
    )
    request = profile.apply({"model": profile.model, "max_tokens": 9999, "thinking": {"type": "disabled"}, "reasoning": {"enabled": False}, "top_p": 1, "top_k": 20, "messages": [{"role": "user", "content": original}]})
    prompt = request["messages"][0]["content"]
    assert request["provider"]["only"] == ["tencent/fp8"]
    assert request["max_tokens"] == 4096 and request["temperature"] == 0.7
    assert profile.endpoint_tag == "tencent/fp8"
    assert request["messages"] == [{"role": "user", "content": prompt}]
    assert prompt.startswith("Translate the following English source post into Simplified Chinese. Only output the translated result")
    assert "literal-translation-lines-v13" not in prompt
    assert prompt.split("SOURCE:\n", 1)[1] == payload
    assert "[[PW-zh-Hans-0001]]" in prompt and "[[PQ0:001]]" in prompt
    assert "response_format" not in request
    assert not {"thinking", "reasoning", "top_p", "top_k"} & request.keys()
    manifest = profile_manifest(profile)
    assert manifest["snapshot_path"] == str(HY_MT2_SNAPSHOT)
    assert manifest["snapshot_sha256"] == HY_MT2_SNAPSHOT_SHA256


def test_hy_mt2_7b_caps_both_supported_completion_field_names():
    profile = get_profile("hy7_translation_v1")
    request = profile.apply({"model": profile.model, "max_tokens": 9999, "max_completion_tokens": 5000, "messages": [{"role": "user", "content": "Translate the following text into Japanese.\nSOURCE:\nx"}]})
    assert request["max_tokens"] == request["max_completion_tokens"] == 4096
    assert profile.upstream_model == "tencent/hy-mt2-7b-20260521"


@pytest.mark.parametrize("profile_key,temperature", [("hy18_translation_v3", 0), ("hy7_translation_v2", 0), ("hy7_translation_v3", 0.7)])
def test_hy_mt2_native_terminology_profile_uses_documented_user_form(profile_key, temperature):
    profile = get_profile(profile_key)
    payload = "[[PW0:001]]\nDeepSeek-V4.1-Flash with OpenCode Go and GPT 5.5\n[[PW0:END]]"
    original = (
        "literal-translation-lines-v13. Translate one en source post into Japanese (ja). "
        "Return exactly 1 numbered blocks from [[PW0:001]] through [[PW0:001]], followed by "
        "[[PW0:END]]; keep each marker unchanged and in order. SOURCE:\n" + payload
    )
    request = profile.apply({"model": profile.model, "max_tokens": 9999, "messages": [{"role": "user", "content": original}]})
    prompt = request["messages"][0]["content"]
    assert request["temperature"] == temperature
    assert request["provider"]["only"] == ["tencent/fp8"]
    assert request["messages"] == [{"role": "user", "content": prompt}]
    assert "Reference the following translations:" in prompt
    assert "`DeepSeek-V4.1-Flash` translates to `DeepSeek-V4.1-Flash`" in prompt
    assert "`OpenCode Go` translates to `OpenCode Go`" in prompt
    assert "Translate the following text into Japanese. Note that you should only output the translated result" in prompt
    assert "[[PW0:001]]" in prompt and "[[PW0:END]]" in prompt
    assert "literal-translation-lines-v13" not in prompt
    if profile_key == "hy7_translation_v3":
        assert "silently check the source's speaker and action" in prompt


def test_line_representation_keeps_source_and_restores_only_framing():
    original = (
        "literal-translation-lines-v13. Translate one ko source post into English (en). "
        "SOURCE:\n[[PW1:001]]\n  first [[PQ0:001]]  \n[[PW1:002]]\nsecond @name\n[[PW1:END]]"
    )
    target, lines, markers = translation_lines(original)
    assert target == "English"
    assert lines == ["  first [[PQ0:001]]  ", "second @name"]
    assert markers == ["[[PW1:001]]", "[[PW1:002]]", "[[PW1:END]]"]
    profile = get_profile("qwen_translation_v4")
    request = profile.apply({"model": profile.model, "messages": [{"role": "user", "content": original}]})
    assert request["messages"][0]["role"] == "system"
    assert json.loads(request["messages"][1]["content"])["source_lines"] == lines
    assert "[[PW1:" not in request["messages"][1]["content"]
    assert request["response_format"] == {"type": "json_object"}
    assert restore_translation_lines(["  translation [[PQ0:001]]  ", "other @name"], original) == (
        "[[PW1:001]]\n  translation [[PQ0:001]]  \n[[PW1:002]]\nother @name\n[[PW1:END]]"
    )
    with pytest.raises(ValueError, match="count mismatch"):
        restore_translation_lines(["only one"], original)
    with pytest.raises(ValueError, match="extra line breaks"):
        restore_translation_lines(["line\nline", "second"], original)


@pytest.mark.parametrize('key,model,price,structured', [
    ('qwen235_translation_v1', 'qwen/qwen3-235b-a22b-2507', (0.0875, 0.35), True),
    ('hy30_translation_v1', 'tencent/hy-mt2-30b-a3b', (0.074, 0.295), False),
    ('gemma4_translation_v1', 'google/gemma-4-31b-it', (0.09, 0.34), False),
])
def test_expanded_translation_profiles_capture_real_caller_and_saved_price_caps(key, model, price, structured):
    import hashlib
    from pathlib import Path
    profile = get_profile(key)
    requests = capture_requests(profile, [{
        'post_id': 'expanded-profile', 'text': 'Aster 2 may be 20% cheaper.\nhttps://example.com',
        'source_language': 'en', 'context': [],
    }])
    assert len(requests) == 2
    for request in requests:
        assert request['model'] == model
        assert request['provider']['only'] == [profile.endpoint_tag]
        assert request['provider']['allow_fallbacks'] is False
        assert request['provider']['require_parameters'] is True
        assert request['provider']['max_price'] == {'prompt': price[0], 'completion': price[1]}
        assert 0 < request['max_tokens'] <= profile.max_output_tokens
        assert ('response_format' in request) is structured
        if model.startswith('google/'):
            assert request['reasoning'] == {'enabled': False, 'exclude': True}
            assert 'temperature' not in request
        else:
            assert 'reasoning' not in request
    endpoint = profile_manifest(profile)['endpoint_snapshot']
    assert hashlib.sha256((Path(endpoint['path']) / 'manifest.json').read_bytes()).hexdigest() == endpoint['sha256']
    assert profile_manifest(profile)['snapshot_path'].endswith('2026-09-17-143812-openrouter-pricing-snapshot')


def test_expanded_second_variants_isolate_recorded_failures():
    from dataclasses import replace
    rows = [{'post_id': 'second-wave', 'text': 'USA has Aster.\nChina may have Nova.', 'source_language': 'en', 'context': []}]
    q1, q2 = get_profile('qwen235_translation_v1'), get_profile('qwen235_translation_v2')
    assert q2.max_concurrency == 1 and q1.max_concurrency == 3
    assert capture_requests(q1, rows) == capture_requests(q2, rows)
    for invalid in (0, 4):
        with pytest.raises(ValueError, match='concurrency'):
            replace(q2, max_concurrency=invalid)
    hy = capture_requests(get_profile('hy30_translation_v2'), rows)[0]
    prompt = hy['messages'][0]['content']
    assert 'Reference the following translations' not in prompt
    assert 'delimiters' in prompt and 'USA has Aster.' in prompt
    assert hy['temperature'] == 0.7 and 'reasoning' not in hy
    gm = capture_requests(get_profile('gemma4_translation_v2'), rows)[0]
    assert 'who performs each action' in gm['messages'][0]['content']
    assert gm['reasoning']['enabled'] is False


def test_expanded_third_variants_pin_their_authorized_controls_and_structured_wire_shape():
    rows = [{'post_id': 'third-wave', 'text': 'OpenCode Go [[PQ0:001]] may be cheaper.', 'source_language': 'en', 'context': []}]
    q2, q3 = get_profile('qwen235_translation_v2'), get_profile('qwen235_translation_v3')
    assert q3.max_concurrency == 1 and q3.min_request_interval_seconds == 4
    assert capture_requests(q2, rows) == capture_requests(q3, rows)
    for key in ('hy30_translation_v3', 'gemma4_translation_v3'):
        profile = get_profile(key)
        request = capture_requests(profile, rows)[0]
        assert request['response_format'] == {'type': 'json_object'}
        assert [message['role'] for message in request['messages']] == ['system', 'user']
        payload = json.loads(request['messages'][1]['content'])
        assert payload['source_lines'] == ['OpenCode Go [[PQ0:001]] may be cheaper.']
        assert 'Opaque names are names' in request['messages'][0]['content']
    hy = get_profile('hy30_translation_v3')
    assert hy.settings['temperature'] == 0.7
    assert hy.provider_only == get_profile('hy30_translation_v2').provider_only
    gemma = get_profile('gemma4_translation_v3')
    assert gemma.settings['reasoning'] == {'enabled': False, 'exclude': True}
    assert gemma.provider_only == get_profile('gemma4_translation_v1').provider_only
    manifest = profile_manifest(q3)
    assert manifest['min_request_interval_seconds'] == 4

"""Regression contract for the selected direct classifier extraction route."""

from __future__ import annotations

from pathlib import Path

from core.targeted_extraction import build_targeted_extraction_calls
from x_monitor.config import TargetedExtractionConfig, load_config
from x_monitor.deepinfra import DEEPSEEK_0731_MODEL, DeepInfraChatCompletionsClient

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"


def _response(model: str) -> dict:
    return {
        "id": "targeted-extraction-route-test",
        "model": model,
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"records": []}'},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def test_committed_targeted_extraction_roles_use_the_selected_direct_classifier_model():
    """M18: every enabled role can call the strict DeepInfra classifier client."""
    cfg = load_config(CONFIG_PATH)

    assert cfg.targeted_extraction.enabled is False
    assert cfg.llm.classifier_model == DEEPSEEK_0731_MODEL
    assert {
        role.model for role in cfg.targeted_extraction.roles.values()
    } == {cfg.llm.classifier_model}

    sent: list[dict] = []
    direct_client = DeepInfraChatCompletionsClient(
        api_key="test-key",
        model=cfg.llm.classifier_model,
        request_profile=cfg.llm.classifier_deepinfra_request_profile,
        base_url=cfg.llm.classifier_base_url,
        transport=lambda request, _timeout: (
            sent.append(request) or _response(request["model"])
        ),
    )
    calls = build_targeted_extraction_calls(
        client=direct_client,
        roles=cfg.targeted_extraction.roles,
        timeout_seconds=cfg.targeted_extraction.request_timeout_seconds,
    )

    for role, role_config in cfg.targeted_extraction.roles.items():
        response = calls[role]("system", "source", role_config.model, 256)
        assert response["records"] == []

    assert [request["model"] for request in sent] == [
        DEEPSEEK_0731_MODEL
    ] * len(cfg.targeted_extraction.roles)


def test_default_targeted_extraction_roles_are_direct_client_compatible():
    """The implicit config route cannot drift from the strict direct client."""
    roles = TargetedExtractionConfig().roles
    assert {role.model for role in roles.values()} == {DEEPSEEK_0731_MODEL}

    sent: list[dict] = []
    direct_client = DeepInfraChatCompletionsClient(
        api_key="test-key",
        model=DEEPSEEK_0731_MODEL,
        request_profile="deepseek_0731",
        transport=lambda request, _timeout: (
            sent.append(request) or _response(request["model"])
        ),
    )
    calls = build_targeted_extraction_calls(
        client=direct_client,
        roles=roles,
        timeout_seconds=30,
    )
    for role, role_config in roles.items():
        assert calls[role]("system", "source", role_config.model, 256)["records"] == []

    assert {request["model"] for request in sent} == {DEEPSEEK_0731_MODEL}


def test_targeted_adapter_retains_anthropic_content_block_compatibility():
    class AnthropicCompatibleClient:
        def messages_create(self, **_kwargs):
            return {
                "content": [{"type": "text", "text": '{"records": []}'}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    calls = build_targeted_extraction_calls(
        client=AnthropicCompatibleClient(),
        roles={"event_extraction": object()},
        timeout_seconds=17,
    )

    assert calls["event_extraction"]("system", "source", "legacy-model", 256) == {
        "records": [],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }

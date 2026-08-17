from __future__ import annotations

from pathlib import Path

from x_monitor.config import Config, LlmConfig, load_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def test_runtime_config_names_every_harvest_llm_model_and_endpoint():
    cfg = load_config(CONFIG_PATH)

    assert cfg.llm.translator_model == "deepseek-v4-pro"
    assert cfg.llm.translator_base_url == "https://api.deepseek.com/anthropic"
    assert cfg.llm.classifier_model == "deepseek-v4-pro"
    assert cfg.llm.classifier_base_url == "https://api.deepseek.com/anthropic"
    assert cfg.llm.relevancy_model == "claude-haiku-4-5"
    assert cfg.llm.relevancy_base_url == "https://api.anthropic.com"


def test_role_factories_use_cfg_endpoints_despite_conflicting_ambient_env(monkeypatch):
    from x_monitor import reattribute

    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        llm=LlmConfig(
            translator_base_url="https://translator.invalid/anthropic",
            classifier_base_url="https://classifier.invalid/anthropic",
            relevancy_base_url="https://relevancy.invalid/anthropic",
        ),
    )
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://ambient.invalid/anthropic")
    monkeypatch.setenv(
        "X_MONITOR_CLASSIFIER_BASE_URL", "https://ambient-classifier.invalid/anthropic"
    )
    seen = []
    monkeypatch.setattr(
        reattribute,
        "_build_client_for_base_url",
        lambda base_url, *, caller_label: (
            seen.append((caller_label, base_url)) or object()
        ),
    )

    reattribute.build_translator_client_from_env(cfg)
    reattribute.build_anthropic_client_from_env(cfg)
    reattribute.build_relevancy_client_from_env(cfg)

    assert seen == [
        ("translator", "https://translator.invalid/anthropic"),
        ("classifier", "https://classifier.invalid/anthropic"),
        ("relevancy", "https://relevancy.invalid/anthropic"),
    ]


def test_translator_uses_cfg_model_and_endpoint_for_thinking_not_ambient(monkeypatch):
    from x_monitor.translator import translate_batch_pragmatics

    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        llm=LlmConfig(
            translator_model="configured-translator",
            translator_base_url="https://api.deepseek.com/anthropic",
        ),
    )
    monkeypatch.setenv("ANTHROPIC_MODEL", "ambient-model")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")

    class Client:
        def __init__(self):
            self.calls = []

        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "results": [
                    {
                        "tweet_id": "1",
                        "lang_detected": "en",
                        "text_en": "hello",
                        "text_zh_cn": "你好",
                    }
                ]
            }

    client = Client()
    translate_batch_pragmatics(
        [{"tweet_id": "1", "text": "hello", "brand_ids": ["deepseek"]}],
        ["en", "zh_cn"],
        client,
        cfg=cfg,
    )

    assert len(client.calls) == 1
    assert client.calls[0]["model"] == "configured-translator"
    assert client.calls[0]["thinking"] == {"type": "disabled"}

from __future__ import annotations

import pytest


class AlwaysFails:
    def __init__(self):
        self.calls = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("provider failed")


def test_budget_counts_actual_retry_attempts_and_blocks_the_next_outbound_call(
    monkeypatch,
):
    from x_monitor.llm_budget import (
        BudgetedLlmClient,
        LlmBudgetExhausted,
        LlmCallBudget,
    )
    from x_monitor.translator import _call_with_retry

    monkeypatch.setattr("x_monitor.translator.time.sleep", lambda seconds: None)
    raw = AlwaysFails()
    budget = LlmCallBudget(max_calls=3)
    client = BudgetedLlmClient(raw, budget)

    with pytest.raises(RuntimeError, match="provider failed"):
        _call_with_retry(client, "prompt", n_tweets=1)
    with pytest.raises(LlmBudgetExhausted):
        client.messages_create(model="must-not-run")

    assert len(raw.calls) == 3
    assert budget.used == 3


def test_classifier_budget_exhaustion_does_not_retry_or_enter_per_post_fallback(
    monkeypatch,
):
    from x_monitor.attribution import classify_batch_pragmatics_full
    from x_monitor.llm_budget import (
        BudgetedLlmClient,
        LlmBudgetExhausted,
        LlmCallBudget,
    )

    monkeypatch.setattr("x_monitor.attribution.time.sleep", lambda seconds: None)
    raw = AlwaysFails()
    client = BudgetedLlmClient(raw, LlmCallBudget(max_calls=1))

    with pytest.raises(LlmBudgetExhausted):
        classify_batch_pragmatics_full(
            [{"tweet_id": "1", "text": "DeepSeek", "brand_ids": ["deepseek"]}],
            [],
            client,
            model="configured-classifier",
            thinking={"type": "disabled"},
        )

    assert len(raw.calls) == 1
    assert raw.calls[0]["model"] == "configured-classifier"


def test_translator_repair_respects_shared_budget(monkeypatch):
    from x_monitor.config import Config
    from x_monitor.llm_budget import (
        BudgetedLlmClient,
        LlmBudgetExhausted,
        LlmCallBudget,
    )
    from x_monitor.translator import translate_batch_pragmatics

    class InvalidLanguage:
        def __init__(self):
            self.calls = []

        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "results": [
                    {
                        "tweet_id": "1",
                        "lang_detected": "invalid",
                        "text_en": "x",
                        "text_zh_cn": "x",
                    }
                ]
            }

    raw = InvalidLanguage()
    client = BudgetedLlmClient(raw, LlmCallBudget(max_calls=1))
    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100)

    with pytest.raises(LlmBudgetExhausted):
        translate_batch_pragmatics(
            [{"tweet_id": "1", "text": "x", "brand_ids": ["deepseek"]}],
            ["en", "zh_cn"],
            client,
            cfg=cfg,
        )

    assert len(raw.calls) == 1
    assert raw.calls[0]["model"] == cfg.llm.translator_model

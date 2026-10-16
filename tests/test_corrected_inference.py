"""Exact cache identity and source boundaries for explicit corrected requests."""

import copy

import pytest

from core.provider_batches import digest
from x_monitor.corrected_inference import VERSION, CorrectedInferenceClient, body_digest
from x_monitor.deepinfra import GEMMA_4_31B_MODEL, DeepInfraChatCompletionsClient
from x_monitor.deferred_inference import DeferredInferenceClient, DeferredRequestPending


@pytest.mark.parametrize("selected", [True, False])
def test_only_selected_requests_change_wire_and_context(selected):
    delegate = DeepInfraChatCompletionsClient(api_key="unused", model=GEMMA_4_31B_MODEL, request_profile="gemma4_translation_v1")
    kwargs = {"max_tokens": 80, "messages": [{"role": "user", "content": "Translate only this source.\nSOURCE:\nOriginal prose."}]}
    original = delegate.build_request(**kwargs)
    retained = copy.deepcopy(original)
    context = {"stage": "translation", "post_ids": ["p"], "chunk_index": 1}
    correction = {"version": VERSION, "spec_sha256": "a" * 64, "prior_call_ids": [1]}
    corrected = CorrectedInferenceClient(
        delegate, feedback="The original prose must be translated.", context=correction,
        body_hashes={body_digest(original)} if selected else set(),
    )
    calls = []
    client = DeferredInferenceClient(
        corrected, resolve=lambda *args: calls.append(args), context_transform=corrected.context_for_request,
    )
    for _ in range(2):
        with pytest.raises(DeferredRequestPending):
            client.messages_create_text(**kwargs, _batch_context=context)
    assert calls[0] == calls[1] and original == retained
    identity, body, kind, actual_context = calls[0]
    assert identity == digest({"body": body, "response_kind": kind, "context": actual_context})
    assert body["messages"][0]["content"].endswith(original["messages"][0]["content"])
    if selected:
        assert actual_context == {**context, "recovery": correction} and body != original
    else:
        assert actual_context == context and body == original

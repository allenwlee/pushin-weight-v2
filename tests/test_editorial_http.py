import json

import pytest

from x_monitor.deepinfra import (
    GEMMA_4_31B_MODEL,
    DeepInfraChatCompletionsClient,
    DeepInfraPermanentError,
)
from x_monitor.provider_http import https_request


def test_existing_deepinfra_client_uses_shared_nonretrying_bounded_transport(
    monkeypatch,
):
    bodies = [
        json.dumps(
            {
                "model": GEMMA_4_31B_MODEL,
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "Source commentary"},
                    }
                ],
                "usage": {},
            }
        ).encode()
    ]
    requests = []
    closed = []

    class Connection:
        def __init__(self, host, port, timeout):
            assert host == "api.deepinfra.com" and port == 443

        def request(self, method, path, body, headers):
            requests.append((method, path))

        def getresponse(self):
            return self

        status = 200

        def read(self, maximum):
            return bodies[0][:maximum]

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        "x_monitor.provider_http.http.client.HTTPSConnection", Connection
    )
    client = DeepInfraChatCompletionsClient(
        api_key="test-only", model=GEMMA_4_31B_MODEL
    )
    assert (
        client.messages_create_text(
            model=GEMMA_4_31B_MODEL, max_tokens=100, messages=[]
        ).text
        == "Source commentary"
    )
    bodies[0] = b"x" * 2_000_001
    with pytest.raises(DeepInfraPermanentError):
        client.messages_create_text(
            model=GEMMA_4_31B_MODEL, max_tokens=100, messages=[]
        )
    assert len(requests) == len(closed) == 2
    with pytest.raises(ValueError):
        https_request("http://127.0.0.1/private", "test-only", {})
    assert len(requests) == 2

import httpx
import pytest

from core.collection_budgets import invocation_budget


@pytest.mark.parametrize(
    "limits",
    [{"requests": 0}, {"seconds": 3601}, {"max_bytes": 33554433}, {"requests": True}],
)
def test_global_budget_rejects_invalid_limits_before_request(limits):
    with pytest.raises(ValueError, match="budget"):
        invocation_budget(
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda _: (_ for _ in ()).throw(AssertionError("network"))
                )
            ),
            **limits,
        )


def test_global_bytes_include_multiple_hf_responses_and_stop_further_requests():
    from scripts.benchmark_download_collector.sources import SourceError

    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200, json={"id": "lab/model", "downloads": 1, "padding": "x" * 40}
        )

    budget = invocation_budget(
        httpx.Client(transport=httpx.MockTransport(respond)), requests=5, max_bytes=150
    )
    budget.hf_counts("lab/model")
    with pytest.raises(SourceError):
        budget.hf_counts("lab/model")
    with pytest.raises(SourceError, match="byte_cap"):
        budget.hf_counts("lab/model")
    assert len(calls) == 2 and budget.total_bytes_read > 150 and budget.remaining == 3

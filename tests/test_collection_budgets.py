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

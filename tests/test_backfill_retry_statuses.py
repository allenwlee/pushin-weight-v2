"""Pure status classification for staging search GETs (no database)."""
import pytest

from monitor.backfill_retry import transient


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503, 504, 520])
def test_transient_statuses_retry_at_the_same_cursor(status):
    assert transient(None, status)


@pytest.mark.parametrize("status", [400, 402, 404, 422])
def test_permanent_statuses_are_not_retried(status):
    assert not transient(None, status)


def test_unknown_sends_are_not_transport_failures():
    assert transient("Timeout", None) and transient("ConnectionError", None)
    assert not transient("MalformedReply", None)

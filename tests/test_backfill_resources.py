"""Real transport boundaries for a finite on-demand invocation."""
from types import SimpleNamespace

import pytest


def test_physical_api_retry_consumes_shared_allowance(monkeypatch):
    from monitor.backfill_resources import BackfillBudget, BackfillBudgetExhausted
    from x_monitor.apify import TwitterApiClient

    budget = BackfillBudget(max_api_requests=1, max_llm_calls=2, run_seconds=30)
    starts = []
    response = SimpleNamespace(status_code=500, text="temporary", content=b"{}")
    monkeypatch.setattr("x_monitor.apify.requests.get", lambda *a, **k: starts.append(k) or response)
    monkeypatch.setattr("x_monitor.apify.time.sleep", lambda *_: None)
    api = TwitterApiClient(api_key="test-only", timeout_s=1,
                           before_request=budget.claim_api_request)
    with pytest.raises(BackfillBudgetExhausted):
        api.run_search("qwen", max_results=20, max_pages=1)
    assert len(starts) == 1
    assert budget.snapshot()["api_requests"] == 1


def test_separate_translation_and_classifier_clients_share_model_allowance():
    from monitor.backfill_resources import BackfillBudget, BackfillBudgetExhausted
    from monitor.cycle import _BoundedClassifierClient

    budget = BackfillBudget(max_api_requests=1, max_llm_calls=1, run_seconds=30)
    starts = []
    delegate = SimpleNamespace(messages_create=lambda **kwargs: starts.append(kwargs) or {})
    translation = _BoundedClassifierClient(delegate, maximum_calls=None, pause_seconds=0,
                                           before_call=budget.claim_llm_request)
    classification = _BoundedClassifierClient(delegate, maximum_calls=None, pause_seconds=0,
                                              before_call=budget.claim_llm_request)
    translation.messages_create(model="test", messages=[])
    with pytest.raises(BackfillBudgetExhausted):
        classification.messages_create(model="test", messages=[])
    assert len(starts) == 1
    assert budget.snapshot()["llm_requests"] == 1


def test_no_api_start_without_full_timeout_envelope():
    from monitor.backfill_resources import BackfillBudget, BackfillBudgetExhausted

    now = [0.0]
    budget = BackfillBudget(max_api_requests=3, max_llm_calls=2, run_seconds=10,
                           monotonic=lambda: now[0])
    now[0] = 9.0
    with pytest.raises(BackfillBudgetExhausted, match="deadline"):
        budget.claim_api_request(2)
    assert budget.snapshot()["api_requests"] == 0


def test_shared_search_page_iterator_resumes_exact_provider_cursor(monkeypatch):
    from x_monitor.apify import TwitterApiClient

    received = []
    api = TwitterApiClient(api_key="test-only")
    def response(path, params):
        received.append(params)
        return {"tweets": [{"id": "1", "text": "Qwen", "author": {"id": "2"}}],
                "has_next_page": False, "next_cursor": ""}
    monkeypatch.setattr(api, "_get", response)
    pages = list(api.run_search_pages("qwen", max_results=20, max_pages=1,
                                     since_time=100, until_time=200,
                                     cursor="committed-cursor"))
    assert received[0]["cursor"] == "committed-cursor"
    assert "since_time:100 until_time:200" in received[0]["query"]
    assert len(pages[0].items) == 1
    assert not pages[0].has_more


def test_overlapping_model_clients_cannot_exceed_shared_allowance():
    from concurrent.futures import ThreadPoolExecutor

    from monitor.backfill_resources import BackfillBudget, BackfillBudgetExhausted
    from monitor.cycle import _BoundedClassifierClient

    budget = BackfillBudget(max_api_requests=1, max_llm_calls=4, run_seconds=30)
    delegate = SimpleNamespace(messages_create=lambda **kwargs: {})
    clients = [_BoundedClassifierClient(delegate, maximum_calls=None, pause_seconds=0,
                                       before_call=budget.claim_llm_request) for _ in range(8)]
    def call(client):
        try:
            client.messages_create(model="test", messages=[])
            return True
        except BackfillBudgetExhausted:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(call, clients))
    assert sum(outcomes) == budget.snapshot()["llm_requests"] == 4


@pytest.mark.parametrize("epoch,expected", [(900, 0), (1019, 0), (1020, 780), (1380, 420)])
def test_scheduled_slot_startup_grace_and_reserve(epoch, expected, monkeypatch):
    from monitor.management.commands import backfill

    monkeypatch.setattr(backfill._time, "time", lambda: epoch)
    assert backfill._seconds_to_next_slot() == expected


def test_staff_relevance_reserve_applies_only_to_current_policy_staff_authors():
    from monitor.backfill_collection import staff_relevance_seconds

    cfg = SimpleNamespace(harvest=SimpleNamespace(relevancy_timeout_seconds=30))
    staff = {"author_scope": {"contexts": {"1": {"official_brands": [], "staff_brands": ["openai"]}}}}
    official = {"author_scope": {"contexts": {"1": {"official_brands": ["openai"], "staff_brands": []}}}}
    assert staff_relevance_seconds(staff, cfg, True) == 30
    assert staff_relevance_seconds(staff, cfg, False) == 0
    assert staff_relevance_seconds(official, cfg, True) == 0
    assert staff_relevance_seconds({}, cfg, True) == 0

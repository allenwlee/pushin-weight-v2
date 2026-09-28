"""Offline call-chain proof for scheduled author exclusions."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_scheduled_author_exclusion_reaches_all_seven_provider_requests(monkeypatch):
    """Policy → scheduled runner → concrete client → captured HTTP request."""
    from monitor.cycle import CycleRunner
    from x_monitor import apify
    from x_monitor.config import load_config
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    purposes = []
    requests = []

    def fake_key(purpose):
        purposes.append(purpose)
        return "fake-scheduled-key"

    def fake_get(_self, path, params, **_kwargs):
        requests.append((path, dict(params)))
        return {"tweets": [], "has_next_page": False}

    monkeypatch.setattr(apify, "require_twitterapi_api_key", fake_key)
    monkeypatch.setattr(apify.TwitterApiClient, "_get", fake_get)

    cfg = load_config(REPO_ROOT / "config.yaml")
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    calls = runner._plan_calls()
    client = apify.TwitterApiClient.from_env(runner.twitterapi_credential_purpose)
    window = (1_785_067_200, 1_785_067_260)
    for call in calls:
        items, outcome = runner._fetch_tweets(call, client, window=window)
        assert items == []
        assert outcome == "ok"

    assert purposes == [TwitterApiCredentialPurpose.SCHEDULED]
    assert [call.call_id for call in calls] == ["A", "B1", "C1", "C2", "C3", "B2", "B3"]
    assert len(requests) == 7
    for path, params in requests:
        assert path == apify.SEARCH_PATH
        assert params["queryType"] == "Latest"
        assert params["limit"] == cfg.search.max_per_page
        assert params["query"].count("-from:xxyweb3") == 1
        assert params["query"].endswith(
            " since_time:1785067200 until_time:1785067260"
        )
        assert len(params["query"]) <= 512

    manual_calls = CycleRunner(cfg=cfg, cycle_kind="manual")._plan_calls()
    assert all("-from:xxyweb3" not in call.query_string for call in manual_calls)


def test_exclusion_growth_over_final_cap_sends_no_provider_request(monkeypatch):
    """The time-bounded request fails closed when registry growth exhausts headroom."""
    from monitor.cycle import CycleRunner
    from x_monitor import apify
    from x_monitor.config import load_config
    from x_monitor.harvest_policy import load_policy
    from x_monitor.query_plan import plan_calls
    from x_monitor.specs_from_policy import primary_keywords_from_policy, specs_from_policy

    policy = load_policy(REPO_ROOT / "config/harvest_policy.yaml")
    handles = tuple(f"spam_author_{index}" for index in range(5))
    calls = plan_calls(
        2067062923525275922,
        specs_from_policy(policy),
        primary_keywords=primary_keywords_from_policy(policy),
        excluded_author_handles=handles,
    )
    b1 = next(call for call in calls if call.call_id == "B1")
    assert len(b1.query_string) <= 512
    assert len(b1.query_string) + 44 > 512

    def forbidden_get(*_args, **_kwargs):
        raise AssertionError("over-cap query reached provider transport")

    monkeypatch.setattr(apify.TwitterApiClient, "_get", forbidden_get)
    runner = CycleRunner(cfg=load_config(REPO_ROOT / "config.yaml"), cycle_kind="scheduled")
    items, outcome = runner._fetch_tweets(
        b1,
        apify.TwitterApiClient(api_key="fake-key"),
        window=(1_785_067_200, 1_785_067_260),
    )
    assert items == []
    assert outcome == "length_cap_exceeded"

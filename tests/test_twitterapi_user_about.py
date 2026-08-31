from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from core.models import Account
from monitor.twitterapi.user_about import (
    FetchSelection,
    IdentityMismatchError,
    SchemaDriftError,
    describe_json_shape,
    fetch_user_about_batch,
    parse_user_about,
)


def _complete_payload() -> dict:
    return {
        "status": "success",
        "data": {
            "id": "42",
            "name": "Example Account",
            "userName": "example",
            "createdAt": "Wed Jul 22 03:40:35 +0000 2026",
            "isVerified": True,
            "isBlueVerified": True,
            "protected": False,
            "profilePicture": "https://cdn.example/avatar.png",
            "verification_info": {
                "id": "verification-42",
                "is_identity_verified": True,
                "reason": {"verified_since_msec": "1784691635000"},
            },
            "affiliates_highlighted_label": {
                "label": {
                    "badge": {"url": "https://cdn.example/badge.png"},
                    "description": "Affiliate",
                    "url": {"url": "https://x.com/example", "urlType": "DeepLink"},
                    "userLabelDisplayType": "Badge",
                    "userLabelType": "BusinessLabel",
                }
            },
            "about_profile": {
                "account_based_in": "United States",
                "location_accurate": True,
                "created_country_accurate": False,
                "learn_more_url": "https://help.x.com/about",
                "affiliate_username": "parent",
                "source": "ip",
                "username_changes": {
                    "count": "2",
                    "last_changed_at_msec": "1784691635000",
                },
            },
            "identity_profile_labels_highlighted_label": {
                "label": {
                    "badge": {"url": "https://cdn.example/identity.png"},
                    "description": "Identity",
                    "long_description": {
                        "text": "Identity details",
                        "entities": [
                            {
                                "from_index": 0,
                                "to_index": 8,
                                "ref": {
                                    "__isTimelineReferenceObject": "TimelineUser",
                                    "__typename": "TimelineUser",
                                    "screen_name": "reference",
                                    "user_results": {},
                                },
                            }
                        ],
                    },
                    "url": {"url": "https://x.com/identity", "urlType": "DeepLink"},
                    "userLabelDisplayType": "Badge",
                    "userLabelType": "IdentityLabel",
                }
            },
        },
    }


def test_complete_response_flattens_every_documented_leaf():
    observed_at = datetime(2026, 8, 29, tzinfo=UTC)
    observation = parse_user_about(
        _complete_payload(), expected_author_id="42", observed_at=observed_at
    )

    assert observation.author_id == "42"
    assert observation.candidates["display_name"] == "Example Account"
    assert observation.candidates["handle"] == "example"
    assert observation.candidates["created_at"].year == 2026
    assert observation.candidates["verified"] is True
    assert observation.candidates["is_blue_verified"] is True
    assert observation.candidates["protected"] is False
    assert observation.candidates["profile_picture"].endswith("avatar.png")
    assert observation.candidates["verification_info_id"] == "verification-42"
    assert observation.candidates["verification_info_is_identity_verified"] is True
    assert (
        observation.candidates["verification_info_reason_verified_since_msec"]
        == 1_784_691_635_000
    )
    assert observation.candidates["affiliate_label_description"] == "Affiliate"
    assert observation.candidates["account_based_in"] == "United States"
    assert observation.candidates["created_country_accurate"] is False
    assert observation.candidates["country_code"] == "US"
    assert observation.candidates["username_changes_count"] == 2
    assert (
        observation.candidates["username_changes_last_changed_at_msec"]
        == 1_784_691_635_000
    )
    assert observation.candidates["identity_profile_label_description"] == "Identity"
    assert (
        observation.candidates["identity_profile_label_long_description"]
        == "Identity details"
    )
    assert observation.candidates["account_based_in_fetched_at"] == observed_at


def test_live_probe_shape_parses_with_empty_optional_labels():
    payload = _complete_payload()
    payload["data"]["affiliates_highlighted_label"] = {}
    payload["data"]["identity_profile_labels_highlighted_label"] = {}
    payload["data"]["about_profile"].pop("affiliate_username")

    observation = parse_user_about(
        payload,
        expected_author_id="42",
        observed_at=datetime(2026, 8, 30, tzinfo=UTC),
    )

    assert observation.candidates["verification_info_id"] == "verification-42"
    assert observation.candidates["created_country_accurate"] is False
    assert observation.candidates["affiliate_label_description"] is None
    assert observation.candidates["identity_profile_label_description"] is None
    assert observation.candidates["identity_profile_label_long_description"] is None


def test_identity_label_long_description_rejects_unknown_entity_shape():
    payload = _complete_payload()
    entity = payload["data"]["identity_profile_labels_highlighted_label"]["label"][
        "long_description"
    ]["entities"][0]
    entity["unexpected"] = "value"

    with pytest.raises(SchemaDriftError, match="unknown leaves"):
        parse_user_about(
            payload,
            expected_author_id="42",
            observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        )


def test_missing_optional_objects_checkpoint_without_implicit_clears():
    observed_at = datetime(2026, 8, 29, tzinfo=UTC)
    observation = parse_user_about(
        {"status": "success", "data": {"id": "42", "name": "Example"}},
        expected_author_id="42",
        observed_at=observed_at,
    )

    assert observation.present_fields == {
        "display_name",
        "account_based_in_fetched_at",
    }
    assert observation.candidates["account_based_in_fetched_at"] == observed_at


def test_unavailable_variant_checkpoints_only_typed_availability_fields():
    observed_at = datetime(2026, 8, 30, tzinfo=UTC)
    observation = parse_user_about(
        {
            "status": "success",
            "msg": "ok",
            "data": {
                "unavailable": True,
                "unavailableReason": "Account unavailable",
            },
        },
        expected_author_id="42",
        observed_at=observed_at,
    )

    assert observation.author_id == "42"
    assert observation.candidates == {
        "unavailable": True,
        "unavailable_reason": "Account unavailable",
        "account_based_in_fetched_at": observed_at,
    }
    assert observation.present_fields == set(observation.candidates)


@pytest.mark.parametrize(
    "data",
    [
        {"unavailable": False, "unavailableReason": "Account unavailable"},
        {"unavailableReason": "Account unavailable"},
        {"unavailable": "true", "unavailableReason": "Account unavailable"},
    ],
)
def test_malformed_unavailable_variant_is_schema_drift(data):
    with pytest.raises(SchemaDriftError):
        parse_user_about(
            {"status": "success", "data": data},
            expected_author_id="42",
            observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        )


def test_unresolved_value_stores_exact_value_and_clears_normalized_targets():
    payload = _complete_payload()
    payload["data"]["about_profile"]["account_based_in"] = "Asia Pacific"
    observation = parse_user_about(
        payload,
        expected_author_id="42",
        observed_at=datetime(2026, 8, 29, tzinfo=UTC),
    )

    assert observation.candidates["account_based_in"] == "Asia Pacific"
    assert observation.candidates["country_code"] is None
    assert observation.candidates["based_in_region_key"] is None
    assert {"country_code", "based_in_region_key"} <= observation.present_fields


def test_provider_region_derives_direct_region_and_clears_country():
    payload = _complete_payload()
    payload["data"]["about_profile"]["account_based_in"] = "Europe"
    observation = parse_user_about(
        payload,
        expected_author_id="42",
        observed_at=datetime(2026, 8, 29, tzinfo=UTC),
    )

    assert observation.candidates["account_based_in"] == "Europe"
    assert observation.candidates["country_code"] is None
    assert observation.candidates["based_in_region_key"] == "europe"
    assert {"country_code", "based_in_region_key"} <= observation.present_fields


@pytest.mark.django_db
def test_real_parser_to_orm_transition_clears_stale_geography_target():
    account = Account.objects.create(author_id="42")
    observed_at = datetime(2026, 8, 29, tzinfo=UTC)

    europe_payload = _complete_payload()
    europe_payload["data"]["about_profile"]["account_based_in"] = "Europe"
    europe = parse_user_about(
        europe_payload,
        expected_author_id="42",
        observed_at=observed_at,
    )
    Account.apply_observation(
        author_id="42",
        observed_author_id=europe.author_id,
        source="user_about",
        observed_at=observed_at,
        candidates=europe.candidates,
        present_fields=europe.present_fields,
    )
    account.refresh_from_db()
    assert account.country_code is None
    assert account.based_in_region_key == "europe"

    country_payload = _complete_payload()
    country_payload["data"]["about_profile"]["account_based_in"] = "United States"
    country = parse_user_about(
        country_payload,
        expected_author_id="42",
        observed_at=observed_at,
    )
    Account.apply_observation(
        author_id="42",
        observed_author_id=country.author_id,
        source="user_about",
        observed_at=observed_at,
        candidates=country.candidates,
        present_fields=country.present_fields,
    )
    account.refresh_from_db()
    assert account.country_code == "US"
    assert account.based_in_region_key is None


@pytest.mark.parametrize(
    ("provider_name", "expected_code"),
    [
        ("Turkey", "TR"),
        ("Russian Federation", "RU"),
        ("Macedonia", "MK"),
    ],
)
def test_provider_country_alias_derives_country_code(provider_name, expected_code):
    payload = _complete_payload()
    payload["data"]["about_profile"]["account_based_in"] = provider_name
    observation = parse_user_about(
        payload,
        expected_author_id="42",
        observed_at=datetime(2026, 8, 29, tzinfo=UTC),
    )

    assert observation.candidates["account_based_in"] == provider_name
    assert observation.candidates["country_code"] == expected_code
    assert observation.candidates["based_in_region_key"] is None
    assert {"country_code", "based_in_region_key"} <= observation.present_fields


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["data"].__setitem__("surprise", "drift"),
        lambda payload: payload["data"].__setitem__("protected", "false"),
        lambda payload: payload["data"]["about_profile"][
            "username_changes"
        ].__setitem__("count", "two"),
        lambda payload: payload["data"]["about_profile"][
            "username_changes"
        ].__setitem__("last_changed_at_msec", "yesterday"),
        lambda payload: payload["data"]["verification_info"]["reason"].__setitem__(
            "verified_since_msec", "yesterday"
        ),
    ],
)
def test_unknown_leaf_or_wrong_type_rejects_entire_response(mutate):
    payload = _complete_payload()
    mutate(payload)
    with pytest.raises(SchemaDriftError):
        parse_user_about(
            payload,
            expected_author_id="42",
            observed_at=datetime(2026, 8, 29, tzinfo=UTC),
        )


def test_schema_shape_contains_paths_and_types_without_values_or_identity():
    payload = _complete_payload()
    payload["data"]["unknownLeaf"] = "secret-value"
    payload["data"]["example"] = {"nested": "also-secret"}

    shape = describe_json_shape(
        payload,
        sensitive_values={"42"},
    )
    rendered = repr(shape)

    assert "$.data.unknownLeaf:string" in shape
    assert "$.data.about_profile.location_accurate:boolean" in shape
    assert "secret-value" not in rendered
    assert "also-secret" not in rendered
    assert "42" not in rendered
    assert "$.data.example" not in rendered
    assert "<redacted-key>" in rendered


def test_returned_id_must_match_selected_account():
    with pytest.raises(IdentityMismatchError):
        parse_user_about(
            _complete_payload(),
            expected_author_id="99",
            observed_at=datetime(2026, 8, 29, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_fetch_batch_reuses_session_and_counts_429_retry(monkeypatch):
    import json
    from unittest.mock import AsyncMock, MagicMock

    payload = _complete_payload()

    def response(status, body, headers=None):
        item = MagicMock()
        item.status = status
        item.headers = headers or {}
        item.text = AsyncMock(return_value=body)
        item.__aenter__ = AsyncMock(return_value=item)
        item.__aexit__ = AsyncMock(return_value=None)
        return item

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = MagicMock(
        side_effect=[
            response(429, "rate limited", {"Retry-After": "0"}),
            response(200, json.dumps(payload)),
        ]
    )
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    result = await fetch_user_about_batch(
        [FetchSelection(author_id="42", handle="example")],
        api_key="secret",
        rate_qps=5,
        max_attempts=2,
        max_credits=36,
        max_wall_seconds=60,
    )

    assert result.attempts == 2
    assert result.retries == 1
    assert result.projected_credits == 36
    assert result.stop_reason is None
    assert result.outcomes[0].observation is not None
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_batch_quarantines_schema_drift_without_raw_payload(monkeypatch):
    import json
    from unittest.mock import AsyncMock, MagicMock

    payload = _complete_payload()
    payload["data"]["unknown"] = "secret-value"
    response = MagicMock()
    response.status = 200
    response.headers = {}
    response.text = AsyncMock(return_value=json.dumps(payload))
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = MagicMock(return_value=response)
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    result = await fetch_user_about_batch(
        [FetchSelection(author_id="42", handle="example")],
        api_key="secret",
        rate_qps=5,
        max_attempts=2,
        max_credits=36,
        max_wall_seconds=60,
    )

    assert result.stop_reason is None
    assert result.outcomes[0].reason == "schema_drift"
    assert "parser_error:unknown_leaves:response.data" in (
        result.outcomes[0].schema_diagnostic or ()
    )
    assert "$.data.unknown:string" in (result.outcomes[0].schema_diagnostic or ())
    assert "secret-value" not in repr(result)


@pytest.mark.asyncio
async def test_fetch_batch_quarantines_identity_mismatch_and_continues(monkeypatch):
    import json
    from unittest.mock import AsyncMock, MagicMock

    mismatched = _complete_payload()
    mismatched["data"]["id"] = "999"
    accepted = _complete_payload()
    accepted["data"]["id"] = "43"
    accepted["data"]["userName"] = "second"
    responses = [
        _fake_response(200, json.dumps(mismatched)),
        _fake_response(200, json.dumps(accepted)),
    ]
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = MagicMock(side_effect=responses)
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    result = await fetch_user_about_batch(
        [
            FetchSelection(author_id="42", handle="example"),
            FetchSelection(author_id="43", handle="second"),
        ],
        api_key="secret",
        rate_qps=5,
        concurrency=1,
        max_attempts=2,
        max_credits=36,
        max_wall_seconds=60,
    )

    assert result.stop_reason is None
    assert [outcome.reason for outcome in result.outcomes] == [
        "identity_mismatch",
        "success",
    ]
    assert result.attempts == 2


def _fake_response(status, body="error", headers=None):
    from unittest.mock import AsyncMock, MagicMock

    response = MagicMock()
    response.status = status
    response.headers = headers or {}
    response.text = AsyncMock(return_value=body)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def _fake_session(monkeypatch, side_effect):
    from unittest.mock import AsyncMock, MagicMock

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = MagicMock(side_effect=side_effect)
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)
    return session


@pytest.mark.asyncio
async def test_fetch_batch_stops_exactly_at_attempt_budget(monkeypatch):
    session = _fake_session(
        monkeypatch,
        [_fake_response(500) for _ in range(3)],
    )

    result = await fetch_user_about_batch(
        [
            FetchSelection(author_id=str(index), handle=f"user{index}")
            for index in range(3)
        ],
        api_key="secret",
        rate_qps=100,
        max_attempts=3,
        max_credits=180,
        max_wall_seconds=60,
        sleep=AsyncMock(),
    )

    assert result.attempts == 3
    assert result.projected_credits == 54
    assert result.stop_reason == "attempt_budget"
    assert session.get.call_count == 3


@pytest.mark.asyncio
async def test_fetch_batch_stops_exactly_at_credit_budget(monkeypatch):
    session = _fake_session(
        monkeypatch,
        [_fake_response(500) for _ in range(2)],
    )

    result = await fetch_user_about_batch(
        [
            FetchSelection(author_id="1", handle="one"),
            FetchSelection(author_id="2", handle="two"),
        ],
        api_key="secret",
        rate_qps=100,
        max_attempts=10,
        max_credits=36,
        max_wall_seconds=60,
        sleep=AsyncMock(),
    )

    assert result.attempts == 2
    assert result.projected_credits == 36
    assert result.stop_reason == "credit_budget"
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_batch_retry_cannot_cross_wall_budget(monkeypatch):
    now = [0.0]

    async def advance(seconds):
        now[0] += seconds

    session = _fake_session(
        monkeypatch,
        [_fake_response(429, headers={"Retry-After": "30"})],
    )
    monkeypatch.setattr("random.uniform", lambda _low, _high: 0.1)

    result = await fetch_user_about_batch(
        [FetchSelection(author_id="1", handle="one")],
        api_key="secret",
        rate_qps=5,
        max_attempts=2,
        max_credits=36,
        max_wall_seconds=5,
        clock=lambda: now[0],
        sleep=advance,
    )

    assert result.attempts == 1
    assert result.wall_seconds == 5
    assert result.stop_reason == "wall_time_budget"
    assert session.get.call_count == 1


@pytest.mark.asyncio
async def test_fetch_batch_paces_retry_request(monkeypatch):
    import json

    now = [0.0]
    starts = []

    async def advance(seconds):
        now[0] += seconds

    responses = iter(
        [
            _fake_response(429, headers={"Retry-After": "0"}),
            _fake_response(200, json.dumps(_complete_payload())),
        ]
    )
    session = _fake_session(monkeypatch, [])

    def get(*args, **kwargs):
        starts.append(now[0])
        return next(responses)

    session.get.side_effect = get
    monkeypatch.setattr("random.uniform", lambda _low, _high: 0.1)

    result = await fetch_user_about_batch(
        [FetchSelection(author_id="42", handle="example")],
        api_key="secret",
        rate_qps=5,
        max_attempts=2,
        max_credits=36,
        max_wall_seconds=60,
        clock=lambda: now[0],
        sleep=advance,
    )

    assert result.stop_reason is None
    assert starts == pytest.approx([0.0, 0.2])


@pytest.mark.asyncio
async def test_fetch_batch_stops_immediately_on_auth_failure(monkeypatch):
    session = _fake_session(monkeypatch, [_fake_response(401)])

    result = await fetch_user_about_batch(
        [
            FetchSelection(author_id="1", handle="one"),
            FetchSelection(author_id="2", handle="two"),
        ],
        api_key="secret",
        rate_qps=5,
        max_attempts=2,
        max_credits=36,
        max_wall_seconds=60,
    )

    assert result.attempts == 1
    assert result.stop_reason == "auth_invalid"
    assert session.get.call_count == 1


@pytest.mark.asyncio
async def test_fetch_batch_opens_circuit_after_ten_failed_accounts(monkeypatch):
    session = _fake_session(
        monkeypatch,
        [_fake_response(500) for _ in range(20)],
    )

    result = await fetch_user_about_batch(
        [
            FetchSelection(author_id=str(index), handle=f"user{index}")
            for index in range(11)
        ],
        api_key="secret",
        rate_qps=100,
        max_attempts=22,
        max_credits=396,
        max_wall_seconds=60,
        sleep=AsyncMock(),
    )

    assert result.attempts == 20
    assert len(result.outcomes) == 10
    assert result.stop_reason == "circuit_open"
    assert session.get.call_count == 20


@pytest.mark.asyncio
async def test_concurrent_fetch_never_exceeds_attempt_or_connector_budget(monkeypatch):
    import asyncio
    from unittest.mock import MagicMock

    active = 0
    peak_active = 0
    request_count = 0

    class ResponseContext:
        status = 500

        def __init__(self):
            self.headers = {}

        async def __aenter__(self):
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            await asyncio.sleep(0)
            return self

        async def __aexit__(self, *_args):
            nonlocal active
            active -= 1

        async def text(self):
            await asyncio.sleep(0)
            return "error"

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    def get(*_args, **_kwargs):
        nonlocal request_count
        request_count += 1
        return ResponseContext()

    session.get.side_effect = get
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)

    result = await fetch_user_about_batch(
        [
            FetchSelection(author_id=str(index), handle=f"user{index}")
            for index in range(10)
        ],
        api_key="secret",
        rate_qps=1_000,
        concurrency=3,
        max_attempts=4,
        max_credits=72,
        max_wall_seconds=60,
    )

    assert result.attempts == 4
    assert result.projected_credits == 72
    assert result.stop_reason == "attempt_budget"
    assert request_count == 4
    assert peak_active <= 3


@pytest.mark.asyncio
async def test_schema_drift_does_not_stop_queued_request_admission(monkeypatch):
    import asyncio
    import json
    from unittest.mock import MagicMock

    request_count = 0

    class ResponseContext:
        status = 200

        def __init__(self, payload):
            self.payload = payload
            self.headers = {}

        async def __aenter__(self):
            await asyncio.sleep(0)
            return self

        async def __aexit__(self, *_args):
            return None

        async def text(self):
            return self.payload

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    def get(*_args, **kwargs):
        nonlocal request_count
        handle = kwargs["params"]["userName"]
        author_id = handle.removeprefix("user")
        payload = _complete_payload()
        payload["data"]["id"] = author_id
        payload["data"]["userName"] = handle
        if author_id == "0":
            payload["data"]["verification_info"]["reason"]["override_verified_year"] = (
                2025.5
            )
        request_count += 1
        return ResponseContext(json.dumps(payload))

    session.get.side_effect = get
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)

    result = await fetch_user_about_batch(
        [
            FetchSelection(author_id=str(index), handle=f"user{index}")
            for index in range(10)
        ],
        api_key="secret",
        rate_qps=1_000,
        concurrency=2,
        max_attempts=10,
        max_credits=180,
        max_wall_seconds=60,
    )

    assert result.stop_reason is None
    assert request_count == 10
    assert len(result.outcomes) == 10
    assert [outcome.reason for outcome in result.outcomes].count("schema_drift") == 1
    assert [outcome.reason for outcome in result.outcomes].count("success") == 9
    assert (
        "parser_error:response.data.verification_info.reason."
        "override_verified_year must be a nonnegative integer"
    ) in (result.outcomes[0].schema_diagnostic or ())


@pytest.mark.asyncio
async def test_consecutive_account_quarantines_stop_systemic_drift(monkeypatch):
    import json
    from unittest.mock import AsyncMock, MagicMock

    payload = _complete_payload()
    payload["data"]["unknown"] = "private"
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = MagicMock(
        side_effect=[_fake_response(200, json.dumps(payload)) for _ in range(12)]
    )
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    result = await fetch_user_about_batch(
        [
            FetchSelection(author_id=str(index), handle=f"user{index}")
            for index in range(12)
        ],
        api_key="secret",
        rate_qps=1_000,
        concurrency=1,
        max_attempts=12,
        max_credits=216,
        max_wall_seconds=60,
    )

    assert result.stop_reason == "account_quarantine_threshold"
    assert result.attempts == 10
    assert len(result.outcomes) == 10

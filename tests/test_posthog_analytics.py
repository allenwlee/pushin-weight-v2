import json
import re
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import resolve

from project.analytics import (
    PostHogMiddleware,
    _get_client,
    _make_client,
    account_distinct_id,
    capture,
)


@pytest.fixture
def configured(settings):
    settings.POSTHOG_ENABLED = True
    settings.POSTHOG_PROJECT_TOKEN = "phc_test_project"
    settings.POSTHOG_REGION = "us"
    settings.POSTHOG_ENVIRONMENT = "test"


def page_response(path="/", *, consent="granted", user_id=None, headers=None):
    request = RequestFactory().get(path, **(headers or {}))
    request.resolver_match = resolve(request.path)
    request.user = SimpleNamespace(is_authenticated=user_id is not None, pk=user_id)
    if consent:
        request.COOKIES["pw_analytics_consent"] = consent
    original = HttpResponse("<html><head></head><body>Page</body></html>")
    original["Content-Length"] = str(len(original.content))
    return PostHogMiddleware(lambda _: original)(request)


def bootstrap(response):
    match = re.search(
        r'<script id="pw-analytics-config" type="application/json">(.*?)</script>',
        response.content.decode(),
    )
    return json.loads(match.group(1)) if match else None


def test_default_disabled(settings):
    settings.POSTHOG_ENABLED = False
    assert bootstrap(page_response()) is None
    with patch("project.analytics._get_client") as factory:
        assert capture("analytics setup test", distinct_id="setup:test") is False
        factory.assert_not_called()


@pytest.mark.parametrize("consent", [None, "denied", "unknown"])
def test_no_browser_loading_without_opt_in(configured, consent):
    assert bootstrap(page_response(consent=consent)) is None


@pytest.mark.parametrize("headers", [{"HTTP_DNT": "1"}, {"HTTP_SEC_GPC": "1"}])
def test_browser_preferences_override_consent(configured, headers):
    assert bootstrap(page_response(headers=headers)) is None


@pytest.mark.parametrize(
    "path", ["/internal/", "/accounts/login/", "/feed/", "/admin/"]
)
def test_private_auth_and_api_routes_excluded(configured, path):
    assert bootstrap(page_response(path)) is None


def test_bounded_bootstrap_and_cache_headers(configured):
    response = page_response("/?email=private@example.com&token=secret", user_id=17)
    config = bootstrap(response)
    assert config == {
        "token": "phc_test_project",
        "host": "https://us.i.posthog.com",
        "environment": "test",
        "isTest": True,
        "path": "/",
        "userId": "pushinweight:user:17",
    }
    assert b"private@example.com" not in response.content
    assert b"secret" not in response.content
    assert "Cookie" in response["Vary"]
    assert "private" in response["Cache-Control"]
    assert int(response["Content-Length"]) == len(response.content)


def test_unconfigured_host_or_token_disables(settings, configured):
    settings.POSTHOG_REGION = "unexpected"
    assert bootstrap(page_response()) is None
    assert capture("analytics setup test", distinct_id="setup:test") is False
    settings.POSTHOG_REGION = "us"
    settings.POSTHOG_PROJECT_TOKEN = ""
    assert bootstrap(page_response()) is None


def test_matching_account_id():
    assert account_distinct_id(17) == "pushinweight:user:17"
    assert account_distinct_id("name@example.com") is None


def test_setup_event_is_always_test_traffic(configured, settings):
    settings.POSTHOG_ENVIRONMENT = "production"
    fake = Mock()
    with patch("project.analytics._get_client", return_value=fake):
        assert capture("analytics setup test", distinct_id="setup:test")
    assert fake.capture.call_args.kwargs["properties"]["is_test"] is True


def test_server_capture_bounds_metadata_and_uses_matching_identity(configured):
    fake = Mock()
    fake.capture.return_value = "event-uuid"
    with patch("project.analytics._get_client", return_value=fake):
        assert capture(
            "analytics setup test",
            user_id=17,
            properties={
                "setup_run_id": "test-run",
                "email": "private",
                "text": "secret",
            },
        )
    fake.capture.assert_called_once_with(
        "analytics setup test",
        distinct_id="pushinweight:user:17",
        properties={
            "setup_run_id": "test-run",
            "environment": "test",
            "channel": "server",
            "is_test": True,
            "$process_person_profile": False,
        },
    )


def test_server_failure_does_not_escape(configured, caplog):
    with patch(
        "project.analytics._get_client",
        side_effect=RuntimeError("private token contents"),
    ):
        assert capture("analytics setup test", distinct_id="setup:test") is False
    assert "private token contents" not in caplog.text


def test_real_sdk_delivery_failure_redacts_response_and_payload(configured, caplog):
    with patch(
        "posthog.consumer.Consumer.request",
        side_effect=RuntimeError("credential-and-payload"),
    ):
        client = _get_client()
        try:
            assert capture("analytics setup test", distinct_id="setup:test")
            client.flush(timeout_seconds=3)
        finally:
            client.shutdown()
            _make_client.cache_clear()
    assert "RuntimeError" in caplog.text
    assert "credential-and-payload" not in caplog.text


def test_unregistered_events_and_unbounded_metadata_rejected(configured):
    with patch("project.analytics._get_client") as factory:
        assert capture("prediction created", distinct_id="setup:test") is False
        assert (
            capture("analytics setup test", distinct_id="private@example.com") is False
        )
        factory.assert_not_called()

from __future__ import annotations

import socket
from dataclasses import replace
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from project.middleware import StagingOwnerOnlyMiddleware
from scripts.ollija.config import load_project_config
from scripts.ollija.database import DatabaseFingerprint, safety_policy_from_config
from scripts.ollija.preview import PreviewError, build_preview_plan, port_is_available

REPO_ROOT = Path(__file__).resolve().parents[2]


def _active_local_database() -> DatabaseFingerprint:
    return DatabaseFingerprint(
        environment="local",
        host="local_socket",
        port=5432,
        database="pushinweight_staging_shadow_20260814t120000z",
        role="fuchitalee",
        resource_id="local:fuchitalee",
        marker_environment="staging",
        marker_status="active",
    )


def test_preview_requires_active_local_postgres_and_an_available_port() -> None:
    config = load_project_config(REPO_ROOT)
    policy = safety_policy_from_config(config)

    with pytest.raises(PreviewError, match="preview_database_not_postgres"):
        build_preview_plan(
            config,
            database_url="sqlite:///tmp/dev.db",
            database=_active_local_database(),
            policy=policy,
            port_available=lambda _host, _port: True,
            tailscale_dns_name="fuchitalee.example.ts.net",
        )

    with pytest.raises(PreviewError, match="preview_port_occupied"):
        build_preview_plan(
            config,
            database_url="postgresql:///pushinweight_staging_shadow_20260814t120000z",
            database=_active_local_database(),
            policy=policy,
            port_available=lambda _host, _port: False,
            tailscale_dns_name="fuchitalee.example.ts.net",
        )

    with pytest.raises(Exception, match="target_is_production"):
        build_preview_plan(
            config,
            database_url="postgresql:///pushinweight_shadow",
            database=replace(
                _active_local_database(),
                database="pushinweight_shadow",
                resource_id="dpg-d9koekqjobas73fvjqng-a",
            ),
            policy=policy,
            port_available=lambda _host, _port: True,
            tailscale_dns_name="fuchitalee.example.ts.net",
        )


def test_preview_plan_is_private_and_disables_provider_work() -> None:
    config = load_project_config(REPO_ROOT)
    plan = build_preview_plan(
        config,
        database_url="postgresql:///pushinweight_staging_shadow_20260814t120000z",
        database=_active_local_database(),
        policy=safety_policy_from_config(config),
        port_available=lambda _host, _port: True,
        tailscale_dns_name="fuchitalee.example.ts.net.",
    )

    assert plan.local_url == "http://127.0.0.1:8011"
    assert plan.private_url == "https://fuchitalee.example.ts.net"
    assert plan.environment["OLLIJA_STAGING_MODE"] == "True"
    assert plan.environment["XMONITOR_DRY_RUN"] == "True"
    assert plan.environment["X_MONITOR_HEADLINE_SERVING_ENABLED"] == "False"
    assert plan.environment["X_MONITOR_HEADLINE_ENQUEUE_ENABLED"] == "False"
    assert plan.environment["X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED"] == "False"
    assert "TWITTERAPI_IO_API_KEY" in plan.removed_environment_keys
    assert "DEEPSEEK_API_KEY" in plan.removed_environment_keys


def test_real_port_probe_rejects_an_existing_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        assert port_is_available("127.0.0.1", port) is False


def _response(_request):
    return HttpResponse("ok")


@override_settings(
    OLLIJA_STAGING_MODE=True,
    OLLIJA_STAGING_ALLOWED_EMAILS=frozenset({"owner@example.com"}),
    LOGIN_URL="/accounts/login/",
)
def test_staging_auth_boundary_allows_login_routes_and_only_allowlisted_owner() -> None:
    middleware = StagingOwnerOnlyMiddleware(_response)
    request = RequestFactory().get("/accounts/google/login/")
    request.user = AnonymousUser()
    assert middleware(request).status_code == 200

    request = RequestFactory().get("/feed/")
    request.user = AnonymousUser()
    response = middleware(request)
    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")

    request = RequestFactory().get("/feed/")
    request.user = get_user_model()(email="someone@example.com")
    request.user.pk = 1
    assert middleware(request).status_code == 403

    request = RequestFactory().get("/feed/")
    request.user = get_user_model()(email=" OWNER@example.com ")
    request.user.pk = 1
    assert middleware(request).status_code == 200


@override_settings(
    OLLIJA_STAGING_MODE=False,
    OLLIJA_STAGING_ALLOWED_EMAILS=frozenset(),
)
def test_production_requests_are_unchanged_by_staging_boundary() -> None:
    middleware = StagingOwnerOnlyMiddleware(_response)
    request = RequestFactory().get("/feed/")
    request.user = AnonymousUser()

    assert middleware(request).status_code == 200

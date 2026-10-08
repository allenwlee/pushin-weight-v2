"""Opt-in pageviews and bounded, asynchronous PostHog server events."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from functools import lru_cache
from threading import Lock

from django.conf import settings
from django.templatetags.static import static
from django.utils.cache import patch_cache_control, patch_vary_headers
from django.utils.html import format_html, json_script

logger = logging.getLogger(__name__)
HOSTS = {"us": "https://us.i.posthog.com", "eu": "https://eu.i.posthog.com"}
ENVIRONMENTS = {"development", "test", "staging", "production"}
SERVER_EVENTS = frozenset({"analytics setup test"})
_client_lock = Lock()


class _SDKLogFilter(logging.Filter):
    def filter(self, record):
        # Vendor logs can include raw response bodies; our callback reports the error type.
        record.msg = "PostHog SDK %s"
        record.args = (record.levelname.lower(),)
        record.exc_info = None
        record.stack_info = None
        return True


def _configuration():
    token = getattr(settings, "POSTHOG_PROJECT_TOKEN", "")
    host = HOSTS.get(getattr(settings, "POSTHOG_REGION", ""))
    environment = getattr(settings, "POSTHOG_ENVIRONMENT", "")
    if (
        not getattr(settings, "POSTHOG_ENABLED", False)
        or not token.startswith("phc_")
        or not host
        or environment not in ENVIRONMENTS
    ):
        return None
    return token, host, environment


def account_distinct_id(user_id):
    """Use the same stable internal account identity in both SDKs."""
    if re.fullmatch(r"[1-9][0-9]{0,19}", str(user_id)):
        return f"pushinweight:user:{user_id}"
    return None


def _delivery_error(error, _items):
    # SDK errors and items can contain credentials or payloads.
    logger.warning("PostHog delivery failed (%s)", type(error).__name__)


@lru_cache(maxsize=1)
def _make_client(pid, token, host):
    from posthog import Posthog

    sdk_logger = logging.getLogger("posthog")
    if not any(isinstance(item, _SDKLogFilter) for item in sdk_logger.filters):
        sdk_logger.addFilter(_SDKLogFilter())
    return Posthog(
        token,
        host=host,
        sync_mode=False,
        max_queue_size=100,
        thread=1,
        flush_at=10,
        flush_interval=2,
        max_retries=1,
        timeout=2,
        disable_geoip=True,
        on_error=_delivery_error,
        enable_exception_autocapture=False,
    )


def _get_client():
    token, host, _environment = _configuration()
    with _client_lock:
        # Initialize after fork, with one cached client per web process.
        return _make_client(os.getpid(), token, host)


def capture(event, *, user_id=None, distinct_id=None, properties=None):
    """Queue an approved event; False means it was disabled or not queued.

    This never flushes or waits for HTTP delivery. Capture is not ingestion
    proof; operator verification queries the labeled event separately.
    """
    configuration = _configuration()
    if not configuration or not isinstance(event, str) or event not in SERVER_EVENTS:
        return False
    identity = account_distinct_id(user_id) if user_id is not None else distinct_id
    if (
        not isinstance(identity, str)
        or not identity
        or (user_id is None and not re.fullmatch(r"setup:[A-Za-z0-9-]{1,64}", identity))
    ):
        return False
    environment = configuration[2]
    bounded = {}
    run_id = properties.get("setup_run_id") if isinstance(properties, Mapping) else None
    if isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id):
        bounded["setup_run_id"] = run_id
    bounded.update(
        environment=environment,
        channel="server",
        is_test=True,  # The only registered event is an operator setup test.
        **{"$process_person_profile": False},
    )
    try:
        return bool(
            _get_client().capture(event, distinct_id=identity, properties=bounded)
        )
    except Exception as error:  # noqa: BLE001 -- optional analytics must fail open
        logger.warning("PostHog capture unavailable (%s)", type(error).__name__)
        return False


class PostHogMiddleware:
    """Add analytics only to opted-in, complete public HTML responses.

    Response insertion keeps the shared shell and future G5 templates intact.
    API/partial/auth/private pages never load the SDK.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        configuration = _configuration()
        if (
            not configuration
            or not match
            or match.url_name not in {"home", "brand_home"}
            or request.method != "GET"
            or response.status_code != 200
            or response.streaming
            or "text/html" not in response.get("Content-Type", "")
            or request.headers.get("HX-Request") == "true"
        ):
            return response
        patch_vary_headers(response, ("Cookie", "DNT", "Sec-GPC"))
        if (
            request.COOKIES.get("pw_analytics_consent") != "granted"
            or request.headers.get("DNT") == "1"
            or request.headers.get("Sec-GPC") == "1"
        ):
            return response
        try:
            body = response.content
            if not re.search(b"</head>", body, re.IGNORECASE):
                return response
            token, host, environment = configuration
            config = {
                "token": token,
                "host": host,
                "environment": environment,
                "isTest": environment != "production",
                "path": request.path,
                "userId": account_distinct_id(request.user.pk)
                if request.user.is_authenticated
                else None,
            }
            markup = json_script(config, "pw-analytics-config") + format_html(
                '<script src="{}" defer></script>',
                static("pw-analytics.js"),
            )
            insertion = str(markup).encode(response.charset)
            updated = re.sub(
                b"</head>",
                lambda m: insertion + m.group(),
                body,
                count=1,
                flags=re.IGNORECASE,
            )
            response.content = updated
            if "Content-Length" in response:
                response["Content-Length"] = str(len(updated))
            if "ETag" in response:
                del response["ETag"]
            patch_cache_control(response, private=True)
        except Exception as error:  # noqa: BLE001 -- preserve the original page on any analytics error
            logger.warning("PostHog bootstrap unavailable (%s)", type(error).__name__)
        return response

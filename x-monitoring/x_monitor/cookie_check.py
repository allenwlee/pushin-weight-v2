# {{AGENT_ATTRIBUTION}}
"""Cookie health sentinel (R19, D6)."""

from __future__ import annotations

import logging

from .apify import ApifyClient
from .cookies import CookieMissingError, load_cookies

log = logging.getLogger(__name__)


def run_cookie_check(
    apify: ApifyClient,
    cookie_path=None,
) -> tuple[bool, str | None]:
    """Returns (ok, error_message).

    ok=True means cookies are present and accepted by X.
    ok=False means either CookieMissingError OR Apify returned 401/0-results.
    """
    try:
        cookies = load_cookies(cookie_path) if cookie_path else load_cookies()
    except CookieMissingError as e:
        return False, str(e)
    ok = apify.probe_cookie(cookies=cookies)
    if not ok:
        return False, "cookie probe returned 0 results or 401"
    return True, None

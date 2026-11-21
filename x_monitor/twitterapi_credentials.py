"""Purpose-specific TwitterAPI credential selection.

Credential purpose is explicit at every caller. Search may use the other
declared purpose as an ordered fallback; the legacy key is never read.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import Enum


class TwitterApiCredentialPurpose(str, Enum):
    SCHEDULED = "scheduled"
    ON_DEMAND = "on-demand"


TWITTERAPI_IO_SCHEDULED_API_KEY_ENV = "TWITTERAPI_IO_SCHEDULED_API_KEY"
TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV = "TWITTERAPI_IO_ON_DEMAND_API_KEY"
TWEXAPI_API_KEY_ENV = "TWEXAPI_API_KEY"


def get_twexapi_api_key(*, environ: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if environ is None else environ
    return source.get(TWEXAPI_API_KEY_ENV) or None

_ENV_BY_PURPOSE = {
    TwitterApiCredentialPurpose.SCHEDULED: TWITTERAPI_IO_SCHEDULED_API_KEY_ENV,
    TwitterApiCredentialPurpose.ON_DEMAND: TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV,
}


def twitterapi_api_key_env(purpose: TwitterApiCredentialPurpose) -> str:
    """Return the environment variable for ``purpose``."""

    if not isinstance(purpose, TwitterApiCredentialPurpose):
        raise TypeError("TwitterAPI credential purpose must use the purpose enum")
    try:
        return _ENV_BY_PURPOSE[purpose]
    except KeyError as exc:
        raise ValueError(
            f"unsupported TwitterAPI credential purpose: {purpose!r}"
        ) from exc


def get_twitterapi_api_key(
    purpose: TwitterApiCredentialPurpose,
    *,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Read the variable assigned to ``purpose``; callers choose fallback order."""

    source = os.environ if environ is None else environ
    value = source.get(twitterapi_api_key_env(purpose))
    return value if value else None


def require_twitterapi_api_key(
    purpose: TwitterApiCredentialPurpose,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Require the key named by ``purpose``."""

    value = get_twitterapi_api_key(purpose, environ=environ)
    if value is None:
        raise RuntimeError(f"{twitterapi_api_key_env(purpose)} not in environment")
    return value

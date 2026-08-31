"""Purpose-specific TwitterAPI credential selection.

Credential purpose is explicit at every caller.  There is deliberately no
default and no fallback between scheduled, on-demand, or legacy names.
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

_ENV_BY_PURPOSE = {
    TwitterApiCredentialPurpose.SCHEDULED: TWITTERAPI_IO_SCHEDULED_API_KEY_ENV,
    TwitterApiCredentialPurpose.ON_DEMAND: TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV,
}


def twitterapi_api_key_env(purpose: TwitterApiCredentialPurpose) -> str:
    """Return the one environment variable authorized for ``purpose``."""

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
    """Read only the variable assigned to ``purpose`` without fallback."""

    source = os.environ if environ is None else environ
    value = source.get(twitterapi_api_key_env(purpose))
    return value if value else None


def require_twitterapi_api_key(
    purpose: TwitterApiCredentialPurpose,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Read the purpose-specific key or fail without trying another key."""

    value = get_twitterapi_api_key(purpose, environ=environ)
    if value is None:
        raise RuntimeError(f"{twitterapi_api_key_env(purpose)} not in environment")
    return value

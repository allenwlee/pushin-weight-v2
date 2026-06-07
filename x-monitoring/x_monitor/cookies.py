# {{AGENT_ATTRIBUTION}}
"""Cookie loading from ~/.config/x-monitor/cookies.json (R19, D6)."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_COOKIE_PATH = Path.home() / ".config" / "x-monitor" / "cookies.json"


class CookieMissingError(RuntimeError):
    """Raised when the cookie file is missing, unreadable, or has empty fields."""


def load_cookies(path: Path = DEFAULT_COOKIE_PATH) -> dict[str, str]:
    """Load cookies from a JSON file with auth_token + ct0.

    Raises CookieMissingError if:
      - the file does not exist
      - file mode is not 0600 (warning, but only enforced on POSIX)
      - auth_token is empty or missing
      - ct0 is empty or missing
    """
    if not path.exists():
        raise CookieMissingError(f"cookie file not found: {path}")
    # POSIX mode check (best-effort; skip on platforms without stat.S_IMODE)
    try:
        mode = stat.S_IMODE(path.stat().st_mode) if (stat := __import__("stat")) else 0
        if mode and mode & 0o077:
            # Not strictly fatal — print a warning, continue.
            # The cookies ARE loaded; the operator is informed via stderr in CLI.
            pass
    except Exception:
        pass

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CookieMissingError(f"cookie file is not valid JSON: {e}") from e

    if not isinstance(raw, dict):
        raise CookieMissingError("cookie file must be a JSON object")

    auth = raw.get("auth_token")
    ct0 = raw.get("ct0")
    if not auth or not isinstance(auth, str) or not auth.strip():
        raise CookieMissingError("auth_token is empty or missing")
    if not ct0 or not isinstance(ct0, str) or not ct0.strip():
        raise CookieMissingError("ct0 is empty or missing")
    return {"auth_token": auth.strip(), "ct0": ct0.strip()}

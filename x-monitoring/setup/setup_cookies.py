#!/usr/bin/env python3
# {{AGENT_ATTRIBUTION}}
"""Re-invokable as `x-monitor setup cookies`. Interactive cookie setup wizard."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_COOKIE_PATH = Path.home() / ".config" / "x-monitor" / "cookies.json"


def main() -> int:
    path = DEFAULT_COOKIE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    print("x-monitor cookie setup")
    print(f"target: {path}")
    print("Open x.com in a browser. Dev tools → Application → Cookies → https://x.com")
    print("Find auth_token and ct0. Paste below.")
    auth = input("auth_token: ").strip()
    ct0 = input("ct0: ").strip()
    if not auth or not ct0:
        print("both fields required", file=sys.stderr)
        return 1
    path.write_text(json.dumps({"auth_token": auth, "ct0": ct0}), encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"wrote {path} (mode 600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

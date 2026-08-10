#!/usr/bin/env python3
"""Deprecated entrypoint — use: python -m scripts.harvest_cost

Delegates to scripts.harvest_cost.cli for backward compatibility.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.harvest_cost.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

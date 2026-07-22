"""project package — Django settings root for x-monitor v2.

The Django project is colocated at the repo root alongside the existing
`x_monitor/` package.  The legacy harvest pipeline (`python -m x_monitor run`)
and launchd agents continue to operate against SQLite unchanged; this Django
surface is a *new* entry point that will eventually become the primary path.

Mirrors the pushin_weight reference shape exactly.
"""
from __future__ import annotations

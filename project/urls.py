"""URL config for x-monitor v2.

v2 baseline: no web routes yet.  Auth + dashboard routes will be added
in U3 (allauth) and U7 (dashboard UI).
"""
from __future__ import annotations

from django.urls import path

# v2 baseline — no views yet.
# U3 will add:  path("accounts/", include("allauth.urls")),
# U7 will add:  path("", include("monitor.urls")),

urlpatterns: list[path] = []

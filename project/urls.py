"""URL config for x-monitor v2.

Auth (allauth) routes added in U3. Dashboard routes will be added in U7.
"""
from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    # django-allauth (Google OAuth login/logout)
    path("accounts/", include("allauth.urls")),
    # Pushin' Weight dashboard (U7)
    path("", include("monitor.urls")),
]

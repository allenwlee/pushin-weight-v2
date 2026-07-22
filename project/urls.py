"""URL config for x-monitor v2.

Auth (allauth) routes added in U3. Dashboard routes will be added in U7.
"""
from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    # django-allauth (Google OAuth login/logout)
    path("accounts/", include("allauth.urls")),
    # U7 will add:  path("", include("monitor.urls")),
]

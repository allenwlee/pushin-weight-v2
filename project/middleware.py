from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


class StagingOwnerOnlyMiddleware:
    """Fail closed around copied data when the staging profile is active."""

    _PUBLIC_PREFIXES = ("/accounts/", "/static/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.OLLIJA_STAGING_MODE:
            return self.get_response(request)
        if request.path.startswith(self._PUBLIC_PREFIXES):
            return self.get_response(request)
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)

        email = (request.user.email or "").strip().casefold()
        allowed = settings.OLLIJA_STAGING_ALLOWED_EMAILS
        if not allowed or email not in allowed:
            return HttpResponseForbidden("This staging environment is owner-only.")
        return self.get_response(request)

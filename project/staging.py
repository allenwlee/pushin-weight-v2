from __future__ import annotations

from collections.abc import Collection

from django.core.exceptions import ImproperlyConfigured


def validate_staging_environment(
    *,
    enabled: bool,
    django_secret_key: str,
    google_client_id: str,
    google_client_secret: str,
    allowed_emails: Collection[str],
) -> None:
    """Refuse a staging boot that could fall back to unsafe auth defaults."""

    if not enabled:
        return
    missing: list[str] = []
    if (
        not django_secret_key
        or django_secret_key == "dev-only-change-in-production-xmonitor-v2"
    ):
        missing.append("DJANGO_SECRET_KEY")
    if not google_client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not google_client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    if not allowed_emails:
        missing.append("OLLIJA_STAGING_ALLOWED_EMAILS")
    if missing:
        raise ImproperlyConfigured(
            "Owner-only staging requires its own values for: "
            + ", ".join(missing)
        )

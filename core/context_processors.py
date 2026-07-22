"""Template context processors for x-monitor v2.

Adds:
- LANGUAGES and current locale to every template context.
- Brand list with locale-aware display names for the locale picker.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import translation


def i18n_context(request: Any) -> dict[str, Any]:
    """Inject i18n-related variables into every template context.

    Returns a dict with:
      - LANGUAGES: the configured language choices (for the locale toggle).
      - current_lang_code: the active language code (e.g. "en" or "zh-cn").
      - current_lang_name: the human-readable name of the active language.
      - brands: a list of brand dicts with display names for the current locale
        (lazy import to avoid circular dependency at startup).
    """
    current_lang_code = translation.get_language() or settings.LANGUAGE_CODE
    lang_map: dict[str, str] = dict(settings.LANGUAGES)
    current_lang_name = lang_map.get(current_lang_code, current_lang_code)

    ctx: dict[str, Any] = {
        "LANGUAGES": settings.LANGUAGES,
        "current_lang_code": current_lang_code,
        "current_lang_name": current_lang_name,
        "brands": _get_brands(current_lang_code),
    }
    return ctx


def _get_brands(lang_code: str) -> list[dict[str, str]]:
    """Return a list of brand dicts with locale-appropriate display names.

    Falls back to `nickname` when no translated display name exists.
    """
    try:
        from core.models import Brand

        qs = Brand.objects.all().order_by("nickname")
    except Exception:
        return []

    brands: list[dict[str, str]] = []
    for b in qs:
        if lang_code == "zh-cn":
            display = b.display_name_zh_cn or b.display_name or b.nickname
        else:
            display = b.display_name_en or b.display_name or b.nickname
        brands.append({
            "nickname": b.nickname,
            "display_name": display,
            "accent_color": b.accent_color or "",
        })
    return brands

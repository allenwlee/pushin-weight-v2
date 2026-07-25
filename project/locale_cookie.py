"""
CustomLocaleMiddleware — reads our `locale` cookie and overrides Django's
LocaleMiddleware activation. LocaleMiddleware always activates LANGUAGE_CODE
(our case: zh-hans). This middleware runs AFTER it and re-activates with the
user's explicit choice. Required because the i18n_patterns URL prefix is
not used in this project, so session[_language] alone does nothing.
"""

from django.utils import translation


class CustomLocaleMiddleware:
    """Translate our `locale` cookie into Django's session _language key."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.utils import translation
        # 1. Read our `locale` cookie
        cookie_locale = request.COOKIES.get("locale")
        if cookie_locale:
            # 2. Map to Django BCP 47 code
            django_code = {
                "zh_cn": "zh-hans",
                "zh-CN": "zh-hans",
                "zh_hans": "zh-hans",
                "en": "en",
                "original": "en",
            }.get(cookie_locale, "zh-hans")
            # 3. Activate translation for {% trans %} resolution
            translation.activate(django_code)

        return self.get_response(request)

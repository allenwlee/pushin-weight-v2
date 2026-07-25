"""
CustomLocaleMiddleware — reads our `locale` cookie (zh_cn/zh-CN/en/original)
and converts it to Django's session _language key BEFORE LocaleMiddleware runs.
This is the only way to override LocaleMiddleware's Accept-Language default
when the user has explicitly selected a locale via our toggle.
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

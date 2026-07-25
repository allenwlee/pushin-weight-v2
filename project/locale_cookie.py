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
        import sys
        print(f"[LOCALE_MW] cookie={request.COOKIES.get('locale')} session[_language]={request.session.get('_language') if hasattr(request, 'session') else None}", file=sys.stderr)
        # Only act if there's a session and our cookie is set
        if hasattr(request, "session") and not request.session.get("_language"):
            cookie_locale = request.COOKIES.get("locale")
            if cookie_locale:
                # Map our flat strings to Django BCP 47 codes
                django_code = {
                    "zh_cn": "zh-hans",
                    "zh-CN": "zh-hans",
                    "zh_hans": "zh-hans",
                    "en": "en",
                    "original": "en",
                }.get(cookie_locale, "zh-hans")
                request.session["_language"] = django_code
        return self.get_response(request)

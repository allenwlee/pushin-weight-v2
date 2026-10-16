"""Public, read-only atomic Post pages."""

from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils import translation
from django.views.decorators.http import require_GET

from monitor.content_readers import read_post


def content_locale(request):
    raw = request.GET.get(
        "lang", request.GET.get("locale", request.COOKIES.get("locale", "en"))
    ).lower()
    locale = {
        "zh-hans": "zh-cn",
        "zh_hans": "zh-cn",
        "zh_cn": "zh-cn",
        "zh": "zh-cn",
        "ja-jp": "ja",
    }.get(raw, raw)
    if locale not in {"en", "zh-cn", "ja"}:
        raise ValueError("Unsupported language")
    return locale


def private_response(response):
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def post_detail(request, post_id):
    try:
        locale = content_locale(request)
    except ValueError:
        return HttpResponseBadRequest("Unsupported language")
    item = read_post(post_id, locale=locale, commentary=request.GET.get("commentary"))
    context = {
        "item": item,
        "locale": locale,
        "canonical_url": request.build_absolute_uri(item["share_url"]),
    }
    with translation.override("zh-hans" if locale == "zh-cn" else locale):
        return private_response(render(request, "monitor/content/detail.html", context))

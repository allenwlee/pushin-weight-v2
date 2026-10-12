"""General's server-rendered shell and progressive, read-only panel updates."""

from urllib.parse import urlencode

from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop, pgettext
from django.views.decorators.http import require_GET

from monitor.content_views import content_locale, private_response
from monitor.editorial.readers import feed_payload as editorial_feed
from monitor.editorial.views import access as editorial_access
from monitor.general_readers import SECTIONS, general_feed
from monitor.views import (
    _home_preferences_namespace,
    _live_brand_projection,
    _partition_home_brands,
)

PANEL_LABELS = {
    "calendar": "Calendar",
    "free": gettext_noop("Free stuff"),
    "jobs": gettext_noop("Jobs"),
    "moving": gettext_noop("Who’s moving"),
}
PANEL_GLYPHS = {
    "calendar": "icon-event",
    "free": "a-opportunity",
    "jobs": "a-jobs",
    "moving": "a-personnel",
}


def editorial_panels(request, locale):
    """Present G2's global publications without changing selection or access."""
    try:
        cfg = editorial_access(request)
    except Http404:
        cfg = None
    panels = {}
    for track, title, glyph in (
        ("chatter", _("Chatter"), "icon-discourse"),
        ("pulse", _("Pulse"), "icon-rise"),
    ):
        panel = {
            "track": track,
            "title": title,
            "glyph": glyph,
            "status": "unavailable",
            "items": [],
            "history": [],
        }
        if cfg is not None:
            feed = editorial_feed(cfg, track=track, locale=locale, limit=6)
            items = feed["items"]
            if track == "chatter":
                primary = feed["hero"] or next(iter(items), None)
                items = [primary] if primary else []
                panel["history"] = [
                    item
                    for item in feed["history"]
                    if not primary or item["story_id"] != primary["story_id"]
                ]
            panel.update(
                items=items,
                status="ready" if items else "empty",
                fallback=feed["locale"] != locale,
            )
        panels[track] = panel
    return panels


def selection(request):
    locale = content_locale(request)
    weights = request.GET.get("weights", "open")
    audience = request.GET.get("audience", "human")
    zone = request.GET.get("timezone", "local")
    if (
        weights not in {"open", "closed", "both", "none"}
        or audience not in {"human", "agent"}
        or zone not in {"local", "ca"}
    ):
        raise ValueError("Invalid preferences")
    # Closed coverage is not available yet; old saved URLs retain Open results.
    if weights in {"closed", "both"}:
        weights = "open"
    inventory = _live_brand_projection(locale)
    opened, _closed = _partition_home_brands(inventory)
    requested = request.GET.getlist("brand")
    if set(requested) - {row["nickname"] for row in inventory}:
        raise ValueError("Unknown brand")
    brands = [
        row["nickname"]
        for row in (opened if weights == "open" else [])
        if not requested or row["nickname"] in requested
    ]
    return {
        "locale": locale,
        "weights": weights,
        "audience": audience,
        "timezone": zone,
        "brands": brands,
    }


def _duration(seconds):
    if seconds < 3600:
        return _("%(count)s min") % {"count": max(1, int(seconds // 60))}
    if seconds < 86400:
        return _("%(count)s hrs") % {"count": int(seconds // 3600)}
    return _("%(count)s days") % {"count": int(seconds // 86400)}


def present_feed(feed):
    from datetime import datetime

    at = datetime.fromisoformat(feed["as_of"])
    for item in feed["items"]:
        params = {"lang": feed["locale"]}
        if item["commentary"]["artifact_id"]:
            params["commentary"] = item["commentary"]["artifact_id"]
        item["share_url"] = item["url"] + "?" + urlencode(params)
        item["display_text"] = (
            item["commentary"]["text"]
            or item["source"]["translation"]["text"]
            or item["source"]["text"]
        )
        item["person"] = next(
            (fact for fact in item["facts"] if fact["kind"] == "personnel"), None
        )
        timing = item["timing"]
        if timing:
            state, target = timing["state"], timing["target"]
            remaining = (
                (datetime.fromisoformat(target) - at).total_seconds()
                if target
                else None
            )
            if state in {"live", "open"}:
                label = (
                    _("Live: ends in %(time)s") % {"time": _duration(remaining)}
                    if target
                    else _("Live: end time unavailable")
                )
            elif state == "upcoming":
                label = (
                    _("Starts in %(time)s") % {"time": _duration(remaining)}
                    if target
                    else _("Start time unavailable")
                )
            else:
                label = (
                    _("Postponed") if state == "postponed" else _("Date unavailable")
                )
        else:
            age = _duration(item["age_seconds"])
            label = (
                _("Just listed %(time)s ago!")
                if item["recent"]
                else _("Fetched %(time)s ago")
            ) % {"time": age}
        item["time_label"] = label
    return feed


def _settings_links(state, request):
    options = {
        "weights": [("open", _("Open")), ("closed", _("Closed"))],
        "audience": [("human", _("Human")), ("agent", _("Agent"))],
        "lang": [("en", "EN"), ("zh-cn", "中"), ("ja", "日")],
        "timezone": [("local", _("Local")), ("ca", "CA")],
    }
    links = {}
    for key, values in options.items():
        rows = []
        for value, label in values:
            params = request.GET.copy()
            params.pop("cursor", None)
            params.pop("section", None)
            params.pop("locale", None)
            params.pop("notice", None)
            params["lang"] = state["locale"]
            params[key] = value
            if key == "weights":
                if value == "open":
                    params[key] = "none" if state[key] == "open" else "open"
                else:
                    params[key] = state[key]
                    params["notice"] = "closed-weights"
            rows.append(
                {
                    "value": value,
                    "label": label,
                    "active": state["locale" if key == "lang" else key] == value,
                    "url": "/general/?" + params.urlencode(),
                }
            )
        links[key] = rows
    return links


@require_GET
def general(request):
    try:
        state = selection(request)
    except ValueError:
        return HttpResponseBadRequest("Invalid General selection")
    locale = state["locale"]
    now = timezone.now()
    with translation.override("zh-hans" if locale == "zh-cn" else locale):
        panels = {}
        for section in SECTIONS:
            feed = present_feed(
                general_feed(section, locale=locale, brands=state["brands"], as_of=now)
            )
            title = (
                pgettext("General page", "Calendar")
                if section == "calendar"
                else _(PANEL_LABELS[section])
            )
            feed.update({"title": title, "glyph": PANEL_GLYPHS[section]})
            panels[section] = feed
        context = {
            "state": state,
            "panels": panels,
            "editorial": editorial_panels(request, locale),
            "locale": locale,
            "preferences_namespace": _home_preferences_namespace(request),
            "settings_links": _settings_links(state, request),
            "return_path": request.get_full_path(),
            "initial_data": {
                "state": state,
                "closed_weights_notice": (
                    request.GET.get("weights") in {"closed", "both"}
                    or request.GET.get("notice") == "closed-weights"
                ),
                "feeds": {
                    key: {"next_cursor": panel["next_cursor"]}
                    for key, panel in panels.items()
                },
                "as_of": now.isoformat(),
            },
        }
        return private_response(render(request, "monitor/general.html", context))


@require_GET
def feed(request):
    try:
        state = selection(request)
        with translation.override(
            "zh-hans" if state["locale"] == "zh-cn" else state["locale"]
        ):
            payload = present_feed(
                general_feed(
                    request.GET.get("section"),
                    locale=state["locale"],
                    brands=state["brands"],
                    cursor=request.GET.get("cursor"),
                    limit=int(request.GET.get("limit", 20)),
                )
            )
            payload["html"] = render_to_string(
                "monitor/general/_cards.html", {"feed": payload}
            )
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid feed selection")
    return private_response(JsonResponse(payload))

"""Saved release discoveries and owner-operated Pulse controls."""

from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from core.models import EventDossier
from core.pulse_readers import PulseReadError, release_page, release_sources
from monitor import pulse_control
from monitor.views import (
    _can_review_products,
    _home_preferences_namespace,
    _resolve_locale,
)

JST = ZoneInfo("Asia/Tokyo")


def _shell_context(request):
    """Use General's navigation without depending on its brand inventory."""
    from monitor.general_views import _settings_links

    if request.GET.get("lang"):
        from monitor.content_views import content_locale
        try:
            locale = content_locale(request)
        except ValueError:
            locale = "en"
        translation.activate("zh-hans" if locale == "zh-cn" else locale)
    else:
        locale = _resolve_locale(request, persist=False)
        locale = "zh-cn" if locale in {"zh_cn", "zh_hans", "zh-CN"} else locale
    state = {"locale": locale, "weights": "open", "audience": "human", "timezone": "local", "brands": []}
    for key, values in {"weights": {"open", "none"}, "audience": {"human", "agent"}, "timezone": {"local", "ca"}}.items():
        if request.GET.get(key) in values:
            state[key] = request.GET[key]
    return {
        "active_locale": locale, "locale": locale, "state": state,
        "panels": {"pulse": {"title": _("Pulse"), "glyph": "icon-rise"}},
        "preferences_namespace": _home_preferences_namespace(request),
        "settings_links": _settings_links(state, request, path=request.path),
        "return_path": request.get_full_path(),
        "initial_data": {"state": state, "feeds": {}, "as_of": timezone.now().isoformat(),
                         "closed_weights_notice": request.GET.get("notice") == "closed-weights"},
    }


def _next_url(path, cursor, locale):
    return path + "?" + urlencode({"cursor": cursor, "locale": locale}) if cursor else ""


def _instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(JST).strftime("%Y-%m-%d %H:%M JST") if value else ""


def _card(row):
    states = {
        "pending": _("Pending review"), "provisional": _("Provisional"),
        "confirmed": _("Confirmed"), "unresolved": _("Unresolved"),
        "retired": _("Retired"), "non_release": _("Not a release"),
        "scam": _("Flagged source"), "superseded": _("Superseded"),
    }
    categories = {
        "model-llm": _("Language model"), "model-other": _("Other model"),
        "agent": _("Agent"), "harness": _("Harness"), "other": _("Other"),
    }
    kinds = {
        "release_report": _("Reported release"), "source_stated_release": _("Reported release"),
        "announcement": _("Announcement"), "availability": _("Availability"),
        "first_observed_usage": _("First observed use"), "rumor": _("Unconfirmed report"),
    }
    dispositions = {"accepted": _("Accepted evidence"), "rejected": _("Rejected evidence"),
                    "uncertain": _("Uncertain evidence"), None: _("Not reviewed")}
    category_label = categories.get(row["category"])
    if category_label and row["category_source"] == "saved_finding":
        category_label = _("Reported category: %(category)s") % {"category": category_label}
    if not category_label:
        category_label = (
            _("Legacy category: %(code)s") % {"code": row["legacy_category"]}
            if row["legacy_category"] else _("Category pending")
        )
    status = row["review_state"]
    if row.get("intake_is_current", True) and row["intake_outcome"] in {"non_release", "scam", "superseded"}:
        status = row["intake_outcome"]
    for claim in row["release_dates"]:
        claim["kind_label"] = kinds.get(claim["kind"], _("Reported date"))
        claim["disposition_label"] = dispositions[claim["disposition"]]
        if claim["precision"] == "datetime":
            claim["display_value"] = _instant(claim["value"])
        elif claim["precision"] == "range":
            claim["display_value"] = " / ".join(_instant(value) if value != "…" else "…" for value in claim["value"].split(" / "))
        else:
            claim["display_value"] = claim["value"]
    novelty = row.get("novelty")
    novelty_labels = {
        "new_release": _("New release"), "historical_release": _("Historical release"),
        "availability_update": _("Availability update"),
    }
    return {**row, "novelty_label": novelty_labels.get(novelty, _("Release type pending")),
            "timeline_kind_label": kinds.get(row.get("timeline_date_kind")),
            "can_open_chart": (novelty != "availability_update" or row.get("has_historical_launch")) and status not in {"non_release", "scam", "superseded", "retired"},
            "state_label": states.get(status, _("Pending review")),
            "category_label": category_label,
            "category_conflict_label": _("Sources report different categories: %(categories)s.") % {
                "categories": " / ".join(categories[code] for code in row["reported_categories"]),
            } if row["category_conflict"] else "",
            "discovered_label": _instant(row["discovered_at"])}


@require_GET
def pulse(request):
    context = _shell_context(request)
    locale = context["active_locale"]
    context.update(entries=[], read_error=False, next_url="")
    try:
        page = release_page(cursor=request.GET.get("cursor"))
    except ValueError:
        context.update(read_error=True, error_message=_("This page link is invalid. Open the latest discoveries."))
        return render(request, "monitor/pulse.html", context, status=400)
    except (DatabaseError, PulseReadError):
        context.update(read_error=True, error_message=_("Release discoveries are temporarily unavailable. Please try again."))
        return render(request, "monitor/pulse.html", context, status=503)
    context["chart_release_id"] = request.GET.get("release", "")[:64]
    context.update(entries=[_card(row) for row in page["entries"]],
                   next_url=_next_url(reverse("pulse"), page["next_cursor"], locale))
    return render(request, "monitor/pulse.html", context)


@require_GET
def pulse_legacy(request):
    target = reverse("pulse")
    if request.GET:
        target += "?" + request.GET.urlencode()
    return redirect(target, permanent=True)


@require_GET
def sources(request, dossier_id):
    context = _shell_context(request)
    locale = context["active_locale"]
    context.update(sources=[], read_error=False, next_url="")
    try:
        page = release_sources(dossier_id, cursor=request.GET.get("cursor"))
    except EventDossier.DoesNotExist as error:
        raise Http404 from error
    except ValueError:
        context.update(read_error=True, error_message=_("This page link is invalid. Open the latest discoveries."))
        return render(request, "monitor/pulse_sources.html", context, status=400)
    except (DatabaseError, PulseReadError):
        context.update(read_error=True, error_message=_("Related sources are temporarily unavailable. Please try again."))
        return render(request, "monitor/pulse_sources.html", context, status=503)
    for row in page["entries"]:
        row["linked_label"] = _instant(row["linked_at"])
    context.update(sources=page["entries"], event_id=page["event_id"],
                   next_url=_next_url(reverse("pulse_sources", args=[page["event_id"]]), page["next_cursor"], locale))
    return render(request, "monitor/pulse_sources.html", context)


def _diagnostic_message(diagnostic):
    stage, code = diagnostic["stage"], diagnostic["code"]
    if stage == "identity" and diagnostic["message"] == "Pulse processing needs investigation.":
        lineage_messages = {
            "lineage_wakeup_budget_blocked": _("Lineage recovery paused after reaching its processing limit."),
            "lineage_wakeup_invalid_evidence": _("Some lineage evidence is invalid and needs investigation."),
            "lineage_nonx_pending": _("Some non-X lineage evidence is pending; automatic recovery is not available yet."),
        }
        if code in lineage_messages:
            return lineage_messages[code]
    processing_error = (stage, code) in {
        ("identity", "identity_processing_error"),
        ("publication", "classification_publication_conflict"),
    } or (stage == "classification" and code.startswith("classification_"))
    if processing_error and diagnostic["message"] == "Pulse processing needs investigation.":
        return _("Pulse processing needs investigation.")
    return diagnostic["message"]


def admin_context():
    """Read P1's actual file API; a GET never initializes or acknowledges it."""
    snapshot = pulse_control.read_status()
    labels = {"running": _("Running"), "stopped": _("Stopped"),
              "stop_requested": _("Stop requested"), "resume_requested": _("Resume requested"),
              "unavailable": _("Control unavailable")}
    snapshot["status_label"] = labels[snapshot["status"]]
    snapshot["observed_label"] = _instant(snapshot["observed_at"])
    snapshot["acknowledged_label"] = _instant(snapshot["acknowledged_at"])
    for diagnostic in snapshot["diagnostics"]:
        diagnostic["reported_label"] = _instant(diagnostic["reported_at"])
        diagnostic["display_message"] = _diagnostic_message(diagnostic)
    return {"pulse_control": snapshot}


@login_required
@require_POST
def control(request):
    if not _can_review_products(request):
        _resolve_locale(request, persist=False)
        return HttpResponseForbidden(_("Pulse control requires owner or staff access."))
    locale = _resolve_locale(request)
    try:
        pulse_control.request_state(
            request.POST.get("state", ""), expected_revision=int(request.POST.get("revision", "")),
            actor=(request.user.email or request.user.get_username()).strip(),
            reason=request.POST.get("reason", "").strip(),
        )
    except pulse_control.PulseControlConflict:
        message, status = _("Pulse control changed. Refresh Admin before trying again."), 409
    except pulse_control.PulseControlUnavailable:
        message, status = _("Pulse control is unavailable. No stop or resume was confirmed."), 503
    except ValueError:
        message, status = _("Choose a valid action and enter a reason."), 400
    else:
        return redirect(reverse("product_review") + "?" + urlencode({"locale": locale}) + "#pulse-control")
    context = _shell_context(request)
    context["error_message"] = message
    return render(request, "monitor/pulse_control_error.html", context, status=status)

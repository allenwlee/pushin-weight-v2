"""Bounded read-only official-account reporting for the owner console."""

from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q

from core.models import (
    OfficialCompanyAccountState,
    OfficialCompanyListIntent,
    OfficialCompanyScan,
)
from core.official_company_accounts import x_account_identifier
from core.official_company_discovery import INITIAL_KEY


def account_report(*, list_id, page=1):
    states = OfficialCompanyAccountState.objects.all()
    intents = OfficialCompanyListIntent.objects.filter(list_id=int(list_id))
    summary = states.aggregate(
        evaluated=Count(
            "pk",
            filter=Q(attempts__gt=0)
            | Q(status__in=["accepted", "registered", "rejected", "review_needed"]),
        ),
        found=Count(
            "pk", filter=Q(status__in=["accepted", "registered"])
            | Q(status="review_needed", decision__outcome="accepted"),
        ),
        registered=Count("pk", filter=Q(status="registered")),
        review_needed=Count("pk", filter=Q(status="review_needed")),
        pending=Count(
            "pk",
            filter=Q(
                status__in=["pending", "claimed", "retry_due"],
                candidate_priority__in=[1, 2, 3],
            ),
        ),
        total=Count("pk"),
    )
    summary.update(
        intents.aggregate(
            added=Count("pk", filter=Q(add_acknowledged_at__isnull=False)),
            membership_confirmed=Count("pk", filter=Q(status="confirmed")),
            awaiting_list=Count(
                "pk", filter=~Q(status__in=["confirmed", "suppressed"])
            ),
        )
    )
    query = (
        states.filter(
            Q(status__in=["accepted", "registered", "review_needed"])
            | Q(pk__in=intents.values("state_id"))
        )
        .select_related("account", "registered_company", "registered_brand")
        .defer("evidence")
        .prefetch_related(
            Prefetch("list_intents", queryset=intents, to_attr="admin_list_intents")
        )
        .order_by("-updated_at", "pk")
    )
    result = Paginator(query, 50).get_page(page)
    rows = []
    for state in result:
        intent = next(iter(state.admin_list_intents), None)
        outcome = "not_queued"
        if intent:
            if intent.add_acknowledged_at:
                outcome = "added"
            elif intent.status == "confirmed":
                outcome = (
                    "confirmed_after_request"
                    if intent.add_requested_at
                    else "already_present"
                )
            elif intent.add_requested_at:
                outcome = "request_unconfirmed"
            else:
                outcome = "queued"
        try:
            identifier = x_account_identifier(state.account)
        except ValueError:
            identifier = ""
        rows.append(
            {
                "state": state,
                "intent": intent,
                "list_outcome": outcome,
                "x_url": f"https://x.com/i/user/{identifier}" if identifier else "",
            }
        )
    return {
        "summary": summary,
        "rows": rows,
        "page": result,
        "scans": list(OfficialCompanyScan.objects.filter(key=INITIAL_KEY)[:1]),
    }

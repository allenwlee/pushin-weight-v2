"""Bounded read-only official-account reporting for the owner console."""

from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.db.models.functions import Collate

from core.models import (
    BrandAccount,
    CompanyAccount,
    OfficialCompanyAccountState,
    OfficialCompanyAttempt,
    OfficialCompanyListIntent,
    OfficialCompanyScan,
)
from core.official_company_accounts import x_account_identifier
from core.official_company_candidates import CANDIDATE_POLICY
from core.official_company_discovery import INITIAL_KEY, coverage


def _account_url(account):
    try:
        identifier = x_account_identifier(account)
    except ValueError:
        return ""
    return f"https://x.com/i/user/{identifier}"


CANDIDATE_STATUSES = {
    "all": None, "waiting": Q(status="pending"), "evaluating": Q(status="claimed"),
    "retry_due": Q(status="retry_due"),
    "review_needed": Q(status="review_needed") | (Q(status="accepted") & ~Q(model="owner-attestation") & ~Q(decision__hf_verification__outcome="passed")),
    "hf_verified": Q(status__in=["accepted", "registered"], decision__hf_verification__outcome="passed"),
    "rejected": Q(status="rejected"), "registered": Q(status="registered"),
    "no_evidence": Q(status="no_evidence"), "owner_settled": Q(model="owner-attestation"),
    "already_tracked": Q(has_official_brand=True) | Q(has_official_company=True),
}


def candidate_report(*, page=1, status="all", query=""):
    states = OfficialCompanyAccountState.objects.filter(
        candidate_priority__in=[1, 2, 3], candidate_policy_version=CANDIDATE_POLICY,
    ).exclude(status="suppressed").annotate(
        has_official_brand=Exists(BrandAccount.objects.filter(account_id=OuterRef("account_id"), role_id="official")),
        has_official_company=Exists(CompanyAccount.objects.filter(account_id=OuterRef("account_id"), role_id="official")),
    )
    completed = OfficialCompanyAttempt.objects.filter(
        state_id=OuterRef("pk"), status="completed",
    ).exclude(model="owner-attestation")
    summary = states.annotate(has_model_decision=Exists(completed)).aggregate(
        selected=Count("pk"),
        llm_evaluated=Count("pk", filter=Q(has_model_decision=True)),
        owner_settled=Count("pk", filter=Q(model="owner-attestation")),
        waiting=Count("pk", filter=Q(status="pending")),
        evaluating=Count("pk", filter=Q(status="claimed")),
        retry_due=Count("pk", filter=Q(status="retry_due")),
        review_needed=Count("pk", filter=CANDIDATE_STATUSES["review_needed"]),
        hf_verified=Count("pk", filter=CANDIDATE_STATUSES["hf_verified"]),
        rejected=Count("pk", filter=Q(status="rejected")),
        already_tracked=Count("pk", filter=CANDIDATE_STATUSES["already_tracked"]),
    )
    status = status if status in CANDIDATE_STATUSES else "all"
    query = query.strip().removeprefix("@")[:100]
    filtered = states
    if CANDIDATE_STATUSES[status]:
        filtered = filtered.filter(CANDIDATE_STATUSES[status])
    if query:
        filtered = filtered.alias(search_handle=Collate("account__handle", "C")).filter(
            Q(search_handle__icontains=query) | Q(account__author_id__icontains=query)
            | Q(decision__organization_name__icontains=query)
        )
    result = Paginator(
        filtered.select_related("account").defer("evidence").prefetch_related(
            Prefetch("account__brands", queryset=BrandAccount.objects.filter(role_id="official"), to_attr="admin_official_brands"),
            Prefetch("account__companies", queryset=CompanyAccount.objects.filter(role_id="official"), to_attr="admin_official_companies"),
        )
        .order_by("candidate_priority", "created_at", "pk"), 50,
    ).get_page(page)
    return {
        "summary": summary, "coverage": coverage(), "page": result,
        "rows": [{"state": state, "x_url": _account_url(state.account),
                  "tracked_brands": [edge.brand_id for edge in state.account.admin_official_brands],
                  "tracked_companies": [edge.company_id for edge in state.account.admin_official_companies]}
                 for state in result],
        "status": status, "query": query,
    }


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
        rows.append(
            {
                "state": state,
                "intent": intent,
                "list_outcome": outcome,
                "x_url": _account_url(state.account),
            }
        )
    return {
        "summary": summary,
        "rows": rows,
        "page": result,
        "scans": list(OfficialCompanyScan.objects.filter(key=INITIAL_KEY)[:1]),
    }

"""Read-only, membership-scoped views of the fixed qualification rerun."""

from django.core.paginator import Paginator

from core.models import OfficialCompanyAccountState
from core.official_company_admin import _account_url
from core.official_company_requalification import cohort_report

TABS = {"newly": "newly_qualified", "awaiting": "retry_pending", "pending": "pending"}


def frozen_run_report(*, tab="newly", page=1, query=""):
    tab = tab if tab in TABS else "newly"
    query = str(query or "").strip()[:100]
    report = cohort_report(include_members=True)
    if report is None:
        return {"summary": None, "tab": tab, "query": query, "rows": [], "page": None}
    members = report.pop("members")
    selected = [row for row in members if row["bucket"] == TABS[tab]]
    # Search only the frozen selection; neither a handle search nor a query
    # parameter can expand the page into the moving discovery inventory.
    if query:
        from django.db.models import Q
        from django.db.models.functions import Collate

        account_matches = set(OfficialCompanyAccountState.objects.filter(
            pk__in=[row["state_id"] for row in selected],
        ).alias(search_handle=Collate("account__handle", "C")).filter(Q(search_handle__icontains=query.lstrip("@"))
                 | Q(account__display_name__icontains=query)).values_list("pk", flat=True))
        folded = query.casefold().lstrip("@")
        selected = [row for row in selected if row["state_id"] in account_matches
                    or folded in str(row["account_id"]).casefold()
                    or folded in str(row["decision"].get("organization_name") or "").casefold()]
    paginator = Paginator(selected, 50)
    current = paginator.get_page(page)
    states = {state.pk: state for state in OfficialCompanyAccountState.objects.filter(
        pk__in=[row["state_id"] for row in current],
    ).select_related("account").defer("evidence")}
    rows = []
    for member in current:
        state = states.get(member["state_id"])
        rows.append({**member, "state": state, "x_url": _account_url(state.account) if state else ""})
    return {"summary": report, "tab": tab, "query": query, "rows": rows, "page": current}

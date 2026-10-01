"""Read the staff union without making network calls or changing identities."""

from collections import defaultdict

from django.utils import timezone

from core.models import (
    BrandAccount,
    CompanyAccount,
    PersonBrandAffiliation,
    TwitterListMembership,
)


def staff_population(*, list_id):
    reasons = defaultdict(set)
    for account in TwitterListMembership.objects.filter(
        list_id=list_id, active=True
    ).values_list("account_id", flat=True):
        reasons[account].add("call_a")
    official = set()
    for model, label in (
        (BrandAccount, "brand_staff"),
        (CompanyAccount, "company_staff"),
    ):
        for account, role in model.objects.filter(
            role_id__in=["official", "staff"]
        ).values_list("account_id", "role_id"):
            if role == "official":
                official.add(account)
            else:
                reasons[account].add(label)
    people = (
        PersonBrandAffiliation.objects.filter(
            affiliation_type__in=["employment", "founder"],
        )
        .exclude(review_status="rejected")
        .values_list("person_id", flat=True)
        .distinct()
    )
    return {
        "captured_at": timezone.now().isoformat(),
        "list_id": str(list_id),
        "accounts": [
            {"account_id": key, "reasons": sorted(value)}
            for key, value in sorted(reasons.items())
            if key not in official
        ],
        "excluded_official_accounts": sorted(official & reasons.keys()),
        "people": sorted(str(pk) for pk in people),
        "overlap_accounts": sum(
            len(value) > 1 for key, value in reasons.items() if key not in official
        ),
    }


def is_official(account_id):
    return any(
        model.objects.filter(account_id=account_id, role_id="official").exists()
        for model in (BrandAccount, CompanyAccount)
    )

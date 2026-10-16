"""Publisher identity and ownership use the shared account/company relationship."""

from django.db import transaction

from core.account_identity import upsert_account
from core.models import Account, CompanyAccount, Role


def publisher_links(
    *, source, identifier=None, company_id=None, confirmed=None, lock=False
):
    links = CompanyAccount.objects.filter(
        account__data_source_id=source
    ).select_related("account", "company")
    if identifier is not None:
        normalized = identifier.casefold() if source == "hf" else identifier
        links = links.filter(account__normalized_identifier=normalized)
    if company_id is not None:
        links = links.filter(company_id=company_id)
    if confirmed is not None:
        links = links.filter(ownership_confirmed=confirmed)
    if lock:
        links = links.select_for_update(of=("self", "account"))
    return links


def get_publisher(**kwargs):
    """Return exactly one ownership link, refusing ambiguous company ownership."""
    try:
        return publisher_links(**kwargs).get()
    except CompanyAccount.MultipleObjectsReturned as exc:
        raise ValueError("conflicting publisher company ownership") from exc


@transaction.atomic
def register_publisher(
    *,
    source,
    identifier,
    company=None,
    company_id=None,
    confirmed=None,
    discovered_via=None,
    added_at=None,
):
    if confirmed is not None and not isinstance(confirmed, bool):
        raise ValueError("publisher confirmation must be boolean or unknown")
    if not identifier or identifier != identifier.strip():
        raise ValueError("exact nonblank publisher identifier required")
    owner = company.pk if company is not None else company_id
    if not owner:
        raise ValueError("publisher company ownership is required")
    normalized = identifier.casefold() if source == "hf" else identifier
    account = (
        Account.objects.select_for_update()
        .filter(data_source_id=source, normalized_identifier=normalized)
        .first()
    )
    if account is None:
        account = upsert_account(
            source=source,
            external_identifier=identifier,
            handle=identifier if source == "hf" else None,
        )
    if (
        CompanyAccount.objects.filter(account=account)
        .exclude(company_id=owner)
        .exists()
    ):
        raise ValueError("conflicting publisher company ownership")
    role, _ = Role.objects.get_or_create(pk="official")
    link, created = CompanyAccount.objects.get_or_create(
        account=account,
        company_id=owner,
        defaults={"role": role, "ownership_confirmed": bool(confirmed)},
    )
    if confirmed is not None and link.ownership_confirmed != confirmed:
        link.ownership_confirmed = confirmed
        link.save(update_fields=["ownership_confirmed"])
    if created and added_at is not None:
        CompanyAccount.objects.filter(pk=link.pk).update(added_at=added_at)
        link.added_at = added_at
    metadata = dict(account.provider_metadata)
    if discovered_via is not None:
        metadata.setdefault("discovered_via", discovered_via)
    if created and added_at is not None:
        metadata.setdefault("legacy_added_at", added_at.isoformat())
    if metadata != account.provider_metadata:
        account.provider_metadata = metadata
        account.save(update_fields=["provider_metadata"])
    return link, created

"""Publisher identity and ownership use the shared account/company relationship."""

import unicodedata

from django.db import transaction
from django.db.models import Q

from core.account_identity import upsert_account
from core.models import Account, Brand, BrandCompany, CompanyAccount, Role


def brand_name_candidates(name, *, nickname=None, include_sentinel=True):
    """Find candidate brands; callers decide whether their evidence supports reuse."""
    query = Q(display_name__iexact=name)
    if nickname is not None:
        query |= Q(nickname=nickname)
    candidates = Brand.objects.filter(query)
    return candidates if include_sentinel else candidates.filter(is_sentinel=False)


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


def link_brand_company(*, brand, company):
    """Reuse the established Brand–Company relationship for qualified callers."""
    return BrandCompany.objects.get_or_create(brand=brand, company=company)


def _release_brand_candidates(name):
    from core.models import BrandDiscoveryCandidateToken

    name = unicodedata.normalize("NFKC", name)
    labels = Q(nickname__iexact=name) | Q(display_name__iexact=name)
    labels |= Q(display_name_en__iexact=name) | Q(display_name_zh_cn__iexact=name)
    reviewed = BrandDiscoveryCandidateToken.objects.filter(
        form__iexact=name, candidate__verification_status="confirmed",
        candidate__reviewed_brand__isnull=False,
    ).values("candidate__reviewed_brand_id")
    return Brand.objects.filter(is_sentinel=False).filter(labels | Q(pk__in=reviewed))


def cited_x_account(post, handle, *, lock=False):
    """Resolve an exact indexed X handle; a saved native mention ID must agree."""
    handle = handle.lstrip("@").casefold()
    if not handle:
        return None
    accounts = Account.objects.filter(data_source_id="x", normalized_handle=handle)
    if lock:
        accounts = accounts.select_for_update()
    entities = post.entities if isinstance(post.entities, dict) else {}
    native_ids = {
        str(entity.get("id_str") or entity.get("id"))
        for entity in entities.get("user_mentions") or []
        if isinstance(entity, dict) and str(entity.get("screen_name", "")).casefold() == handle
        and str(entity.get("id_str") or entity.get("id") or "").isascii()
        and str(entity.get("id_str") or entity.get("id") or "").isdecimal()
    }
    if len(native_ids) > 1:
        return None
    if native_ids:
        accounts = accounts.filter(normalized_identifier=native_ids.pop())
    return accounts.first()


@transaction.atomic
def resolve_release_publisher(*, post, finding, verified_account=None):
    """Resolve the selected P1 issuer. A verified account must come from publisher-owned evidence."""
    from core.models import BrandAccount, BrandKeyword, OfficialCompanyAccountState, Product, ProductGroup
    from core.official_company_accounts import official_organization_links, registration_slug
    from core.organization_identity_locks import acquire_writer_identity_locks, organization_lock_keys

    issuer = finding.get("issuer_evidence") or {}
    name = (issuer.get("observed_name") or "").strip()
    selected = finding.get("brand_id")
    relation = issuer.get("relation")
    if relation not in ("source_author", "attributed_party"):
        return None

    account = None
    profile_supported = False
    accounts = Account.objects.select_for_update().filter(data_source_id="x")
    if relation == "source_author" and post.author_id:
        account = accounts.filter(pk=post.author_id).first()
        profile = finding.get("publisher_profile") or {}
        if profile and account:
            binding = profile.get("external_identifier")
            handle = (profile.get("handle") or "").casefold()
            if (binding and str(binding) != str(account.author_id)) or (
                not binding and (not handle or handle != (account.handle or "").casefold())
            ):
                return None
            if not name or (profile.get("display_name") or "").casefold() != name.casefold():
                return None
            # The source's stable account, own launch and corroborating profile
            # identify its line. An account display name by itself is only a lead.
            def identifier(value):
                return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())

            organization = identifier(name)
            domain_labels = {
                identifier(label) for domain in profile.get("domains", ()) for label in domain.split(".")[:-1]
            }
            has_profile_context = bool(domain_labels) or any(
                src.get("text") and not src.get("id", "").endswith(":display_name")
                for src in profile.get("sources", ())
            )
            profile_supported = bool(organization and has_profile_context and (
                organization == identifier(account.handle or "") or organization in domain_labels
            ))
    elif relation == "attributed_party" and issuer.get("observed_handle"):
        account = cited_x_account(post, issuer["observed_handle"], lock=True)

    if verified_account is not None and (not account or account.pk != verified_account.pk):
        return None
    if name:
        from django.utils.text import slugify

        stable_account = account if account and str(account.author_id or "").isdecimal() else None
        slug = registration_slug(name, stable_account) if stable_account else slugify(name)[:64] or None
        # Ingestion may be publishing this exact organization while P2 has only
        # a reporter's name. Read current official links and aliases after it commits.
        acquire_writer_identity_locks(organization_lock_keys(
            name=name, nickname=slug, account=stable_account.pk if stable_account else None,
        ))
    owners, companies = official_organization_links(account) if account else ([], [])
    owner_ids = {link.brand_id for link in owners if not link.brand.is_sentinel}
    matches = set(_release_brand_candidates(name).values_list("pk", flat=True)[:2]) if name else set()
    # One publisher account can officially represent several catalog lines.
    # P1 may select a specific, already verified member of that set.
    if selected in owner_ids:
        return selected if not matches or selected in matches else None
    if len(owner_ids) > 1 or len(companies) > 1:
        return None
    owner = next(iter(owner_ids), None)
    if selected:
        if not Brand.objects.filter(pk=selected, is_sentinel=False).exists():
            return None
        if (owner and selected != owner) or (name and owner != selected and matches != {selected}):
            return None
    if owner:
        return owner if not matches or owner in matches else None
    if len(matches) > 1:
        return None
    known = selected or next(iter(matches), None)
    if account and (BrandAccount.objects.filter(account=account).exclude(role_id="official").exists()
                    or CompanyAccount.objects.filter(account=account).exclude(role_id="official").exists()):
        return None

    # Historical packets without a publisher profile may reuse P1's known
    # catalog attribution. They cannot qualify a new official affiliation.
    state = (OfficialCompanyAccountState.objects.filter(account=account).first() if account else None)
    approved_name = (state.decision or {}).get("organization_name") if state else None
    if state and state.status in {"rejected", "suppressed"}:
        return None
    attested = (verified_account is not None or profile_supported or (
        state and state.status in {"accepted", "registered"} and approved_name and name
        and approved_name.casefold() == name.casefold()
    ))
    if not known and name:
        # Discovery keywords (including transliterations), Products and
        # families locate plausible existing identities. They cannot certify
        # the publisher of a new Brand.
        if (BrandKeyword.objects.filter(pattern__iexact=name, is_regex=False).exists()
                or Product.objects.filter(display_name__iexact=name).exists()
                or ProductGroup.objects.filter(group_kind="family", name__iexact=name).exists()):
            return None
    if not (account and attested and name and str(account.author_id or "").isdecimal()):
        if name and (finding.get("observed_name") or "").casefold() == name.casefold():
            return None
        return known
    company_link = companies[0] if companies and companies[0].ownership_confirmed else None
    if not known and company_link:
        linked = list(BrandCompany.objects.filter(company_id=company_link.company_id)
                      .values_list("brand_id", flat=True)[:2])
        if len(linked) > 1:
            return None
        known = linked[0] if linked else None
    if known:
        brand = Brand.objects.select_for_update().get(pk=known)
    else:
        brand, created = Brand.objects.get_or_create(pk=slug, defaults={"display_name": name})
        if not created and (brand.is_sentinel or (brand.display_name or "").casefold() != name.casefold()):
            return None
    # A different official account for a name-only match can be a namesake.
    if BrandAccount.objects.filter(brand=brand, role_id="official").exclude(account=account).exists():
        return None
    if company_link and BrandCompany.objects.filter(brand=brand).exclude(company_id=company_link.company_id).exists():
        return None
    role, _ = Role.objects.get_or_create(pk="official")
    BrandAccount.objects.get_or_create(brand=brand, account=account, defaults={"role": role})
    if company_link:
        link_brand_company(brand=brand, company=company_link.company)
    return brand.pk

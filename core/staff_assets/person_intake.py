"""Resolve a named subject from supplied observations, without starting research."""

import re
import uuid
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Collate, Lower, StrIndex

from core.account_identity import upsert_account
from core.models import (
    Account,
    AccountProfileSnapshot,
    Brand,
    BrandAccount,
    BrandCompany,
    Company,
    CompanyAccount,
    CompanyLabel,
    Person,
    PersonAccount,
    PersonMedia,
    PersonName,
    PersonNameEvidence,
    Post,
    Product,
    Role,
    StaffIntake,
)
from core.person_affiliations import active_claims
from core.person_identity import (
    IdentityConflict,
    account_has_observed_handle,
    account_person,
    canonical_person,
    identity_ids,
    normalized_handle,
    person_id_for_account,
)
from core.person_names import digest, record_name
from core.staff_assets.arrivals import without_collection_registration
from core.staff_assets.intake import observed_time, validate_record
from core.staff_assets.job_history import normalized
from core.staff_assets.job_history_identity import IdentityHold, validate_x_identity
from core.staff_assets.person_roles import KNOWN_TITLES, named_employers, phrase, sourced_role
from core.staff_assets.population import is_official
from core.staff_assets.queue import _lock


def _mentioned(model, passage, fields):
    where = Q()
    aliases = {}
    for pos, field in enumerate(fields):
        key = f"match_{pos}"
        # After folding case, match literal bytes. Locale-aware substring scans
        # are extremely slow on multilingual story passages in staging.
        aliases[key] = StrIndex(Collate(Lower(Value(passage)), "C"), Lower(field))
        where |= Q(**{key + "__gt": 0}) & ~Q(**{field: ""})
    return model.objects.alias(**aliases).filter(where)


def _organization(subject, passage, evidence, gaps):
    proposal = evidence.get("affiliation") or {}
    if not isinstance(proposal, dict):
        raise TypeError("affiliation must be an object")
    if not proposal and not re.search(KNOWN_TITLES, passage, re.IGNORECASE):
        return {}, None, None
    brands, companies = {}, {}
    for row in (
        _mentioned(
            Brand,
            passage,
            ("nickname", "display_name", "display_name_en", "display_name_zh_cn"),
        )
        .filter(is_sentinel=False)
        .values_list(
            "nickname", "display_name", "display_name_en", "display_name_zh_cn"
        )
    ):
        for name in filter(None, row):
            brands.setdefault(name, set()).add(row[0])
    for name in _mentioned(Company, passage, ("nickname",)).values_list(
        "nickname", flat=True
    ):
        companies.setdefault(name, set()).add(name)
    for name, company in _mentioned(CompanyLabel, passage, ("label",)).values_list(
        "label", "company_id"
    ):
        companies.setdefault(name, set()).add(company)
    stated = (
        proposal.get("organization")
        or proposal.get("brand_id")
        or proposal.get("company_id")
    )
    names = {stated} if stated else set(brands) | set(companies)
    title = proposal.get("title") or proposal.get("title_raw")
    spellings = [subject]
    local_name = evidence.get("name")
    if (
        local_name
        and local_name != subject
        and evidence.get("person_id")
        and PersonName.objects.filter(
            person_id=evidence["person_id"],
            full_name__iexact=local_name,
            evidence__source_reference=evidence.get("source_url"),
        )
        .exclude(review_status="rejected")
        .exists()
    ):
        spellings.append(local_name)
    own_profile = bool(title and _own_profile(evidence))
    roles = {}
    for name in sorted(names, key=len, reverse=True):
        for spelling in spellings:
            relation = sourced_role(
                spelling, name, passage, title, own_profile=own_profile
            )
            if relation and not any(
                normalized(name) in normalized(old) for old in roles
            ):
                roles[name] = relation
                break
    if not roles and not stated:
        for org in named_employers(subject, passage):
            role = sourced_role(subject, org, passage, title)
            if role:
                roles[org] = role
    if len(roles) != 1:
        if proposal or roles:
            gaps.append("affiliation_unresolved")
        return {}, None, None
    org, parsed = next(iter(roles.items()))
    if (
        proposal.get("status")
        and parsed.get("status")
        and proposal["status"] != parsed["status"]
    ):
        gaps.append("affiliation_status_conflict")
        return {}, None, None
    role = {**proposal, **parsed}
    if role.get("status", "unknown") not in {"current", "former", "unknown"}:
        raise ValueError("Invalid sourced affiliation status")

    def candidates(mapping):
        return {
            pk
            for spelling, pks in mapping.items()
            if normalized(spelling) == normalized(org)
            for pk in pks
        }

    brand_ids, company_ids = candidates(brands), candidates(companies)
    if proposal.get("brand_id"):
        if proposal["brand_id"] not in brand_ids:
            gaps.append("brand_identity_conflict")
            return role, None, None
        brand_ids = {proposal["brand_id"]}
    elif proposal.get("company_id"):
        brand_ids = set()
    if proposal.get("company_id"):
        company_ids &= {proposal["company_id"]}
    brand = next(iter(brand_ids)) if len(brand_ids) == 1 else None
    company = next(iter(company_ids)) if len(company_ids) == 1 else None
    if brand:
        owners = list(
            BrandCompany.objects.filter(
                brand_id=brand, ownership_pct__gt=0
            ).values_list("company_id", flat=True)
        )
        if company and owners and company not in owners:
            gaps.append("company_ownership_conflict")
            company = None
        elif (
            (
                not company
                and proposal.get("company_id")
                and owners == [proposal["company_id"]]
            )
            or not company
            and len(owners) == 1
            and not proposal.get("company_id")
        ):
            company = owners[0]
        elif not company and len(owners) > 1:
            gaps.append("company_ownership_ambiguous")
    if proposal.get("company_id") and company != proposal["company_id"]:
        gaps.append("company_identity_conflict")
    if len(brand_ids) > 1 or len(company_ids) > 1 or not (brand or company):
        gaps.append("organization_unresolved")
    return role, brand, company


def _profile_handle(url):
    profile = urlsplit(url)
    spelling = profile.path.strip("/")
    if (
        profile.scheme not in {"https", "http"}
        or profile.username
        or profile.hostname
        not in {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}
        or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", spelling)
    ):
        return ""
    return spelling.casefold()


def _own_profile(evidence):
    packet = evidence.get("personal_account")
    if not isinstance(packet, dict) or not evidence.get("source_url"):
        return False
    try:
        source_handle = _profile_handle(evidence["source_url"])
        if not source_handle:
            return False
        handle = normalized_handle(packet.get("handle")) or _profile_handle(
            packet.get("profile_url") or packet.get("url") or ""
        )
        if handle:
            return source_handle == handle
        if packet.get("native_id"):
            return Account.x.filter(
                author_id=str(packet["native_id"]), handle__iexact=source_handle
            ).exists()
    except (TypeError, ValueError):
        pass
    return False


def _account(packet, candidates):
    if not packet:
        return None, None
    if not isinstance(packet, dict):
        raise IdentityConflict("invalid_personal_account")
    native = packet.get("native_id")
    handle = normalized_handle(packet.get("handle"))
    profile_url = packet.get("profile_url") or packet.get("url")
    if profile_url:
        try:
            spelling = _profile_handle(profile_url)
            if not spelling or handle and handle != spelling:
                raise IdentityConflict("invalid_personal_profile")
        except (TypeError, ValueError) as exc:
            raise IdentityConflict("invalid_personal_profile") from exc
        handle = spelling
    if packet.get("provider", "x") != "x":
        raise IdentityConflict("invalid_personal_account")
    try:
        validate_x_identity(
            str(native) if native is not None else None, handle or None, partial=True
        )
    except IdentityHold as exc:
        raise IdentityConflict("invalid_personal_account") from exc
    account = None
    if packet.get("account_key"):
        account = Account.x.filter(pk=packet["account_key"]).first()
        if not account or native is not None and account.author_id != str(native):
            raise IdentityConflict("account_identity_conflict")
    elif native is not None:
        account = Account.x.filter(author_id=str(native)).first()
    if handle and account:
        if not account_has_observed_handle(account, handle):
            raise IdentityConflict("account_handle_conflict")
    elif handle:
        ids = set(Account.x.filter(handle__iexact=handle).values_list("pk", flat=True))
        ids.update(
            AccountProfileSnapshot.objects.filter(
                handle__iexact=handle, account__data_source_id="x"
            ).values_list("account_id", flat=True)
        )
        ids.update(
            Post.objects.filter(
                author_handle__iexact=handle, author__data_source_id="x"
            )
            .values_list("author_id", flat=True)
            .distinct()
        )
        candidates.update(ids)
        if len(ids) == 1 and native is None:
            account = Account.x.get(pk=ids.pop())
        elif ids:
            raise IdentityConflict("account_handle_ambiguous")
    if account and (
        account.account_kind in {"organization", "channel"} or is_official(account.pk)
    ):
        raise IdentityConflict("account_is_not_personal")
    if not account and native is None:
        raise IdentityConflict("personal_account_unresolved")
    if account:
        candidates.add(account.pk)
    return account, str(native) if native is not None else None


def _staff_account_ids(brand, company):
    matches = set()
    if brand:
        matches.update(
            BrandAccount.objects.filter(brand_id=brand, role_id="staff").values_list(
                "account_id", flat=True
            )
        )
    if company:
        matches.update(
            CompanyAccount.objects.filter(
                company_id=company, role_id="staff"
            ).values_list("account_id", flat=True)
        )
    return matches


def _canonical_ids(ids):
    """Follow redirects in batches. A namesake list can contain hundreds of people."""
    redirects = {}
    pending = set(ids)
    while pending:
        rows = dict(
            Person.objects.filter(pk__in=pending).values_list("pk", "merged_into_id")
        )
        if rows.keys() != pending:
            raise IdentityConflict("person_identity_conflict")
        redirects.update(rows)
        pending = set(filter(None, rows.values())) - redirects.keys()
    roots = set()
    for pk in ids:
        visited = set()
        while redirects[pk]:
            if pk in visited:
                raise IdentityConflict("cyclic_person_redirect")
            visited.add(pk)
            pk = redirects[pk]
        roots.add(pk)
    return roots


def _stored_subject_matches(ids, subject, evidence, *, unique):
    """Find corroborating records for the whole candidate set in a fixed number of reads."""
    source_refs = set(evidence.get("source_urls") or []) | {evidence.get("source_url")}
    source_refs.discard(None)
    source_refs.discard("")
    names = PersonNameEvidence.objects.filter(
        name__person_id__in=ids, name__full_name__iexact=subject
    ).exclude(name__review_status="rejected")
    name_match = Q(source_reference__in=source_refs) & ~Q(source_kind="legacy_unknown")
    if unique:
        name_match |= Q(
            source_kind="owner_supplied",
            collection_method__in=(
                "explicit_owner_cast_selection",
                "explicit_owner_media_confirmation",
            ),
        )
    matched = set(names.filter(name_match).values_list("name__person_id", flat=True))
    if unique:
        matched.update(
            PersonAccount.objects.filter(
                person_id__in=ids,
                resolution_status="confirmed",
                account__data_source_id="x",
                account__display_name__iexact=subject,
            ).values_list("person_id", flat=True)
        )
    media = PersonMedia.objects.filter(
        person_id__in=ids, source_kind="saved_g2_cast", media__isnull=False
    ).exclude(suitability="rejected")
    for row in media.only(
        "person_id", "source_url", "media_id", "review_history", "evidence"
    ):
        proof = row.evidence.get("identity_resolution") or {}
        if proof.get("person_id") != str(row.person_id) or not proof.get("evidence"):
            continue
        if proof.get("state") != "verified" and not any(
            isinstance(event, dict)
            and event.get("event") == "owner_confirmed_media"
            and event.get("person_id") == str(row.person_id)
            and event.get("sha256") == row.media_id
            and event.get("source_reference")
            for event in row.review_history
        ):
            continue
        spellings = [
            proof.get(key)
            for key in (
                "source_name",
                "confirmed_name",
                "recorded_name",
                "owner_selected_name",
            )
        ]
        spellings.append(row.evidence.get("source_person_key"))
        if not any(
            spelling and normalized(spelling) == normalized(subject)
            for spelling in spellings
        ):
            continue
        if unique or (
            source_refs & {row.source_url, proof.get("matched_source_reference")}
        ):
            matched.add(row.person_id)
            continue
        org = proof.get("organization") or proof.get("source_context_term")
        if (
            isinstance(org, str)
            and org
            and sourced_role(subject, org, evidence["passage"])
        ):
            matched.add(row.person_id)
    return matched


def personal_accounts_named(subject):
    """Display-name candidates still need independent evidence before linking."""
    return list(
        Account.x.filter(display_name__iexact=subject)
        .exclude(account_kind__in=("organization", "channel"))
        .exclude(
            pk__in=BrandAccount.objects.filter(role_id="official").values(
                "account_id"
            )
        )
        .exclude(
            pk__in=CompanyAccount.objects.filter(role_id="official").values(
                "account_id"
            )
        )
    )


def _resolve(
    subject,
    evidence,
    source_key,
    role,
    brand,
    company,
    candidates,
    account_candidates,
    occupation,
    account_lookup,
):
    named = PersonName.objects.filter(full_name__iexact=subject).exclude(
        review_status="rejected"
    )
    candidates.update(_canonical_ids(set(named.values_list("person_id", flat=True))))
    bound = _canonical_ids(
        set(
            StaffIntake.objects.filter(
                source_key=source_key, person__isnull=False
            ).values_list("person_id", flat=True)
        )
    )
    explicit = evidence.get("person_id")
    if explicit:
        bound.add(canonical_person(explicit).pk)
    account, native = _account(evidence.get("personal_account"), account_candidates)
    org_accounts = None
    if not (account or native or evidence.get("personal_account")) and role:
        accounts = account_lookup(subject)
        org_accounts = _staff_account_ids(brand, company)
        # A display name can locate a candidate. The catalog staff link or the
        # account's own matching employer/title must independently identify it.
        matches = [
            a
            for a in accounts
            if (
                a.pk in org_accounts
                or sourced_role(
                    subject,
                    role["organization"],
                    a.description or "",
                    role["title"],
                    own_profile=True,
                )
            )
        ]
        account_candidates.update(a.pk for a in matches)
        if len(matches) > 1:
            raise IdentityConflict("personal_account_ambiguous")
        account = matches[0] if matches else None
    if account:
        links = list(
            PersonAccount.objects.filter(account=account).values_list(
                "person_id", "resolution_status"
            )
        )
        active = _canonical_ids({pk for pk, status in links if status != "rejected"})
        candidates.update(active)
        if len(active) > 1 or any(status == "needs_review" for _, status in links):
            raise IdentityConflict("person_account_conflict")
        linked = account_person(account, create=False)
        if linked:
            bound.add(linked.pk)
        elif active and active != bound:
            # A previous source-based link is reusable when its name and account
            # observation refer to the same subject. Other pending matches stay held.
            if not StaffIntake.objects.filter(
                person_id__in=active,
                payload__intake_account_key=str(account.pk),
                payload__display_name__iexact=subject,
            ).exists():
                raise IdentityConflict("pending_account_match")
            bound |= active
        if (
            bound
            and _canonical_ids({pk for pk, status in links if status == "rejected"})
            & bound
        ):
            raise IdentityConflict("person_account_rejected")
        if (
            account.display_name
            and normalized(account.display_name) != normalized(subject)
            and not named.filter(person_id__in=bound).exists()
        ):
            raise IdentityConflict("personal_account_name_conflict")
    if bound and candidates and not (bound & candidates):
        raise IdentityConflict("person_identity_conflict")
    if len(bound) > 1:
        raise IdentityConflict("person_identity_conflict")
    if not bound and candidates:
        # Include evidence on retired identities, grouping all matches by survivor.
        family = {pk: pk for pk in candidates}
        frontier = set(candidates)
        while frontier:
            children = dict(
                Person.objects.filter(merged_into_id__in=frontier).values_list(
                    "pk", "merged_into_id"
                )
            )
            family.update((pk, family[parent]) for pk, parent in children.items())
            frontier = set(children)
        matched = _stored_subject_matches(
            family, subject, evidence, unique=len(candidates) == 1
        )
        if brand:
            matched.update(
                active_claims()
                .filter(person_id__in=family, brand_id=brand)
                .values_list("person_id", flat=True)
            )
        if org_accounts is None:
            org_accounts = _staff_account_ids(brand, company)
        if org_accounts:
            matched.update(
                PersonAccount.objects.filter(
                    person_id__in=family,
                    account_id__in=org_accounts,
                    resolution_status="confirmed",
                ).values_list("person_id", flat=True)
            )
        if role:
            matched.update(
                StaffIntake.objects.filter(
                    person_id__in=family,
                    payload__intake_organization__iexact=role["organization"],
                ).values_list("person_id", flat=True)
            )
        corroborated = {family[pk] for pk in matched}
        if len(corroborated) != 1:
            raise IdentityConflict("identity_unresolved")
        bound = corroborated
    if bound:
        if (
            account
            and _canonical_ids({pk for pk, status in links if status == "rejected"})
            & bound
        ):
            raise IdentityConflict("person_account_rejected")
        person = Person.objects.get(pk=next(iter(bound)))
        if not account and not native:
            links = PersonAccount.objects.filter(
                person_id__in=identity_ids(person.pk),
                account__data_source_id="x",
                resolution_status="confirmed",
            ).select_related("account")
            primary = [link.account for link in links if link.is_primary]
            accounts = primary or [link.account for link in links]
            account_candidates.update(a.pk for a in accounts)
            if (
                len(accounts) == 1
                and accounts[0].account_kind not in {"organization", "channel"}
                and not is_official(accounts[0].pk)
            ):
                account = accounts[0]
        return person, account, native, False
    if not (
        account
        or native
        or role
        or occupation is not None
        or evidence.get("identity_supported") is True
    ):
        raise IdentityConflict("identity_unresolved")
    pk = (
        person_id_for_account(account.author_id if account else native)
        if account or native
        else uuid.uuid5(uuid.NAMESPACE_URL, "staff-library:source:" + source_key)
    )
    if Person.objects.filter(pk=pk).exists():
        raise IdentityConflict("person_identity_conflict")
    return Person(pk=pk), account, native, True


def _occupation_industry(subject, passage):
    """Only a role directly attributed to the subject establishes industry from prose."""
    name = phrase(subject)
    for pattern, industry in (
        (
            r"(?:AI|artificial intelligence|machine learning) (?:researcher|engineer|scientist)",
            True,
        ),
        (
            r"(?:(?:U\.?S\.?|United States|American) president|president of the United States)",
            False,
        ),
    ):
        if re.search(
            rf"\b(?:{pattern})\s+{name}|{name},?\s+(?:(?:is )?(?:the |an? ))?(?:{pattern})\b",
            passage,
            re.IGNORECASE,
        ):
            return industry
    return None


def _account_china_clue(account):
    if not account:
        return None
    codes = {"CN", "HK", "MO", "TW"}
    place = account.profile_location
    if place and (
        place.iso2_country_code in codes
        or place.country_id
        and place.country.iso2_country_code in codes
    ):
        return {
            "kind": "self_reported_profile_location",
            "geolocation_id": place.pk,
            "account_key": str(account.pk),
            "source_url": f"https://x.com/{account.handle}" if account.handle else None,
            "observed_at": account.last_seen_at.isoformat(),
        }
    return None


def _route(evidence, person, account, role, brand, company, needs, occupation):
    industry = evidence.get("industry")
    if industry is not None and type(industry) is not bool:
        raise ValueError("industry must be true, false or null")
    if industry is None:
        industry = occupation
    china_reason = evidence.get("china_reason") or ""
    connection = evidence.get("china_connection") or {}
    if connection.get("route") == "chinese_staff" and connection.get("status") in {
        "documented_connection",
        "search_clue",
    }:
        china_reason = china_reason or connection.get("evidence")
    brands = {brand} if brand and role.get("status") == "current" else set()
    companies = {company} if company and role.get("status") == "current" else set()
    if person and not person._state.adding:
        ids = identity_ids(person.pk)
        prior = StaffIntake.objects.filter(person_id__in=ids).order_by(
            "-observed_at", "-pk"
        )
        for saved_industry, saved_reason, clue in prior.values_list(
            "payload__intake_industry",
            "payload__intake_china_reason",
            "payload__china_connection",
        ):
            if industry is None and type(saved_industry) is bool:
                industry = saved_industry
            clue = clue or {}
            if not china_reason and clue.get("route") == "chinese_staff":
                china_reason = clue.get("evidence")
            china_reason = china_reason or saved_reason
            if industry is not None and china_reason:
                break
        brands.update(
            active_claims()
            .filter(
                person_id__in=ids,
                status="current",
                affiliation_type_reference__code__in=("founder", "employment"),
            )
            .values_list("brand_id", flat=True)
        )
        linked = PersonAccount.objects.filter(
            person_id__in=ids, resolution_status="confirmed"
        ).values("account_id")
        brands.update(
            BrandAccount.objects.filter(
                account_id__in=linked, role_id="staff"
            ).values_list("brand_id", flat=True)
        )
        companies.update(
            CompanyAccount.objects.filter(
                account_id__in=linked, role_id="staff"
            ).values_list("company_id", flat=True)
        )
    if not china_reason and industry is not False:
        china_reason = _account_china_clue(account)
    if industry is None and (brands or companies):
        ai_products = Product.objects.filter(product_type__code__startswith="model-")
        if ai_products.filter(
            Q(brand_id__in=brands) | Q(brand__companies__company_id__in=companies)
        ).exists():
            industry = True
    if industry is None and re.search(
        r"\b(AI|artificial intelligence|machine learning)\b",
        role.get("title", ""),
        re.IGNORECASE,
    ):
        industry = True
    return {
        "industry": industry,
        "china": industry is True
        and bool(china_reason)
        and evidence.get("china") is not False,
        "china_reason": china_reason or None,
        "jobs": industry is True and "jobs" in needs,
        "facematch": "portrait" in needs and evidence.get("facematch") is True,
    }


def _account_roles(account, brand, company, result, apply):
    created_links = []
    for model, key, target in (
        (BrandAccount, "brand_id", brand),
        (CompanyAccount, "company_id", company),
    ):
        if not target:
            continue
        filters = {key: target, "account_id": result["account_key"]}
        current = model.objects.filter(**filters).first() if account else None
        action = "reuse" if current else "create"
        if current and current.role_id != "staff":
            action = "hold"
            result["gaps"].append(f"{model._meta.db_table}_role_conflict")
        if not current and not Role.objects.filter(pk="staff").exists():
            action = "hold"
            result["gaps"].append("staff_role_unregistered")
        result["proposed_changes"].append(
            {
                "table": model._meta.db_table,
                "action": action,
                **filters,
                "role_id": "staff",
            }
        )
        if apply and action == "create":
            link, created = model.objects.get_or_create(
                **filters, defaults={"role_id": "staff"}
            )
            if created:
                created_links.append(
                    [model._meta.db_table, target, link.added_at.isoformat()]
                )
    return created_links


def create_or_update_person(
    subject, evidence, needs=frozenset({"portrait"}), *, apply=True, collect=True,
    account_lookup=personal_accounts_named,
):
    """Preview or reconcile one attributed subject. Author/reporter fields are never identity inputs.

    Supply passage, source_url or source_id and observed_at. personal_account refers
    to the subject, and person_id is a known identity. identity_supported is a
    source assessment that distinguishes the person, not a name-only match.
    """
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or not isinstance(evidence, dict)
    ):
        raise ValueError("A subject name and evidence object are required")
    needs = frozenset(needs)
    if needs - {"portrait", "jobs"}:
        raise ValueError("Unsupported person intake need")
    subject = subject.strip()
    identity = _reconcile_person(subject, evidence, needs, apply, account_lookup)
    if collect and apply:
        from core.staff_assets.person_research import collect_missing

        return collect_missing(identity, subject, evidence, needs)
    return identity


def _reconcile_person(subject, evidence, needs, apply, account_lookup):
    passage = evidence.get("passage") or ""
    reference = evidence.get("source_url") or str(evidence.get("source_id") or "")
    when = evidence.get("observed_at")
    observed = observed_time(when) if when else None
    source_key = "person-intake:" + digest([subject.casefold(), reference])
    gaps, candidates, account_candidates = [], set(), set()
    changes = []
    created_links = []
    occupation = _occupation_industry(subject, passage)
    with transaction.atomic(), without_collection_registration():
        if apply:
            _lock()
        role, brand, company = _organization(subject, passage, evidence, gaps)
        result = {
            "subject": subject,
            "person_id": None,
            "account_key": None,
            "gaps": gaps,
            "proposed_changes": changes,
            "source": {
                "passage": passage,
                "source_url": evidence.get("source_url"),
                "source_id": evidence.get("source_id"),
                "observed_at": observed.isoformat() if observed else None,
            },
        }
        try:
            if not (observed and reference and passage):
                if not evidence.get("person_id"):
                    raise IdentityConflict("source_observation_missing")
                person = canonical_person(evidence["person_id"])
                # A known identity may be read using its key alone. Writes need a dated observation.
                read_only_identity = True
                account, native, creating = None, None, False
            else:
                read_only_identity = False
                if not re.search(phrase(subject), passage, re.IGNORECASE) and not (
                    evidence.get("person_id")
                    or evidence.get("personal_account")
                    and evidence.get("identity_supported") is True
                ):
                    raise IdentityConflict("subject_not_in_source")
                person, account, native, creating = _resolve(
                    subject,
                    evidence,
                    source_key,
                    role,
                    brand,
                    company,
                    candidates,
                    account_candidates,
                    occupation,
                    account_lookup,
                )
        except (IdentityConflict, Person.DoesNotExist, ValidationError) as exc:
            person, account, native, creating, read_only_identity = (
                None,
                None,
                None,
                False,
                False,
            )
            if str(exc) != "identity_unresolved":
                gaps.append(
                    str(exc)
                    if isinstance(exc, IdentityConflict)
                    else "person_identity_conflict"
                )
            gaps.append("identity_unresolved")
        result.update(
            _route(evidence, person, account, role, brand, company, needs, occupation)
        )
        result["candidate_person_ids"] = sorted(map(str, candidates))
        result["candidate_account_keys"] = sorted(map(str, account_candidates))
        if person and not account and len(account_candidates) > 1:
            gaps.append("personal_account_ambiguous")
        result["affiliation"] = (
            {**role, "brand_id": brand, "company_id": company} if role else None
        )
        if role and not evidence.get("affiliation"):
            # The resolver can recover a role from prose before research starts.
            # The observation remains untouched in the immutable intake below.
            result["affiliation"]["source_reference"] = reference
        if person:
            result["person_id"] = str(person.pk)
        if read_only_identity:
            gaps.append("source_observation_missing")
            return result
        if person:
            new_account = native is not None and account is None
            if new_account:
                changes.append(
                    {"table": "accounts", "action": "create", "native_id": native}
                )
                if apply:
                    account = upsert_account(
                        source="x",
                        external_identifier=native,
                        handle=normalized_handle(
                            evidence["personal_account"].get("handle")
                        )
                        or None,
                        account_kind="individual",
                    )
            changes.append(
                {
                    "table": "people",
                    "action": "create" if creating else "reuse",
                    "person_id": str(person.pk),
                }
            )
            if creating and apply:
                person.save(force_insert=True)
            if account or new_account:
                result["account_key"] = str(account.pk) if account else None
                links = PersonAccount.objects.filter(
                    person_id__in=identity_ids(person.pk)
                    if not creating
                    else [person.pk],
                    account=account,
                )
                link = (
                    links.exclude(resolution_status="rejected").first()
                    if account
                    else None
                )
                changes.append(
                    {
                        "table": "people_accounts",
                        "action": "reuse" if link else "create",
                        "account_key": result["account_key"],
                        "person_id": str(person.pk),
                    }
                )
                if apply and link is None:
                    PersonAccount.objects.create(
                        person=person,
                        account=account,
                        resolution_status="pending",
                        first_observed_at=observed,
                        last_observed_at=observed,
                    )
                elif apply and observed > link.last_observed_at:
                    PersonAccount.objects.filter(pk=link.pk).update(
                        last_observed_at=observed
                    )
                if role.get("status") == "current":
                    created_links = _account_roles(
                        account, brand, company, result, apply
                    )
            if apply and re.search(phrase(subject), passage, re.IGNORECASE):
                record_name(
                    person,
                    full_name=subject,
                    language="und",
                    source_kind="person_intake",
                    source_reference=reference,
                    source_text=passage,
                    collection_method="person-intake-v1",
                    observed_at=observed,
                )
        if not (observed and reference and passage):
            return result
        payload = {
            "source_key": source_key,
            "display_name": subject,
            "eligibility": "unestablished" if person else "needs_review",
            "collection_mode": "evidence_only",
            "evidence_only": {"schema": "staff-evidence-only/v1", "claims": []},
            "observed_at": observed.isoformat(),
            "person_intake": {**evidence, "observed_at": observed.isoformat()},
            "intake_organization": role.get("organization"),
            "intake_affiliation": {**role, "brand_id": brand, "company_id": company}
            if role
            else None,
            "intake_account_key": result["account_key"],
            "intake_industry": result["industry"],
            "intake_china_reason": result["china_reason"],
        }
        if not person:
            payload.update(
                candidate_person_ids=result["candidate_person_ids"], gaps=gaps
            )
        validate_record(payload)
        intake = None
        if apply:
            intake, _ = StaffIntake.objects.get_or_create(
                source_key=source_key,
                fingerprint=digest(payload),
                defaults={
                    "person": person,
                    "payload": payload,
                    "observed_at": observed,
                    "eligibility": payload["eligibility"],
                },
            )
        if created_links:
            # Creation time distinguishes this data-only membership from a legitimately
            # removed and later independently recreated catalog link.
            marker = {
                "source_key": f"person-intake-links:{account.pk}:{digest(created_links)}",
                "display_name": subject,
                "eligibility": "unestablished",
                "collection_mode": "evidence_only",
                "evidence_only": {"schema": "staff-evidence-only/v1", "claims": []},
                "observed_at": observed.isoformat(),
                "observation_id": intake.pk,
                "account_key": str(account.pk),
                "staff_links": created_links,
            }
            validate_record(marker)
            StaffIntake.objects.get_or_create(
                source_key=marker["source_key"],
                fingerprint=digest(marker),
                defaults={
                    "person": person,
                    "observed_at": observed,
                    "eligibility": marker["eligibility"],
                    "payload": marker,
                },
            )
        if (
            person
            and result["jobs"]
            and role
            and brand
            and not evidence.get("source_url")
        ):
            gaps.append("job_source_url_missing")
        elif person and result["jobs"] and role and brand:
            from core.staff_assets.job_history_apply import intake_role

            action = intake_role(
                person,
                role,
                brand,
                passage=passage,
                reference=reference,
                observed=observed,
                intake=intake,
            )
            changes.append({"table": "people_brand_affiliations", **action})
            if action["action"] == "hold":
                gaps.append("job_role_unresolved")
        return result

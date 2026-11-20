"""Atomic source-first application of one reviewed employment claim.

The caller owns target selection and preview approval. This helper never opens a
connection, chooses an environment, or initiates a provider request.
"""

from datetime import datetime
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.geolocation_evidence import write_source_evidence
from core.models import (
    Account,
    AccountProfileSnapshot,
    AffiliationType,
    Brand,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    Post,
    StaffIntake,
)
from core.person_affiliations import ROLE_TEXT_FIELDS, reconcile_role
from core.person_identity import (
    IdentityConflict,
    account_has_observed_handle,
    account_observation_person_ids,
    account_person,
)
from core.person_names import digest
from core.staff_assets.intake import validate_record


class _Hold(Exception):
    pass


def source_account_matches_person(person, account):
    """Accept confirmed links or this account's sole direct provisional identity."""
    links = list(
        PersonAccount.objects.filter(account=account).exclude(
            resolution_status="rejected"
        )
    )
    if len(links) != 1 or links[0].person_id != person.pk:
        return False
    if links[0].resolution_status == "confirmed":
        return True
    if links[
        0
    ].resolution_status != "pending" or person.pk not in account_observation_person_ids(
        account.author_id or account.pk
    ):
        return False
    try:
        resolved = account_person(account)
    except IdentityConflict:
        return False
    return resolved is not None and resolved.pk == person.pk


def _instant(value):
    result = parse_datetime(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or timezone.is_naive(result):
        raise _Hold("A source observation needs its original timezone-aware clock")
    return result


def _source(person, source):
    """Resolve a source before attaching it; never mutate a conflicting source."""
    observed = _instant(source.get("observed_at"))
    text = source.get("text")
    url = source.get("url")
    if not isinstance(text, str) or not text.strip() or not isinstance(url, str):
        raise _Hold("Source text and URL are required")
    kind = source.get("kind")
    if kind == "post":
        post_id = source.get("post_id")
        if (
            not isinstance(post_id, str)
            or not post_id.isascii()
            or not post_id.isdigit()
            or str(int(post_id)) != post_id
            or int(post_id) <= 0
        ):
            raise _Hold("Invalid source post identity")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"x.com", "twitter.com", "www.twitter.com"}
            or parsed.username is not None
            or not parsed.path.rstrip("/").endswith("/status/" + post_id)
        ):
            raise _Hold("Source URL does not identify the post")
        account_key = source.get("account_key")
        account = Account.objects.filter(pk=account_key).first()
        if account is None or not source_account_matches_person(person, account):
            raise _Hold("Source account is not unambiguously linked to this person")
        path_parts = parsed.path.strip("/").split("/")
        if (
            len(path_parts) != 3
            or path_parts[1:] != ["status", post_id]
            or not account_has_observed_handle(account, path_parts[0])
        ):
            raise _Hold("Source URL handle does not match the confirmed account")
        published = _instant(source.get("published_at"))
        if observed < published:
            raise _Hold("Source observation precedes its publication")
        post, created = Post.objects.get_or_create(
            tweet_id=post_id,
            defaults={
                "author": account,
                "author_handle": path_parts[0],
                "text": text,
                "created_at": published,
            },
        )
        if not created and (
            post.author_id != account.pk
            or post.text != text
            or post.created_at != published
        ):
            raise _Hold("Existing post conflicts with saved source")
        return post, None, observed
    if kind == "profile":
        snapshot = AccountProfileSnapshot.objects.filter(
            pk=source.get("snapshot_id")
        ).first()
        if snapshot is None or not source_account_matches_person(
            person, snapshot.account
        ):
            raise _Hold("Source profile is not bound to a confirmed account")
        Account.objects.select_for_update().get(pk=snapshot.account_id)
        snapshot = AccountProfileSnapshot.objects.select_for_update().get(
            pk=snapshot.pk
        )
        parsed = urlsplit(url)
        handle = snapshot.handle or snapshot.account.handle
        path_parts = parsed.path.strip("/").split("/")
        valid_suffix = len(path_parts) == 1 or (
            len(path_parts) == 3
            and path_parts[1] == "status"
            and path_parts[2] == str(snapshot.first_source_post_id or "")
        )
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"x.com", "twitter.com", "www.twitter.com"}
            or parsed.username is not None
            or not handle
            or not valid_suffix
            or path_parts[0].casefold() != handle.casefold()
        ):
            raise _Hold("Profile URL does not match the snapshot account")
        if not any(
            text in (value or "")
            for value in (snapshot.description, snapshot.profile_bio_text)
        ):
            raise _Hold("Source profile text does not match")
        if observed not in {snapshot.first_observed_at, snapshot.last_observed_at}:
            raise _Hold("Source observation is not a known profile interval boundary")
        from core.geolocation_evidence import source_evidence
        from core.staff_assets.job_history import _match_target_profile

        rows = []
        for row in AccountProfileSnapshot.objects.select_for_update().filter(
            account_id=snapshot.account_id
        ):
            rows.append(
                {
                    "id": row.pk,
                    "account_key": row.account_id,
                    "profile_hash": row.profile_hash,
                    "first_observed_at": row.first_observed_at.isoformat(),
                    "last_observed_at": row.last_observed_at.isoformat(),
                    "first_source_post_id": row.first_source_post_id,
                    "first_source_kind": row.first_source_kind,
                    "present_fields": row.present_fields,
                    "profile_data": source_evidence(row).profile_data,
                    "handle": row.handle,
                }
            )
        action = {
            "fields": {
                "account_key": snapshot.account_id,
                "observed_at": observed.isoformat(),
                "observed_handle": source.get("observed_handle"),
                "observation_kind": source.get("observation_kind"),
                "source_reference": url,
                "saved_bio": text,
            }
        }
        if _match_target_profile(action, rows) != snapshot.pk:
            raise _Hold(
                "Profile evidence no longer matches the target source and clock"
            )
        return None, snapshot, observed
    raise _Hold("Unsupported or unresolved source kind")


def apply_profile_action(*, person, account, person_packet, action):
    """Reuse an exact profile or capture a dated bio after a locked history check."""
    try:
        with transaction.atomic():
            if action.get("action") not in {"reuse", "compare_or_create"}:
                raise _Hold("Prepared profile is held")
            fields = action.get("fields") or {}
            if str(fields.get("account_key")) != str(
                account.pk
            ) or not source_account_matches_person(person, account):
                raise _Hold(
                    "Profile account is not unambiguously linked to this person"
                )
            if action["action"] == "reuse":
                _source(
                    person,
                    {
                        "kind": "profile",
                        "snapshot_id": fields.get("target_snapshot_id"),
                        "url": fields.get("source_reference"),
                        "text": fields.get("saved_bio"),
                        "observed_at": fields.get("observed_at"),
                        "observed_handle": fields.get("observed_handle"),
                        "observation_kind": fields.get("observation_kind"),
                    },
                )
                return {"action": "reuse", "snapshot_id": fields["target_snapshot_id"]}
            observed = _instant(fields.get("observed_at"))
            handle, text, reference = (
                fields.get("observed_handle"),
                fields.get("saved_bio"),
                fields.get("source_reference"),
            )
            if (
                fields.get("observation_kind") != "account.profile_bio_text"
                or not isinstance(handle, str)
                or not isinstance(text, str)
                or not text
                or not isinstance(reference, str)
                or reference.casefold() != f"https://x.com/{handle}".casefold()
                or not account.handle
                or account.handle.casefold() != handle.casefold()
            ):
                raise _Hold("Profile source is not an observed account bio")
            if not any(
                source.get("kind") == "saved_bio"
                and source.get("text") == text
                and any(
                    o.get("kind") == "account.profile_bio_text"
                    and (o.get("handle") or "").casefold() == handle.casefold()
                    and not o.get("post_id")
                    and o.get("observed")
                    and _instant(o["observed"]) == observed
                    for o in source.get("observations", [])
                )
                for source in person_packet.get("sources", [])
            ):
                raise _Hold("Profile source clock or text does not match the packet")
            Account.objects.select_for_update().get(pk=account.pk)
            from core.profile_snapshots import profile_observation_from_payload
            from core.staff_assets.job_history_identity import _marker
            from core.staff_assets.job_history_import import (
                record_saved_profile_snapshot,
            )

            observation = profile_observation_from_payload(
                {
                    "author_handle": handle,
                    "author_profile_bio_text": text,
                    "_author_present_fields": [
                        "author_handle",
                        "author_profile_bio_text",
                    ],
                }
            )
            result = record_saved_profile_snapshot(
                account=account, observation=observation, observed_at=observed
            )
            if result["action"] == "hold":
                raise _Hold(result["reason"])
            _marker(
                person,
                account.author_id,
                observed,
                purpose="profile:"
                + digest([str(account.pk), reference, observed.isoformat(), text]),
                details={
                    "source_reference": reference,
                    "observation_kind": "account.profile_bio_text",
                    "observed_handle": handle,
                    "observed_at": observed.isoformat(),
                    "saved_bio": text,
                    "snapshot_id": result["snapshot_id"],
                },
            )
            return result
    except _Hold as exc:
        return {"action": "hold", "reason": str(exc)}


def _source_account_key(source):
    if source.get("kind") == "post":
        return source.get("account_key")
    if source.get("kind") == "profile":
        return AccountProfileSnapshot.objects.filter(pk=source.get("snapshot_id")).values_list("account_id", flat=True).first()
    raise _Hold("Unsupported or unresolved source kind")


def apply_sourced_role(
    *,
    person_id,
    fields,
    source,
    expected_action,
    expected_id=None,
    brand_definition=None,
    selected_brands=None,
    supporting_sources=(),
):
    """Apply one prepared role and its bound sources atomically, or return a hold.

    A hold rolls back source creation as well as role/evidence writes. Signals
    remain enabled; a durable evidence-only intake prevents automatic enrollment.
    """
    try:
        with transaction.atomic():
            source_account_key = _source_account_key(source)
            bound_sources = [source, *supporting_sources]
            if any(str(_source_account_key(entry)) != str(source_account_key) for entry in bound_sources):
                raise _Hold("Role sources belong to different accounts")
            if (
                not source_account_key
                or not Account.objects.select_for_update()
                .filter(pk=source_account_key)
                .exists()
            ):
                raise _Hold("Source account is unavailable")
            person = Person.objects.select_for_update().get(pk=person_id)
            if expected_action not in {"create", "enrich", "add_evidence"}:
                raise _Hold("Prepared role is held or has an unsupported action")
            brand = fields.get("brand_id")
            affiliation_type = fields.get("affiliation_type")
            allowed_fields = set(ROLE_TEXT_FIELDS) | {
                "brand_id",
                "affiliation_type",
                "observed_organization_name",
                "observed_organization_handle",
                "status",
                "start_date",
                "start_date_precision",
                "end_date",
                "end_date_precision",
                "review_status",
                "review_note",
                "confidence",
                "geolocation_id",
            }
            if (
                set(fields) - allowed_fields
                or fields.get("review_status", "pending") != "pending"
                or fields.get("geolocation_id")
            ):
                raise _Hold("Unsupported fields or review state in prepared role")
            if not brand or affiliation_type not in {
                "employment",
                "founder",
                "contractor",
            }:
                raise _Hold(
                    "A resolved brand and supported affiliation type are required"
                )
            if selected_brands is not None and brand not in selected_brands:
                raise _Hold("Prepared brand is outside the selected scope")
            if any(not isinstance(entry.get("text"), str) for entry in bound_sources):
                raise _Hold("Source text is required")
            source_texts = [entry["text"].casefold() for entry in bound_sources]
            held_fields = {}
            held_field_reasons = {}
            status = fields.get("status")
            if (
                isinstance(status, str)
                and status != "unknown"
                and not any(status.casefold() in text for text in source_texts)
            ):
                # A saved bio may support the role without literally supporting
                # the proposed status. Preserve the original proposal for review
                # and persist only the supported, status-unknown role.
                held_fields["status"] = status
                held_field_reasons["status"] = "Status is not literally supported by the bound sources"
                fields = {**fields, "status": "unknown"}
            for key in (
                "observed_organization_name",
                "observed_organization_handle",
                *ROLE_TEXT_FIELDS,
                "start_date",
                "end_date",
                "status",
            ):
                value = fields.get(key)
                if (
                    value
                    and value != "unknown"
                    and (
                        not isinstance(value, str)
                        or not any(value.casefold() in text for text in source_texts)
                    )
                ):
                    raise _Hold("Role field lacks literal source support: " + key)
            resolved_sources = [(entry, *_source(person, entry)) for entry in bound_sources]
            brand_created = False
            existing_brand = Brand.objects.filter(pk=brand).first()
            if (
                existing_brand
                and isinstance(brand_definition, dict)
                and brand_definition.get("action") == "create"
            ):
                proposed_name = (brand_definition.get("fields") or {}).get(
                    "display_name"
                )
                if (
                    not isinstance(proposed_name, str)
                    or existing_brand.display_name
                    and existing_brand.display_name.casefold()
                    != proposed_name.casefold()
                ):
                    raise _Hold("Target brand changed since preview")
            if existing_brand is None:
                if (
                    not isinstance(brand_definition, dict)
                    or brand_definition.get("action") != "create"
                    or brand_definition.get("table") != "brands"
                    or brand not in (selected_brands or [])
                ):
                    raise _Hold("Target brand is absent or outside the prepared scope")
                definition = brand_definition.get("fields") or {}
                display_name = definition.get("display_name")
                if (
                    set(definition) != {"nickname", "display_name"}
                    or definition.get("nickname") != brand
                    or not isinstance(display_name, str)
                    or not display_name.strip()
                    or not any(display_name.casefold() in text for text in source_texts)
                ):
                    raise _Hold("New brand name is not supported by this source")
                brand_row, brand_created = Brand.objects.get_or_create(
                    pk=brand, defaults={"display_name": display_name}
                )
                if (
                    not brand_created
                    and brand_row.display_name
                    and brand_row.display_name.casefold() != display_name.casefold()
                ):
                    raise _Hold("Target brand changed since preview")
            from core.staff_assets.job_history import normalized

            organization = fields.get("observed_organization_name")
            if not isinstance(organization, str) or not organization.strip():
                raise _Hold("Role requires a source-supported organization name")
            organization_key = normalized(organization)
            matches = {
                row.nickname
                for row in Brand.objects.all().only(
                    "nickname", "display_name", "display_name_en", "display_name_zh_cn"
                )
                if organization_key
                in {
                    normalized(value)
                    for value in (
                        row.nickname,
                        row.display_name,
                        row.display_name_en,
                        row.display_name_zh_cn,
                    )
                    if value
                }
            }
            if matches != {brand}:
                raise _Hold(
                    "Organization name is not uniquely bound to the selected brand"
                )
            qs = PersonBrandAffiliation.objects.select_for_update().filter(
                person=person, brand_id=brand
            )
            rows = list(
                qs.values(
                    "id",
                    "claim_identity",
                    "affiliation_type_reference__code",
                    "status",
                    "start_date",
                    "start_date_precision",
                    "end_date",
                    "end_date_precision",
                    "review_status",
                    "superseded_at",
                    "superseded_by_id",
                    *ROLE_TEXT_FIELDS,
                )
            )
            for row in rows:
                row["affiliation_type"] = row.pop("affiliation_type_reference__code")
            decision = reconcile_role(fields, rows)
            if decision["action"] == "review_existing":
                raise _Hold("Role matches are conflicting or ambiguous")
            identity = digest(["save-person-job-role/v1", str(person.pk), fields])
            match = decision["match"]
            if (
                expected_action == "create"
                and match
                and match["claim_identity"] != identity
            ):
                raise _Hold("Target role changed since preview")
            if expected_action != "create" and (
                not match or str(match["id"]) != str(expected_id)
            ):
                raise _Hold("Target role changed since preview")
            if match:
                role = qs.get(pk=match["id"])
                tagged = [
                    entry
                    for intake in person.staff_intakes.all()
                    if intake.payload.get("collection_mode") == "evidence_only"
                    for entry in intake.payload.get("evidence_only", {}).get(
                        "claims", []
                    )
                    if entry.get("claim_identity") == role.claim_identity
                ]
                prior_hashes = set(
                    role.evidence.values_list("evidence_hash", flat=True)
                )
                independent_before = (
                    not tagged
                    or any(entry["independent_before"] for entry in tagged)
                    or bool(prior_hashes - {entry["evidence_hash"] for entry in tagged})
                )
                if independent_before and "title_raw" in decision["updates"]:
                    # This field participates in the existing collection-work
                    # fingerprint. Retain the sourced proposal without causing
                    # the next catch-up pass to schedule paid collection again.
                    held_fields["title_raw"] = decision["updates"].pop("title_raw")
                    held_field_reasons["title_raw"] = "Preserve independently established collection context"
                    decision["action"] = "enrich" if decision["updates"] else "add_evidence"
                if decision["updates"]:
                    PersonBrandAffiliation.objects.filter(pk=role.pk).update(
                        **decision["updates"]
                    )
            else:
                allowed = {f.name for f in PersonBrandAffiliation._meta.concrete_fields}
                defaults = {
                    key: value
                    for key, value in fields.items()
                    if key in allowed
                    and key
                    not in {
                        "id",
                        "person",
                        "brand",
                        "claim_identity",
                        "affiliation_type_reference",
                    }
                }
                role = PersonBrandAffiliation.objects.create(
                    person=person,
                    brand_id=brand,
                    affiliation_type_reference=AffiliationType.objects.get(
                        code=affiliation_type
                    ),
                    claim_identity=identity,
                    **defaults,
                )
                independent_before = False
            evidence_rows = []
            for bound_source, post, snapshot, observed in resolved_sources:
                source_data = {
                    "kind": bound_source["kind"],
                    "post_id": post.pk if post else None,
                    "profile_snapshot_id": snapshot.pk if snapshot else None,
                    "observed_at": observed.isoformat(),
                }
                evidence_hash = digest([bound_source["url"], bound_source["text"], source_data])
                evidence, made = PersonBrandAffiliationEvidence.objects.get_or_create(
                    affiliation=role,
                    evidence_hash=evidence_hash,
                    defaults={
                        "source_post": post,
                        "source_profile_snapshot": snapshot,
                        "source_url": bound_source["url"],
                        "evidence_text": bound_source["text"],
                        "observed_at": observed,
                        "extraction_method": "record-job-history-saved-review-v1",
                    },
                )
                if not made and (
                    evidence.source_post_id != (post.pk if post else None)
                    or evidence.source_profile_snapshot_id
                    != (snapshot.pk if snapshot else None)
                ):
                    raise _Hold("Existing evidence has different source binding")
                if made:
                    write_source_evidence(evidence, extracted_claim_data=source_data)
                payload = {
                    "source_key": "save-person-job:" + evidence_hash,
                    "display_name": str(person.pk),
                    "eligibility": "staff",
                    "observed_at": observed.isoformat(),
                    "affiliations": [
                        {
                            "brand_id": brand,
                            "source_url": bound_source["url"],
                            "evidence_text": bound_source["text"],
                        }
                    ],
                    "collection_mode": "evidence_only",
                    "evidence_only": {
                        "schema": "staff-evidence-only/v1",
                        "claims": [
                            {
                                "claim_identity": role.claim_identity,
                                "evidence_hash": evidence_hash,
                                "independent_before": independent_before,
                            }
                        ],
                    },
                }
                validate_record(payload)
                StaffIntake.objects.get_or_create(
                    source_key=payload["source_key"],
                    fingerprint=digest(payload),
                    defaults={
                        "person": person,
                        "eligibility": "staff",
                        "payload": payload,
                        "observed_at": observed,
                    },
                )
                evidence_rows.append((evidence, made))
            return {
                "action": "create" if not match else decision["action"],
                "role_id": role.pk,
                "evidence_id": evidence_rows[0][0].pk,
                "evidence_ids": [row.pk for row, _ in evidence_rows],
                "evidence_created": any(made for _, made in evidence_rows),
                "brand_created": brand_created,
                "held_fields": held_fields,
                "held_field_reasons": held_field_reasons,
            }
    except _Hold as exc:
        return {"action": "hold", "reason": str(exc)}

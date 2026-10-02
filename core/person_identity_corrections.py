"""Explicit identity repairs. Source representations and request history survive."""

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from core.models import (
    Account,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonIdentityCorrection,
    PersonMedia,
    PersonName,
    PersonNameEvidence,
    PersonText,
    PersonTextTranslation,
    StaffCollectionWork,
    StaffIntake,
)
from core.person_names import digest, review_name, select_names
from core.staff_assets.queue import _lock

TRANSFER_MODELS = {
    "affiliations": PersonBrandAffiliation,
    "intakes": StaffIntake,
    "media": PersonMedia,
    "texts": PersonText,
    "names": PersonName,
}


def snapshot(queryset):
    return json.loads(json.dumps(list(queryset.values()), cls=DjangoJSONEncoder))


def _selection(source, kind, selection):
    if set(selection) - {*TRANSFER_MODELS, "accounts"}:
        raise ValueError("Unknown correction selection")
    if kind == "split" and not any(selection.values()):
        raise ValueError("A split requires explicit source rows")
    chosen = {}
    for key, model in TRANSFER_MODELS.items():
        rows = model.objects.filter(person=source)
        ids = (
            list(rows.values_list("pk", flat=True))
            if kind == "merge"
            else selection.get(key, [])
        )
        if len(ids) != len(set(ids)) or rows.filter(pk__in=ids).count() != len(ids):
            raise ValueError(f"Selected {key} must belong to the source person")
        chosen[key] = list(rows.filter(pk__in=ids).order_by("pk"))
    links = PersonAccount.objects.filter(person=source)
    accounts = (
        list(links.values_list("account_id", flat=True))
        if kind == "merge"
        else selection.get("accounts", [])
    )
    if len(accounts) != len(set(accounts)) or links.filter(
        account_id__in=accounts
    ).count() != len(accounts):
        raise ValueError("Selected accounts must belong to the source person")
    chosen["accounts"] = list(
        links.filter(account_id__in=accounts).order_by("account_id")
    )
    if kind == "split":
        ids = {row.pk for row in chosen["affiliations"]}
        for row in chosen["affiliations"]:
            dependencies = set(row.replaced_claims.values_list("pk", flat=True))
            if row.superseded_by_id:
                dependencies.add(row.superseded_by_id)
            if dependencies - ids:
                raise ValueError("Select the complete employment replacement chain")
        texts = {row.pk for row in chosen["texts"]}
        required_texts = set(
            PersonText.objects.filter(affiliation_id__in=ids).values_list(
                "pk", flat=True
            )
        )
        if required_texts - texts:
            raise ValueError("Select the texts belonging to the moved affiliations")
        for row in chosen["texts"]:
            if row.affiliation_id and row.affiliation_id not in ids:
                raise ValueError("Select the affiliation belonging to the moved text")
            dependencies = set(row.derived_texts.values_list("pk", flat=True))
            if row.derived_from_id:
                dependencies.add(row.derived_from_id)
            if dependencies - texts:
                raise ValueError("Select the complete text derivation chain")
    return chosen


def _copy_names(source, target, names, *, kind, reviewer, reason):
    mapping = {}
    visiting = set()

    def copy(row):
        if row.pk in mapping:
            return PersonName.objects.get(pk=mapping[row.pk])
        if row.pk in visiting:
            raise ValueError("Name derivation cycle needs repair")
        visiting.add(row.pk)
        parent = copy(row.derived_from) if row.derived_from_id else None
        representation = {
            "full_name": row.full_name,
            "language": row.language,
            "name_type": row.name_type,
            "origin": row.origin,
            "derived_from_id": parent.pk if parent else None,
        }
        new, created = PersonName.objects.get_or_create(
            person=target,
            fingerprint=digest(representation),
            defaults={
                **representation,
                "given_name": row.given_name,
                "family_name": row.family_name,
                "name_order": row.name_order,
                "review_status": row.review_status,
                "review_history": row.review_history,
            },
        )
        if not created and any(
            getattr(new, key) not in (None, getattr(row, key))
            and getattr(row, key) is not None
            for key in ("given_name", "family_name")
        ):
            raise ValueError("Conflicting name components need separate review")
        for evidence in row.evidence.all():
            values = {
                field.attname: getattr(evidence, field.attname)
                for field in evidence._meta.concrete_fields
                if field.name not in {"id", "name", "created_at"}
            }
            evidence_hash = values.pop("evidence_hash")
            PersonNameEvidence.objects.get_or_create(
                name=new, evidence_hash=evidence_hash, defaults=values
            )
        mapping[row.pk] = new.pk
        visiting.remove(row.pk)
        return new

    for row in names:
        copy(row)
    choices = {"primary": target.primary_name, "english": target.english_name}
    for key, selected in choices.items():
        original_id = getattr(source, key + "_name_id")
        if selected is None and original_id in mapping:
            candidate = PersonName.objects.get(pk=mapping[original_id])
            if candidate.review_status == "confirmed":
                choices[key] = candidate
    select_names(target, **choices)
    if kind == "split":
        for row in names:
            review_name(row, "rejected", reviewer, "Identity split: " + reason)
    return {str(key): value for key, value in mapping.items()}


def _move_account(link, target):
    values = {
        field.attname: getattr(link, field.attname)
        for field in link._meta.concrete_fields
        if field.name not in {"person", "account"}
    }
    account_id = link.account_id
    existing = PersonAccount.objects.filter(
        person=target, account_id=account_id
    ).first()
    # Remove the old confirmed edge before creating its replacement; the
    # database enforces one confirmed person per account throughout the move.
    link.delete()
    has_primary = (
        PersonAccount.objects.filter(
            person=target, resolution_status="confirmed", is_primary=True
        )
        .exclude(account_id=account_id)
        .exists()
    )
    if has_primary:
        values["is_primary"] = False
    if existing:
        existing.first_observed_at = min(
            existing.first_observed_at, values["first_observed_at"]
        )
        existing.last_observed_at = max(
            existing.last_observed_at, values["last_observed_at"]
        )
        if values["resolution_status"] == "confirmed":
            existing.resolution_status = "confirmed"
            existing.is_primary = values["is_primary"]
        existing.save()
    else:
        PersonAccount.objects.create(person=target, account_id=account_id, **values)


def _transfer(row, target, *, kind):
    """Move ordinary edges; preserve colliding originals on the retired identity."""
    if isinstance(row, PersonMedia):
        collision = PersonMedia.objects.filter(
            person=target, fingerprint=row.fingerprint
        ).first()
    elif isinstance(row, PersonText):
        collision = PersonText.objects.filter(
            person=target,
            affiliation_id=row.affiliation_id,
            kind=row.kind,
            source_reference=row.source_reference,
            version_hash=row.version_hash,
        ).first()
    else:
        collision = None
    if collision:
        if isinstance(row, PersonText) and (
            row.derived_from_id or row.derived_texts.exists()
        ):
            raise ValueError("Text derivation collision needs separate review")
        if kind == "split":
            raise ValueError(
                "Selected record already exists on target; review collision separately"
            )
        # The original remains addressable and the journal records the collision.
        # No contradictory attribution or translation is silently overwritten.
        if isinstance(row, PersonText):
            for translation in row.translations.all():
                PersonTextTranslation.objects.get_or_create(
                    original=collision,
                    language=translation.language,
                    provider=translation.provider,
                    model=translation.model,
                    prompt_version=translation.prompt_version,
                    defaults={"text": translation.text},
                )
        return {"source": row.pk, "target": collision.pk, "retained_original": True}
    type(row).objects.filter(pk=row.pk).update(person=target)
    return {"source": row.pk, "target": row.pk, "retained_original": False}


@transaction.atomic
def correct_identity(
    *,
    kind,
    source_id,
    target_id,
    reviewer,
    reason,
    request_key,
    selection=None,
    account_id=None,
    apply=True,
):
    if kind not in {"merge", "split", "confirm_account"}:
        raise ValueError("Unknown identity correction")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (reviewer, reason, request_key)
    ):
        raise ValueError("Reviewer, reason and request key are required")
    selection = selection or {}
    request = {
        "kind": kind,
        "source": str(source_id),
        "target": str(target_id),
        "reviewer": reviewer,
        "reason": reason,
        "selection": selection,
        "account_id": account_id,
    }
    _lock()  # Same short lock as worker claims and paid reservations.
    existing = PersonIdentityCorrection.objects.filter(request_key=request_key).first()
    if existing:
        if existing.request != request:
            raise ValueError("Request key already describes a different correction")
        return existing
    people = {
        str(person.pk): person
        for person in Person.objects.select_for_update()
        .filter(pk__in=[source_id, target_id])
        .order_by("pk")
    }
    if str(source_id) not in people or str(target_id) not in people:
        raise ValueError("Source and target people must exist")
    source, target = people[str(source_id)], people[str(target_id)]
    if source.merged_into_id or target.merged_into_id:
        raise ValueError("Use the active person ID for a new correction")
    if kind != "confirm_account" and source.pk == target.pk:
        raise ValueError("Source and target must differ")
    if kind == "confirm_account" and source.pk != target.pk:
        raise ValueError("Account confirmation uses the same source and target person")
    people_before = snapshot(Person.objects.filter(pk__in=[source.pk, target.pk]))
    person_ids = list(people)
    if StaffCollectionWork.objects.filter(
        person_id__in=person_ids, state="running"
    ).exists():
        raise ValueError("Cannot correct identity while collection work is running")
    if kind == "confirm_account":
        account = Account.objects.get(pk=account_id)
        if (
            PersonAccount.objects.filter(account=account, resolution_status="confirmed")
            .exclude(person=target)
            .exists()
        ):
            raise ValueError(
                "Account is confirmed for another person; review a merge or split first"
            )
        changes = {
            "accounts_before": snapshot(PersonAccount.objects.filter(account=account))
        }
        if apply:
            now = timezone.now()
            PersonAccount.objects.update_or_create(
                person=target,
                account=account,
                defaults={
                    "resolution_status": "confirmed",
                    "reviewed_at": now,
                    "review_note": reviewer + ": " + reason,
                },
                create_defaults={
                    "resolution_status": "confirmed",
                    "reviewed_at": now,
                    "review_note": reviewer + ": " + reason,
                    "first_observed_at": now,
                    "last_observed_at": now,
                },
            )
    else:
        chosen = _selection(source, kind, selection)
        changes = {
            "rows_before": {
                key: snapshot(
                    model.objects.filter(pk__in=[row.pk for row in chosen[key]])
                )
                for key, model in TRANSFER_MODELS.items()
            },
            "accounts_before": snapshot(
                PersonAccount.objects.filter(
                    person=source,
                    account_id__in=[row.account_id for row in chosen["accounts"]],
                )
            ),
        }
        if apply:
            changes["name_mapping"] = _copy_names(
                source,
                target,
                chosen["names"],
                kind=kind,
                reviewer=reviewer,
                reason=reason,
            )
            changes["transfers"] = {
                key: [_transfer(row, target, kind=kind) for row in chosen[key]]
                for key in TRANSFER_MODELS
                if key != "names"
            }
            for link in chosen["accounts"]:
                _move_account(link, target)
            if kind == "merge":
                children = Person.objects.filter(merged_into=source)
                changes["redirected_ids"] = [
                    str(pk) for pk in children.values_list("pk", flat=True)
                ]
                children.update(merged_into=target)
                Person.objects.filter(pk=source.pk).update(merged_into=target)
            StaffCollectionWork.objects.filter(
                person=source, state__in=["queued", "retry_due"]
            ).update(state="needs_review", error_category="identity_corrected")
    if not apply:
        return {
            "applied": False,
            "request_key": request_key,
            "request": request,
            "changes": changes,
        }
    changes["people_before"] = people_before
    changes["people_after"] = snapshot(
        Person.objects.filter(pk__in=[source.pk, target.pk])
    )
    changes["accounts_after"] = snapshot(
        PersonAccount.objects.filter(person__in=[source, target])
    )
    result = PersonIdentityCorrection.objects.create(
        request_key=request_key,
        kind=kind,
        source=source,
        target=target,
        reviewer=reviewer,
        reason=reason,
        request=request,
        changes=changes,
    )
    from core.staff_assets.arrivals import register_person

    transaction.on_commit(lambda: register_person(target.pk))
    if kind == "split":
        transaction.on_commit(lambda: register_person(source.pk))
    return result

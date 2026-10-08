"""Resolve source identities without promoting guessed cross-source matches."""

import unicodedata
import uuid

from django.db import transaction
from django.utils import timezone

from core.models import Account, Person, PersonAccount, StaffIntake


class IdentityConflict(ValueError):
    """The source is retained, but attaching it to a person requires review."""


def canonical_person(person_id):
    seen = set()
    while person_id not in seen:
        seen.add(person_id)
        person = Person.objects.get(pk=person_id)
        if not person.merged_into_id:
            return person
        person_id = person.merged_into_id
    raise IdentityConflict("Cyclic identity redirect requires repair")


def identity_ids(person_id):
    person = canonical_person(person_id)
    # Corrections flatten redirects, so every retired ID points to its survivor.
    return [
        person.pk,
        *Person.objects.filter(merged_into=person).values_list("pk", flat=True),
    ]


def _write_lock():
    from core.staff_assets.queue import _lock

    _lock()


def normalized_handle(handle):
    return (
        unicodedata.normalize("NFKC", handle or "").strip().removeprefix("@").casefold()
    )


def person_id_for_account(account_id):
    # Preserve existing derived person IDs when the caller now has an account UUID.
    if isinstance(account_id, uuid.UUID):
        account = Account.objects.get(pk=account_id)
        account_id = account.author_id or str(account.pk)
    return uuid.uuid5(uuid.NAMESPACE_URL, f"pushinweight:account:{account_id}")


def person_id_for_handle(handle):
    handle = normalized_handle(handle)
    if not handle:
        raise ValueError("person handle must be nonblank")
    return uuid.uuid5(uuid.NAMESPACE_URL, f"pushinweight:person:x-handle:{handle}")


@transaction.atomic
def account_person(account, *, create=False, observed_at=None, display_name=None):
    """Reuse confirmed identity or this account's own provisional observation.

    A provisional account observation is repeatable. It is not permission to
    attach an independently researched biography to an unconfirmed person.
    """
    if create:
        _write_lock()
        account = Account.objects.get(pk=account.pk)
    links = list(PersonAccount.objects.filter(account=account).select_related("person"))
    confirmed = [link for link in links if link.resolution_status == "confirmed"]
    if confirmed:
        person = canonical_person(confirmed[0].person_id)
    else:
        ids = [
            person_id_for_account(account.pk),
            uuid.uuid5(uuid.NAMESPACE_URL, f"staff-library:account:{account.author_id or account.pk}"),
        ]
        resolved = [
            canonical_person(pk)
            for pk in Person.objects.filter(pk__in=ids).values_list("pk", flat=True)
        ]
        people = list({person.pk: person for person in resolved}.values())
        if len(people) > 1:
            raise IdentityConflict(
                "Conflicting account identities need reviewed correction"
            )
        person = people[0] if people else None
        if person and any(
            link.person_id == person.pk and link.resolution_status == "rejected"
            for link in links
        ):
            raise IdentityConflict(
                "Account identity was rejected; reviewed correction required"
            )
        if person is None and create:
            person, _ = Person.objects.get_or_create(
                pk=ids[0],
                defaults={
                    "display_name": display_name
                    or account.display_name
                    or account.handle
                    or str(account.pk)
                },
            )
    if person and create:
        observed = observed_at or timezone.now()
        link, _ = PersonAccount.objects.get_or_create(
            person=person,
            account=account,
            defaults={
                "resolution_status": "pending",
                "first_observed_at": observed,
                "last_observed_at": observed,
            },
        )
        if observed > link.last_observed_at:
            link.last_observed_at = observed
            link.save(update_fields=["last_observed_at"])
    return person


@transaction.atomic
def subject_person(*, handle, display_name, source_key, account=None, observed_at=None):
    """Personnel subjects use a stored account when unambiguous, otherwise a source ID."""
    _write_lock()
    handle = normalized_handle(handle)
    if account is None and handle:
        accounts = list(Account.x.filter(handle__iexact=handle)[:2])
        if len(accounts) > 1:
            raise IdentityConflict("Handle matches multiple stored accounts")
        account = accounts[0] if accounts else None
    if account:
        return account_person(
            account, create=True, observed_at=observed_at, display_name=display_name
        )
    identity = (
        person_id_for_handle(handle)
        if handle
        else uuid.uuid5(uuid.NAMESPACE_URL, "pushinweight:person:" + source_key)
    )
    person = Person.objects.get_or_create(
        pk=identity, defaults={"display_name": display_name}
    )[0]
    return canonical_person(person.pk)


@transaction.atomic
def manifest_person(record, *, create=False):
    if create:
        _write_lock()
    account_id = record.get("account_id")
    accounts = Account.x
    account = None
    if record.get("account_key"):
        account = Account.objects.filter(pk=record["account_key"]).first()
    elif account_id:
        # Legacy manifests identify X by native ID; typed UUIDs are internal keys.
        if isinstance(account_id, uuid.UUID):
            account = accounts.filter(pk=account_id).first()
        else:
            account = accounts.filter(author_id=str(account_id)).first()
    if (account_id or record.get("account_key")) and not account:
        raise ValueError(
            "Account ID is not stored; import the real account first or omit it"
        )
    existing = set(
        StaffIntake.objects.filter(
            source_key=record["source_key"], person__isnull=False
        ).values_list("person_id", flat=True)
    )
    if record.get("person_id"):
        existing.add(Person.objects.get(pk=record["person_id"]).pk)
    links = list(PersonAccount.objects.filter(account=account)) if account else []
    confirmed = {
        link.person_id for link in links if link.resolution_status == "confirmed"
    }
    existing.update(confirmed)
    existing = {canonical_person(pk).pk for pk in existing}
    if len(existing) > 1:
        raise IdentityConflict(
            "Conflicting identity links need review; no name-based merge"
        )
    if existing:
        person = Person.objects.get(pk=next(iter(existing)))
        if not confirmed and any(
            link.person_id != person.pk and link.resolution_status != "rejected"
            for link in links
        ):
            raise IdentityConflict(
                "Pending account match needs confirmation before cross-source linking"
            )
        if any(
            link.person_id == person.pk and link.resolution_status == "rejected"
            for link in links
        ):
            raise IdentityConflict("Account link is rejected")
        return person, account
    if account:
        direct = record["source_key"] in {
            "account:" + (account.author_id or str(account.pk)),
            "x-account:" + (account.author_id or str(account.pk)),
        } and record.get("eligibility") in {"db_staff", "call_a_person"}
        if not direct and (links or account_person(account) is not None):
            raise IdentityConflict(
                "Pending account match needs confirmation before cross-source linking"
            )
        return account_person(account, create=create), account
    if not create:
        return None, None
    person, _ = Person.objects.get_or_create(
        pk=uuid.uuid5(
            uuid.NAMESPACE_URL, "staff-library:source:" + record["source_key"]
        ),
        defaults={"display_name": record["display_name"]},
    )
    return canonical_person(person.pk), None

"""Resolve source identities without promoting guessed cross-source matches."""

import unicodedata
import uuid

from django.db import transaction
from django.utils import timezone

from core.models import Account, Person, PersonAccount, StaffIntake


class IdentityConflict(ValueError):
    """The source is retained, but attaching it to a person requires review."""


def normalized_handle(handle):
    return (
        unicodedata.normalize("NFKC", handle or "").strip().removeprefix("@").casefold()
    )


def person_id_for_account(account_id):
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
        account = Account.objects.select_for_update().get(pk=account.pk)
    links = list(PersonAccount.objects.filter(account=account).select_related("person"))
    confirmed = [link for link in links if link.resolution_status == "confirmed"]
    if confirmed:
        person = confirmed[0].person
    else:
        ids = [
            person_id_for_account(account.pk),
            uuid.uuid5(uuid.NAMESPACE_URL, f"staff-library:account:{account.pk}"),
        ]
        people = list(Person.objects.filter(pk__in=ids))
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
                    or account.pk
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


def subject_person(*, handle, display_name, source_key, account=None, observed_at=None):
    """Personnel subjects use a stored account when unambiguous, otherwise a source ID."""
    handle = normalized_handle(handle)
    if account is None and handle:
        accounts = list(Account.objects.filter(handle__iexact=handle)[:2])
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
    return Person.objects.get_or_create(
        pk=identity, defaults={"display_name": display_name}
    )[0]


@transaction.atomic
def manifest_person(record, *, create=False):
    account_id = record.get("account_id")
    accounts = Account.objects.select_for_update() if create else Account.objects
    account = accounts.filter(pk=account_id).first() if account_id else None
    if account_id and not account:
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
        direct = record["source_key"] == "account:" + account.pk and record.get(
            "eligibility"
        ) in {"db_staff", "call_a_person"}
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
    return person, None

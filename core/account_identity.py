"""Provider-qualified accounts. Native X IDs are compatibility data, never UUIDs."""

from django.db import transaction


def _namespace_discovery(account):
    evidence = account.provider_metadata.get("namespace_discovery_evidence", {})
    if (
        account.data_source_id == "hf"
        and isinstance(evidence, dict)
        and isinstance(evidence.get("namespace"), str)
        and evidence["namespace"].casefold() == account.normalized_identifier
    ):
        return evidence
    return {}


def publisher_identifier(account):
    """Preserve a migrated namespace's presentation while its identity matches."""
    return _namespace_discovery(account).get("namespace", account.external_identifier)


def publisher_discovery_label(account):
    """Keep namespace evidence separate from independent account provenance."""
    return _namespace_discovery(account).get(
        "discovered_via", account.provider_metadata.get("discovered_via", "curated")
    )


def normalize_account(account):
    # An explicit legacy author_id is the X adapter boundary, not a generic default.
    if not account.data_source_id and account.author_id is not None:
        account.data_source_id = "x"
    if not account.data_source_id:
        raise ValueError("account source is required")
    if account.data_source_id == "x":
        account.external_identifier = (
            account.external_identifier or account.author_id or ""
        )
        if account.author_id not in (None, account.external_identifier):
            raise ValueError("X author ID does not match provider identity")
        account.author_id = account.external_identifier
        account.identifier_kind = "provider_id"
    elif account.author_id is not None:
        raise ValueError("author_id is reserved for X")
    external = account.external_identifier.strip()
    if not external or external != account.external_identifier:
        raise ValueError("nonempty exact provider identifier required")
    account.normalized_identifier = (
        external.casefold() if account.data_source_id == "hf" else external
    )
    account.normalized_handle = account.handle.casefold() if account.handle else None


@transaction.atomic
def upsert_account(
    *,
    source,
    external_identifier,
    handle=None,
    account_kind="unknown",
    provider_metadata=None,
):
    from core.models import Account, DataSource

    if not source or not DataSource.objects.filter(pk=source).exists():
        raise ValueError("registered account source is required")
    if source not in {"x", "hf", "github"}:
        raise ValueError("account source identifier contract is not yet supported")
    if source == "github" and (
        not isinstance(external_identifier, str)
        or not external_identifier.isascii()
        or not external_identifier.isdigit()
        or str(int(external_identifier)) != external_identifier
        or int(external_identifier) <= 0
    ):
        raise ValueError("canonical positive GitHub native account ID required")
    if account_kind not in {"organization", "individual", "channel", "unknown"}:
        raise ValueError("unsupported account kind")
    identity = external_identifier.casefold() if source == "hf" else external_identifier
    account = (
        Account.objects.select_for_update()
        .filter(data_source_id=source, normalized_identifier=identity)
        .first()
    )
    if account is None:
        account = Account(
            data_source_id=source,
            external_identifier=external_identifier,
            identifier_kind="namespace" if source == "hf" else "provider_id",
        )
    account.handle = handle
    account.account_kind = account_kind
    if provider_metadata is not None:
        account.provider_metadata = provider_metadata
    account.save()
    return account

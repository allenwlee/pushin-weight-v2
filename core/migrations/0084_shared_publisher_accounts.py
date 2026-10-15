# Generated schema state plus alias-aware publisher data preservation.
import uuid
from datetime import datetime

import django.db.models.deletion
from django.db import migrations, models


def migrate_publishers(apps, schema_editor):
    alias = schema_editor.connection.alias
    Account = apps.get_model("core", "Account")
    Org = apps.get_model("core", "HFOrg")
    Link = apps.get_model("core", "CompanyAccount")
    Product = apps.get_model("core", "Product")
    Source = apps.get_model("core", "DataSource")
    Role = apps.get_model("core", "Role")
    if not Org.objects.using(alias).exists():
        return
    Source.objects.using(alias).get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    Role.objects.using(alias).get_or_create(pk="official")
    for org in Org.objects.using(alias).select_for_update().iterator():
        normalized = org.namespace.casefold()
        account = (
            Account.objects.using(alias)
            .filter(data_source_id="hf", normalized_identifier=normalized)
            .first()
        )
        if org.account_id:
            linked = Account.objects.using(alias).get(pk=org.account_id)
            if (
                linked.data_source_id != "hf"
                or linked.normalized_identifier != normalized
                or (account and account.pk != linked.pk)
            ):
                raise RuntimeError("HF namespace account identity conflict")
            account = linked
        if account is None:
            account = Account.objects.using(alias).create(
                account_key=uuid.uuid4(),
                data_source_id="hf",
                external_identifier=org.namespace,
                normalized_identifier=normalized,
                identifier_kind="namespace",
                handle=org.namespace,
                normalized_handle=normalized,
                account_kind="unknown",
            )
            Account.objects.using(alias).filter(pk=account.pk).update(
                first_seen_at=org.added_at, last_seen_at=org.added_at
            )
        if (
            Link.objects.using(alias)
            .filter(account_id=account.pk)
            .exclude(company_id=org.company_id)
            .exists()
        ):
            raise RuntimeError("HF namespace company ownership conflict")
        metadata = dict(account.provider_metadata)
        metadata.setdefault("discovered_via", org.discovered_via)
        metadata.setdefault("legacy_added_at", org.added_at.isoformat())
        evidence = {
            "namespace": org.namespace,
            "previous_account_key": str(org.account_id) if org.account_id else None,
            "discovered_via": org.discovered_via,
            "added_at": org.added_at.isoformat(),
        }
        if (
            "namespace_discovery_evidence" in metadata
            and metadata["namespace_discovery_evidence"] != evidence
        ):
            raise RuntimeError("HF discovery provenance conflict")
        metadata["namespace_discovery_evidence"] = evidence
        Account.objects.using(alias).filter(pk=account.pk).update(
            provider_metadata=metadata
        )
        link, created = Link.objects.using(alias).get_or_create(
            account_id=account.pk,
            company_id=org.company_id,
            defaults={"role_id": "official", "ownership_confirmed": org.confirmed},
        )
        Link.objects.using(alias).filter(
            account_id=account.pk, company_id=org.company_id
        ).update(
            ownership_confirmed=org.confirmed,
            **({"added_at": org.added_at} if created else {}),
        )
        Product.objects.using(alias).filter(hf_org_id=org.namespace).update(
            publisher_account_id=account.pk
        )


def restore_publishers(apps, schema_editor):
    alias = schema_editor.connection.alias
    Org = apps.get_model("core", "HFOrg")
    Link = apps.get_model("core", "CompanyAccount")
    Product = apps.get_model("core", "Product")
    if (
        Product.objects.using(alias)
        .filter(publisher_account__isnull=False)
        .exclude(publisher_account__data_source_id="hf")
        .exists()
    ):
        raise RuntimeError(
            "Non-HF product publishers cannot be preserved in the old HF schema"
        )
    seen = set()
    for link in (
        Link.objects.using(alias)
        .filter(account__data_source_id="hf")
        .select_related("account")
        .iterator()
    ):
        if link.account_id in seen or link.ownership_confirmed is None:
            raise RuntimeError(
                "Ambiguous or unknown publisher ownership cannot be reversed"
            )
        seen.add(link.account_id)
        account = link.account
        evidence = account.provider_metadata.get("namespace_discovery_evidence", {})
        namespace = evidence.get("namespace", account.external_identifier)
        if account.normalized_identifier != namespace.casefold():
            raise RuntimeError(
                "Changed publisher identity cannot be reversed into its prior namespace"
            )
        added_at = (
            datetime.fromisoformat(evidence["added_at"])
            if evidence.get("added_at")
            else link.added_at
        )
        Org.objects.using(alias).create(
            namespace=namespace,
            account_id=evidence.get("previous_account_key", account.pk),
            company_id=link.company_id,
            confirmed=link.ownership_confirmed,
            discovered_via=evidence.get(
                "discovered_via",
                account.provider_metadata.get("discovered_via", "curated"),
            ),
        )
        Org.objects.using(alias).filter(pk=namespace).update(added_at=added_at)
        Product.objects.using(alias).filter(publisher_account_id=account.pk).update(
            hf_org_id=namespace
        )
    if (
        Product.objects.using(alias)
        .filter(publisher_account__isnull=False, hf_org__isnull=True)
        .exists()
    ):
        raise RuntimeError("Product publisher lacks reconstructable ownership")


class Migration(migrations.Migration):
    dependencies = [("core", "0083_account_extensions")]
    operations = [
        migrations.AddField(
            model_name="companyaccount",
            name="ownership_confirmed",
            field=models.BooleanField(default=None, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="publisher_account",
            field=models.ForeignKey(
                blank=True,
                db_column="publisher_account_key",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="core.account",
            ),
        ),
        migrations.RunPython(migrate_publishers, restore_publishers),
        migrations.RemoveIndex(
            model_name="product",
            name="idx_products_hf_org_id",
        ),
        migrations.RemoveField(
            model_name="product",
            name="hf_org",
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["publisher_account"], name="idx_products_publisher_account"
            ),
        ),
        migrations.DeleteModel(
            name="HFOrg",
        ),
    ]

"""Add durable User About coordination and install the separate Muse catalog."""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

MUSE_TERMS = ("Meta Muse", "Muse Spark", "Muse Glimmer", "Muse Realtime")
CONFIRMED_MODELS = ("Muse Spark", "Muse Glimmer")


def install_muse_catalog(apps, schema_editor):
    Brand = apps.get_model("core", "Brand")
    Company = apps.get_model("core", "Company")
    BrandCompany = apps.get_model("core", "BrandCompany")
    BrandKeyword = apps.get_model("core", "BrandKeyword")
    BrandSearchTerm = apps.get_model("core", "BrandSearchTerm")
    Product = apps.get_model("core", "Product")

    muse, _ = Brand.objects.get_or_create(
        nickname="muse",
        defaults={
            "display_name": "Meta Muse",
            "display_name_en": "Meta Muse",
            "is_sentinel": False,
        },
    )
    meta, _ = Company.objects.get_or_create(
        nickname="meta",
        defaults={
            "display_name": "Meta Platforms Inc.",
            "display_name_en": "Meta Platforms Inc.",
            "hq_country": "US",
        },
    )
    if BrandCompany.objects.filter(brand=muse).exclude(company=meta).exists():
        raise RuntimeError("Muse already has a conflicting company link")
    BrandCompany.objects.get_or_create(
        brand=muse, company=meta, defaults={"ownership_pct": 1.0}
    )

    for term in MUSE_TERMS:
        BrandKeyword.objects.get_or_create(
            brand=muse,
            pattern=term,
            defaults={"is_regex": False, "is_primary": False},
        )
        BrandSearchTerm.objects.get_or_create(brand=muse, term=term)
    # Production previously assigned this exact phrase to Llama. Move only
    # the false-owner keyword; do not rewrite historical post attributions.
    BrandKeyword.objects.filter(
        brand_id="llama", pattern__in=("Muse Spark", '"Muse Spark"')
    ).delete()

    for name in CONFIRMED_MODELS:
        if not Product.objects.filter(brand=muse, display_name=name).exists():
            Product.objects.create(
                brand=muse,
                display_name=name,
                type="llm-model",
            )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0058_postenrichmentstate_translation_diagnostics"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountUserAboutActivation",
            fields=[
                (
                    "key",
                    models.PositiveSmallIntegerField(
                        default=1, primary_key=True, serialize=False
                    ),
                ),
                (
                    "activated_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
            ],
            options={"db_table": "account_user_about_activation"},
        ),
        migrations.CreateModel(
            name="AccountUserAboutClaim",
            fields=[
                (
                    "account",
                    models.OneToOneField(
                        db_column="author_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="user_about_claim",
                        serialize=False,
                        to="core.account",
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("retry_due", "Retry due"),
                            ("uncertain", "Uncertain"),
                            ("quarantined", "Quarantined"),
                            ("fetched", "Fetched"),
                        ],
                        max_length=16,
                    ),
                ),
                ("owner", models.CharField(blank=True, default="", max_length=128)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("next_eligible_at", models.DateTimeField(blank=True, null=True)),
                ("admissions", models.PositiveIntegerField(default=0)),
                (
                    "last_reason",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "account_user_about_claims"},
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(
                fields=["author", "fetched_at"], name="idx_posts_author_fetch"
            ),
        ),
        migrations.AddConstraint(
            model_name="accountuseraboutactivation",
            constraint=models.CheckConstraint(
                condition=models.Q(("key", 1)), name="ck_aua_singleton"
            ),
        ),
        migrations.AddIndex(
            model_name="accountuseraboutclaim",
            index=models.Index(
                fields=["state", "next_eligible_at"], name="idx_aua_claim_due"
            ),
        ),
        migrations.RunPython(install_muse_catalog, migrations.RunPython.noop),
    ]

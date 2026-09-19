from django.db import migrations


ORGANIZATIONS = (
    {
        "brand": "anthropic",
        "brand_display": "Anthropic",
        "company": "anthropic",
        "company_display": "Anthropic",
        "hq_country": "US",
    },
    {
        "brand": "google_deepmind",
        "brand_display": "Google DeepMind",
        "company": "google",
        "company_display": "Google",
        "hq_country": "US",
    },
)


def seed_organization_brands(apps, schema_editor):
    Brand = apps.get_model("core", "Brand")
    Company = apps.get_model("core", "Company")
    BrandCompany = apps.get_model("core", "BrandCompany")
    for item in ORGANIZATIONS:
        brand, _ = Brand.objects.get_or_create(
            nickname=item["brand"],
            defaults={
                "display_name": item["brand_display"],
                "display_name_en": item["brand_display"],
                "is_sentinel": False,
            },
        )
        company, _ = Company.objects.get_or_create(
            nickname=item["company"],
            defaults={
                "display_name": item["company_display"],
                "display_name_en": item["company_display"],
                "hq_country": item["hq_country"],
            },
        )
        BrandCompany.objects.get_or_create(
            brand=brand,
            company=company,
            defaults={"ownership_pct": 1.0},
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0032_stage1c_people_jobs_events")]

    operations = [
        migrations.RunPython(seed_organization_brands, migrations.RunPython.noop)
    ]

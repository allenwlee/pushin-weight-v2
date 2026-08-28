from django.db import migrations


def refuse_destructive_per_brand_reverse(apps, schema_editor):
    """Require application rollback while any durable per-brand state exists."""
    model_names = (
        "TrendNarrativeRun",
        "TrendNarrativeProviderCall",
        "BrandTrendNarrative",
        "TrendNarrativeVisibleRun",
        "TrendNarrativeWorkSlot",
    )
    if any(apps.get_model("core", name).objects.exists() for name in model_names):
        raise RuntimeError(
            "cannot reverse per-brand trend narratives while durable rows exist; "
            "use publication_source=legacy_only for application rollback"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_trend_narrative_work_slots"),
    ]

    operations = [
        migrations.RunPython(
            migrations.RunPython.noop,
            refuse_destructive_per_brand_reverse,
        ),
    ]

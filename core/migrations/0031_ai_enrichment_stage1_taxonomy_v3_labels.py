from django.db import migrations


POST_TYPES = {
    "events": ("Events", "活动", "イベント"),
    "opportunities": ("Opportunities", "机会", "機会"),
    "job_listings": ("Job Listings", "招聘信息", "求人情報"),
    "personnel_changes": ("Personnel Changes", "人事变动", "人事異動"),
}
LOCALES = ("en", "zh-cn", "ja")


def seed_taxonomy_v3_labels(apps, schema_editor):
    PostTypeKey = apps.get_model("core", "PostTypeKey")
    PostTypeLabel = apps.get_model("core", "PostTypeLabel")
    database = schema_editor.connection.alias

    for key, labels in POST_TYPES.items():
        PostTypeKey.objects.using(database).get_or_create(key=key)
        for lang, label in zip(LOCALES, labels, strict=True):
            PostTypeLabel.objects.using(database).update_or_create(
                post_type_id=key,
                lang=lang,
                defaults={"label": label},
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0030_ai_enrichment_stage1_taxonomy_v2_edges")]

    operations = [
        migrations.RunPython(seed_taxonomy_v3_labels, migrations.RunPython.noop),
    ]

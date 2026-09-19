from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0041_event_canonical_url_event_external_event_id_and_more")]

    operations = [
        migrations.AlterField(
            model_name="postbrandclassificationjudgment",
            name="stage",
            field=models.CharField(choices=[("primary", "Primary"), ("review", "Review"), ("content", "Content"), ("brand_interpretation", "Brand interpretation"), ("final", "Final")], max_length=32),
        ),
        migrations.AddField(
            model_name="postbrandclassificationjudgment",
            name="content_judgment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="content_finals", to="core.postbrandclassificationjudgment"),
        ),
        migrations.AddField(
            model_name="postbrandclassificationjudgment",
            name="brand_interpretation_judgment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="brand_interpretation_finals", to="core.postbrandclassificationjudgment"),
        ),
        migrations.RemoveConstraint(
            model_name="postbrandclassificationjudgment",
            name="ck_pb_cls_judgment_parent",
        ),
        migrations.AddConstraint(
            model_name="postbrandclassificationjudgment",
            constraint=models.CheckConstraint(
                name="ck_pb_cls_judgment_parent",
                condition=models.Q(models.Q(
                    models.Q(brand_interpretation_judgment__isnull=True, content_judgment__isnull=True, parent_judgment__isnull=True, stage="primary"),
                    models.Q(brand_interpretation_judgment__isnull=True, content_judgment__isnull=True, parent_judgment__isnull=False, stage="review"),
                    models.Q(brand_interpretation_judgment__isnull=True, content_judgment__isnull=True, parent_judgment__isnull=True, stage__in=["content", "brand_interpretation"]),
                    models.Q(brand_interpretation_judgment__isnull=True, content_judgment__isnull=True, parent_judgment__isnull=False, stage="final"),
                    models.Q(brand_interpretation_judgment__isnull=False, content_judgment__isnull=False, parent_judgment__isnull=True, stage="final"),
                    _connector="OR",
                )),
            ),
        ),
    ]

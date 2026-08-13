import django.db.models.deletion
from django.db import migrations, models

# Django migrations intentionally declare mutable operation lists as class data.
# ruff: noqa: RUF012


def backfill_canonical_narrative_fields(apps, schema_editor):
    TrendNarrative = apps.get_model("core", "TrendNarrative")
    TrendNarrativeSubject = apps.get_model("core", "TrendNarrativeSubject")

    for narrative in TrendNarrative.objects.all().iterator(chunk_size=500):
        updates = {}
        if narrative.body_zh_cn is None:
            updates["body_zh_cn"] = narrative.body_zh_hans
        if narrative.llm_model_name is None:
            updates["llm_model_name"] = narrative.model_name
        if updates:
            TrendNarrative.objects.filter(pk=narrative.pk).update(**updates)

        legacy_subjects = (
            (
                0,
                narrative.primary_brand_id,
                narrative.primary_brand_key,
                narrative.primary_brand_name_en,
                narrative.primary_brand_name_zh_hans,
            ),
            (
                1,
                narrative.secondary_brand_id,
                narrative.secondary_brand_key,
                narrative.secondary_brand_name_en,
                narrative.secondary_brand_name_zh_hans,
            ),
        )
        seen_keys = set()
        for position, brand_id, key, name_en, name_zh_cn in legacy_subjects:
            if not key or not name_en or not name_zh_cn or key in seen_keys:
                continue
            seen_keys.add(key)
            TrendNarrativeSubject.objects.get_or_create(
                trend_narrative_id=narrative.pk,
                position=position,
                defaults={
                    "support_type": "measured_candidate",
                    "entity_type": "brand",
                    "identity_type": "brand",
                    "brand_id": brand_id,
                    "canonical_key_snapshot": key,
                    "name_en_snapshot": name_en,
                    "name_zh_cn_snapshot": name_zh_cn,
                    "candidate_id": f"{key}:legacy",
                    "evidence_ids": [],
                },
            )


def reverse_guard(apps, schema_editor):
    TrendNarrative = apps.get_model("core", "TrendNarrative")
    TrendNarrativeSubject = apps.get_model("core", "TrendNarrativeSubject")

    expansion_only_parent = (
        TrendNarrative.objects.exclude(output_schema_version=1).exists()
        or TrendNarrative.objects.exclude(observations_en=[]).exists()
        or TrendNarrative.objects.exclude(observations_zh_cn=[]).exists()
        or TrendNarrative.objects.exclude(selected_candidate_ids=[]).exists()
        or TrendNarrative.objects.exclude(claims=[]).exists()
        or TrendNarrative.objects.exclude(consecutive_failures=0).exists()
        or TrendNarrative.objects.filter(body_zh_cn__isnull=False)
        .exclude(body_zh_cn=models.F("body_zh_hans"))
        .exists()
        or TrendNarrative.objects.filter(llm_model_name__isnull=False)
        .exclude(llm_model_name=models.F("model_name"))
        .exists()
    )
    if expansion_only_parent:
        raise RuntimeError(
            "cannot reverse trend narrative expansion with canonical-only data"
        )

    if TrendNarrativeSubject.objects.exists():
        raise RuntimeError(
            "cannot reverse trend narrative expansion with normalized subjects"
        )


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ("core", "0013_trend_narrative_version"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="TrendNarrativeVersion",
            new_name="TrendNarrative",
        ),
        migrations.AlterModelTable(
            name="trendnarrative",
            table="trend_narratives",
        ),
        migrations.AddField(
            model_name="trendnarrative",
            name="output_schema_version",
            field=models.PositiveSmallIntegerField(db_default=1, default=1),
        ),
        migrations.AddField(
            model_name="trendnarrative",
            name="observations_en",
            field=models.JSONField(blank=True, db_default=[], default=list),
        ),
        migrations.AddField(
            model_name="trendnarrative",
            name="observations_zh_cn",
            field=models.JSONField(blank=True, db_default=[], default=list),
        ),
        migrations.AddField(
            model_name="trendnarrative",
            name="selected_candidate_ids",
            field=models.JSONField(blank=True, db_default=[], default=list),
        ),
        migrations.AddField(
            model_name="trendnarrative",
            name="claims",
            field=models.JSONField(blank=True, db_default=[], default=list),
        ),
        migrations.AddField(
            model_name="trendnarrative",
            name="body_zh_cn",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trendnarrative",
            name="llm_model_name",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="trendnarrative",
            name="consecutive_failures",
            field=models.PositiveIntegerField(db_default=0, default=0),
        ),
        migrations.CreateModel(
            name="TrendNarrativeSubject",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "position",
                    models.PositiveSmallIntegerField(
                        choices=[(0, "Primary"), (1, "Secondary")]
                    ),
                ),
                (
                    "support_type",
                    models.CharField(
                        choices=[
                            ("measured_candidate", "Measured candidate"),
                            ("evidence_only", "Evidence only"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("company", "Company"),
                            ("brand", "Brand"),
                            ("product", "Product"),
                            ("model", "Model"),
                            ("organization", "Organization"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "identity_type",
                    models.CharField(
                        choices=[
                            ("brand", "Brand"),
                            ("product", "Product"),
                            ("unresolved", "Unresolved"),
                        ],
                        max_length=16,
                    ),
                ),
                ("observed_name", models.TextField(blank=True, default="")),
                (
                    "canonical_key_snapshot",
                    models.TextField(blank=True, default=""),
                ),
                ("name_en_snapshot", models.TextField(blank=True, default="")),
                (
                    "name_zh_cn_snapshot",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "candidate_id",
                    models.CharField(blank=True, default="", max_length=192),
                ),
                ("evidence_ids", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "brand",
                    models.ForeignKey(
                        blank=True,
                        db_column="brand_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="core.brand",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        db_column="product_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="core.product",
                    ),
                ),
                (
                    "trend_narrative",
                    models.ForeignKey(
                        db_column="trend_narrative_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subjects",
                        to="core.trendnarrative",
                    ),
                ),
            ],
            options={
                "db_table": "trend_narrative_subjects",
                "ordering": ["position", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="trendnarrativesubject",
            constraint=models.UniqueConstraint(
                fields=("trend_narrative", "position"),
                name="uq_tns_narrative_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="trendnarrativesubject",
            constraint=models.CheckConstraint(
                condition=models.Q(("position__in", [0, 1])),
                name="ck_tns_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="trendnarrativesubject",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "entity_type__in",
                        ["company", "brand", "product", "model", "organization"],
                    )
                ),
                name="ck_tns_entity_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="trendnarrativesubject",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("canonical_key_snapshot__gt", ""),
                        ("identity_type", "brand"),
                        ("name_en_snapshot__gt", ""),
                        ("name_zh_cn_snapshot__gt", ""),
                        ("observed_name", ""),
                        ("product__isnull", True),
                    ),
                    models.Q(
                        ("brand__isnull", True),
                        ("canonical_key_snapshot__gt", ""),
                        ("identity_type", "product"),
                        ("name_en_snapshot__gt", ""),
                        ("name_zh_cn_snapshot__gt", ""),
                        ("observed_name", ""),
                    ),
                    models.Q(
                        ("brand__isnull", True),
                        ("canonical_key_snapshot", ""),
                        ("identity_type", "unresolved"),
                        ("name_en_snapshot__gt", ""),
                        ("name_zh_cn_snapshot__gt", ""),
                        ("observed_name__gt", ""),
                        ("product__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="ck_tns_identity_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="trendnarrativesubject",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("candidate_id__gt", ""),
                        ("evidence_ids", []),
                        ("support_type", "measured_candidate"),
                    ),
                    models.Q(
                        ("candidate_id", ""),
                        ("support_type", "evidence_only"),
                        models.Q(("evidence_ids", []), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="ck_tns_support_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="trendnarrativesubject",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("support_type", "measured_candidate"),
                    ("position", 1),
                    _connector="OR",
                ),
                name="ck_tns_evidence_pos",
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE VIEW trend_narrative_versions AS "
                "SELECT * FROM trend_narratives"
            ),
            reverse_sql="DROP VIEW trend_narrative_versions",
        ),
        migrations.RunPython(backfill_canonical_narrative_fields, reverse_guard),
    ]

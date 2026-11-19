"""Allow truthful personalized-trend provenance without blocking active writers."""

from typing import ClassVar

from django.db import migrations, models, transaction

LEGACY_KINDS = ("semantic_shortlist", "memory_only", "keyword_only", "release")


def replace_constraint(schema_editor, kinds):
    def execute(*statements):
        with transaction.atomic(using=schema_editor.connection.alias):
            schema_editor.execute("SET LOCAL lock_timeout = '5s'")
            for statement in statements:
                schema_editor.execute(statement)

    # The original guard remains enforced until its replacement is validated.
    # Restarting after interrupted validation can safely replace our temporary guard.
    allowed = ", ".join(f"'{kind}'" for kind in kinds)
    execute(
        'ALTER TABLE "original_content" DROP CONSTRAINT IF EXISTS "ck_oc_appearance_kind_next"',
        'ALTER TABLE "original_content" ADD CONSTRAINT "ck_oc_appearance_kind_next" '
        f'CHECK ("appearance_kind" IS NULL OR "appearance_kind" IN ({allowed})) NOT VALID',
    )
    try:
        # This scan holds a writer-compatible lock in its own transaction.
        execute(
            'ALTER TABLE "original_content" VALIDATE CONSTRAINT "ck_oc_appearance_kind_next"'
        )
        execute(
            'ALTER TABLE "original_content" DROP CONSTRAINT "ck_oc_appearance_kind"',
            'ALTER TABLE "original_content" RENAME CONSTRAINT '
            '"ck_oc_appearance_kind_next" TO "ck_oc_appearance_kind"',
        )
    except Exception:
        # A narrowing rollback with personalized rows must leave the wider guard
        # and every saved value intact, rather than partially reverting provenance.
        execute(
            'ALTER TABLE "original_content" DROP CONSTRAINT IF EXISTS "ck_oc_appearance_kind_next"'
        )
        raise


def forwards(apps, schema_editor):
    replace_constraint(schema_editor, (*LEGACY_KINDS, "personalized_trend"))


def backwards(apps, schema_editor):
    replace_constraint(schema_editor, LEGACY_KINDS)


class Migration(migrations.Migration):
    atomic = False

    dependencies: ClassVar[list] = [
        ("core", "0228_merge_staging_chatter_translation"),
    ]

    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, backwards, atomic=False)
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="originalcontent",
                    name="ck_oc_appearance_kind",
                ),
                migrations.AlterField(
                    model_name="originalcontent",
                    name="appearance_kind",
                    field=models.CharField(
                        blank=True,
                        choices=[
                            ("semantic_shortlist", "semantic_shortlist"),
                            ("memory_only", "memory_only"),
                            ("keyword_only", "keyword_only"),
                            ("release", "release"),
                            ("personalized_trend", "personalized_trend"),
                        ],
                        max_length=24,
                        null=True,
                    ),
                ),
                migrations.AddConstraint(
                    model_name="originalcontent",
                    constraint=models.CheckConstraint(
                        condition=models.Q(
                            ("appearance_kind__isnull", True),
                            (
                                "appearance_kind__in",
                                [
                                    "semantic_shortlist",
                                    "memory_only",
                                    "keyword_only",
                                    "release",
                                    "personalized_trend",
                                ],
                            ),
                            _connector="OR",
                        ),
                        name="ck_oc_appearance_kind",
                    ),
                ),
            ],
        )
    ]

# Django migration declarations intentionally use class-level lists.
# ruff: noqa: RUF012
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0197_enrichment_budget_window")]

    operations = [
        migrations.RemoveConstraint(
            model_name="enrichmentbudgetwindow", name="uq_enrich_budget_start",
        ),
        migrations.RemoveConstraint(
            model_name="enrichmentbudgetwindow", name="ck_enrich_budget_scope",
        ),
        migrations.RenameField(
            model_name="enrichmentbudgetwindow",
            old_name="scope", new_name="enrichment_window_kind",
        ),
        migrations.AddConstraint(
            model_name="enrichmentbudgetwindow",
            constraint=models.UniqueConstraint(
                fields=("enrichment_window_kind", "starts_at"), name="uq_enrich_budget_start",
            ),
        ),
        migrations.AddConstraint(
            model_name="enrichmentbudgetwindow",
            constraint=models.CheckConstraint(
                condition=models.Q(enrichment_window_kind__in=["pilot", "scheduled"]),
                name="ck_enrich_budget_window_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="enrichmentbudgetwindow",
            constraint=models.CheckConstraint(
                condition=models.Q(config_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="ck_enrich_budget_fingerprint",
            ),
        ),
    ]

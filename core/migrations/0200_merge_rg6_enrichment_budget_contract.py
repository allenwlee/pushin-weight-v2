"""Merge the RG6 detachment and enrichment budget contract branches."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0198_merge_enrichment_rg6"),
        ("core", "0199_enrichment_budget_contract"),
    ]

    operations = []

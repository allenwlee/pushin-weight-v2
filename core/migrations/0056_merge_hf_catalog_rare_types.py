"""Join the HF catalog and rare-type migration branches."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0045_hf_catalog_observations"),
        ("core", "0055_relax_rare_type_decision_response_id"),
    ]

    operations = []

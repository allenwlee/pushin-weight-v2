import io
import json

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_upgrade_preserves_source_versions_and_normalization_is_repeatable():
    before = [("core", "0063_reviewed_affiliation_replacement")]
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        from django.utils import timezone
        person = apps.get_model("core", "Person").objects.create(display_name="Staff")
        brand = apps.get_model("core", "Brand").objects.create(nickname="deepseek", display_name="DeepSeek")
        role = apps.get_model("core", "PersonBrandAffiliation").objects.create(person=person, brand=brand,
            affiliation_type="employment", observed_organization_name="DeepSeek", status="current",
            title_raw="研究员", claim_identity="migration-role")
        payload = {"source_dossier": {"deepseek": {"source": "https://example.com"}, "presentation": {"fields": {
            "job_title_zh": {"value": "研究员", "original": "研究员", "source": "https://example.com", "status": "Verified official bio"},
            "job_title_en": {"value": "Researcher", "source": "https://example.com", "status": "Translated"}}}}}
        intake = apps.get_model("core", "StaffIntake").objects.create(person=person, source_key="migration",
            fingerprint="original", payload=payload, observed_at=timezone.now(), eligibility="staff")
        prose = apps.get_model("core", "PersonText").objects.create(person=person, kind="role", language="zh-Hans",
            text="研究工作", source_reference="https://example.com", version_hash="original", observed_at=timezone.now())
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        from core.models import PersonText, StaffIntake
        assert StaffIntake.objects.get(pk=intake.pk).payload == payload
        assert PersonText.objects.get(pk=prose.pk).text == "研究工作"
        output = io.StringIO()
        call_command("normalize_staff_dossier_fields", stdout=output)
        assert not json.loads(output.getvalue())["applied"]
        assert PersonText.objects.count() == 1
        call_command("normalize_staff_dossier_fields", apply=True, stdout=io.StringIO())
        call_command("normalize_staff_dossier_fields", apply=True, stdout=io.StringIO())
        titles = PersonText.objects.filter(affiliation_id=role.pk)
        assert titles.count() == 2
        assert titles.get(language="en").derived_from_id == titles.get(language="zh-Hans").pk
        assert StaffIntake.objects.get(pk=intake.pk).payload == payload
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

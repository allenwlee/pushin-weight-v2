"""RG2 locale rows retain current values without discarding older names."""

import hashlib
import json
import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.django_db(transaction=True),
]

BASE = ("core", "0128_require_correction_actor")
EXPAND = ("core", "0130_rg2_person_name_locale_required")
REMOVE = ("core", "0131_rg2_remove_legacy_locale_columns")


@pytest.mark.usefixtures("migration_rehearsal_schema")
def test_rg2_company_and_person_values_move_to_locale_owners():
    executor = MigrationExecutor(connection)
    final = executor.loader.graph.leaf_nodes()
    executor.migrate([BASE])
    apps = MigrationExecutor(connection).loader.project_state([BASE]).apps

    company = apps.get_model("core", "Company").objects.create(
        nickname="rg2-company",
        display_name="Example Company",
        display_name_en="Example Co.",
        display_name_zh_cn="示例公司",
    )
    person_model = apps.get_model("core", "Person")
    person = person_model.objects.create(
        display_name="Current Name",
        display_name_en="Current English Name",
        display_name_zh_cn="当前姓名",
    )
    old_name = "Previous Name"
    old_fingerprint = hashlib.sha256(
        json.dumps(["display_name", old_name], ensure_ascii=False).encode()
    ).hexdigest()
    name = apps.get_model("core", "PersonName").objects.create(
        person=person,
        full_name=old_name,
        language="und",
        origin="legacy",
        fingerprint=old_fingerprint,
    )
    apps.get_model("core", "PersonNameEvidence").objects.create(
        name=name,
        source_kind="legacy_unknown",
        source_reference=f"people:{person.pk}:display_name",
        source_text=old_name,
        supports_fields=["full_name"],
        observed_at=timezone.now(),
        collection_method="migration",
        evidence_hash=old_fingerprint,
    )
    account = apps.get_model("core", "Account").objects.create(
        author_id="rg2-account",
        bio_en="English profile translation",
        bio_zh_cn="中文个人简介翻译",
    )

    from tests.test_trend_narrative_lifecycle import _reserve

    now = timezone.now()
    run = apps.get_model("core", "OriginalContentRun").objects.create(
        source_cycle_id="rg2-original-content",
        workflow_key="editorial-dispatch",
        scope_key="rg2-original-content",
        facts_as_of=now,
        window_days=None,
        packet_schema_version=1,
        snapshot={},
    )
    content = apps.get_model("core", "OriginalContent").objects.create(
        run=run,
        workflow_key="social-brief",
        output_key="rg2-content",
        subject_key="rg2-content",
        story_id=uuid.uuid4(),
        status="prepared",
        attempted_at=now,
        brand_key_snapshot="",
        brand_name_en_snapshot="",
        brand_name_zh_cn_snapshot="",
    )
    content_text = apps.get_model("core", "OriginalContentText").objects.create(
        narrative=content,
        locale="en",
        headline="RG2 content",
        secondary="Migration test",
        body="Saved context.",
    )
    apps.get_model("core", "OriginalContent").objects.filter(
        pk=content_text.narrative_id
    ).update(
        brand_name_en_snapshot="Frozen English company label",
        brand_name_zh_cn_snapshot="冻结的中文公司标签",
    )
    narrative = _reserve(source_cycle_id="rg2-locale-migration")
    subject = apps.get_model("core", "TrendNarrativeSubject").objects.create(
        trend_narrative_id=narrative.pk,
        position=0,
        support_type="measured_candidate",
        entity_type="brand",
        identity_type="brand",
        brand_id="minimax",
        observed_name="",
        canonical_key_snapshot="minimax",
        name_en_snapshot="Minimax",
        name_zh_cn_snapshot="中minimax",
        candidate_id="brand:minimax",
        evidence_ids=[],
    )

    try:
        MigrationExecutor(connection).migrate([EXPAND])
        migrated = MigrationExecutor(connection).loader.project_state([EXPAND]).apps
        labels = migrated.get_model("core", "CompanyLabel")
        assert dict(
            labels.objects.filter(company_id=company.pk).values_list(
                "locale_id", "label"
            )
        ) == {
            "und": "Example Company",
            "en": "Example Co.",
            "zh-Hans": "示例公司",
        }

        Selection = migrated.get_model("core", "PersonNameSelection")
        selections = {
            row.display_locale_id: row.name
            for row in Selection.objects.filter(person_id=person.pk).select_related(
                "name"
            )
        }
        assert {locale: row.full_name for locale, row in selections.items()} == {
            "und": "Current Name",
            "en": "Current English Name",
            "zh-Hans": "当前姓名",
        }
        assert {locale: row.locale_id for locale, row in selections.items()} == {
            "und": "und",
            "en": "en",
            "zh-Hans": "zh-Hans",
        }
        assert selections["und"].review_status == "pending"
        assert migrated.get_model("core", "PersonName").objects.filter(
            pk=name.pk, full_name=old_name
        ).exists()
        assert migrated.get_model("core", "PersonNameEvidence").objects.filter(
            name_id=selections["und"].pk,
            source_kind="legacy_unknown",
            source_text="Current Name",
        ).exists()
        migrated_translations = migrated.get_model(
            "core", "AccountProfileTextTranslation"
        )
        assert dict(
            migrated_translations.objects.filter(account_id=account.pk).values_list(
                "locale_id", "text"
            )
        ) == {
            "en": "English profile translation",
            "zh-Hans": "中文个人简介翻译",
        }
        assert migrated_translations.objects.filter(
            account_id=account.pk, source_text_role="legacy_unknown"
        ).count() == 2
        assert dict(
            migrated.get_model("core", "OriginalContentSubjectLabel")
            .objects.filter(content_id=content_text.narrative_id)
            .values_list("locale_id", "label_snapshot")
        ) == {
            "en": "Frozen English company label",
            "zh-Hans": "冻结的中文公司标签",
        }
        assert dict(
            migrated.get_model("core", "TrendNarrativeSubjectLabel")
            .objects.filter(subject_id=subject.pk)
            .values_list("locale_id", "label_snapshot")
        ) == {"en": "Minimax", "zh-Hans": "中minimax"}
        retired_fields = {
            "Company": {"display_name", "display_name_en", "display_name_zh_cn"},
            "Person": {"display_name", "display_name_en", "display_name_zh_cn", "display_name_ja"},
            "Account": {"bio_en", "bio_zh_cn"},
            "OriginalContent": {"brand_name_en_snapshot", "brand_name_zh_cn_snapshot"},
            "TrendNarrativeSubject": {"name_en_snapshot", "name_zh_cn_snapshot"},
            "PersonName": {"language"},
        }
        for model_name, fields in retired_fields.items():
            model = migrated.get_model("core", model_name)
            assert fields.isdisjoint({field.name for field in model._meta.fields})

        # Cutover removes ORM fields while the previous application can still
        # use their physical columns during the rolling deployment.
        with connection.cursor() as cursor:
            cursor.execute("SELECT display_name FROM companies WHERE nickname=%s", [company.pk])
            assert cursor.fetchone() == ("Example Company",)
        apps.get_model("core", "Company").objects.filter(pk=company.pk).update(
            display_name_en="Old image update"
        )
        assert labels.objects.get(company_id=company.pk, locale_id="en").label == "Old image update"

        from tests.company_factory import company_with_label
        from tests.person_factory import person_with_name

        new_company = company_with_label("new-image-company", "New company")
        new_person = person_with_name("New person")
        with connection.cursor() as cursor:
            cursor.execute("SELECT display_name FROM companies WHERE nickname=%s", [new_company.pk])
            assert cursor.fetchone() == (None,)
            cursor.execute("SELECT display_name FROM people WHERE id=%s", [new_person.pk])
            assert cursor.fetchone() == (None,)

        MigrationExecutor(connection).migrate([REMOVE])
        for model_name, fields in retired_fields.items():
            table = migrated.get_model("core", model_name)._meta.db_table
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name=%s",
                    [table],
                )
                assert fields.isdisjoint({row[0] for row in cursor.fetchall()})
        assert labels.objects.get(company_id=new_company.pk, locale_id="und").label == "New company"
        assert Selection.objects.get(person_id=new_person.pk, display_locale_id="und").name.full_name == "New person"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT brand_name_en_snapshot,brand_name_zh_cn_snapshot "
                "FROM brand_trend_narratives WHERE id=%s", [content.pk]
            )
            assert cursor.fetchone() == ("Frozen English company label", "冻结的中文公司标签")
            cursor.execute("SELECT pg_get_functiondef('g1_check_person_name()'::regprocedure)")
            definition = cursor.fetchone()[0]
            assert "NEW.locale_id" in definition
            assert "NEW.language" not in definition
    finally:
        MigrationExecutor(connection).migrate(final)

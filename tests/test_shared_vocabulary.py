"""Catalogue boundaries: exact source evidence and separate app edition aliases."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_seed_command_and_resolution_preserve_source_language():
    from core.models import Language, Locale, MeasurementUnit, TimeZone
    from core.shared_vocabulary import resolve_locale, resolve_time_zone

    call_command("seed_shared_vocabulary", verbosity=0)
    assert resolve_locale("zh-cn").code == "zh-CN"
    assert resolve_locale("zh_CN", context="app_edition").code == "zh-Hans"
    assert resolve_locale("zh").code == "zh"
    assert resolve_locale("xx-mystery") is None
    assert resolve_locale("") is None
    assert resolve_time_zone("CST") is None
    assert resolve_time_zone("UTC").code == "UTC"
    assert resolve_time_zone("Asia/Tokyo").code == "Asia/Tokyo"
    assert resolve_time_zone("US/Eastern").code == "US/Eastern"
    assert Language.objects.filter(pk="und").exists()
    assert Locale.objects.get(pk="zh-Hans").language_id == "zh"
    assert MeasurementUnit.objects.filter(pk="arena_points").exists()
    assert MeasurementUnit.objects.filter(pk="hf_trending_points").exists()
    assert not TimeZone.objects.filter(pk__in=["unknown", "", "CST"]).exists()


def test_repeated_seeding_is_idempotent_and_does_not_rewrite_references():
    from core.models import Language, Locale, MeasurementUnit, TimeZone

    call_command("seed_shared_vocabulary", verbosity=0)
    models = [Language, Locale, MeasurementUnit, TimeZone]
    before = {
        model: set(model.objects.values_list("pk", flat=True)) for model in models
    }
    call_command("seed_shared_vocabulary", verbosity=0)
    assert before == {
        model: set(model.objects.values_list("pk", flat=True)) for model in models
    }


def test_locale_language_parent_is_enforced_for_bulk_and_sql_writes():
    from core.models import Language, Locale

    Language.objects.bulk_create([Language(code="en"), Language(code="ja")], ignore_conflicts=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        Locale.objects.bulk_create([Locale(code="en-US", language_id="ja")])
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("INSERT INTO locales(code,language_id) VALUES ('ja-JP','en')")
    with pytest.raises(IntegrityError), transaction.atomic():
        Locale.objects.create(code="zz-ZZ", language_id="zz")
        connection.check_constraints(table_names=["locales"])


def test_language_deletion_is_protected_and_codes_are_unique():
    from core.models import Language, Locale

    language, _ = Language.objects.get_or_create(code="ja")
    Locale.objects.get_or_create(code="ja", defaults={"language": language})
    with pytest.raises(ProtectedError):
        language.delete()
    with pytest.raises(IntegrityError), transaction.atomic():
        Language.objects.create(code="ja")


def test_invalid_catalogue_code_grammar_rejected_by_database():
    from core.models import Language, MeasurementUnit, TimeZone

    for model, code in [
        (Language, "EN"),
        (Language, ""),
        (MeasurementUnit, "two units"),
        (TimeZone, " UTC"),
    ]:
        with pytest.raises(IntegrityError), transaction.atomic():
            model.objects.bulk_create([model(code=code)])


def test_seed_rejects_tampered_input_before_any_catalogue_write(tmp_path, monkeypatch):
    import shutil

    import core.shared_vocabulary as vocabulary
    from core.models import Language, TimeZone

    before = {model: set(model.objects.values_list("pk", flat=True)) for model in (Language, TimeZone)}
    for name in [
        "shared_vocabulary_manifest.json",
        *[entry[1] for entry in vocabulary.CATALOGUES.values()],
    ]:
        shutil.copy(vocabulary.SEED_DIRECTORY / name, tmp_path / name)
    monkeypatch.setattr(vocabulary, "SEED_DIRECTORY", tmp_path)
    (tmp_path / "shared_time_zones.csv").write_text("code\nUTC\n")
    with pytest.raises(CommandError, match="Seed hash mismatch"):
        call_command("seed_shared_vocabulary", verbosity=0)
    assert before == {model: set(model.objects.values_list("pk", flat=True)) for model in before}


def test_resolution_context_must_be_explicit_and_supported():
    from core.shared_vocabulary import resolve_locale

    with pytest.raises(ValueError, match="context"):
        resolve_locale("zh-cn", context="guess")


def test_case_alias_collision_aborts_seed_atomically():
    from core.models import Language, Locale, TimeZone

    Language.objects.get_or_create(code="en")
    Locale.objects.create(code="en-us", language_id="en")
    before = {model: set(model.objects.values_list("pk", flat=True)) for model in (Language, Locale, TimeZone)}
    with pytest.raises(CommandError, match="Canonical seed identity conflict"):
        call_command("seed_shared_vocabulary", verbosity=0)
    assert before == {model: set(model.objects.values_list("pk", flat=True)) for model in before}


def test_dry_run_does_not_write():
    from core.models import Language, Locale, MeasurementUnit, TimeZone

    before = {model: set(model.objects.values_list("pk", flat=True)) for model in (Language, Locale, MeasurementUnit, TimeZone)}
    call_command("seed_shared_vocabulary", dry_run=True, verbosity=0)
    assert before == {model: set(model.objects.values_list("pk", flat=True)) for model in before}

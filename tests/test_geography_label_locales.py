"""Shared place names preserve locale identity and historical label cutover."""

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from core.models import Account, GeolocationAlternateName, Locale, Post
from monitor.views import _feed_geography_sources, _feed_geography_wire
from tests.geolocation_factory import feed_places

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_current_geography_labels_use_shared_locale_keys_and_keep_feed_output():
    places = feed_places()
    posts = []
    for key in ("US", "europe"):
        account = Account.objects.create(author_id="locale-" + key, based_in_location=places[key])
        posts.append(Post.objects.create(tweet_id="locale-" + key, author=account))
    sources = _feed_geography_sources(posts)
    wire = {(item.author_id, locale): _feed_geography_wire(sources[item.author_id], locale)
            for item in posts for locale in ("en", "ja", "zh_cn")}
    assert all(wire.values())
    assert "米国" in str(wire) and "美利坚合众国" in str(wire)


def test_exact_duplicate_place_locale_name_is_rejected_and_locale_is_protected():
    place = feed_places()["US"]
    row = place.alternate_names.filter(locale_id="en").first()
    with pytest.raises(IntegrityError), transaction.atomic():
        GeolocationAlternateName.objects.create(
            geolocation=place, locale_id="en", name=row.name, source_archive=row.source_archive,
        )
    with pytest.raises(ProtectedError):
        Locale.objects.get(pk="en").delete()


@pytest.mark.parametrize("migration_rehearsal_schema", [("core", "0125_correction_actor_writer_cutover")], indirect=True)
@pytest.mark.django_db(transaction=True)
def test_locale_cutover_preserves_old_writers_and_new_fk_writers(migration_rehearsal_schema):
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    pre_cutover = ("core", "0125_correction_actor_writer_cutover")
    cutover = ("core", "0126_remove_countrylabel_ck_country_label_locale_and_more")
    executor.migrate([pre_cutover])
    old = executor.loader.project_state([pre_cutover]).apps
    Country = old.get_model("core", "Country")
    Language = old.get_model("core", "Language")
    Locale = old.get_model("core", "Locale")
    CountryLabel = old.get_model("core", "CountryLabel")
    for code in ("en", "ja", "zh"):
        Language.objects.get_or_create(code=code)
    for code, language in (("en", "en"), ("ja", "ja"), ("zh-Hans", "zh")):
        Locale.objects.get_or_create(code=code, defaults={"language_id": language})
    from importlib import import_module

    with connection.cursor() as cursor:
        cursor.execute(
            import_module(
                "core.migrations.0119_geography_label_locale_references"
            ).MAP_EXISTING
        )
    Country.objects.get_or_create(code="XZ", defaults={"m49_code": "999"})
    CountryLabel.objects.create(
        country_id="XZ", lang="zh-cn", label="示例"
    )
    executor = MigrationExecutor(connection)
    executor.migrate([cutover])

    CurrentCountryLabel = executor.loader.project_state([cutover]).apps.get_model("core", "CountryLabel")

    row = CurrentCountryLabel.objects.get(pk=("XZ", "zh-Hans"))
    assert row.label == "示例"
    new_row = CurrentCountryLabel.objects.create(
        country_id="XZ", locale_reference_id="ja", label="仮"
    )
    assert new_row.pk == ("XZ", "ja")

    # A pre-cutover application image still writes through the compatibility
    # trigger. The old wording remains available until the later drop release.
    OldCountryLabel = executor.loader.project_state([pre_cutover]).apps.get_model(
        "core", "CountryLabel"
    )
    legacy = OldCountryLabel.objects.create(
        country_id="XZ", lang="en", label="Example"
    )
    assert CurrentCountryLabel.objects.get(pk=("XZ", "en")).label == "Example"
    assert legacy.lang == "en"

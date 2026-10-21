"""Geography labels use shared locale identities in current readers and writers."""

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from core.models import (
    Account,
    Country,
    CountryLabel,
    Locale,
    Post,
    Region,
    RegionLabel,
)
from monitor.views import _feed_geography_sources, _feed_geography_wire

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def parents():
    country, _ = Country.objects.get_or_create(code="XZ", defaults={"m49_code": "999"})
    region, _ = Region.objects.get_or_create(
        key="locale-fixture", defaults={"source": "fixture", "level": "region"}
    )
    return country, region


def test_current_geography_labels_use_shared_locale_keys_and_keep_feed_output():
    call_command("seed_shared_vocabulary", catalogue=["languages", "locales"])
    country, region = parents()
    labels = (("en", "Fixture"), ("ja", "仮の地名"), ("zh-Hans", "示例地名"))
    for locale, label in labels:
        CountryLabel.objects.create(
            country=country, locale_reference_id=locale, label=label
        )
        RegionLabel.objects.create(
            region=region, locale_reference_id=locale, label=label
        )
    account = Account.objects.create(
        author_id="locale-characterization",
        handle="locale-fixture",
        based_in_region=region,
    )
    post = Post.objects.create(tweet_id="locale-characterization", author=account)
    visible_country, _ = Country.objects.get_or_create(
        code="US", defaults={"m49_code": "840"}
    )
    for locale, label in (("en", "United States"), ("ja", "米国"), ("zh-Hans", "美国")):
        CountryLabel.objects.get_or_create(
            country=visible_country,
            locale_reference_id=locale,
            defaults={"label": label},
        )
    country_account = Account.objects.create(
        author_id="locale-country-characterization",
        handle="country-fixture",
        country=visible_country,
    )
    country_post = Post.objects.create(
        tweet_id="locale-country-characterization", author=country_account
    )
    posts = [post, country_post]
    sources = _feed_geography_sources(posts)
    wire = {
        (item.author_id, locale): _feed_geography_wire(sources[item.author_id], locale)
        for item in posts
        for locale in ("en", "ja", "zh_cn")
    }
    assert all(wire.values())
    assert CountryLabel.objects.filter(country=country).count() == 3
    assert RegionLabel.objects.filter(region=region).count() == 3


def test_duplicate_owner_locale_is_rejected_and_locale_is_protected():
    call_command("seed_shared_vocabulary", catalogue=["languages", "locales"])
    country, _ = parents()
    CountryLabel.objects.create(
        country=country, locale_reference_id="en", label="Example"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CountryLabel.objects.create(
            country=country, locale_reference_id="en", label="Duplicate"
        )
    with pytest.raises(ProtectedError):
        Locale.objects.get(pk="en").delete()


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_locale_cutover_preserves_old_writers_and_new_fk_writers():
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

    from core.models import CountryLabel as CurrentCountryLabel

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

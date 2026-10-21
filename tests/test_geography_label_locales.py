"""Locale references preserve composite label identities and actual feed output."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Event

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from core.geography_label_locales import OWNERS, map_geography_label_locales
from core.models import (
    Account,
    Country,
    CountryLabel,
    Language,
    Locale,
    Post,
    Region,
    RegionLabel,
)
from core.shared_vocabulary import resolve_locale
from monitor.views import _feed_geography_sources, _feed_geography_wire

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def parents():
    country, _ = Country.objects.get_or_create(code="XZ", defaults={"m49_code": "999"})
    region, _ = Region.objects.get_or_create(
        key="locale-fixture", defaults={"source": "fixture", "level": "region"}
    )
    return country, region


def seed_locales():
    Language.objects.bulk_create(
        [Language(code=code) for code in ("en", "ja", "zh")], ignore_conflicts=True
    )
    Locale.objects.bulk_create(
        [
            Locale(code=code, language_id=code.split("-")[0])
            for code in ("en", "ja", "zh", "zh-Hans", "zh-CN", "zh-TW", "zh-Hant")
        ],
        ignore_conflicts=True,
    )


def label_owner(owner):
    country, region = parents()
    model, field = OWNERS[owner]
    parent = country if owner == "country_labels" else region
    return model, field, parent


def test_actual_feed_sources_and_label_triples_characterization():
    country, region = parents()
    for lang, label in [("en", "Fixture"), ("ja", "仮の地名"), ("zh-cn", "示例地名")]:
        CountryLabel.objects.create(country=country, lang=lang, label=label)
        RegionLabel.objects.create(region=region, lang=lang, label=label)
    account = Account.objects.create(
        author_id="locale-characterization",
        handle="locale-fixture",
        based_in_region=region,
    )
    post = Post.objects.create(tweet_id="locale-characterization", author=account)
    visible_country, _ = Country.objects.get_or_create(
        code="US", defaults={"m49_code": "840"}
    )
    for lang, label in [("en", "United States"), ("ja", "米国"), ("zh-cn", "美国")]:
        CountryLabel.objects.get_or_create(
            country=visible_country, lang=lang, defaults={"label": label}
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
    before = {
        (item.author_id, lang): _feed_geography_wire(sources[item.author_id], lang)
        for item in posts
        for lang in ("en", "ja", "zh_cn")
    }
    assert all(before.values())
    triples = (
        list(
            CountryLabel.objects.order_by("country_id", "lang").values_list(
                "country_id", "lang", "label"
            )
        ),
        list(
            RegionLabel.objects.order_by("region_id", "lang").values_list(
                "region_id", "lang", "label"
            )
        ),
    )
    call_command("seed_shared_vocabulary", catalogue=["languages", "locales"])
    for owner in OWNERS:
        map_geography_label_locales(owner=owner, apply=True)
    sources = _feed_geography_sources(posts)
    assert {
        (item.author_id, lang): _feed_geography_wire(sources[item.author_id], lang)
        for item in posts
        for lang in ("en", "ja", "zh_cn")
    } == before
    assert (
        list(
            CountryLabel.objects.order_by("country_id", "lang").values_list(
                "country_id", "lang", "label"
            )
        ),
        list(
            RegionLabel.objects.order_by("region_id", "lang").values_list(
                "region_id", "lang", "label"
            )
        ),
    ) == triples


def test_old_label_inserts_use_existing_app_edition_resolution():
    from core.shared_vocabulary import resolve_locale

    country, region = parents()
    call_command("seed_shared_vocabulary", catalogue=["languages", "locales"])
    CountryLabel.objects.create(country=country, lang="zh-cn", label="示例")
    RegionLabel.objects.create(region=region, lang="JA", label="仮")
    assert (
        CountryLabel.objects.get(country=country, lang="zh-cn").locale_reference_id
        == resolve_locale("zh-cn", context="app_edition").pk
    )
    assert (
        RegionLabel.objects.get(region=region, lang="JA").locale_reference_id
        == resolve_locale("JA", context="app_edition").pk
    )


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.parametrize(
    "raw",
    [
        "EN",
        "ja",
        "zh-cn",
        "zh_CN",
        "ZH-CN",
        "zh-Hans",
        "zh",
        "zh_TW",
        "zh-Hant",
        "xx-unknown",
        "",
    ],
)
def test_raw_sql_guard_matches_the_existing_app_resolver_for_each_tag(owner, raw):
    seed_locales()
    model, field, parent = label_owner(owner)
    row = model.objects.create(
        **{field: parent.pk, "lang": raw, "label": "Fixture wording"}
    )
    row.refresh_from_db()
    canonical = resolve_locale(raw, context="app_edition")
    assert row.locale_reference_id == (canonical.pk if canonical else None)
    assert row.lang == raw and row.label == "Fixture wording"
    if raw in ("zh-cn", "zh_CN", "ZH-CN"):
        assert resolve_locale(raw, context="source").pk == "zh-CN"
        assert row.locale_reference_id == "zh-Hans"


@pytest.mark.parametrize("owner", OWNERS)
def test_late_mapping_is_bounded_resumable_and_preserves_composite_keys_and_copy(owner):
    model, field, parent = label_owner(owner)
    for raw in ("en", "ja", "zh-cn", "xx-unknown"):
        model.objects.create(**{field: parent.pk, "lang": raw, "label": "Copy " + raw})
    before = list(
        model.objects.order_by(field, "lang").values_list(field, "lang", "label")
    )
    seed_locales()
    first = map_geography_label_locales(
        owner=owner, apply=True, batch_size=1, max_batches=1
    )
    assert first["updated"] == first["examined"] == 1
    second = map_geography_label_locales(
        owner=owner,
        apply=True,
        batch_size=2,
        max_batches=1000,
        after_owner_key=first["after_owner_key"],
        after_lang=first["after_lang"],
    )
    assert second["remaining_resolvable"] == second["collision_count"] == 0
    assert second["unmatched_count"] == 1
    assert map_geography_label_locales(owner=owner, apply=True)["updated"] == 0
    assert (
        list(model.objects.order_by(field, "lang").values_list(field, "lang", "label"))
        == before
    )
    assert (
        model.objects.get(**{field: parent.pk, "lang": "zh-cn"}).locale_reference_id
        == "zh-Hans"
    )


@pytest.mark.parametrize("owner", OWNERS)
def test_preview_and_invalid_cursor_or_write_controls_do_not_mutate(owner):
    model, field, parent = label_owner(owner)
    model.objects.create(**{field: parent.pk, "lang": "en", "label": "Unchanged"})
    seed_locales()
    output = StringIO()
    call_command("map_geography_label_locales", owner=owner, stdout=output)
    preview = json.loads(output.getvalue())
    assert preview["updated"] == 0 and preview["apply"] is False
    assert preview["examined"] >= 1 and preview["collision_count"] == 0
    for kwargs in [
        {"owner": "metrics"},
        {"batch_size": 0},
        {"max_batches": 10001},
        {"after_owner_key": "XZ"},
        {"after_lang": "en"},
        {"after_owner_key": "", "after_lang": "en"},
        {"apply": True, "dry_run": True},
    ]:
        with pytest.raises(CommandError):
            call_command("map_geography_label_locales", **{"owner": owner, **kwargs})
    assert (
        model.objects.get(**{field: parent.pk, "lang": "en"}).locale_reference_id
        is None
    )


@pytest.mark.parametrize("owner", OWNERS)
def test_alias_collisions_are_reported_and_refuse_mapping_without_losing_rows(owner):
    model, field, parent = label_owner(owner)
    for raw in ("zh-cn", "zh_CN"):
        model.objects.create(**{field: parent.pk, "lang": raw, "label": "Copy " + raw})
    seed_locales()
    assert map_geography_label_locales(owner=owner)["collision_count"] == 1
    with pytest.raises(ValueError, match="collisions"):
        map_geography_label_locales(owner=owner, apply=True)
    assert set(
        model.objects.filter(**{field: parent.pk}).values_list(
            "lang", "label", "locale_reference_id"
        )
    ) == {
        ("zh-cn", "Copy zh-cn", None),
        ("zh_CN", "Copy zh_CN", None),
    }


@pytest.mark.parametrize("owner", OWNERS)
def test_old_pk_updates_keep_contextual_reference_and_resolved_owner_unique(owner):
    seed_locales()
    model, field, parent = label_owner(owner)
    row = model.objects.create(**{field: parent.pk, "lang": "en", "label": "Copy"})
    column = model._meta.get_field(field.removesuffix("_id")).column
    with connection.cursor() as c:
        c.execute(
            f"UPDATE {owner} SET lang='zh_CN' WHERE {column}=%s AND lang='en'",
            [parent.pk],
        )
    assert model.objects.get(pk=(parent.pk, "zh_CN")).locale_reference_id == "zh-Hans"
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.create(
            **{field: parent.pk, "lang": "zh-cn", "label": "Other copy"}
        )
    with pytest.raises(IntegrityError, match="locale reference"), transaction.atomic():
        model.objects.filter(pk=(parent.pk, "zh_CN")).update(
            locale_reference_id="zh-CN"
        )
    with pytest.raises(ProtectedError):
        Locale.objects.get(pk="zh-Hans").delete()
    with connection.cursor() as c:
        c.execute(
            f"UPDATE {owner} SET lang='xx-unknown' WHERE {column}=%s AND lang='zh_CN'",
            [parent.pk],
        )
    final = model.objects.get(pk=(parent.pk, "xx-unknown"))
    assert final.label == row.label and final.locale_reference_id is None


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.django_db(transaction=True)
def test_mapping_rechecks_a_composite_key_changed_by_a_concurrent_old_writer(owner):
    from django.db import connections

    model, field, parent = label_owner(owner)
    model.objects.create(**{field: parent.pk, "lang": "en", "label": "Before"})
    seed_locales()
    column = model._meta.get_field(field.removesuffix("_id")).column
    backend = []
    started = Event()

    def map_one():
        try:
            with connections["default"].cursor() as c:
                c.execute("SELECT pg_backend_pid()")
                backend.append(c.fetchone()[0])
            started.set()
            return map_geography_label_locales(
                owner=owner,
                apply=True,
                batch_size=1,
                max_batches=1,
                after_owner_key=parent.pk,
                after_lang="a",
            )
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic(), connection.cursor() as c:
            c.execute(
                f"SELECT lang FROM {owner} WHERE {column}=%s AND lang='en' FOR UPDATE",
                [parent.pk],
            )
            future = pool.submit(map_one)
            assert started.wait(5)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                c.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                    [backend[0]],
                )
                if c.fetchone() == ("Lock",):
                    break
                time.sleep(0.01)
            else:
                pytest.fail("Mapper did not reach the expected row-lock wait")
            c.execute(
                f"UPDATE {owner} SET lang='xx-unknown',label='After' WHERE {column}=%s AND lang='en'",
                [parent.pk],
            )
        result = future.result(timeout=10)
    assert result["updated"] == 0
    final = model.objects.get(pk=(parent.pk, "xx-unknown"))
    assert final.label == "After" and final.locale_reference_id is None


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_populated_forward_reverse_and_old_label_writers_preserve_original_rows():
    from django.db.migrations.executor import MigrationExecutor

    from tests.collection_fixtures import historical_fixture_models

    base = ("core", "0118_intelligence_timezone_references")
    target = ("core", "0119_geography_label_locale_references")
    MigrationExecutor(connection).migrate([base])
    old = MigrationExecutor(connection).loader.project_state([base]).apps
    with historical_fixture_models(old):
        country, region = parents()
        CountryLabel.objects.create(country=country, lang="zh-cn", label="示例")
        RegionLabel.objects.create(region=region, lang="JA", label="仮")
        seed_locales()
    originals = {}
    for name, field in [("CountryLabel", "country_id"), ("RegionLabel", "region_id")]:
        originals[name] = list(
            old.get_model("core", name).objects.order_by(field, "lang").values()
        )
    MigrationExecutor(connection).migrate([target])
    for name, model, field, parent in [
        ("CountryLabel", CountryLabel, "country_id", country),
        ("RegionLabel", RegionLabel, "region_id", region),
    ]:
        rows = list(model.objects.order_by(field, "lang").values())
        codes = {
            lang: resolve_locale(lang, context="app_edition")
            for lang in {row["lang"] for row in rows}
        }
        for row in rows:
            canonical = codes[row["lang"]]
            assert row.pop("locale_reference_id") == (
                canonical.pk if canonical else None
            )
        assert rows == originals[name]
        OldLabel = old.get_model("core", name)
        OldLabel.objects.create(
            **{field: parent.pk, "lang": "zh_TW", "label": "Old writer"}
        )
        assert model.objects.get(pk=(parent.pk, "zh_TW")).locale_reference_id == "zh-TW"
        OldLabel.objects.filter(pk=(parent.pk, "zh_TW")).update(lang="xx-unknown")
        assert (
            model.objects.get(pk=(parent.pk, "xx-unknown")).locale_reference_id is None
        )
    MigrationExecutor(connection).migrate([base])
    for name, field in [("CountryLabel", "country_id"), ("RegionLabel", "region_id")]:
        assert (
            list(
                old.get_model("core", name)
                .objects.exclude(lang="xx-unknown")
                .order_by(field, "lang")
                .values()
            )
            == originals[name]
        )
    MigrationExecutor(connection).migrate([target])

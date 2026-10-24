"""Shared places retain identity while source names and local policy stay distinct."""

import pytest
from django.db import IntegrityError, ProgrammingError, connection, transaction
from django.utils import timezone

from core import models

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def archive(body=b"verified provider fixture"):
    from core.collection_capture import archive_document

    return archive_document(body, media_type="text/plain", capture_kind="geolocation_source")


def place(geonames_id, *, country=False, **kwargs):
    return models.Geolocation.objects.create(
        geonames_id=geonames_id, place_kind=kwargs.pop("place_kind", 4 if country else 6),
        source_archive=archive(), **kwargs,
    )


def test_internal_references_use_local_ids_and_codes_cannot_be_fk_targets():
    india = place(1269750, country=True, iso2_country_code="IN")
    city = place(1275339, country=False, country_id=india.pk)
    assert city.country_id == india.pk
    assert city.country.geonames_id == 1269750
    with (
        pytest.raises(ProgrammingError, match="no unique constraint"),
        transaction.atomic(), connection.cursor() as cursor,
    ):
        cursor.execute("CREATE TABLE forbidden_country_reference (code varchar(2) REFERENCES geolocations(iso2_country_code))")
    with pytest.raises(IntegrityError), transaction.atomic():
        place(9999001, country=True, iso2_country_code="IN")


def test_hierarchy_rejects_cycles_and_non_country_targets():
    country = place(6252001, country=True, iso2_country_code="US")
    state = place(5332921, place_kind=5, country_id=country.pk)
    city = place(5391959, country_id=country.pk, administrative_parent=state)
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Geolocation.objects.filter(pk=state.pk).update(administrative_parent=city)
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Geolocation.objects.filter(pk=city.pk).update(country_id=state.pk)
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Geolocation.objects.filter(pk=country.pk).update(place_kind=6)


def test_multilingual_names_do_not_make_a_collision_unambiguous():
    first, second = place(5391959), place(9999002)
    for target in (first, second):
        models.GeolocationAlternateName.objects.create(
            geolocation=target, locale_id="en", name="San Francisco", source_archive=archive(),
        )
    models.GeolocationAlternateName.objects.create(
        geolocation=first, locale_id="ja", name="サンフランシスコ", source_archive=archive(),
    )
    models.GeolocationAlternateName.objects.create(
        geolocation=first, locale_id="zh-Hans", name="旧金山", source_archive=archive(),
    )
    assert first.alternate_names.count() == 3
    with pytest.raises(IntegrityError), transaction.atomic():
        models.GeolocationAlternateName.objects.create(
            geolocation=first, locale_id="en", name="San Francisco", source_archive=archive(),
        )


def test_policy_history_is_immutable_owned_and_separate_from_provider_identity():
    china = place(1814991, country=True, iso2_country_code="CN")
    taiwan = place(1668284, country=True, iso2_country_code="TW")
    actor = models.Actor.objects.create(actor_kind="system", actor_key="geolocation-test")
    policy = models.GeolocationPolicy.objects.create(
        geolocation=taiwan, actor=actor, decided_at=timezone.now(), source_archive=archive(),
        dispute_state=1, display_relationship=2, display_parent=china, flag_mode=1, label_mode=1,
    )
    models.Geolocation.objects.filter(pk=taiwan.pk).update(current_policy=policy)
    taiwan.refresh_from_db()
    assert taiwan.geonames_id == 1668284 and taiwan.iso2_country_code == "TW"
    assert taiwan.current_policy.display_parent_id == china.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Geolocation.objects.filter(pk=china.pk).update(current_policy=policy)
    with pytest.raises(IntegrityError), transaction.atomic():
        models.GeolocationPolicy.objects.filter(pk=policy.pk).update(dispute_state=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        models.GeolocationPolicy.objects.filter(pk=policy.pk).delete()


def rdf(identifier, name, *, feature="A.PCLI", extra=""):
    return f'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:gn="http://www.geonames.org/ontology#">
        <gn:Feature rdf:about="https://sws.geonames.org/{identifier}/">
            <gn:name>{name}</gn:name><gn:officialName xml:lang="en">{name}</gn:officialName>
            <gn:featureCode rdf:resource="https://www.geonames.org/ontology#{feature}"/>
            {extra}
        </gn:Feature></rdf:RDF>'''.encode()


def test_import_preserves_policy_and_language_attribution_on_replay():
    from core.geolocations import geolocation_label, import_geonames_documents

    source = rdf(1668284, "Taiwan", extra='''
        <gn:officialName xml:lang="ja">台湾</gn:officialName>
        <gn:alternateName xml:lang="zh">台灣</gn:alternateName>
        <gn:alternateName xml:lang="zh-Hans">台湾</gn:alternateName>''')
    identities = import_geonames_documents({1668284: source}, country_metadata={1668284: "TW"})
    target = models.Geolocation.objects.get(pk=identities[1668284])
    actor = models.Actor.objects.create(actor_kind="system", actor_key="import-refresh")
    policy = models.GeolocationPolicy.objects.create(
        geolocation=target, actor=actor, decided_at=timezone.now(), source_archive=archive(),
        dispute_state=1, country_attribution=2,
    )
    models.Geolocation.objects.filter(pk=target.pk).update(current_policy=policy)
    assert import_geonames_documents({1668284: source}, country_metadata={1668284: "TW"}) == identities
    target.refresh_from_db()
    assert target.current_policy_id == policy.pk
    assert target.alternate_names.count() == 5
    assert target.alternate_names.get(locale_id="zh").name == "台灣"
    assert geolocation_label(target, "ja") == "台湾"
    assert geolocation_label(target, "zh-Hans") == "台湾"
    assert geolocation_label(target, "fr") == "Taiwan"


def test_import_requires_ancestors_and_is_atomic():
    from core.geolocations import import_geonames_documents

    city = rdf(5391959, "San Francisco", feature="P.PPLA2", extra='''
        <gn:parentCountry rdf:resource="https://sws.geonames.org/6252001/"/>
        <gn:parentADM1 rdf:resource="https://sws.geonames.org/5332921/"/>''')
    with pytest.raises(ValueError, match="required ancestors"):
        import_geonames_documents({5391959: city})
    assert models.Geolocation.objects.count() == 0
    source = {
        5391959: city,
        6252001: rdf(6252001, "United States"),
        5332921: rdf(5332921, "California", feature="A.ADM1"),
    }
    ids = import_geonames_documents(source, country_metadata={6252001: "US"})
    target = models.Geolocation.objects.get(pk=ids[5391959])
    assert target.country_id == ids[6252001]
    assert target.administrative_parent_id == ids[5332921]
    assert import_geonames_documents(source, country_metadata={6252001: "US"}) == ids
    assert models.Geolocation.objects.count() == 3


def test_owner_bare_name_defaults_do_not_replace_explicit_other_countries():
    from core.geolocations import owner_default_geonames_id, resolve_owner_default

    korea, congo = place(1835841, country=True), place(203312, country=True)
    assert resolve_owner_default("Korea").pk == korea.pk
    assert resolve_owner_default(" congo ").pk == congo.pk
    for explicit in ("North Korea", "Republic of the Congo", "Congo Brazzaville", "Korea and Japan"):
        assert owner_default_geonames_id(explicit) is None
    assert resolve_owner_default("Springfield") is None
    assert models.GeolocationAlternateName.objects.count() == 0


def test_import_rejects_wrong_identity_and_entities_before_writing():
    from core.geolocations import import_geonames_documents

    with pytest.raises(ValueError, match="requested place"):
        import_geonames_documents({203312: rdf(1835841, "South Korea")})
    with pytest.raises(ValueError, match="Invalid or oversized"):
        import_geonames_documents({203312: b'<!DOCTYPE rdf [<!ENTITY leak SYSTEM "file:///etc/passwd">]>'})
    assert models.Geolocation.objects.count() == 0


def test_model_check_rejects_external_geography_reference_keys():
    from django.db import models as fields
    from django.test.utils import isolate_apps

    from core.geolocation_checks import check_geolocation_reference_targets

    with isolate_apps("core") as registry:
        class BadReference(fields.Model):
            place = fields.ForeignKey(models.Geolocation, to_field="geonames_id", on_delete=fields.PROTECT)

            class Meta:
                app_label = "core"

        errors = check_geolocation_reference_targets([registry.get_app_config("core")])
        assert [(error.id, error.obj.name) for error in errors] == [("core.E041", "place")]


def test_broad_region_centroid_and_multiple_generic_parents_are_not_containment():
    from core.geolocations import parse_geonames_rdf

    southern_asia = rdf(7729895, "Southern Asia", feature="L.RGN", extra='''
        <gn:parentADM1 rdf:resource="https://sws.geonames.org/1278629/"/>
        <gn:parentFeature rdf:resource="https://sws.geonames.org/1278629/"/>
        <gn:parentFeature rdf:resource="https://sws.geonames.org/6255147/"/>''')
    region = parse_geonames_rdf(southern_asia, 7729895)
    assert region.administrative_parent_id is None
    assert region.geographical_parent_id == 6255147
    india = parse_geonames_rdf(rdf(1269750, "India", extra='''
        <gn:parentFeature rdf:resource="https://sws.geonames.org/11812257/"/>
        <gn:parentFeature rdf:resource="https://sws.geonames.org/7729895/"/>'''), 1269750)
    assert india.place_kind == models.Geolocation.Kind.COUNTRY_AREA
    assert india.geographical_parent_id is None


def test_selected_import_excludes_political_parent_candidates():
    from core.geolocations import import_geonames_documents

    source = {
        1269750: rdf(1269750, "India", extra='''
            <gn:parentFeature rdf:resource="https://sws.geonames.org/11812257/"/>'''),
        11812257: rdf(11812257, "Commonwealth of Nations", feature="A.ZN"),
    }
    ids = import_geonames_documents(source, selected_ids=[1269750])
    assert set(ids) == {1269750}
    assert models.Geolocation.objects.get(pk=ids[1269750]).geographical_parent_id is None


def test_pinned_provider_bundle_has_preserved_names_and_idempotent_identity():
    from django.conf import settings

    from core.geolocations import (
        import_geonames_documents,
        load_pinned_geonames,
        resolve_owner_default,
    )

    documents, metadata, roots = load_pinned_geonames(settings.BASE_DIR / "data" / "geonames")
    ids = import_geonames_documents(documents, country_metadata=metadata, selected_ids=roots)
    assert resolve_owner_default("Congo").pk == ids[203312]
    assert resolve_owner_default("Korea").pk == ids[1835841]
    assert models.Geolocation.objects.get(pk=ids[1269750]).place_kind == 4
    assert models.Geolocation.objects.get(pk=ids[5391959]).country_id == ids[6252001]
    before_names = models.GeolocationAlternateName.objects.count()
    assert import_geonames_documents(documents, country_metadata=metadata, selected_ids=roots) == ids
    assert models.GeolocationAlternateName.objects.count() == before_names


@pytest.mark.django_db(transaction=True)
def test_explicit_fetch_is_bounded_and_precedes_import(monkeypatch):
    import io

    from core.geolocations import fetch_geonames_documents

    calls = []

    class Response(io.BytesIO):
        def geturl(self):
            return "https://sws.geonames.org/203312/about.rdf"

    def fetch(request, timeout):
        calls.append((request.full_url, timeout))
        return Response(rdf(203312, "Democratic Republic of the Congo"))

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    assert set(fetch_geonames_documents([203312], max_places=1)) == {203312}
    assert calls == [("https://sws.geonames.org/203312/about.rdf", 20)]
    assert models.Geolocation.objects.count() == 0
    with pytest.raises(ValueError, match="positive GeoNames IDs"):
        fetch_geonames_documents([-1])
    with transaction.atomic(), pytest.raises(ValueError, match="before opening"):
        fetch_geonames_documents([203312])


def test_provider_refresh_preserves_the_selected_localized_label():
    from core.geolocations import geolocation_label, import_geonames_documents

    first = rdf(1835841, "Republic of Korea")
    ids = import_geonames_documents({1835841: first})
    target = models.Geolocation.objects.get(pk=ids[1835841])
    target.alternate_names.filter(locale_id="en").update(is_preferred=False)
    models.GeolocationAlternateName.objects.create(
        geolocation=target, locale_id="en", name="South Korea", is_preferred=True,
        source_archive=archive(b"existing approved country label"),
    )
    import_geonames_documents({1835841: first})
    assert geolocation_label(target, "en") == "South Korea"

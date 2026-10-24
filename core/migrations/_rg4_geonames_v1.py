"""Frozen RG4 provider import used by historical migrations; do not edit in place."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import IntEnum
from xml.etree import ElementTree

from django.utils import timezone


class Kind(IntEnum):
    WORLD = 1
    CONTINENT = 2
    REGION = 3
    COUNTRY_AREA = 4
    ADMINISTRATIVE = 5
    POPULATED_PLACE = 6
    POINT = 7

INITIAL_NAME_LOCALES = frozenset({"und", "en", "ja", "zh", "zh-CN", "zh-Hans"})
RDF_RESOURCE = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"
RDF_ABOUT = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
GEONAMES_NAMESPACES = frozenset({"http://www.geonames.org/ontology#", "https://www.geonames.org/ontology#"})


def archive_document(apps, body, *, media_type="application/json", capture_kind="geolocation_source", encoding="wire-bytes-v1"):
    Archive = apps.get_model("core", "CollectionEvidenceArchive")
    row, _ = Archive.objects.get_or_create(
        content_sha256=hashlib.sha256(body).hexdigest(), encoding=encoding,
        defaults={"body":body, "byte_count":len(body), "media_type":media_type, "capture_kind":capture_kind},
    )
    if bytes(row.body) != body:
        raise ValueError("Source archive checksum conflict")
    return row

@dataclass(frozen=True)
class ParsedPlace:
    geonames_id: int
    place_kind: int
    latitude: Decimal | None
    longitude: Decimal | None
    country_id: int | None
    administrative_parent_id: int | None
    geographical_parent_id: int | None
    names: tuple[tuple[str, str, bool, bool], ...]

    @property
    def ancestors(self):
        return frozenset(value for value in (
            self.country_id, self.administrative_parent_id, self.geographical_parent_id,
        ) if value is not None)

def normalized_place_wording(value):
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFKC", value).strip().casefold()

def _external_id(uri):
    match = re.fullmatch(r"https?://sws\.geonames\.org/([1-9][0-9]*)/", uri or "")
    if not match:
        raise ValueError("Invalid GeoNames feature identity")
    return int(match[1])

def parse_geonames_rdf(body: bytes, expected_id: int) -> ParsedPlace:
    """Read one bounded provider document; reject entities and identity mismatch."""
    if not isinstance(body, bytes) or len(body) > 500_000 or b"<!" in body:
        raise ValueError("Invalid or oversized GeoNames RDF document")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as error:
        raise ValueError("Invalid GeoNames RDF document") from error
    features = [node for node in root if node.tag in {
        "{" + namespace + "}Feature" for namespace in GEONAMES_NAMESPACES
    } and _external_id(node.get(RDF_ABOUT)) == expected_id]
    if len(features) != 1:
        raise ValueError("GeoNames document does not identify the requested place")
    fields = {}
    names = {}
    for node in features[0]:
        namespace, separator, key = node.tag[1:].partition("}")
        if not separator:
            continue
        if namespace in GEONAMES_NAMESPACES:
            fields.setdefault(key, []).append(node)
            if key in {"name", "toponymName", "officialName", "alternateName", "shortName"}:
                locale = node.get(XML_LANG, "und")
                wording = node.text or ""
                if locale in INITIAL_NAME_LOCALES and wording.strip():
                    previous = names.get((locale, wording), (False, False))
                    names[(locale, wording)] = (
                        previous[0] or key == "officialName", previous[1] or key == "shortName",
                    )
        elif namespace == "http://www.w3.org/2003/01/geo/wgs84_pos#":
            fields.setdefault(key, []).append(node)
    if not names:
        raise ValueError("GeoNames document has no supported place name")

    def reference(key):
        rows = fields.get(key, [])
        if len(rows) > 1:
            raise ValueError(f"Multiple {key} references need explicit resolution")
        return _external_id(rows[0].get(RDF_RESOURCE)) if rows else None

    code_rows = fields.get("featureCode", [])
    if len(code_rows) != 1:
        raise ValueError("GeoNames document needs one feature code")
    feature = code_rows[0].get(RDF_RESOURCE, "").split("#")[-1]
    if feature in {"A.PCLI", "A.PCLD", "A.PCLF", "A.PCLS", "A.PCL", "A.TERR"}:
        kind = Kind.COUNTRY_AREA
    elif feature.startswith("A.ADM"):
        kind = Kind.ADMINISTRATIVE
    elif feature.startswith("P."):
        kind = Kind.POPULATED_PLACE
    elif feature == "L.CONT":
        kind = Kind.CONTINENT
    elif feature in {"L.RGN", "L.RGNE"}:
        kind = Kind.REGION
    else:
        kind = Kind.POINT
    country = reference("parentCountry")
    if country == expected_id:
        country = None
    reported_administrative = [value for key in (
        "parentADM5", "parentADM4", "parentADM3", "parentADM2", "parentADM1",
    ) if (value := reference(key)) not in (None, expected_id)]
    # Broad-region ADM fields can describe the map centre, not containment.
    administrative = (
        next(iter(reported_administrative), None)
        if kind in {Kind.ADMINISTRATIVE, Kind.POPULATED_PLACE, Kind.POINT}
        else None
    )
    if administrative is None and kind in {Kind.ADMINISTRATIVE, Kind.POPULATED_PLACE}:
        administrative = country
    geographical_candidates = {
        _external_id(node.get(RDF_RESOURCE)) for node in fields.get("parentFeature", [])
    } - {expected_id, country, *reported_administrative}
    # The generic relation also includes political/economic groupings. Multiple
    # choices do not establish one geographic parent; retain the source only.
    geographical = next(iter(geographical_candidates)) if len(geographical_candidates) == 1 else None
    lat = fields.get("lat", [])
    lon = fields.get("long", [])
    if len(lat) != len(lon) or len(lat) > 1:
        raise ValueError("Incomplete GeoNames coordinates")
    latitude = Decimal(lat[0].text) if lat else None
    longitude = Decimal(lon[0].text) if lon else None
    if latitude is not None and (
        not latitude.is_finite() or not longitude.is_finite()
        or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
    ):
        raise ValueError("Invalid GeoNames coordinates")
    return ParsedPlace(
        expected_id, kind, latitude, longitude, country, administrative, geographical,
        tuple((locale, name, preferred, short) for (locale, name), (preferred, short)
              in sorted(names.items())),
    )

def import_geonames_documents(apps, documents, *, country_metadata=None, selected_ids=None):
    """Import a bounded, explicit document set; all ancestors must be available.

    country_metadata comes from the pinned countryInfo import, never a caller's
    country guess. No network operation occurs inside this transaction.
    """
    Geolocation = apps.get_model("core", "Geolocation")
    GeolocationAlternateName = apps.get_model("core", "GeolocationAlternateName")
    Language = apps.get_model("core", "Language")
    Locale = apps.get_model("core", "Locale")
    if not documents or len(documents) > 1000:
        raise ValueError("Import requires between 1 and 1000 explicit documents")
    country_metadata = country_metadata or {}
    parsed = {key: parse_geonames_rdf(body, key) for key, body in documents.items()}
    parent_kinds = dict(Geolocation.objects.filter(
        geonames_id__in={row.geographical_parent_id for row in parsed.values()},
    ).values_list("geonames_id", "place_kind"))
    parent_kinds.update({key: row.place_kind for key, row in parsed.items()})
    parsed = {
        key: replace(row, geographical_parent_id=None)
        if parent_kinds.get(row.geographical_parent_id) not in (
            None, Kind.CONTINENT, Kind.REGION,
        )
        else row for key, row in parsed.items()
    }
    if selected_ids is not None:
        selected = set(selected_ids)
        if not selected or selected - parsed.keys():
            raise ValueError("Selected places must have explicit source documents")
        pending = list(selected)
        while pending:
            row = parsed.get(pending.pop())
            if row is not None:
                new = row.ancestors - selected
                selected.update(new)
                pending.extend(new)
        parsed = {key: row for key, row in parsed.items() if key in selected}
    required = set(parsed).union(*(row.ancestors for row in parsed.values()))
    existing = dict(Geolocation.objects.filter(geonames_id__in=required).values_list("geonames_id", "pk"))
    missing = required - parsed.keys() - existing.keys()
    if missing:
        raise ValueError(f"Import required ancestors first or include them: {sorted(missing)}")
    now = timezone.now()
    registered_locales = set()
    for identifier, source in parsed.items():
        capture = archive_document(apps, documents[identifier], media_type="application/rdf+xml", capture_kind="geolocation_source")
        defaults = {
            "place_kind": Kind.COUNTRY_AREA if identifier in country_metadata else source.place_kind,
            "latitude": source.latitude, "longitude": source.longitude,
            "source_archive": capture, "refreshed_at": now,
        }
        if identifier in country_metadata:
            defaults["iso2_country_code"] = country_metadata[identifier]
        location, _ = Geolocation.objects.update_or_create(geonames_id=identifier, defaults=defaults)
        existing[identifier] = location.pk
        selected_locales = set(location.alternate_names.filter(
            is_preferred=True, is_historical=False,
        ).values_list("locale_id", flat=True))
        preferred_names = {}
        for locale, name, preferred, _short in sorted(source.names, key=lambda row: (not row[2], row[1])):
            preferred_names.setdefault(locale, name)
        for locale, name, _preferred, short in source.names:
            if locale not in registered_locales:
                language = locale.split("-", 1)[0]
                Language.objects.get_or_create(code=language)
                Locale.objects.get_or_create(code=locale, defaults={"language_id": language})
                registered_locales.add(locale)
            name_values = {"is_short": short, "source_archive": capture}
            if locale not in selected_locales:
                name_values["is_preferred"] = name == preferred_names[locale]
            GeolocationAlternateName.objects.update_or_create(
                geolocation=location, locale_id=locale, name=name,
                defaults=name_values,
            )
    for identifier, source in parsed.items():
        Geolocation.objects.filter(pk=existing[identifier]).update(
            country_id=existing.get(source.country_id),
            administrative_parent_id=existing.get(source.administrative_parent_id),
            geographical_parent_id=existing.get(source.geographical_parent_id),
        )
    return {identifier: existing[identifier] for identifier in parsed}

def parse_country_metadata(body: bytes):
    """Translate the provider's countryInfo identifiers at the import boundary."""
    result = {}
    codes = set()
    for line in body.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 19 or not re.fullmatch(r"[A-Z]{2}", fields[0]) or not fields[16].isdigit():
            raise ValueError("Invalid GeoNames countryInfo row")
        identifier = int(fields[16])
        if identifier <= 0 or identifier in result or fields[0] in codes:
            raise ValueError("Duplicate or invalid GeoNames country identity")
        result[identifier] = fields[0]
        codes.add(fields[0])
    if not result:
        raise ValueError("Empty GeoNames country metadata")
    return result

def load_pinned_geonames(directory):
    """Verify the versioned bundle without extracting archive paths to disk."""
    import hashlib
    import json
    import tarfile
    from pathlib import Path

    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported GeoNames bundle version")
    metadata_body = (directory / "countryInfo.txt").read_bytes()
    archive_path = directory / "selected-places-rdf.tar.gz"
    if (hashlib.sha256(metadata_body).hexdigest() != manifest["country_info_sha256"]
            or hashlib.sha256(archive_path.read_bytes()).hexdigest() != manifest["archive_sha256"]):
        raise ValueError("GeoNames bundle checksum mismatch")
    expected = manifest["documents"]
    if not 1 <= len(expected) <= 1000:
        raise ValueError("GeoNames bundle must contain 1–1000 documents")
    documents = {}
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            match = re.fullmatch(r"([1-9][0-9]*)\.rdf", member.name)
            if not member.isfile() or not match or match[1] not in expected or not 0 < member.size <= 500_000:
                raise ValueError("Unexpected GeoNames archive member")
            identifier = int(match[1])
            if identifier in documents:
                raise ValueError("Duplicate GeoNames archive member")
            body = archive.extractfile(member).read(500_001)
            record = expected[match[1]]
            if len(body) != record["bytes"] or hashlib.sha256(body).hexdigest() != record["sha256"]:
                raise ValueError("GeoNames document checksum mismatch")
            documents[identifier] = body
    roots = manifest["selected_geonames_ids"]
    if (len(documents) != len(expected) or not roots
            or any(type(key) is not int for key in roots) or set(roots) - documents.keys()):
        raise ValueError("Incomplete GeoNames bundle")
    return documents, parse_country_metadata(metadata_body), roots


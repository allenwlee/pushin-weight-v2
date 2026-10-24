# Selected GeoNames source documents

These pinned public documents support the shared-place migration and later
corrections. They cover the existing 249-country catalogue, individually checked
region/city additions, and provider parent documents needed to examine those
places. This is not the full GeoNames gazetteer.

`manifest.json` identifies the selected roots, capture time, sizes and SHA-256
checksums. `selected-places-rdf.tar.gz` preserves the original RDF response bytes;
`countryInfo.txt` supplies provider IDs and approved country-code metadata.
Database import is limited to the selected roots and usable ancestors. Captured
political/economic parent candidates need not become stored geographic parents.

Sources are [GeoNames](https://www.geonames.org/) under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/):
[country metadata](https://download.geonames.org/export/dump/countryInfo.txt),
[RDF format](https://www.geonames.org/ontology/documentation.html), and each
`https://sws.geonames.org/<id>/about.rdf` document identified in the manifest.

Names retain their actual language/script tags. An unspecified Chinese (`zh`)
name is not relabelled as Simplified Chinese. User submissions do not create
aliases. Original source documents remain evidence; application readers use
local `geolocations.id` references and typed fields.

Administrative fields on broad geographic regions can describe a map centre.
Do not turn those into administrative containment. Generic `parentFeature`
links may include political or economic groups. Multiple alternatives remain
unresolved, and non-region/continent targets are excluded from the optional
geographical-parent reference. This does not prevent importing a known place.

Bare `Korea` → South Korea (1835841) and bare `Congo` → Democratic Republic of
the Congo (203312) are explicit owner resolution defaults recorded October 24,
2026. They do not redefine the provider records or match substrings of explicit
other-country names. Other unresolved claims keep SQL NULL references and
necessary original wording; the owner requires no further review wait.

To load the pinned selection, run `python manage.py import_geolocations` with
an ingestion/migration database connection. To import one newly verified place,
run `python manage.py import_geolocations --fetch --geonames-id 5391959`.
The latter explicitly fetches public GeoNames documents and missing ancestors,
with a default bound of 100 places. Fetching happens before the atomic database
write. Scheduled harvesting never calls this command or makes these requests.

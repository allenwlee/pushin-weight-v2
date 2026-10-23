# Chinese administrative geography: research for future matching

Checked: 2026-10-23 JST. External-source research; no importer or database change implemented.

For Chinese locations, use original Chinese names, administrative level, parent area and date to verify a GeoNames match. Keep source wording where it carries evidence needed for disambiguation or correction. Unambiguous normalized country codes can be replaced by a shared location FK without a duplicate raw-code column. This follows the owner's selected Option C in the [global schema plan](../plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md). The [production value audit](../analysis/2026-10-23-161234-geonames-x-based-in-job-location-audit.md) lists our actual X/job inputs; it is not a completed administrative crosswalk.

## Sources to consult

| Source | Purpose | Boundary |
| --- | --- | --- |
| Ministry of Civil Affairs (MCA), 中国·国家地名信息库 | Official standard place names and place-name information | Public access does not establish an open bulk export, supported API or reuse licence. |
| MCA administrative codes and official local change announcements | Administrative identity, level, parent relationship and changes over time | An administrative area is not necessarily the same feature or extent as a GeoNames city point. |
| National Bureau of Statistics (NBS) statistical area codes | Statistical geography, including township/village detail | Statistical constructs are not all legally constituted administrative divisions. |
| Amap (高德) district/geocoding APIs | Chinese address interpretation and candidate parent areas | Commercial service terms apply; its IDs are not GeoNames IDs. |
| GeoNames | Shared international identifiers, feature types and multilingual names | Verify the individual feature; coverage is not proof of uniform accuracy. |

### Official names and administrative codes

The MCA's [National Place Names Database announcement](https://app.www.gov.cn/govdata/gov/202212/25/495555/article.html) identifies [dmfw.mca.gov.cn](https://dmfw.mca.gov.cn/) as its public database and describes standard-name publication and administrative/place-name updates. The announcement is for its 2022 edition; it does not establish that 2022 is the latest dataset. The live portal was not successfully inspected in this research. Bulk access, an API contract and redistribution rights remain unverified.

The 2025 Administrative Division Code Management Measures took effect on 2025-09-01. Article 16 requires national publication each January of the previous year-end's administrative-code information through the National Place Names Database; provincial departments also publish township-level information. Consult the [official rule text](https://www.moj.gov.cn/pub/sfbgw/flfggz/flfggzbmgz/202512/t20251204_528920.html) and [Ministry of Justice explanation](https://legalinfo.moj.gov.cn/zhfxfzzx/fzzxyw/202507/t20250707_522250.html). The rule-text page's indexed content was available during recheck, but direct fetching encountered a redirect error.

Project recommendation: retain the publication vintage and effective date of a change separately from our retrieval date. A renamed, merged or reorganized district needs a dated interpretation; today's hierarchy must not silently replace the meaning of an older job/profile observation. This research did not download or validate a complete current code release.

### NBS statistical areas are a separate definition

The NBS specification divides a 12-digit statistical area code into province (digits 1–2), prefecture (3–4), county (5–6), township (7–9) and village (10–12). The combined statistical/urban-rural scheme has 17 digits, with five additional classification digits. The first six use the national administrative-code standard. Lower levels include similar and virtual units, so a code prefix does not prove legal administrative identity. [NBS coding rules](https://www.stats.gov.cn/sj/tjbz/gjtjbz/202302/t20230213_1902741.html).

Keep the identifier namespace, complete value and dataset vintage. Do not treat MCA administrative codes, NBS statistical codes and Amap `adcode` as interchangeable because some values coincide. Availability/freshness of a particular annual export must still be checked.

### Amap: useful candidate lookup, with access and identity limits

The [Amap district API](https://lbs.amap.com/api/webservice/guide/api/district) requires an API key and describes country/province/city/district/street hierarchy. Township/street results use their parent district's `adcode`; street boundary polylines are unavailable. The documentation also states detailed Taiwan division queries are unsupported. Therefore `adcode` alone is not a unique street identifier.

The [official download page](https://developer.amap.com/api/webservice/download) says its code tables are for offline reference, not cached operational use, and recommends online geocoding/reverse-geocoding for codes. Its official indexed content was available during this check; direct fetching timed out. Recheck applicable licence, storage/caching rights, quotas and intended use before an integration. No paid calls are authorized by these notes.

### Coordinate systems

Amap describes its coordinates as **GCJ-02**, distinct from **WGS84** and Baidu's **BD-09**. GeoNames specifies WGS84 latitude/longitude. Preserve the source coordinate system and identify any transformation; never overwrite or compare these coordinates as though they used the same system. Sources: [Amap conversion documentation](https://lbs.amap.com/api/javascript-api-v2/guide/transform/convertfrom), [GeoNames export specification](https://download.geonames.org/export/dump/readme.txt).

## Matching rules for later work

These are project recommendations, not implemented behavior:

- Preserve exact Chinese characters where needed for correction. The job audit flags `黄浦区` versus `黄埔区`; matching only romanized “Huangpu” can select the wrong place.
- Use stated province/city and dated source context to disambiguate districts. Employer headquarters does not establish a job's location. Leave a district-only claim unresolved when the context is insufficient.
- Compare geographic extent and feature type, not just names. A municipality, urban settlement, district and representative coordinate can describe different things.
- Use Chinese official sources to verify a crosswalk into the shared local place table; do not create another set of domain location targets for a Chinese provider.
- Keep current preferred names, translations and historical aliases distinguishable. Names are not globally unique identifiers.
- Retain only necessary source evidence. Clear existing code references can be fully replaced with geographic-location FKs; free-form, ambiguous and disputed observations may need original wording and provenance.
- A later correction changes the interpretation, not preserved source evidence. Local dispute/display policies remain separate from the provider's territorial classification.

Before implementation, verify current release/access rights, exact administrative extent and date, whether an NBS unit is statistical or administrative, coordinate system, and the individual GeoNames feature. No new provider, schema field, JSON column, collection job or production change was created by this research.

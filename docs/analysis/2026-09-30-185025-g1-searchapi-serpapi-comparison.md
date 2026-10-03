---
title: G1 SearchApi versus SerpApi — measured Baidu comparison
checked_at: "2026-09-30T18:50:25+09:00"
session: g1-chinese-faces-20260930
status: bounded-comparison-complete
---

# SearchApi versus SerpApi

SearchApi worked with the owner's new key and completed the same six queries
faster in this run. It rediscovered the sources behind all five photographs
accepted in the [SerpApi test](2026-09-30-183447-g1-serpapi-baidu-media-test.md).
The additional image candidates are promising, but the returned JSON assigned
the wrong original URL to ten of eleven inline images. The saved Baidu HTML
confirmed the mismatch and allowed recovery of the correct mappings.

| Observation | SerpApi | SearchApi |
| --- | --- | --- |
| Successful search requests | 6/6 | 6/6 |
| Total measured search-request time | 68.159 seconds | 38.742 seconds |
| Organic result entries | 52 | 44 |
| Distinct organic result URLs | 43 | 35 |
| Accepted photos beyond the pre-test gallery | 5 in 7 files | Sources for the same 5 photos / 7 files rediscovered; existing evidence reused |
| Additional verified photos beyond SerpApi | Baseline | 0 in this bounded pass |
| Fresh additional candidate downloads | See baseline report | 5 files held for attribution review |
| Direct playable video URL returned | 1 downloaded mixed-footage clip | None in these six responses |
| Search allowance used | Six searches if uncached; account delta unmeasured | Measured 6 credits, from 100 to 94 |

Thirty-four of SearchApi's 35 distinct organic URLs also appeared in SerpApi.
Its only extra organic URL was a Luo Fuli Weibo post; Firecrawl could not
retrieve it. SearchApi also placed Luo's Baike entry in `knowledge_graph`,
where SerpApi treated it as an organic result. Raw entry totals therefore mix
ranking differences and differences in how each provider structures results.

## Test controls and limits

The fixed queries were `罗福莉 小米`, `罗福莉 演讲`, `李子玄 智谱`,
`李子玄 智谱 演讲`, `张昱轩 智谱`, and `张昱轩 智谱 分享`.
Each provider received one first-page request per query, asking for ten results.
There were no search retries, pagination, purchases, or account changes.

[SearchApi's Baidu documentation](https://www.searchapi.io/docs/baidu) specifies
`engine=baidu`, `num=10`, `page=1`, and `ct=1` for Simplified Chinese;
[SerpApi](https://serpapi.com/baidu-search-api) specifies `rn=10`, `pn=0`,
and `ct=2` for that language. The actual upstream URLs used different `ct`
values; equivalence is based on the providers' documentation and is not
independently established. SearchApi does not document a Baidu device parameter.
Results were collected at different times. The speed and result differences
are observations of this run, not a controlled provider-only benchmark.

SearchApi's [Account API](https://www.searchapi.io/docs/account-api) was read
before and after the searches and once after saved-HTML retrieval. It reported
100, 94, and 94 remaining credits respectively. One saved-result HTML request
did not cause a further observed credit decrease. The six searches consumed
six credits, irrespective of the result count. The account reported no monthly
allowance; do not describe its initial 100 credits as a recurring monthly plan.

The same source/media limits applied: at most five source pages per query,
ten candidate image files and two videos per person. Twenty sources were
assessed: seventeen reused the just-fetched SerpApi evidence, and three were
new Firecrawl attempts. The Weibo fetch failed; two Baidu image-detail pages
returned image captions. No previously failed source was retried. The two
shared WeChat pages remain verification-blocked, with zero retrieved images.

## Image parsing finding and candidate review

The `罗福莉 小米` response included eleven distinct thumbnail URLs but repeated
one Sohu-hosted original URL for every entry. Matching each thumbnail against
the saved HTML showed one correct original mapping and ten incorrect mappings.
The HTML contained thirty image metadata entries; those are unreviewed leads,
not thirty accepted photographs. Correct mappings are saved separately, with
the original API response preserved. This proves a parsing defect in this
specific response; it does not establish that every SearchApi response has it.

Five candidate files were downloaded and visually inspected:

- A 1280 × 1907 stage photograph and its 500 × 745 thumbnail show the same
  photograph. Its Baidu image-detail caption names Luo Fuli.
- A 730 × 500 photograph outside the Louvre also has a Baidu image-detail
  caption naming Luo Fuli. The original publisher article was not retrieved.
- A 500 × 655 stage thumbnail and a 200 × 133 Weibo thumbnail remain
  unverified; the Weibo source failed and the inline original mapping was wrong.

The two named image-index candidates are held separately from the gallery
because their original publisher pages/captions remain unverified at the source
budget limit. The other candidates also lack sufficient attribution. No
identity was inferred from facial appearance. Five downloaded files do not
mean five distinct, verified photos. No SearchApi candidates were added to the
staff gallery or its accepted-photo totals.

The five previously accepted photographs remain supported by the same source
pages: Luo 3, Li 1, Zhang 1. Matching evidence and files were reused rather
than downloaded again. SearchApi returned the same restricted CCF recording
page but no direct playable video URL in these responses; no new video was
downloaded. SerpApi's held clip is mixed footage, not verified subject footage
throughout.

## Implication for G1

**Owner note, 2026-09-30:** SerpApi is the more reliable option for the tested
Baidu photo workflow and remains the preferred provider. The concrete evidence
is SearchApi's incorrect original-image mapping in ten of eleven inline entries;
this is a workflow decision from this sample, not a general uptime comparison.
SearchApi remains a possible alternative requiring image-mapping correction
and publisher attribution.
SearchApi added image discovery leads and was quicker in this sample; it did
not demonstrate additional accepted-photo coverage or closed-platform access.
Neither documented Baidu endpoint provides a human-photos-only filter.

The existing 20-staff gallery remains at 38 distinct photographs in 44 files,
including the seven labelled SerpApi additions. Its previous desktop/mobile
checks remain applicable because this comparison did not change its files.
Full staff-union acquisition and ongoing intake remain open in the
[G1 plan](../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md).

## Local evidence

`.context/g1-searchapi-baidu-test-20260930/` holds the request fixture, one-shot
runner, six redacted JSON responses, three usage observations, saved HTML and
its receipt, recovered image mappings, source/media manifests, both gallery
baselines, and `comparison.json`. The five new files are in its `media/`
directory. Firecrawl source evidence is under `.firecrawl/g1-searchapi-*`;
reused files retain their SerpApi provenance.

The owner's `SEARCHAPI_KEY` was read from `/Users/fuchitalee/.env.secrets`
and sent only to SearchApi in an Authorization header. Its value was not
printed or placed in project configuration. No database, scheduler, product
code, deployment, commit, or push changed.

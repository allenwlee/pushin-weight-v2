---
title: SerpApi and Baidu discovery under Chinese law
created_at: "2026-10-02T05:31:59+09:00"
sources_checked: 2026-10-02
status: research-for-legal-review
workstream: G1
jurisdiction: mainland-China
---

# SerpApi and Baidu discovery under Chinese law

SerpApi changes how we obtain search results. It does not, by itself, establish
permission under Chinese law to collect, retain, publish or analyze the people
and photos found through those results. Its U.S. Legal Shield expressly excludes
foreign-law claims and proceedings outside U.S. courts.
[Legal Shield scope](https://serpapi.com/us-legal-shield).

This note applies the earlier
[China compliance research](2026-10-02-051235-mainland-china-staff-data-and-travel-risk.md)
to our actual SerpApi/Baidu workflow. It distinguishes published provider terms,
saved project evidence and legal assessment. It does not determine that SerpApi
or our existing collection is unlawful, or certify either as compliant.

## What we actually used

SerpApi describes its Baidu endpoint as scraping Baidu search-result pages.
It is a SerpApi service, not a Baidu-issued API credential. The documentation
reviewed does not establish a Baidu authorization agreement; absence of such an
agreement from these pages does not prove there is none.
[Baidu Search API documentation](https://serpapi.com/baidu-search-api).

The saved September 30 test
records six searches, subsequent extraction of selected publisher pages through
Firecrawl, and separate image/video downloads. Two indexed WeChat links reached
verification screens and produced no images. The
October 1 follow-up
records additional searches and downloads; its last account observation was the
Free Plan. That is historical evidence, not a check of today's subscription.

Local evidence paths, relative to the authoritative fuchitalee checkout
(`/Users/fuchitalee/development/pushin-weight-v2`):

- September 30 test: `docs/analysis/2026-09-30-183447-g1-serpapi-baidu-media-test.md`.
- October 1 follow-up: `docs/analysis/2026-10-01-070200-g1-chinese-names-and-images.md`.

These supporting files are not published with this report and may not exist in
another clone.

| Stage | What the evidence shows | Legal significance |
| --- | --- | --- |
| Discovery | We submitted names and context to SerpApi for Baidu results. | Outsourcing the search does not establish rights to every returned item. |
| Source access | We then fetched selected publisher pages and media separately. | Those activities require their own assessment; a SerpApi search contract does not automatically cover another service or downloader. |
| Storage | Selected images and professional facts were saved in dossiers. | Source attribution and permitted retention/use are different questions. |
| Future use | Editorial illustration and possible facial matching were discussed. | A search result is not permission for either use; matching raises additional biometric questions covered in the companion report. |

## The provider's legal protection has a specific limit

SerpApi's terms, updated August 27, 2026, identify a Texas company. Section 13
offers qualifying recurring plans up to USD 2 million of U.S. Legal Shield
coverage, excluding Free, Starter and Developer plans. Coverage concerns
collection of public search data, excludes unlawful downstream use, and is
limited to U.S.-law claims in U.S. courts.
[Terms, section 13](https://serpapi.com/legal).

**Assessment:** this is a contractual protection with limits, not Chinese
regulatory approval. It cannot be relied on as a defense to a Chinese privacy,
copyright, national-security or immigration issue. The historic Free Plan
observation supplies no evidence of coverage for those test calls. Current
coverage would require the current subscription and applicable agreement.

## Chinese-law questions that remain

### Public professional information

PIPL Article 27 permits reasonable processing of lawfully public information,
subject to explicit objections and consent requirements where processing
significantly affects individual rights. Article 3 covers processing within
China and specified overseas activities involving mainland individuals.
[PIPL](https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm).

**Assessment:** a public company biography can supply evidence for a name or
role. It does not automatically authorize unlimited aggregation, evaluation,
redistribution or face recognition. A paid search invoice does not change that
question. Overseas processing is not automatically outside PIPL; the actual
purposes and territorial connection need review.

### Photos have separate rights

Civil Code Articles 1019–1020 regulate use of a person's recognizable likeness
and provide specified exceptions, including certain necessary news uses.
[Civil Code](https://www.cac.gov.cn/2020-06/01/c_15925617772683193.htm).
Copyright Law Articles 10, 24 and 26 separately address copying and online
communication, exceptions and licences.
[Copyright Law](https://www.ncac.gov.cn/xxfb/flfg/flfg_532/202103/t20210309_50530.html).

**Assessment:** the photographer's copyright and the depicted person's rights
are distinct. A company publishing a headshot, a search engine indexing it, and
our correctly identifying the person do not establish permission for every
reuse. Whether an exception covers a particular news illustration needs review;
calling the entire product news or research is not enough to settle it.

### Collection methods and other operators' data

The revised Anti-Unfair Competition Law, effective October 15, 2025, addresses
improper acquisition or use of other businesses' lawfully held data. Article 13
includes deception, coercion and evading or defeating technical management
measures, with harm to rights and disruption of competition among its elements.
[Official revised law](https://www.cnipa.gov.cn/art/2026/5/20/art_104_206437.html).

**Assessment:** public accessibility is relevant but does not conclusively
resolve every commercial-scraping dispute. The provision is not a blanket
finding that all scraping is unlawful. This review did not audit SerpApi's
Baidu retrieval methods and does not allege a violation. Using an intermediary
does not remove the need to assess source permissions and collection methods.

### Queries and results also pass through a foreign provider

SerpApi's privacy policy says search data is retained for 31 days and describes
international processing safeguards and an available data-processing agreement.
It says ZeroTrace prevents storage of search parameters, queries and results.
[Privacy policy, sections 9–11](https://serpapi.com/legal).
The Baidu endpoint documents ZeroTrace as an Enterprise-only option; availability
or activation for our account was not checked.
[Endpoint parameters](https://serpapi.com/baidu-search-api).

**Assessment:** person-specific queries and returned profiles belong in the
data-flow review. ZeroTrace may reduce provider retention; it does not prevent
the provider from processing the request or delete our saved copies. An
EU-oriented transfer clause is not automatically a Chinese transfer mechanism.
The provider's exact processing locations, its role and applicable PRC
requirements remain unresolved.

China's 2024 rules provide qualified transfer exemptions while preserving
applicable underlying duties.
[Cross-border provisions](https://www.cac.gov.cn/2024-03/22/c_1712776611775634.htm).
Do not assume either that every offshore search is prohibited data export or
that overseas retrieval exempts us from every Chinese rule. Operating the
workflow while physically in mainland China adds facts for that analysis and
for the separate tourist-visa question in the companion report.

## Practical conclusion for this project

SerpApi remains a possible discovery supplier; our earlier finding that it was
more reliable than SearchApi was a technical observation, not legal clearance.
The most useful next legal review would cover the actual sequence: named-person
queries, vendor retrieval, publisher downloads, storage, intended publication
and any proposed biometric use.

For that review, preserve original publisher links and acquisition records,
distinguish attribution from reuse permissions, and identify the current vendor
agreement, processing terms and plan. Prefer expressly licensed or
subject/company-supplied material where the permissions cover our intended use;
do not assume a company holds all relevant rights. These are recommendations
for consideration, not newly accepted collection rules or release gates.

No paid searches, credential reads, account changes, provider messages, new
person collection or database writes were performed for this note.

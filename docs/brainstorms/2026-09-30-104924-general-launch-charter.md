---
title: General Launch Charter
created_at: "2026-09-30T10:49:24+09:00"
status: active-requirements
---

# General Launch Charter

## Plain-English Summary

PushinWeight's general page is a public-facing AI news experience, drawing on
the project's translations, commentary, classifications, and headlines. Before
launch, the owner wants four capabilities: verified researcher identities and
photos, a distinctive multilingual editorial voice, topic histories behind
headlines, and controlled access for external agents through an API and MCP
(Model Context Protocol).

This charter records the shared requirements and open decisions for those four
workstreams. Sessions may work on different tasks and hand them to later
sessions. Use the [General Launch Index](2026-09-30-104924-general-launch-index.md)
to find the current task plans, owners, next steps, and session log.

The charter is maintained in place. Update it as the owner changes requirements;
Git preserves committed history. Distinguish owner requirements from proposed
approaches and unconfirmed findings. Creating these coordination documents does
not authorize collection batches, implementation, external publication, or
deployment. Retain any separate authorization the owner gives a working session.

## Purpose and scope

- **General:** the news experience for general readers; the active launch target.
- **Product:** the paid offering for AI labs; surrounding context, not part of
  these four workstreams unless explicitly added.
- **Dashboard:** primarily administrative use; surrounding context, not a
  redesign target in this charter.
- **Homepage design:** the initial prototype covers the first screen. Its
  proportions and interactions have not yet been accepted by the owner. Final
  URL allocation between general, product, and dashboard remains unresolved.
- **Launch:** all four G items are prelaunch requirements. They are not an order
  of execution. A requirement can be deferred only by a later owner decision.

This is a shared requirements document, not an implementation plan or a claim
about deployed behavior. Detailed task plans belong in `docs/plans/` and follow
the repository's Ollija plan-selection rules. Do not run plan creation merely
to maintain this charter or its index.

## G1 — Researcher identities and images

### Owner requirements

- **G1-R01 (expanded by the owner on 2026-09-30):** Comprehensively collect real,
  verified researcher photos for the union of staff accounts in Call A and
  staff accounts in the database, including database staff outside Call A.
  Count overlapping accounts once. The owner's expectation that many are
  Chinese nationals is context, not evidence of any individual's nationality
  or a filter on which staff receive assets.
  For the current Call A list, the owner's latest inclusion rule presumes every
  non-company account is a person; a missing database staff role does not exclude
  it. Preserve identity and employment uncertainty separately.
  The October 1 expansion in G1-R08 adds publicly identified official-site staff
  from the 15 China-based tracked brands, including people without X accounts.
- **G1-R02:** Verify each person's identity and name, including their Chinese
  name where applicable. Do not invent Chinese characters from a romanized
  name, or treat an uncertain match as verified.
- **G1-R03:** Persist the verified identity/photo records to the database and
  retain the evidence needed to inspect and correct a match. The storage design
  for image bytes and database references remains to be planned.
- **G1-R04:** These assets must support lighthearted AI-generated illustrations
  accompanying news items. Identity verification and permission/suitability for
  the intended reuse are separate questions that must be recorded.
- **G1-R05:** Provide an initial batch process to find and persist assets for
  the existing population in G1-R01, with coverage and unresolved cases recorded.
- **G1-R06:** Establish an ongoing process for staff added by the user or
  discovered through the personnel-change mechanism, with or without an X account.
  New arrivals must enter
  the same identity and asset workflow; a completed initial batch alone does
  not satisfy G1.
- **G1-R07 (owner direction on 2026-09-30):** Investigate deeper mainland-China
  photo collection integrations, including platform-specific APIs, paid data
  services, WeChat's agent functionality, and Chinese models' native search.
  Assess reusable patterns in top-gun and Scrolls; the owner corrected the
  earlier cross-post reference to Scrolls on 2026-09-30. Use official-doc and
  third-party GitHub crawls to distinguish consumer-app access, callable API
  capabilities, and retrieval of actual platform images. The owner considers
  the current collection approach insufficient. Provider and budget choices
  remain open until the research and proposed coverage test are assessed.
  The owner selected Baidu through SerpApi, replacing direct Baidu Cloud access
  after signup difficulty, and then supplied a SearchApi key for a comparison
  against the same sample. After that comparison, the owner identified SerpApi
  as the more reliable option for this Baidu photo workflow; it remains preferred.
  The owner subsequently requested a Phyllo test for Xiaohongshu search access
  and supplied account-setup screenshots. While awaiting Phyllo's reply, the
  owner requested a Firecrawl documentation assessment of Parse.bot's Xiaohongshu
  API. Parse.bot research does not authorize a live test or API revision.
  The owner then requested broader image/video acquisition through SerpApi,
  with the filtering method explained first, and restricted Baidu searches to
  Chinese people in the current list. This restricts the source used for this
  batch; other staff remain within the overall G1 population.
  The owner agreed to requesting up to 50 results per call and flagged noise
  from name-only searches. Preserve identity context while expanding retrieval
  depth; the detailed query method belongs in the G1 plan.
  The latest batch request is one search per remaining Chinese person. The
  owner then put searches on hold until the reported 77-member X list versus
  dossier coverage is explained, specifically citing missing `@Ronny_MiniMax`.
  Existing database staff-role assignments must not silently exclude unresolved
  people from the roster review.
  The owner subsequently authorized current list retrieval and dossier expansion:
  treat every account except official company accounts as a person. This private
  list belongs to `allenwlee`; use the owner's authenticated X access rather than
  TwitterAPI.io. Preserve uncertain names/affiliations as uncertain without
  excluding the person. On October 1 the owner resumed acquisition: find Chinese
  names for all 40 people, using Baidu if needed, update the dossier, then find
  their images. Distinguish sourced Chinese names from transliterations and
  unresolved aliases. The earlier asset-search hold is lifted; Baidu media
  collection remains Chinese-only, with other sources used for other people.
  The owner then requested repair of broken dossier image links and addition
  of all available X account profile images from stored records, including
  nonhuman avatars. Account images supplement the researched photographs;
  they do not establish the account owner's identity or resolve human-photo gaps.
  The owner also requested a suggested Xiaohongshu search phrase beside every
  dossier name for manual photo/video discovery; suggestions retain name and
  affiliation uncertainty and do not imply tested platform results.
  OpenCLI and Yuanbao tests remain deferred.
  Each provider's result/media coverage must be measured independently
  of the official Baidu AI Search API. This narrows the immediate experiment
  without removing the initial-batch or ongoing-acquisition requirements.
- **G1-R08 (owner direction on 2026-10-01):** Use the existing `people` identity
  model for staff, with optional real X-account links. Collect as many staff as
  the official websites of the 15 China-based tracked brands publicly identify,
  using the existing job-listing crawler instructions and applicable fetching
  patterns. Match existing people and account-linked identities before adding
  records; preserve unresolved matches and avoid name-only merges. Do not create
  placeholder accounts for people without X. Retain sourced roles, job history,
  exact organization wording, and observed/effective dates separately. The
  selected 15 brands and implementation details are in the G1 plan.
- **G1-R09 (owner direction on 2026-10-01):** Keep full names and add optional
  given/family name components for Chinese, English/romanized, and Japanese
  versions. Preserve aliases and uncertain splits; components are not required
  for importing a person. Rename `sexs` to `sex`, preserving existing values
  and related records, and update readers/contracts with the schema change.
  The latest request adds these changes to the plan; implementation is pending.
- **G1-R10 (owner direction on 2026-10-01):** Preserve Chinese originals from
  crawled people/job pages, including names, titles, organization/team names,
  descriptions and supporting evidence. Record actual source language separately
  from the person's primary language. Generate and save English or Japanese
  translations when needed for display, deriving each from the original and
  reusing it while that source version is unchanged. Translation must not replace
  the original, block source collection, or be presented as published name/role
  evidence. The owner explicitly selected translation on demand over translating
  both languages during collection or storing originals only.
  G1-R14 subsequently makes English-facing person names an intake requirement,
  outside this on-demand prose-translation policy.
- **G1-R11 (owner correction on 2026-10-01):** Make each dossier easy to audit:
  separate romanized name, Chinese name, Chinese job title and English job title,
  with a source for each and explicit title-verification status. Label translations
  and missing evidence. Every image must carry a short explanation of its identity
  evidence. Show actual Chinese-web search attempts and their outcomes; distinguish
  an unperformed search, an access failure and a completed search that saved no
  attributable photo. Require at least one fully source-verified individual
  portrait for each person. The owner explicitly treats photos directly from a
  confirmed personal X account or an official company bio page as qualifying
  sources. Account avatars that are logos, cartoons or unattributed groups do not
  satisfy individual-portrait coverage. Additional source-category choices belong
  in the test/plan until settled; report unmet portrait requirements explicitly.
- **G1-R12 (owner correction on 2026-10-01):** Contributors are not staff merely
  because they appear in a paper, report credit, repository or organization
  membership. Do not seek names, biographies, photos or videos for contributor-only
  people unless the owner specifically requests them. Apply this to both batch
  collection and new-person intake. A contributor with separate employment evidence
  can qualify through that evidence. Keep current claims, former staff and dated
  staff evidence with unknown current status distinct. Preserve existing contributor
  evidence as history, outside default staff views, active queues and staff coverage
  denominators. The 591 DeepSeek report entries are not an employee roster.
- **G1-R13 (owner execution direction on 2026-10-01):** Build the database and
  shared intake foundation first, use DeepSeek as its first end-to-end test,
  then expand to the other Chinese brands. Reuse the existing DeepSeek evidence
  to validate persistence, matching, job history, media provenance and dossier
  output; the prototype alone is not evidence that the database/intake foundation
  works. Preserve both initial-batch and ongoing-intake outcomes and the G1-R12
  contributor exclusion. The owner requests a short plan summary before starting
  implementation.
- **G1-R14 (owner correction on 2026-10-01):** English-facing person names are
  too important to defer until display. Research and persist the established
  English/Latin professional form during intake, alongside the original-script
  name and separate source evidence. Preserve unresolved gaps and distinguish
  a generated romanization from an attested spelling. The owner requests
  researched CJK guidance and an explicit column/count and primary-name design
  before the people-schema implementation. The linked G1 plan records the
  related-name schema; G1-R15 subsequently selects its structure and provenance
  requirements. Implementation remains pending.
- **G1-R15 (owner decision on 2026-10-01):** Include `Person`, `PersonName` and
  separate `PersonNameEvidence` records in the first DeepSeek scaffold, with
  simple links from generated or converted spellings to their originals. Keep
  full names and optional components, selected primary/English names and
  multiple source observations, including uncertain or conflicting claims.
  Preserve original excerpts, source/capture references, observation times,
  collection methods and review decisions with reasons. Evidence must connect
  the name to the person; name-only matches do not establish identity. Keep
  original publishers separate from search/scraping providers. Defer general
  provenance graphs, automatic confidence scoring and elaborate component-level
  review workflows. Final column details belong to scaffold implementation;
  this selection does not claim that a migration or production import has run.

### Proposed first step and completion evidence

Audit a dated roster before collection so comprehensive coverage has an explicit
denominator. Account for every entry as verified, unresolved, inapplicable, or
otherwise excluded with a reason. Require at least one source-verified individual
portrait per person under G1-R11; record remaining quality limits. Report name verification, photo verification, and reuse
eligibility separately; a downloaded profile picture does not establish all
three. Demonstrate that an approved identity/photo record can support the
intended illustration workflow.

Use stored profile and post history first, including metadata and personal links
behind alias accounts, then research remaining gaps. The initial batch must
cover database-only staff, Call A staff, and the G1-R08 official-site population.
Report accountless people and reused identities explicitly. Ongoing completion
evidence must include both a user addition and a personnel discovery reaching the
library automatically, with recovery for missed intake and failed source
requests. A personnel report may name someone other than its author; preserve
the subject's identity uncertainty instead of assigning the reporter's photo.

The [G1 plan](../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md)
defines the shared workflow and both deliverables. The completed public-source
sample is baseline evidence, not proof that the available photos are sufficient.
The owner's subsequent G1-R07 direction requires deeper mainland-platform
integration research. Full-population coverage and reuse eligibility remain
unestablished.

The [October 1 collection report](../analysis/2026-10-01-070200-g1-chinese-names-and-images.md)
accounts for all 40 people in the current-list dossier: 17 Chinese names,
eight published Chinese renderings, and 15 unresolved forms; 75 distinct
photographs cover 36 people. Four photo gaps remain visible. This local result
does not complete the database-only staff population or either ongoing intake
path, and does not settle the launch photo-quality or reuse criteria.

### Open decisions

Roster freshness and ongoing scan cadence; acceptable identity evidence; photo
quantity/quality; handling unavailable Chinese names; durable image storage;
source budgets; rights and reuse evidence; illustration labeling and editorial
boundaries; whether any unresolved entry blocks launch. The union population
and two required acquisition paths are settled. Do not silently replace the
comprehensive requirement with a convenient subset.

## G2 — General-page editorial voice

### Owner requirements

- **G2-R01:** Develop an English voice combining Variety's insider fluency,
  abbreviations, and industry terminology with the New York Post's irreverence,
  directness, and attention-getting writing, without excessive clickbait.
- **G2-R02:** Use Togetter as a reference for Japanese headlines.
- **G2-R03:** Research an appropriate Chinese voice that triangulates between
  the Variety and New York Post directions. Do not assume a literal translation
  of the English style resolves this requirement.
- **G2-R04:** Make the resulting guidance usable across general-page headlines
  and commentary, including the longitudinal experience.

### Proposed first step and completion evidence

Create a bounded comparison packet using the same underlying stories in English,
Chinese, and Japanese. Research real examples from the named publications and
candidate Chinese references. Let the owner judge rendered examples before
turning them into prompt/style rules. Preserve approved examples, terminology,
and distinctions between fact, allegation, inference, and editorial attitude.

Before open-ended evaluation begins, freeze the sample, evaluation criteria,
iteration limit, and spending limit. Completion requires owner-approved examples
and evidence that the selected guidance reproduces the intended voice on
additional stories without changing their factual meaning.

### Open decisions

Chinese publications/references; how much insider shorthand general readers can
handle; when acronyms need explanation; acceptable irreverence; story/headline
lengths; transliteration and proper-name conventions; tone across languages and
professional/general reading modes.

## G3 — Topic history and longitudinal reporting

### Owner requirements

- **G3-R01:** Each headline on the general page needs an icon through which a
  reader can inspect the longitudinal trend of its topic.
- **G3-R02:** The history must use database evidence. Its generation and serving
  may be dynamic, lazy-loaded, or saved, depending on resource use.
- **G3-R03:** Build on the existing longitudinal research: help readers understand
  how the evidence and explanation of a topic changed over time.

### Proposed first step and completion evidence

Prototype one topic across several headlines. Show the difference between a
discussion-volume chart and an explanation of what changed, when, and why. Make
source support, uncertainty, and insufficient history visible.

A starting proposal is a shared topic history generated on first request, saved
for reuse, and refreshed when relevant evidence changes; popular topics might
be prepared ahead of time. This is an unapproved implementation hypothesis to
measure, not a settled architecture. Completion evidence should cover topic
continuity, supported changes, source traceability, freshness, corrections, and
bounded latency/cost.

### Open decisions

Topic identity and merging/splitting; history time windows; graph versus narrative
presentation; drawer versus separate page; refresh triggers; correction handling;
resource budgets; and behavior when history is unavailable. Final product
decisions belong in the task plan before implementation.

## G4 — Public API and MCP

### Owner requirements

- **G4-R01:** Provide a way for users to connect agents to PushinWeight through
  an API and MCP.
- **G4-R02:** Stay within strict compliance with applicable X and TwitterAPI.io
  terms of service/use. Start from the repository's compliance materials and
  verify relevant current terms before concluding that a proposed output is
  permitted.
- **G4-R03:** External users must not receive actual post text. Author/account
  identity, including usernames, must be obscured.
- **G4-R04:** The intended useful outputs include commentary and classifications.
  Links to underlying X posts are allowed by the owner's requested product
  boundary, subject to the compliance review in G4-R02.
- **G4-R05:** Apply the content boundary to every externally exposed response,
  including generated prose and metadata; removing named database fields is
  insufficient if other output repeats the same prohibited content.

### Proposed first step and completion evidence

Define an explicit permitted-output contract before building the external
interface. Check it against current provider/platform terms. Keep approved
public outputs distinct from internal source records and G1's identity library.
Demonstrate useful agent requests and negative cases that exercise leakage
through commentary, classification evidence, errors, and metadata, alongside
access and resource limits. Define correction/deletion behavior where required.

### Open decisions

An X source link can reveal its author when followed. Clarify the distinction
between omitting identity from our response and promising anonymity; do not
claim both a discoverable source link and guaranteed anonymity. Decide which
classifications and commentary are permitted, at what granularity, and whether
some outputs require aggregation or redaction. Authentication, rate limits,
commercial access, source changes, and permitted use by downstream agents also
remain to be specified. Redaction alone is not a compliance determination.

## Shared boundaries and dependencies

| Shared subject | Coordinating workstream | Other consumers |
| --- | --- | --- |
| Verified person identity and photo provenance | G1 | Personnel news and illustration workflow; G4 must enforce its own output boundary |
| Editorial voice and terminology | G2 | Chatter, headlines, G3 history, and permitted G4 commentary |
| Continuing topic identity and supporting evidence | G3 | Headlines, history UI, and any approved G4 topic tools |
| Permitted external content | G4 | G3 if histories are agent-accessible; any other externally exposed content |

G1's identity records must not automatically become agent-accessible because they
exist in the database. Similarly, an editorial treatment approved for a named
person's news article does not automatically satisfy G4's obscured-identity rule.

Proposed sequence: investigate G1 coverage and G4's permitted-output boundary
early; research G2 alongside them; then exercise one G3 story with the emerging
voice and public-output constraints. Independent progress is allowed. Do not
invent a dependency merely because two tasks share a branch, environment, or
session.

## Homepage context carried forward

The owner supplied a first-screen sketch with Chatter on the left, a chart and
scrolling news area on the right, then Calendar, Free Stuff/Jobs, and Who's Moving
below. The design references Polymarket's rounded white frames, borders, chart
colors, transitions, and automatic headline scrolling. Each major section needs
sharing. Images and video surfaces need rounded edges; personnel images should
be full bleed, as in the supplied Facebook reference. Chatter should wrap text
around the changing transparent silhouette of a generated image; the prototype
uses a conceptual Meta Muse illustration.

These are owner design instructions. The prototype uses illustrative data and
sample personnel; it is not a source for production facts or a selected final
design. Language controls currently demonstrate navigation labels only.

## Maintaining this charter

- Keep requirement IDs stable. New requirements receive new IDs. Explicitly mark
  withdrawn or replaced requirements and link to their replacement where needed.
- Update this document in place; no frozen-version or immutable-file procedure
  is required. Never turn an agent suggestion into an owner decision silently.
- Record material shared-scope changes in the index log with their authority and
  affected G items. Update the affected task plans without copying this whole
  charter into them.
- Current explicit owner instructions take precedence. Recording an instruction
  is not an additional authorization gate.
- Commit, push, collection, deployment, and production activation require the
  applicable session authorization; a readiness checkbox supplies none.

## Source map

- [General Launch Index](2026-09-30-104924-general-launch-index.md)
- [Longitudinal and agentic-media research](../research/2026-09-28-111844-agentic-ai-media-advantages.md), especially section 4 and Appendix A.
- [TwitterAPI.io compliance materials](../external_vendors/twitterapi_docs/compliance/)
- [X compliance materials](../external_vendors/x_twitter/compliance/)
- [Prototype decisions and limitations](../../.context/compound-engineering/ce-prototype/2026-09-29-general-homepage/decisions.md) — local, ignored artifact on fuchitalee.
- [First-screen prototype](../../.context/compound-engineering/ce-prototype/2026-09-29-general-homepage/01-above-the-fold/screens/index.html) — local, ignored artifact; a preview server may need restarting.

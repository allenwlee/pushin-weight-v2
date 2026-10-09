---
title: General Launch Charter
created_at: "2026-09-30T10:49:24+09:00"
status: active-requirements
active_round: 2
---

# General Launch Charter

## Plain-English Summary

PushinWeight's general page is a public-facing AI news experience, drawing on
the project's translations, commentary, classifications, and headlines. Before
launch, the owner wants five capabilities: verified researcher identities and
photos, a distinctive multilingual editorial voice, historical comparisons
supporting predictions, and controlled access for external agents through an API and MCP
(Model Context Protocol), brought together through the general-page design and
integration workstream. The page and its prototype will keep evolving.

This charter records the shared requirements and open decisions for those five
workstreams. Sessions may work on different tasks and hand them to later
sessions. Use the [General Launch Index](2026-09-30-104924-general-launch-index.md)
to find the current task plans, owners, next steps, and session log.

The charter is maintained in place. Update it as the owner changes requirements;
Git preserves committed history. Distinguish owner requirements from proposed
approaches and unconfirmed findings. Creating these coordination documents does
not authorize collection batches, implementation, external publication, or
deployment. Retain any separate authorization the owner gives a working session.

## October 9 next-round intake

The owner closes the first G1–G5 round, accepts unfinished work moving into round
two, and requests round-one compounding to inform the new work. The
[round-one closeout](../analysis/2026-10-09-110145-general-round-one-closeout.md)
records actual outcomes; the [round-two register](2026-10-09-110145-general-round-two.md)
is the fresh scope and carry-forward record. Every unmet, non-superseded owner
requirement below transfers to its assigned stream. Prior proposals stay
proposals, and waived/excluded work is not reinstated. The
[index checkpoint](2026-09-30-104924-general-launch-index.md#october-9-round-one-checkpoint-and-next-round-proposal)
preserves the pre-rollover audit of delivered code, completed research/planning
and locally verified work. Ending round one does not establish that every earlier charter
requirement is implemented or that the General redesign is in production.

### G1 session continuity

Before resuming G1 round two, read the existing register's
[G1 session-clear handoff](2026-10-09-110145-general-round-two.md#g1-session-clear-handoff--october-9).
It carries the locked staff-roster decision tree, the uncommitted filing step
on collect-chinese-workers, and the boundary between filings, a lab's own
named report, staff-role accounts, and leads. Clearing chat does not select
a graphics implementation, a new collection, a production write, or a release.

### G3 session continuity

Before resuming G3 round two, read the existing register's
[G3 session-clear handoff](2026-10-09-110145-general-round-two.md#g3-session-clear-handoff--october-9).
It carries the chart-engine priority, delivered benchmark dependency and pending
window migration, inherited statistical/scenario requirements, Kalshi support
workflow, dated settlement-source research and retained local artifacts. Old
benchmark-wait wording is historical; delivered charts are not proof of a trained
forecast engine. Clearing chat selects no implementation or release endpoint.

The [G3 workspace rule](2026-10-09-110145-general-round-two.md#round-two-working-directory--owner-decision)
places implementation in G3's assigned round-two worktree. Read shared knowledge
from the authoritative root; update shared coordination there and return to the
G3 worktree for implementation. Its exact path/branch remain to be assigned.

### G5 session continuity

Before resuming General-page work after the session reset, read the existing
round-two register's [G5 session handoff](2026-10-09-110145-general-round-two.md#g5-session-handoff--october-9).
It records the accepted design and exact control wording, local implementation,
published-content/URL behavior, preview and isolated database, retained evidence,
domain purchase and outstanding round-two work. The round-one plan stays closed;
its dirty G5 worktree remains the implementation source. No delivery endpoint is
selected by this continuity note.

### Owner-set vocabulary

- **Content** is the atomic, independently addressable unit and umbrella term
  for third-party **posts** and PushinWeight **original content**. Keep those
  two kinds distinguishable. This vocabulary does not select another database
  parent table or replace the existing `Post`/`OriginalContent` storage contract.
- **Graphics editor**, **graphicsed**, **pics editor** and **picture editor**
  name the same editorial role. The new names do not create a second worker or
  independently funded generation pipeline.

### Owner priorities for the next round

1. Develop the GLM-5.3 release/data-source chart into a reusable **chart engine**
   with the interactive capability expected of the existing homepage line chart.
   Build on the deployed benchmark/usage readers and existing chart behavior;
   the chart is no longer just one manually configured release example.
2. Define the editor's rules for choosing a chart and its settings for a content
   item. Specify the **chart-setter** role that sets its variables according to
   that item's subject and claims.
3. Make a chart shareable with its settings intact. Coordinate the saved chart
   state with the content's permanent identity and language.
4. Accompany **every content item** with an image or video. The owner-specified
   fallback order is a relevant person's picture when available, then the
   source post author's profile picture, then the relevant company logo.
5. Establish a graphicsed guide for selecting and creating assets. The handling
   of multiple source authors and the last fallback when all three choices are
   missing need decisions; a generated or branded title card is a proposal,
   not an already selected policy. Asset presence alone does not establish
   subject identity or permission to reuse it.
6. Develop **Japanese (`ja`) and Simplified Chinese (`zh_cn`) house voices**.
   Existing source-faithfulness rules still apply to commentary on third-party
   posts; the house voice applies within G2's established original-content scope.
7. Brainstorm robust sharing for content and charts, including direct sharing
   on X, images/video, native playback and preservation of the shared language.
   Research current X technical requirements and use rules as part of that work.
8. **Option raised by the owner:** require users to sign in to PushinWeight
   with X and grant appropriate OAuth permissions. This is an option to assess,
   not a selected mandatory login policy. Distinguish account login from the
   user's permission to upload media and publish a specific post.

The round-two register uses the five-session split for organizing these
priorities and inherited work; precise implementation boundaries belong in the
subsequent bounded plans. Version `0.2.0b2` remains the proposed next beta.
This intake does not select implementation, paid trials, account access,
external posting or a release endpoint. Round-one lessons map to specific
round-two items in the closeout; use those mappings when writing the plans.

## Purpose and scope

**G1-R16 owner amendment (2026-10-08; U21):** The owner accepts the five-offering classifier and authorizes direct production deployment plus induction of the exact123 frozen accounts into Call A. Apply `model-llm`, `model-other`, `agent`, `harness`, `other` and attributable multi-offering evidence to the recurring extractor; these remain internal screening labels, with canonical product taxonomy changes separate. Record cohort approval independently from model findings, preserve native identity/suppression/list safeguards, and retain human/HF review for future unapproved positives. Require exact live source, independent123-member readback and natural-cycle collection proof. Preserve completed benchmark and concurrent G2 schema/storage changes, other sessions, budgets, credentials and normal cron. The completed v3 frozen report remains historical.

- **General:** the news experience for general readers; the active launch target.
- **Product:** the paid offering for AI labs; surrounding context, not part of
  these five workstreams unless explicitly added.
- **Dashboard:** primarily administrative use; surrounding context, not a
  redesign target in this charter.
- **Homepage design:** G5 owns the evolving general page and its integration.
  The initial first-screen prototype is the starting reference; adding G5 does
  not approve every existing proportion or interaction. Final URL allocation
  between general, product, and dashboard remains unresolved.
- **Launch:** all five G items are prelaunch requirements. They are not an order
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
  The October 5 display correction requires explicit name-field types and
  verification: distinguish personal/professional names, aliases, account display
  names, handles, generated romanizations and avatars. Show the actual saved
  table.column where evidenced, distinguish dated database snapshots from live
  state and proposed import targets, and never treat a verified alias as a
  verified given name or surname.
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


- **G1-R16 (owner direction updated 2026-10-06; independent ingestion support for G2):** Implement `official_co_account_extraction` in its independent branch: (1) one-time resumable scan of the entire stored author population and available post/profile evidence, without a 30-day or other age cutoff, to identify official AI labs developing/releasing any kind of AI model (LLM and non-LLM); (2) a separate incremental extractor with the existing 15-minute harvester for newly stored authors and materially changed evidence. Register settled official company/brand accounts and synchronize them to the existing Call A private X list. Preserve person-focused affiliation extraction. Reflection, Aleph Alpha and Bad Theory Labs are owner-verified positive examples; include unseen closed/pre-release and non-LLM labs, without Business badge, HF or open-weight requirements. Report full-scan coverage, evidence, uncertainty, retry/funding state and stable identities. Owner authorizes LFG through production activation plus verified collection; local owner list read/write is already proven, encrypted runtime provisioning and live renewal were verified on 2026-10-07; initial coverage, list outcomes and collection proof remain. Owner selected encrypted PostgreSQL storage for rotated X tokens, with a dedicated encryption key and matching client configuration in Render secrets (2026-10-06). This supports G2 collection and shares G1 identity records; single-post Chatter/Pulse admission stays separate. Coordinate additive account references and migration ordering with the actively implementing benchmark/account branch, without importing its taxonomy migration. [Implementation plan](../../.worktrees/feat/official-co-account-extraction/docs/plans/2026-10-06-100039-feat-official-co-account-extraction-plan.md).

- **G1-R16 owner pause and filtering direction (2026-10-07):** Official-company initial scan and ongoing extraction/registration/list sync are paused; normal harvesting remains active. Preserve enumeration/queue/evidence and encrypted credentials. Before resuming, reduce the roughly 91k author population with inexpensive stored-evidence filters grounded in the three settled examples, measure their retained coverage and include counterexamples. Do not require multiple stored posts: Reflection and Aleph Alpha each have only one. Flat bios are blank but nested post-author bios and expanded company domains are present. Gold/business verification is a standalone evaluation entrance and gets top queue priority (owner direction); it does not itself prove AI model development or authorize registration. There are 733 stored Business accounts in the original 91,028-author population. This revises the initial approach; read-only filter research does not authorize restarting collection or model evaluation.

- **G1-R16 candidate-filter measurements (2026-10-07, recommendation):** Original91,028-author population: gold733 is the owner-settled first entrance; proposed development-bio/external-website tier adds3,022, and organization/domain/release alternatives add3,955, yielding7,710 candidates (91.53% reduction) with all three examples retained. First two tiers total3,755. Two-stored-post gate retains36,384 but misses Reflection and Aleph Alpha. These filters still admit some individuals; final official/model-developer decisions remain necessary. Alternate tiers are recommendations, not deployed filtering; preserve deferred records and reuse existing settled mappings. [Measured evidence](../../.worktrees/feat/official-co-account-extraction/docs/analysis/2026-10-07-103605-official-company-candidate-filter-measurements.md). Extraction remains paused.

- **G1-R16 filtered restart authorized (2026-10-07):** Owner accepted the measured three entrances and said “ok let's run it.” This supersedes the official-company feature pause above. Screen the entire original database population cheaply, preserve deferred accounts and the old checkpoint, and model-evaluate selected candidates. Business/gold alone admits an account and takes first queue priority; badge-free development-bio/website and organization/domain/release entrances retain the three settled examples. Resume extraction, registration and Call A list synchronization after the filtered revision is observed deployed. Normal harvesting remains active. The cached features predict 7,710 candidates; report live selected counts and actual evaluation/registration/list-add progress separately from whole-population screening. Full collection proof remains the original endpoint.

- **G1-R16 live acceptance repair (2026-10-07, 11:40 JST):** Filtered revision `4ad401ce` is live; gold staging covered 733 accounts and the 02:26 UTC inventory observation covered 2,500/91,028 authors with 872 selected. NEAR Protocol was incorrectly accepted from a system using DeepSeek. The owned initial job was canceled and registration/list additions temporarily held for repair; discovery and normal harvesting remain active. Its unsupported list addition was removed with complete owner-authenticated membership readback, and only its two newly created official account edges were removed. Preserve entities, immutable model attempt and addition timestamps; state/intent remain for review. Reflection and Aleph Alpha settlements remain. Test the model-development evidence boundary before restoring additions and resuming the same filtered checkpoints. Full coverage and verified subsequent collection remain open.

- **G1-R16 qualification amendment (owner direction, 2026-10-07; U15):** A company qualifies if it develops at least one of: an AI model (proprietary or derivative of an open-weight model), its own proprietary agent, or its own proprietary harness. These are alternative routes; an agent/harness can use another publisher's model without developing an underlying model. A harness means company-developed software that runs, orchestrates or controls models/agents. Require attributable development evidence and a separately supported official account; generic AI usage, hosting, resale or unchanged mirrors do not establish development. Fine-tuning and attributable quantized derivatives belong to the model route; do not exclude the company's own developed model solely because its release is quantized. HF is an optional evidence source for all three routes. Model developers, including closed-weight developers, qualify without an HF page or public weights; agents/harnesses likewise need no HF page. "Proprietary" does not impose an additional closed-source-license requirement. This supersedes the model-only population and wrapper exclusions in earlier G1-R16 wording. Ordinary non-HF positives retain human settlement; the existing HF shortcut bypasses review. Earlier implementation-only HF badge/X-link/card-credit restrictions must be reconciled with the owner's HF-company-page-with-models rule, rather than treated as owner-approved eligibility. Version the policy, cheaply re-screen deferred authors and reconsider affected prior decisions without erasing history/suppressions or launching91k model calls. The plan records caller-level regression and activation requirements. Current deployed1243ba01/source-pinned scan still enforce the narrower rule; this amendment is documentation, with implementation/activation pending. Preserve normal cron, scan checkpoints/budgets, credentials and other sessions.

- **G1-R16 original human review boundary (historical owner decision, 2026-10-07; qualifying HF exception now supersedes blanket review):** The owner accepts NEAR-style false positives as candidates for review and selects the original v2 evaluator. Every new model-positive account requires human settlement before registration/list addition. Preserve the three previously explicit owner settlements. This supersedes the stricter v3 prompt repair and zero-false-positive activation gate; no extra paid prompt experiment is required. Preserve evidence, immutable model decisions and saved population/gold checkpoints; expose review-needed candidates on `/admin`, including those with no list intent. Resume the full filtered scan through the existing direct production route with registration/list-sync flags false and normal harvesting unchanged. New company approval and later collection are separate owner-reviewed actions; do not silently approve a candidate to satisfy a delivery check.

- **G1-R16 independent execution and admin tracking (owner follow-up, 2026-10-07):** Decouple initial cheap screening/model evaluation from the harvest writer lock while retaining one discovery evaluator, fenced row claims and budgets. Scheduled incremental discovery and the initial job share their own nonblocking lock; normal collection stays on its existing lock. Track selected candidates and their queue/results on `/admin`, with screening, selection, actual model decisions and owner settlements counted separately; preserve the found-account/list-history table. Identity schema, taxonomy and normal cron remain unchanged. Ordinary model positives require human settlement; the later verified-HF exception permits automatic settlement. Owner adds model-development verification examples and a higher technical-evidence hurdle for any blockchain/Web3 mention. HF hosting alone is insufficient; actual own-model training/fine-tuning qualifies even for blockchain-associated labs (Nous/Hermes is a documented counterexample). Existing official brand/company links skip paid rediscovery and are visible in admin; missing account links remain unconfirmed. Bounded HF checks run through the same initial and recurring helpers. A verified HF organization must identify the exact X account (or its verified research publisher must share its company domain and related name), publish a model artifact, and explicitly credit its own development in a pinned model card. Those accounts bypass human review via a dedicated-key signed receipt; other candidates remain reviewable. No global HF crawler or schema migration is introduced.

- **G1-R16 live human-reviewed scan (2026-10-07, 14:24 JST observation):** Original v2 evaluator and mandatory human settlement are live at `d66d8508` on production web/harvest. Owned source-pinned initial job is running from saved checkpoints, registration/list-sync false, normal15-minute cron unchanged. Cheap whole-population screening is 6,500/91,028 with 1,114 selected;733 gold accounts were staged first. Screening counts are not paid evaluation counts. Runway/SambaNova retain positive decisions and now require human review; owner settlements remain. Zero new unsettled official edges/list intents observed after activation. Full scan and subsequent owner approvals/collection proof remain open; latest20-post enrichment is still unhealthy. No staging, taxonomy or account-key change.

- **G1-R16 evaluator gate result (2026-10-07, 12:08 JST; historical, superseded by the human review boundary above):** Independent review found stale v2 acceptances could register after activation and the first frozen pass graded labels without validating development citations. Local repair requeues stale non-owner acceptances; owner settlements and stable evidence identities are preserved. Final regression suite passed228 tests, including194 required PostgreSQL checks with zero skips/errors. The second/final evaluator variant passed11/12 with zero unsupported acceptances but held Bad Theory Labs despite its fine-tuning intent. Both variants/24-call limit are exhausted; registration and list synchronization remain disabled, the initial job remains canceled, and production remains4ad401ce. Discovery and normal15-minute harvesting continue. Frozen filtered coverage remains2,500/91,028 enumerated,733 gold staged,872 selected. Plan and evidence retain the failed gate; no deployment or new paid experiment. A new bounded evaluation must address first-person planned fine-tuning while excluding mere model use. Full scan and verified collection remain open.

- **G1-R16 admin history addition (owner direction, 2026-10-07):** Record X accounts added to Call A's private list on `/admin`, the owner-selected renamed product-review inbox. Distinguish actual additions from already-present members and uncertain requests later confirmed by readback, with stable account identity, organization, timestamps and outcome. Preserve existing access controls and exclude credentials. Retain product approval, owner/staff permissions, old-link redirects and usable already-open forms. Show found accounts and durable list history in the table, with whole-population pending/coverage totals separately so queued authors do not bury companies. This does not authorize redesigning the general page, `/internal/` or `/dashboard/each`.

- **G1-R16 admin category separation (owner direction, 2026-10-07; U16):** Add Failed evaluations and Already tracked tabs to `/admin` and exclude both from Review needed. Failed evaluations show the latest failed attempt for current evidence, retry-pending failures and evaluation blocked by limits; historical/recovered failures do not qualify. Already tracked uses existing official brand/company links or the recorded skip marker, excludes settled Found identities and takes precedence over failures. Show category counts, recorded errors and existing links, preserve fixed filters/search/pagination/locales/auth and product approvals. Keep Found, Scan queue and List history. This is a read-only reporting change; do not change underlying scan outcomes, qualification policy, jobs, credentials or normal collection. U15's broader company definition remains a separately recorded implementation requirement.

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

The [G1 plan](../plans/2026-09-30-022746-docs-general-launch-coordination-plan.md)
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

### October 5 shared media storage decision

The owner selected Cloudflare R2 for shared G1 staff-original and G2 generated
media storage, accepting a bounded follow-up in the existing G1 plan with a
fresh implementation branch/PR and staged production rollout. G1 owns the
shared storage setup, migration and verification; G2 owns editorial integration
and authorized direct media delivery. Preserve existing database object
references and source/derivative separation, isolate staging from production,
and verify access from both web and worker services. The October 4 scaffold
release remains complete. Storage readiness does not enable paid collection or
media generation. The first requested deliverable is a G2 handoff; R2 is not
implemented or live at this decision point.

### Open decisions

Roster freshness and ongoing scan cadence; acceptable identity evidence; photo
quantity/quality; handling unavailable Chinese names; media retention and URL lifetime;
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
- **G2-R04 (clarified by the owner on 2026-10-05):** Apply the editorial voice
  to general-page headlines and bylines, and to editorials, summaries, and
  other editorial writing built from one or more post-level commentaries,
  including the longitudinal experience. A story can be based on a single
  source post. Individual-post commentary is outside this voice
  boundary; G2-R05 governs it. The two-track direction in G2-R36 limits the
  New York Post-style treatment to Chatter. Pulse uses standard factual
  headlines and supporting lines, not tabloid wordplay.
- **G2-R05:** Individual-post commentary must have no imposed PushinWeight
  editorial voice. Remain as faithful as possible to the underlying source's
  meaning, voice, stance, attribution, and uncertainty; do not flatten the
  source's own tone or add publication attitude.
- **G2-R06:** Generate Japanese and Simplified Chinese post-level commentary
  directly from the original post and its supplied source context, rather than
  translating generated English commentary. English commentary must likewise
  remain grounded in that source context. This defines the source of meaning,
  not a requirement for a separate model call for each language.
- **G2-R07 (clarified by the owner on 2026-10-05):** The atomic unit is one
  original source-platform post: currently one X post; future sources include
  individual Substack posts, YouTube videos, Instagram posts and other platforms.
  Its text and attached media supply the source evidence. Post-level commentary
  is a derived, source-faithful interpretation attached to that unit, with locale
  and version retained. Chatter and Pulse stories aggregate one or more of these
  commentaries and retain access to their original evidence. Preserve attribution,
  uncertainty and factual scope across these three layers: source post,
  commentary and editorial story. Future platform support is planned scope,
  not a claim that those collectors or storage contracts already exist.
- **G2-R08:** Keep model-call costs constrained when designing, evaluating, and
  operating these capabilities. Account for calls, input/output tokens,
  retries, and refresh frequency. On October 5 the owner selected a combined
  **$5/day** ceiling for G2 editorial selection, writing and generated media.
  Existing accepted stories remain visible when new paid work is held by the cap.
- **G2-R09:** Begin with English. The owner's selected emphasis is catchy,
  punning, tongue-in-cheek New York Post headlines and supporting headline
  lines (called "bylines" in the request). First research available corpora
  containing the original Post headline and its subject matter, preferably
  paired with New York Times, Washington Post, CNN, or BBC coverage of the same
  event. This sequencing does not remove the Chinese/Japanese requirements.
- **G2-R10:** Before further corpus work, prepare a bare CLI test using the
  owner's exact New York Post print-headline prompt and six supplied X links.
  Preserve the bare prompt and each run's original response before adding
  examples or further voice instructions. The owner subsequently selected two
  independent Codex runs: `gpt-6-astra` at high reasoning and `gpt-5.6-luna` at
  medium reasoning, saved as separate result files. Grok runs are recorded
  separately from these Codex runs.
- **G2-R11:** After the link-only tests failed to read the X posts directly,
  the owner requested a rerun using actual post content. Retrieve the six posts
  through TwitterAPI.io with the on-demand credential. The initial ceiling was
  30 direct physical calls; the owner later increased it to 100 cumulative calls
  across this session's retrievals, including the 13 already used, failures,
  retries, pagination, and context lookups. Preserve the source evidence and give both Codex models the same
  complete input. Provide the identical prompt/source paths for the owner's
  independent Grok test. Keep original failed-access results distinct.
- **G2-R12:** For the rerun, inspect other posts around each source post's
  publication time to recover nuance, corrections, jokes, and follow-ups.
  Advanced keyword searches or other appropriate post/context lookups are
  allowed within the current cumulative ceiling in G2-R11. Pull attached images for context
  and provide the same evidence and images to the model comparisons. Preserve
  the distinction between the six source posts, nearby context, and any
  unavailable media.
- **G2-R13:** The six-link test requires six separate headlines, one for each
  original post. The owner identified Luna's combined headline as missing the
  assignment. Make the count explicit in a separate correction prompt; retain
  the earlier prompt and outputs as historical evidence. Check six-post coverage
  before presenting a corrected result as complete.
- **G2-R14:** Use the owner's selected examples from the saved tests: Astra
  headlines 1, 3, and 5, and original Grok headlines 3 and 6 (WHAT THE HOP? and
  CODE RED, SIX WEEKS LATE, confirmed by the owner). Create a new editorial brief
  and run Luna in a fresh session. The selected examples are the intended prior
  material; exclude other prior responses, earlier Luna outputs, model rankings,
  and evaluation notes. This replaces the immediately preceding request to
  resume web corpus selection. Preserve the new brief and unchanged run output
  separately from the earlier bare-prompt tests.
- **G2-R15:** The owner rejected the example-guided Luna/medium output as below
  the desired standard: THRIFT STORE, RICH-LIFE! lacks a recognizable English
  basis or double meaning, and BUNNY IN DISGUISE! lacks wit. Evaluate meaningful
  wordplay or irony tied to the story, not merely a short, headline-shaped phrase.
  Explore cheaper ways to reach the preferred Astra quality, including the
  owner's suggested Luna high/xhigh reasoning settings; retain bounded calls
  and cost accounting. Higher effort is an experiment, not an accepted solution.
- **G2-R16:** The owner supplied nine new X posts and explicitly delegated
  separate `gpt-6-astra` / `high` and `gpt-5.6-sol` / `medium` tests. Reuse the
  five-example brief, changing the assignment count to nine; retrieve the actual
  new posts with nearby context and images under G2-R11/R12. Give both models
  identical supplied evidence and images in fresh sessions, excluding other
  prior results. Save nine headline/supporting-line pairs per model in separate
  new files, preserve original outputs, and copy the review files to
  `allenwlee:~/Downloads/agents/`. This is additional to the bounded Luna effort
  comparison and grants no runtime or release authority.
- **G2-R17:** The owner judged the five-example runs weaker than the original
  outputs and suspects the examples constrained the writing. Rerun the same
  nine-post test on `gpt-6-astra` / `high` and `gpt-5.6-sol` / `medium` with the
  original bare editorial instruction and no style examples, later editorial
  brief, prior responses, or owner evaluations. Reuse identical retrieved source
  evidence and images, preserve each first response in a separate new report,
  and copy both reports to the existing review destination. The owner's quality
  judgment is recorded; the examples' causal effect is not yet established.
  After Sol returned one combined cover headline, the owner explicitly requested
  a further Sol rerun for nine headlines. Add only a nine-headline count/order
  instruction to the original prompt, keeping examples and added style guidance
  absent; preserve the one-cover response separately.
- **G2-R18:** Distinguish announcements of underlying news from humorous or
  sarcastic reactions to that news when preparing headline inputs. Identify
  what the headline is about before writing it; an event and a meme/reaction
  about that event can be different editorial subjects. The owner attributes
  part of the mixed test quality to treating these alike. This is a diagnosis
  to evaluate, not a demonstrated causal result or a request for more style
  examples. Preserve faithful post-level commentary under G2-R05–R07.
- **G2-R19:** Give images explicit weight alongside accompanying text. Visual
  content can carry the central joke or meaning, rather than merely illustrate
  it. Preserve what is directly visible separately from interpretations and
  source claims. This requirement does not prescribe a separate model call for
  every image; the cost boundary in G2-R08 still applies.
- **G2-R20 (cadence clarified 2026-10-02):** The intended general-page assignment is one headline and supporting
  line for the highest-ranked worthy event or meme, reconsidered every 15
  minutes under G2-R33 rather than necessarily replaced each interval. All
  collected posts associated with that subject are available as the evidence
  pool, including the faithful post-level commentary, source material, reactions,
  and relevant images. This changes the production writing unit from each
  supplied post to the selected subject. The owner proposes keyword/semantic
  grouping with classification and post volume, prioritizing events, personnel
  changes, and releases; reaction/opinion activity could indicate interest when
  engagement measurements are unavailable. The grouping method, score, and
  thresholds remain open. Reaction volume is not independent verification of
  the underlying claim. Coordinate continuing subject identity with G3.
- **G2-R21 (2026-10-01):** The owner authorized the multi-candidate diagnostic
  across eleven exact settings: GPT-6.1-Sol/xhigh; GPT-6-Astra/medium, high,
  xhigh, ultra; GPT-6-Sol/medium, high, xhigh; GPT-5.6-Sol/medium, high; and
  GPT-5.6-Luna/high. The owner then selected only Wang's outfit-price correction
  as the subject. Generate eight new headline/supporting-line candidates per
  setting using identical saved evidence/images and no prior headline examples.
  Compare owner choices with independent model selections, preserving all
  candidates and model settings. Bound the experiment, save blind and revealed
  review artifacts, and retain the existing authorized review-copy destination.
  This does not authorize application changes, production selection, or an
  unlimited retry loop.
- **G2-R22 (2026-10-01):** Extend the Wang-only candidate/selection test to
  DeepSeek V4.1 Flash and V4 Flash 0731, allowing explicit output-count and
  JSON-shape instructions without prior headline examples. Preserve provider,
  effort, input and cost receipts; disclose the older model's text-only input.
  Add the results to the existing review file on allenwlee. The owner corrects
  the display order: GPT-6.1-Sol precedes GPT-6-Astra.
- **G2-R23 (owner assessment, 2026-10-01):** Across the model versions tested
  so far, thinking level has had little impact on the final choice. The owner
  considers GPT-6.1-Sol, GPT-6-Astra and GPT-6-Sol acceptable for this headline
  task; models below that range, including GPT-5.6-Sol and GPT-5.6-Luna, are
  unacceptable. This records the owner's current quality judgment, separately
  from the models' own acceptable-candidate lists. It does not mean every
  candidate from an accepted model is publishable, establish a general model
  ranking, or select a production model/effort. DeepSeek results are pending
  owner review when this assessment is recorded.
- **G2-R24 (owner decision, clarified 2026-10-02):** Limit the voiced headline feature to
  **at most one new headline with its supporting line every 15 minutes**: at most 96 per
  day at continuous operation. The fifteen-headline-per-refresh costing
  scenario and proposed five/fifteen-assignment writing tests are superseded
  for this feature. Continue selecting one worthy subject from the collected
  evidence under G2-R18–R20; individual-post commentary remains faithful and
  receives no imposed editorial voice. This changes the design boundary and
  does not authorize a live schedule or production deployment.
- **G2-R25 (owner decision, 2026-10-01):** Accompany each selected headline with
  one model-generated visual asset: a photo/image, GIF, or short video. Account
  for media-generation cost separately from headline tokens. The owner asks
  which tested models can supply this and whether generation should be
  sequential or concurrent; the exact media model, asset format mix and
  production sequence remain to be selected. Preserve distinctions between
  source evidence and generated editorial imagery.
- **G2-R26 (authorized test, 2026-10-01):** Test MiniMax H3 for the new media
  requirement. The official `MiniMax-H3` is a video-generation model, distinct
  from MiniMax M3, and has not been tested in the headline-writing comparison.
  Use a bounded media-only trial, preserve prompt/source/response/cost evidence
  and deliver a reviewable result at the existing authorized destination.
- **G2-R27 (owner boundary, 2026-10-01):** Use a separate MiniMax credential
  for this project; the existing shared key is used by other applications and
  must not be reused or replaced. Agent discovery is recorded in the root
  `AGENTS.md`: `PUSHINWEIGHT_MINIMAX_API_KEY` in the process environment or
  `/Users/fuchitalee/.env.secrets`. A missing project credential stops the
  request, with no shared-key fallback. The variable name/file convention is
  the implementation of the owner's isolation requirement; no new secret has
  been supplied or created by recording it.
- **G2-R28 (authorized sample, 2026-10-01):** The owner directs another Wang
  video using the actual posted photo showing him standing in the outfit.
  Preserve the original photo in the evidence and use it as the visual basis,
  with Wang visible. The first H3 clothing-display sample is retained as an
  earlier treatment. This authorizes a bounded source-photo video test, not a
  production-format decision; generated motion must be distinguishable from
  recorded source footage.
- **G2-R29 (authorized sample, 2026-10-01):** For the next Wang video, animate
  the red pen crossing out underlying luxury labels and writing the replacements
  one by one. Keep Wang still. Preserve the source's claims and distinguish
  any reconstructed starting frame from an original posted image. This is a
  bounded new treatment, with prior samples retained, not a production rollout.
- **G2-R30 (owner direction, 2026-10-01):** In the G5 prototype, Chatter is the
  surface for voiced New York Post-style headlines and supporting bylines.
  Keep one main hero headline visible and stationary while a list of past
  headlines scrolls automatically below it, most recent first. Show five past
  headlines for this iteration; the final history count is undecided. Past
  items use smaller headlines with their bylines. Scrolling the history must
  not move or rotate the hero. The one-new-headline-per-15-minute generation
  boundary remains; showing history does not mean regenerating every item.
- **G2-R31 (owner direction, 2026-10-01):** Customize headline assets for their
  Chatter presentation, including a background identical to the surrounding
  section. The current prototype uses white. This iteration uses THE PRICE IS
  WANG! and its supporting line, a newly generated matching-background pen
  video, and 0731 for the remaining commentary. Reuse five earlier voiced
  headline/byline pairs for the history. Source evidence and generated imagery
  remain distinguishable; individual-post commentary remains source-faithful.
- **G2-R32 (owner direction, 2026-10-01):** Keep clickable source-list entries
  leading to the underlying posts as a to-do. Preserve source URLs in the
  evidence, but this prototype iteration need not implement those links.
  Deliver the updated prototype to allenwlee after verification. G5 has its
  own session; this G2 authorization covers Chatter and its necessary local
  integration, not unrelated G5 redesign or production deployment.
- **G2-R33 (owner direction, 2026-10-02):** Treat 15 minutes as the decision
  cadence. Compare new worthy subjects against the current hero and retain a
  dominant story when appropriate, including for much of a day. Depreciate
  the older story's priority so continued retention requires sufficient
  underlying importance relative to a newer challenger. The score, age origin,
  decay rate and replacement margin must be tested rather than assumed.
- **G2-R34 (owner-accepted consequence, 2026-10-02):** A slow news day may
  produce more replacements because worthy subjects have similar strength.
  This is acceptable; the cadence is not a quota requiring 96 publications.
  Costs must distinguish selection checks from new writing and asset generation.
- **G2-R35 (owner evaluation requirement, 2026-10-02):** Newsworthiness is an
  editorial judgment distinct from headline-writing quality. Test it using
  real posts from one complete 24-hour period: the model chooses which pass
  muster, then a human judges those choices. Preserve the actual text and
  relevant images. Review accepted and rejected subjects so missed stories can
  be identified. The owner requested a manual first pass before implementation;
  the October 1 JST pilot and subsequent owner review are saved. Any separate model
  comparison still needs explicit settings and bounded spend; prior writer-model
  preferences do not establish editor-model quality.
- **G2-R36 (owner direction, 2026-10-02):** Discover and judge two editorial
  tracks: Chatter covers human interest, memes and AI-industry insider fun;
  Pulse covers newsworthy current events with standard factual headlines.
  First consider whether a rare, industry-shaping event merits both, then
  assess each lens independently. Subjects may qualify for either, both or
  neither; a strong single-post joke can merit Chatter without a volume spike.
  Rerun the real-day manual test with both lenses and generate a headline and
  supporting byline for each accepted track. The owner selected writing both
  in this session rather than a separate 0731 call.
- **G2-R37 (owner correction, 2026-10-02):** Chart support is not a condition
  for choosing a headline. Choose the event for newsworthiness first, then
  report whether the stored data shows related movement, no clear movement,
  conflicting signals or insufficient coverage. Tracked-brand movement remains
  a discovery route and context for Pulse. Do not miss a major event because
  our charts fail to reflect it, fabricate corroborating movement, or treat
  absent movement as evidence that the event did not occur. Preserve source
  verification and distinguish observed counts from causal explanations.
  This replaces the initial chart-required interpretation in the rerun.
- **G2-R38 (owner review, 2026-10-02):** The two-track test primarily evaluates
  newsworthiness; the changed New York Post wording does not require a writing
  rerun. Preserve the owner's raw choices, notes and secondary writing ratings.
  The owner directs that remaining blank newsworthiness choices count as not
  headline worthy. Keep those inferred rejections distinguishable from explicit
  choices; do not infer writing ratings or exceptional-event flags.
- **G2-R39 (owner review notes E12/E19):** Give a quieter tracked brand a
  spotlight when it releases a model. Give priority to major agent/application
  providers entering model competition with the tracked brands. The owner
  highlights Upstage and Perplexity in this test; preserve the actual product
  type, including Perplexity's embedding model. Existing volume must not be the
  only route to prominence. The owner's Chatter selections include major
  releases and competitive developments, not only preexisting jokes.
- **G2-R40 (owner review notes E13/E16/E27):** Explain unfamiliar names and
  why the development matters: identify who a featured person is, give companies
  outside the tracked set a one- or two-word description, and explicitly
  describe STEPX Neo as a handset sold by an AI lab.
- **G2-R41 (owner review notes E34/E35):** A personnel-change headline must
  involve a well-known figure or a very key role, such as head of DeepMind.
  Other personnel announcements remain in “Who's Moved.”
- **G2-R42 (owner review note E23):** An unproven allegation needs multiple
  supporting posts. Preserve their provenance; multiple copies of one claim
  are not independent confirmation. A subject's newsworthiness is separate
  from whether its factual claims are ready to publish.
- **G2-R43 (owner clarification, 2026-10-05; prompt starting point clarified 2026-10-06):** Retain the existing brand/time-
  window headline feature while G3 investigates and expands it. Pulse is an
  additional use of that capability, and Chatter is another editorial output.
  Share evidence handling, writing infrastructure and applicable validation,
  persistence and cost controls; avoid independent copied scripts that require
  the same fix in several places. Start G2's grounding and attribution design
  from the existing headline prompts and source-validation contracts, carrying
  their learned safeguards forward rather than designing an unrelated prompt.
  The October 6 learning baseline also covers thinking, provider request profiles,
  response parsing, budgets, retries, evidence selection and publication behavior;
  learning these contracts does not require literal code or pipeline duplication.
  Adapt source ownership to grouped stories: multiple posts may inform one
  story, with clear support for each factual claim. This does not require
  copying the existing pipeline's extra calls, brand/window eligibility rules
  or English-to-other-locale generation into G2. Preserve output-specific selection, voice,
  cadence and presentation. The concrete shared-module design remains proposed;
  this clarification does not freeze defects in current headline behavior or
  transfer the active G3 investigation to G2.
- **G2-R44 (owner naming/boundary, 2026-10-05):** Call the newsworthiness and
  track-selection responsibility the **editor-in-chief**. G3 will find
  longitudinal angles for selected subjects, but that expansion must not
  determine newsworthiness or Chatter's hero-replacement judgment. Carry the
  selected subject/angle, source evidence and cutoff to G3; availability or
  richness of historical analysis must not become an eligibility condition.
- **G2-R45 (owner naming and scope, 2026-10-05):** Call the visual-asset
  responsibility the **picture editor**. It serves article/commentary imagery,
  including Chatter and Pulse, and implements the applicable media and visual
  integration requirements in G2-R25/R30/R31. This is a responsibility name,
  not a requirement for a new autonomous agent, separate script or additional
  model call on every refresh. Its sequence, provider and bounded cost policy
  still need to be selected.
- **G2-R46 (owner picture-selection direction, 2026-10-05):** Use G1's person
  and verified-image library to choose the person and photograph most relevant
  to the article. A single-brand story must use an appropriate subject from
  that brand. Company direction generally favors the founder/CEO; a model
  release may favor a relevant senior researcher; an agent release may favor
  someone on its development team. Prefer the identifiable staff subject or
  staff author when the story mentions or comes from that person. If the
  preferred person has no verified photograph, select an appropriate fallback,
  normally the brand's founder. Exact precedence when several people qualify,
  terminal fallback without any verified portrait, and model-versus-code
  implementation remain design proposals. Preserve original post media when
  it carries the story's evidence under G2-R12/R28/R29.
- **G2-R47 (owner derivative direction, 2026-10-05):** Selecting the source
  image is only the first picture-editor responsibility. Create a derivative
  appropriate to the selected story: humorous for Chatter, restrained for
  Pulse. Keep source photographs and generated treatments distinct. Layout
  decisions are deferred in this discussion; do not change G5's prototype.
  This design direction does not authorize per-post media generation during
  harvesting, a new paid trial, or production activation. Detailed treatment
  for standalone atomic commentary and numerical generation budgets remain open.
- **G2-R48 (owner modularity requirement, 2026-10-05):** Make the picture
  editor a reusable capability that can be independently applied to or removed
  from content types, such as an individual X-post/commentary item versus a
  headline. Share person/photo selection, fallback and derivative-generation
  machinery; do not embed separate implementations into each collector or
  headline writer. Turning it on for one type must not turn it on for others.
  Content-type activation is separate from visual treatment. Concrete settings,
  defaults and runtime implementation remain in the G2 design; this requirement
  does not activate picture generation for every harvested post.

- **G2-R49 (owner provider correction, 2026-10-06):** Route 0731 editor and
  Pulse calls directly through DeepInfra using the project's `DEEPINFRA_API_KEY`.
  OpenRouter is not the route or a fallback for those calls. Keep Chatter's
  writer-model decision separate; this correction does not silently replace
  GPT-6 Sol with 0731. Codex CLI was selected for the historical manual rerun.
  On October 7 the owner selects direct OpenAI for production Chatter, using
  `gpt-6-sol` with medium reasoning and the exact `OPENAI_API_KEY` from
  `/Users/fuchitalee/.env.secrets`, provisioned into the editorial runtime's
  environment during delivery. The owner waives the proposed fresh live-quality
  rerun and its dependent new experiment-budget gate; earlier failures remain
  evidence, not passing checks. Existing combined spending limits remain.
  Later on October 7 the owner explicitly requests a fresh live generation run.
  This authorizes the bounded saved-evidence comparison recorded in the G2 plan;
  it does not turn the earlier waiver into a release gate or authorize an
  unbounded retry loop.

- **G2-R50 (owner direction, 2026-10-07):** Set a measured, reasonable evidence byte limit. Keep shared-brand and recency signals, add material relevance, and recover relevant story/meme history across months using a bounded backward lookup seeded by recurring distinctive names or keywords. Context must reach the selected story's writer; record retrieval and trimming limits. Operator-added context must become reusable normal sampler behavior, with manual and automatic selection sharing the same evidence collector. Owner's additional example is a GLM 5.2 weekend tease followed by a later launch: recover relevant expectation/update/launch context, preserving source links and date uncertainty before asserting an exact delay. This example is a retrieval requirement, not a verified event chronology in this document.
- **G2-R51 (owner direction, 2026-10-07):** Post attribution must include the distinct number of supporting posts and every supporting post URL. Persist it with the edition so attribution remains inspectable; retrieved candidates are not automatically cited sources or independent confirmations. Clarify image evidence references separately from generated image descriptions.
- **G2-R52 (owner draft direction, 2026-10-07):** Start a planning-only migration draft that generalizes existing brand trend narrative storage for trend narratives, Chatter and Pulse, with the owner-selected `OriginalContent` entity name (October 8) and explicit producing-workflow/execution identity independent of mutable display names. Workflow/call provenance must make resources and budget accounting inspectable, including shared editor steps; the October 8 canonical G2 plan specifies the headline-first schema, per-language/version citations, migration and rollback. Normalize cited-post relationships using post-ID foreign keys, preserving distinct source counts and all URLs for each published version/language. Keep Chatter/Pulse running. The canonical G2 plan records proposed publication/text consolidation, existing constraint conflicts and open decisions; the original draft granted no implementation or delivery authority. Operational ledgers, story/hero identity and pictures require dependency review before deciding which additional tables to consolidate. Current owner continuation: staging LFG and “that's fine. deploy” later authorized the compatible implementation, now verified in production at926ef61c with shared storage, relational citations and preserved budgets. The owner clarified that physical PostgreSQL names must change too, then selected finishing compatible production first and recording that follow-up as U16 in the same plan. No physical rename or destructive retirement is included in this continuation. Subsequent owner request: proceed immediately with the physical-name amendment and assess disruption to G1–G5 deployments. U16 now proposes atomic physical renames with temporary old-name views, mixed-version ORM proof and a measured staging rollout; reserve a later bounded shared-service deployment window while development and harvesting continue. No rename, pause or deployment hold has been applied in this amendment pass. Latest explicit U16 LFG authorized the amendment through production, now verified at 00d73117: six retained physical tables use the canonical names and six temporary old-name views preserve compatibility. Full-row/FK/index/sequence identities, relational citations and budgets reconcile; writing resumed, harvest continued and original service controls were restored. Keep U15 retirement, alias/column removal and paid quality trials outside this completed release. Latest owner timing decision: replace the seven-day rollback window with24hours from the unchanged production cutover2026-10-08T07:37:56.303216Z; reevaluate October9 at16:37:56JST. Keep old-name views/legacy storage until review and the remaining consumer/preservation/encrypted-restore requirements are satisfied; there is no automatic removal. Record policy only in this follow-up; the deployed retirement report still uses seven days and must be reconciled before later cleanup execution. No redeployment or scheduler is selected.
- **G2-R53 (owner architecture direction, 2026-10-08):** Draft a shared `packet-maker` that accepts bounded subject, quantity/size, time-window, language, classification and context parameters; queries stored evidence and performs normalization, relevance retrieval, calculations and compact projection in code before a customized final LLM writing call. Reuse existing trend/editorial collectors and grounding. New OriginalContent formats should reuse preparation through profiles and explicit enrichment modules. Preserve exact source ownership, historical context, language/version provenance and attribution; distinguish packet preparation from execution/budget and display names. Combining or removing existing judgement/critic calls requires demonstrated source/quality parity and measured call/token savings. The original direction was planning only. The later authorized compatible release implements shared deterministic preparation while retaining existing writing/judgement stages; no additional paid quality trial, cadence/model/prompt or collection change is authorized by that implementation.
- **G2-R54 (owner schema design reset, 2026-10-08):** Start target schema design from existing headline tables, treating the prior editorial tables as absent for design purposes. Compare no schema changes, existing-table columns/constraint extensions, and minimal shared tables that existing headlines also need. Existing published material remains later migration input. The owner selects scenario 3: extend/generalize existing headline tables and add one shared `original_content_sources` relation used by headlines, Chatter and Pulse. The later staging LFG and explicit production continuation implement this selection compatibly. Physical table names remain old during that release; the owner explicitly requests the final physical names as a separately planned amendment after production completion. That prior planning pass did not grant a new migration. The later U16 LFG explicitly authorized physical renames, now observed in production at 00d73117; destructive retirement and column renames remain excluded.




### Proposed first step and completion evidence

The [owner's newsworthiness review](../../worktrees/g2-voices-corpus/docs/analysis/2026-10-02-193700-g2-chatter-pulse-manual-rerun/2026-10-02-230912-owner-review/README.md)
is collected and validated: **18 Chatter-worthy cases, 21 Pulse-worthy cases,
12 in both**. There are 64 explicit track choices and 44 blank fields resolved
as rejections under the owner's follow-up. Original blanks and all notes remain
preserved. These case counts are not publication quotas or a blind accuracy
measure; Creatify was already included in the grouped H3 story. Next carry the
accepted editorial directions into future selection design while retaining
the open routing and priority questions below.

The preserved [October 1 two-track manual rerun](../../worktrees/g2-voices-corpus/docs/analysis/2026-10-02-193700-g2-chatter-pulse-manual-rerun/review.html) contains:
2,924 stored posts, 54 subject-level judgments and 12 Chatter / 21 Pulse
headline-byline pairs, written in this session. Five subjects qualify for both
through distinct angles; the editor assigned none to the exceptional category.
The later owner export marks E12 and E19 exceptional. Pulse
selection follows newsworthiness even when chart support is absent, with the
data observation shown separately. The [first selection-only pass](../../worktrees/g2-voices-corpus/docs/analysis/2026-10-02-183000-g2-manual-editor-day/review.html)
is preserved. All original leads were screened; representative full texts and
52 images/posters were inspected and reused. This is not a complete media
review, a named-model benchmark or a proven production editor. The two-track
split does not create an additional production writing/media budget; Pulse
cadence and call accounting remain to be settled alongside the existing
Chatter cap. The [editor and sharing brief](../../worktrees/g2-voices-corpus/docs/brainstorms/2026-10-02-181827-g2-editor-judgment-and-sharing.md)
separates that test from a proposed later 15-minute replay, which must use only
evidence available at each checkpoint. It also records candidate depreciation,
cost controls and permanent shared-story access. These proposals are not
implemented behavior or a selected production formula.

English corpus-source research and the CLI headline tests, including the
bounded Wang-only candidate/selection comparison under G2-R21–R22, are complete.
The owner's current quality assessment is in G2-R23. The current media trial
is MiniMax H3 under G2-R26; its execution evidence and any access blocker
belong in the G2 plan. Keep headline/media experiments separate from production
event/meme selection under
G2-R18–R20. Extend the comparison to Chinese and Japanese using
the same underlying grouped stories and faithful post-level commentary. Research
real examples from the named publications and candidate Chinese references. Let
the owner judge rendered headlines/bylines and grouped writing before turning
them into prompt/style rules. Preserve approved examples, terminology, and
distinctions between fact, allegation, inference, and editorial attitude.

Owner assessment on 2026-09-30: the [original source-grounded Astra/high
run](../../worktrees/g2-voices-corpus/docs/analysis/2026-09-30-152158-g2-en-source-grounded-gpt-6-astra-high.md)
is the best of the saved English tests, including over Grok, and is the current
preferred English reference. Retain its six headline/supporting-line pairs and
the prepared source/image inputs that produced them. Repeat performance and
production cost remain to be established.

Before open-ended evaluation begins, freeze the sample, evaluation criteria,
iteration limit, and spending limit. Completion requires owner-approved examples
and evidence that the selected guidance reproduces the intended voice on
additional stories without changing their factual meaning. Separately verify
that post-level commentary preserves the source's own voice, that Japanese and
Simplified Chinese commentary use original source context rather than generated
English, and that grouped claims remain traceable to their source evidence.

For the initial cost comparison, measure a baseline that reuses saved atomic
commentary and grouped results, requests multiple locales in one draft call
where fidelity permits, incorporates voice checks into existing editorial
review where applicable, and bounds any repair calls. Multiple competing
drafts, a separate voice-review call, and model training are optional techniques
to justify with measured benefit and cost, not assumed per-output steps. This
is a proposed approach, not a selected call topology. Report cost per new or
refreshed grouped item and projected total spend, with the workload assumptions.

### Open decisions

Chinese publications/references; how much insider shorthand general readers can
handle; when acronyms need explanation; acceptable irreverence; story/headline
lengths; transliteration and proper-name conventions; tone across languages and
professional/general reading modes; per-item and total model-spend budgets;
retry and refresh limits; and the behavior when a cost limit is reached.
For event/meme selection: subject boundaries, ranking weights, distinct-source
counting, meme eligibility, image interpretation/storage, context lookback,
editor test date/models/spend limits, depreciation rate and age origin,
replacement margin, and behavior when no subject is worthy. Retaining a
dominant winner is required by G2-R33. The existing `events`
classification means attended occurrences such as conferences; it is not a
generic identity for a news story. The 15-minute decision interval and any wider
evidence context must remain distinguishable.

The owner's E25 review note proposes keeping untracked-model stories in Chatter
rather than Pulse. Reconcile that proposal with explicit Pulse approvals for
adjacent/untracked companies and the E19 competitive-entry priority before
turning it into a categorical routing rule. E12/E19 are marked exceptional in
the raw review, while their notes stress spotlight and strategic priority;
the relationship to the rare, earth-shattering category is also unresolved.
Preserve the actual case choices without inventing a universal threshold.

### Independent discovery supporting G2

The owner-selected official-company discovery branch implements the two distinct operations in G1-R16: a complete initial database sweep and continuing extraction with the harvester. Its production endpoint is verified collection with correct existing brand attribution; it does not change G2 editorial admission or depend on completing G1–G5. The linked implementation plan owns execution details and the benchmark-account compatibility contract.

<a id="g3--topic-history-and-longitudinal-reporting"></a>

## G3 — Historical comparisons supporting prediction

G3 includes a major prediction engine supported by comparisons of products
and trends over defined historical windows, estimating future user attention,
downloads, rankings and token usage. It learns from the benchmark/usage history,
verified releases and changes in collected posts. Qualitative descriptions and
2–5 reader-facing variable questions explain and explore those estimates.
Headline histories remain a reader entry point and a way to inspect the
comparisons. G3-R13 and R15–R28 record this owner-selected direction;
G3-R12 retains the
implementation hold while the independent benchmark work proceeds.

### Owner requirements

- **G3-R01:** Each headline on the general page needs an icon through which a
  reader can inspect the longitudinal trend of its topic.
- **G3-R02 (clarified by the owner on 2026-09-30):** The history must use
  database evidence. G3-R04/R05 define the selected time windows and the
  distinction between saved short histories and asynchronous longer histories.
- **G3-R03 (purpose clarified by G3-R13):** Build on the existing longitudinal
  research to supply relevant historical comparisons to the prediction engine
  and help readers understand how the evidence and estimates changed over time.
- **G3-R04:** Every general-page headline topic has a time-window control with
  **15 minutes, 1 day, 7 days, 30 days, and 360 days**. Preserve 360 days as
  requested; do not substitute an existing 365-day window.
- **G3-R05:** Pregenerate the 15-minute and 1-day analyses and save them in the
  database. The 7-day, 30-day, and 360-day analyses load asynchronously when
  requested. Reuse, refresh, and generation timing for those longer windows
  remain design decisions within this behavior.
- **G3-R06 (scope clarified by G3-R08):** For a release-centered headline,
  follow its subject through relevant predecessors and gather related posts
  and metadata within the selected window. The analysis
  must address the headline's subject matter: a performance story should
  explain the new release in relation to relevant earlier performance evidence.
  The owner's illustrative GLM 5.3 Flash example calls for finding GLM 5.2 or
  another relevant precursor, rather than restricting retrieval to the new
  release's exact name. The example does not itself verify a release or ancestry.
- **G3-R08 (owner clarification on 2026-10-01):** An audience topic can also
  organize the history. A story about local LLMs in general can follow that
  subject across products, model families, and brands. Product/family identity
  and AudienceTopic are available organizing dimensions; the headline's subject
  and angle determine the relevant scope. A broader topic story does not require
  one model family as its anchor.

### Prediction requirements and later market exploration

- **G3-R07 (proposed by the owner on 2026-09-30):** Each headline topic would
  have a prediction action. Selecting it compares today's development with
  predictions made in earlier sessions and accompanies the comparison with a
  visual. The source of those earlier predictions, when they are created,
  and the criteria for judging an outcome remain open. Comparing prior
  predictions does not yet specify generating a fresh forecast on every click.
- **G3-R09 (owner direction on 2026-10-05, purpose clarified by G3-R13):**
  Connect stored posts, Arena benchmark observations, Hugging Face downloads
  and OpenRouter usage with the prediction engine through historical
  comparisons. Use that evidence to support, explain and evaluate dated
  predictions. The owner previously reported an existing engine; G3-R15 now
  explicitly requires delivery of the engine feature, reusing any existing
  implementation after its location and contract are identified.
  Consume the independent benchmark/usage collector's contracts rather
  than assigning its collection work to G3. OpenRouter's relevant measurement
  is routed token usage, not downloads.
- **G3-R10 (owner decision on 2026-10-05):** Use a PushinWeight poll to attract
  attention and demonstrate demand for proposing a tradable market to Polymarket
  and/or Kalshi. The owner requests an isolated prototype of the current G3 idea
  and explicitly requires it to conform to the maintained G5 prototype. Preserve
  G5's visual language and shared layout; the G3 prototype does not replace or
  alter the authoritative G5 artifact. Specific poll fields and demand thresholds
  remain design choices; G3-R28 subsequently selects the pre-listing support
  action, proposal submission and supporter notification sequence.
- **G3-R11 (owner scope decision on 2026-10-06):** For now, track internally
  which proposed trades attract the most clicks. The owner requests a current
  analytics-tool comparison that also considers future API/MCP calls. Measure
  interest in the proposed questions; a click is not an executed trade or a
  commitment to bet. Analytics provider, event definitions and implementation
  remain to be selected. G4/G5 are consumers of the proposed measurement design,
  not reassigned implementation workstreams.
- **G3-R12 (owner sequencing direction on 2026-10-06):** Wait for the separately
  active [benchmark/usage implementation](../../.worktrees/feat/benchmark-download-collector/docs/plans/2026-10-05-070106-feat-benchmark-download-collector-plan.md)
  before resuming G3 implementation. Read the current charter and its dependency
  contracts now. Its October 7 staging delivery verifies collector/history and
  cutoff-aware numeric inputs at `1375d1c0`; later R37–R40/U22–U23 chart/panel
  additions remain pending. Production deployment and scheduling remain separate. G3 consumes
  its delivered identity, product-relationship and measurement contracts under
  G3-R09 rather than duplicating or taking over that work.
- **G3-R13 (owner purpose clarification on 2026-10-06):** G3 primarily services
  the prediction engine. Comparisons and qualitative descriptions of products
  and trends over defined time windows supply evidence for estimates of future
  **user attention, downloads, rankings and token usage**. Historical analysis
  and explanation support this forecasting purpose. Retain the selected
  historical windows and saved/asynchronous behavior in G3-R04/R05; forecast
  horizons are separate and remain to be selected. Define each prediction's
  subject, metric, source scope and target period before treating it as a
  measurable outcome. The exact attention measure and engine integration remain
  open; internal proposal clicks under G3-R11 are one distinct interest measure,
  not an automatic definition of all user attention. This direction preserves
  the implementation hold in G3-R12 and does not activate external trading.
- **G3-R14 (owner requirement on 2026-10-07):** Provide a way to send a popular
  prediction on PushinWeight to an external prediction-market platform as a
  candidate for a tradable market. Focus the initial design on one venue, choosing
  between Kalshi and Polymarket based on partner openness, application effort
  and plausible listing acceptance as well as technical capability. The owner
  requests brainstorming now; this adds the proposal workflow to the product
  requirements without lifting G3-R12's implementation hold or authorizing an
  actual external application/submission. Keep partner admission, market review,
  listing and eventual user trading distinct. Popularity supports consideration
  and does not guarantee acceptance. G3-R15 subsequently selects Kalshi for
  this feature's planning; demand criteria, partnership terms and submission
  mechanics remain design decisions.
- **G3-R15 (owner major-feature direction on 2026-10-07):** Deliver a prediction
  engine using the totality of usable benchmark/usage evidence from the
  independent plan and historical relationships between those measurements.
  Forecast the next legitimate model release's Arena performance or usage;
  Arena versus usage as the first target remains an explicit owner question.
  Reuse any existing engine after inspecting its actual entry point. Identify
  releases from collected X evidence and triangulate with verified publishers,
  official announcements and HF repository/weight-publication metadata where
  applicable. Preserve release versus repository creation and true successor
  versus derivative; closed/API-only models need no HF repository. Save dated
  forecasts with exact targets, horizons, input availability and uncertainty,
  and evaluate on later releases against simple baselines. Connect promising
  popular questions to a **Kalshi market-candidate request**, with demand,
  public outcome rules and actual submission/listing states distinct. Planning
  this function does not submit a proposal, lift G3-R12 or authorize trading.
- **G3-R16 (owner qualitative-view direction on 2026-10-07):** Include a
  qualitative view based on collected posts and their classification mix.
  Test whether marked volume/composition changes precede releases, how early
  and reliably, and whether they improve ranking/usage forecasts. Compare
  release periods with non-release periods; distinguish independent authors,
  official sources, copied promotion and collection/classification changes.
  Retain exact counting units, classification versions, missing coverage and
  as-of evidence. Supply a sourced narrative and visual with supporting and
  contrary evidence; pre-release patterns are hypotheses, not established facts.
- **G3-R17 (owner timing observation on 2026-10-07):** Test publisher-specific
  release regularity by weekday/time of day, time since previous release and
  evidenced calendar context. Preserve source timezones/precision and uncertain
  holiday effects. Compare post activity with normal weekday/time patterns
  and include non-release controls. Estimate release timing separately from
  ranking/usage conditional on a release; calendar patterns do not confirm one.
- **G3-R18 (owner interaction requirement and Jev clarification on 2026-10-07):**
  Each usable forecast gives readers **2–5 key variables as questions**.
  Show the baseline and how Yes/No or other defined assumptions affect the
  same exact outcome; the owner's example concerns holiday slowdown and an
  October 30 ranking/deadline scenario. Readers can combine answers into a
  personal forecast, saved separately from canonical engine and community
  estimates. Include **Jev concurrent question evaluation plus a quick
  probability-update calculation** in the design: batch supplied questions
  against shared evidence, then evaluate learned factor updates and/or direct
  conditional outcome estimates. Distinguish factor probability from outcome
  probability and account for overlapping factors. The proposed Jev path needs
  forecasting/latency/cost verification; it does not change the existing 0731
  classifier or authorize model calls. Never invent branch probabilities or
  force Yes/No to straddle 50% without supporting evidence.
- **G3-R19 (owner chart direction on 2026-10-07):** Accompany the prediction
  panel with a simple probability line chart that moves up/down with the
  reader's answers. Show a 50% reference and the same saved scenario's exact
  Yes-outcome probability: above 50% leans Yes, below leans No, exactly 50% is
  even. Preserve G5 design, readable labels, baseline/change, reset/edit and
  coherent latest-response behavior. The owner's intended Kalshi Yes/No action
  also needs the exact listed contract and actual price: forecast direction
  alone is not a trade-value calculation. Separate the 50% direction cue from
  market-price/cost comparison and never invent a listing or automatic order.
  Axis/animation details remain proposals. Design only; G3-R12 remains in force.

- **G3-R20 (owner review amendment on 2026-10-07):** Consume the benchmark
  plan's R32–R36 source-use decisions and cutoff-aware input contract. Separate
  collector/storage deployment, public charts/forecasts and exchange/trading
  activation. Before public probabilities, demonstrate chronological evaluation,
  calibration and reproducible personal scenarios. Before Kalshi data/model use
  or trading-related integration, establish applicable terms and qualified legal/
  audience review; API accessibility is not permission. Frozen future corrections,
  unknown availability and reconstructed history must not become past-known
  inputs. These are review requirements, not verified clearance or a live engine.
- **G3-R21 (owner ranking-history amendment on 2026-10-07):** The benchmark
  dependency adds a separately labeled Arena predecessor-rank history under
  R31/KD22. It uses reviewed previous-release observations until the successor's
  first valid evaluation, visibly marks the model switch and retains exact
  measured identities. G3 may consume that proxy as explanatory context; do not
  treat it as the successor's historical performance or a settlement observation.
  General post/download/engagement proxy attribution remains deferred. G3-R12's
  implementation hold and separate trading authorization remain in force.

- **G3-R22 (owner dependency refresh on 2026-10-07):** Base the engine on the
  benchmark worktree's precise source measurements and selected graph contracts,
  R26–R40/KD16–KD25. Use distinct collected brand/topic/product post evidence;
  exact-product completed-day OpenRouter tokens; HF rolling-download levels and
  explicitly labeled adjacent-snapshot net changes; repository likes/account
  followers where honest history exists; and exact-variant Arena score, bounds,
  variance, reported battles and rank. Preserve measurement scope, units,
  source configuration, missingness and provenance. Do not treat HF net change
  as daily new downloads, brand posts as release attribution or battles as
  unique people. Forecast features use underlying dated observations, with
  chronological tests of relationships and lags, rather than visually inferred
  correlations or an average of chart percentages.
- **G3-R23 (forecast design consequence of the owner-selected graph):** The
  G5-R17/benchmark R37–R38 three-line chart uses separate raw means over one
  common first complete post-release week and optional trailing-three-day
  means. That future reference cannot enter a pre-release/early-release forecast.
  Preserve the chosen graph for retrospective explanation; operational inputs,
  normalizations and all smoothing/reference dependencies must be available at
  the forecast cutoff. Use the dependency's cutoff-aware reader and reproducible
  revision selection, plus a separately evidenced post/classification adapter.
  The response chart's percentage change and the G3-R19 personal outcome
  probability have different meanings. Preserve G3-R04/R05 window behavior.
- **G3-R24 (Arena/feature acceptance consequence of the owner refresh):** Use
  Arena raw score with published confidence bounds and reported battle count
  together, in the exact `text`/`overall` no-style-control configuration. Test
  whether evaluation precision/participation adds predictive information beyond
  score/rank alone. Verify score-scale/anchor compatibility before score-change
  conclusions; keep rank's competitor context and actual publication samples.
  Missing optional fields, sparse publications and held chart steps do not
  become zeros or additional independent evaluations. Preserve R21's narrow
  predecessor-rank context. The [G3 working design](2026-10-05-163237-g3-evidence-forecasts-markets.md#benchmark-measurement-and-chart-basis--october-7-refresh)
  records exact inputs, delivered/pending scope, reader gaps and regression
  requirements. This amendment is documentation only and retains G3-R12.

- **G3-R25 (owner-selected additional usage source, 2026-10-07):** OpenCode
  joins OpenRouter, Arena and HF as a peer in the independent benchmark plan
  R42–R45/U25–U27. Its hosted Go + free-model daily UTC totals are refreshed
  hourly. Preserve each changed partial/completed-day revision, endpoint update
  and local observation time; a refresh or snapshot difference is not exact
  hourly tokens or new users. Forecast inputs must select revisions available
  at the stated cutoff, keep OpenCode and OpenRouter scope/counting separate,
  and preserve approximate-user/session definitions. The collector captures
  available tracked-product daily history and retains it after upstream expiry;
  retroactive exports do not establish historical hourly availability. The
  collector's OpenCode revision/cutoff reader is implemented and staging verified
  at `e28cbda9`; this newly imported history is excluded from past operational
  cutoffs. G3 implementation remains on hold under G3-R12; this handoff grants no new run,
  deployment, forecast publication or trading authority.

- **G3-R26 (owner statistical-foundation direction, 2026-10-07):** Base the
  engine on statistical analysis of verified releases across models in the
  database and their following 30 days. Examine source measurements and
  individual-post classifications for relationships that can predict the next
  GLM release's usage, rank and attention. Preserve target-specific cohort/
  coverage, reviewed release identity, independent launch groups and source
  scope. The 30-day study window supplies outcomes and retrospective analysis;
  a forecast uses only evidence and training outcomes available at its issue
  cutoff. Test pre-release versus later updates separately. Catalogue products,
  posts, variant siblings and repeated daily rows are not independent releases.
- **G3-R27 (owner small-sample/calendar/geography direction, 2026-10-07):**
  Examine time of year, weekday, company HQ and researchers' documented work
  locations with explicit historical precision/coverage and small-sample limits.
  Distinguish publisher effects, calendar changes and geography; unknown team
  location or sparse public affiliations cannot support invented workforce or
  holiday effects. Require a bounded, prespecified statistical evaluation with
  uncertainty, sensitivity to influential launches and chronological grouped
  validation against simple baselines. The [statistical pilot design](2026-10-05-163237-g3-evidence-forecasts-markets.md#statistical-pilot--release-cohorts-and-small-samples)
  recommends partial pooling and names candidate tools, without selecting or
  fitting them. Jev can supply concurrent factor/evidence judgments, but final
  forecast probabilities must be grounded in the evaluated statistical method;
  raw Jev estimates alone do not satisfy this foundation. Design only; retain R12.
- **G3-R28 (owner pre-listing workflow direction, 2026-10-08):** Before a
  market exists, provide **“Vote to make a market on Kalshi.”** Collect distinct
  support for creating the proposed market, then send an eligible, versioned
  proposal packet once the configured demand threshold is met and notify
  supporters of confirmed submission and later verified status/listing.
  A support vote is separate from the reader's Yes/No forecast, involves no
  payment and commits the reader to no trade. State that Kalshi decides whether
  to list the proposal; reaching our threshold is not acceptance. Preserve exact
  resolution rules/deadline, existing-contract checks, duplicate/expiry handling,
  aggregate demand and actual submission receipts. G5 consumes the action and
  status copy; G4 access remains separately owned. The threshold, review owner,
  count-quality policy, notification channel and agreed submission route remain
  open. This selects the product flow; it does not lift R12 or authorize current
  external messages, applications, submission, orders or deployment.

The owner also wants an eventual Kalshi or Polymarket connection so readers can
bet. This is a future product ambition for exploration; its launch scope,
eligible audience and account/trading integration remain unselected. Kalshi
is selected for the G3-R15 candidate-request design; eventual trading is a
separate scope.
The October 5 follow-up authorizes a local prototype and provider research;
G3-R14 subsequently requires a market-candidate workflow and a single-venue
partnership assessment. Actual external proposals and live orders remain
unauthorized. Internal forecast questions need not have an
available external market, and poll participation does not guarantee a listing.

### Proposed first step and completion evidence

After the benchmark dependency is ready and G3 implementation resumes, exercise
one product or topic through the engine's actual integration: retrieve dated
comparisons, supply the evidence available at a stated cutoff, save an estimate
for a defined target and horizon, and show its explanation and later outcome
when available. G3-R15–R19 add verified release history, pre-release composition
and calendar comparisons, 2–5 variable questions, the proposed Jev parallel
probability-update path and a live probability line chart. The engine interface and first target remain to be
selected.
Extend this across the four owner-named target categories without treating one
successful example as proof of forecasting accuracy for all four.

G3-R22–R24 align this exercise with the selected benchmark response graph and
Arena evaluation panel. Verify the actual cutoff-aware numeric reader plus
post/classification adapter, reference-week availability, HF adjacent-snapshot
rules, OR reporting/denominator coverage and Arena publication/anchor handling.
Demonstrate raw source values through reproducible features, personal scenario
and outcome; later chart information cannot improve an earlier saved forecast.

Test chronological release and non-release cohorts, preserving evidence
availability at each forecast cutoff. Compare benchmark-only, post-only and
combined forecasts, and measure whether the proposed Jev path and user factors
add predictive value. Verify same-outcome branch/joint estimates, preserved
personal/canonical records and no future-data leakage through the actual
reader-to-forecast-to-candidate call chain. The detailed requirements-stage
sequence is in the existing [G3 working design](2026-10-05-163237-g3-evidence-forecasts-markets.md#major-feature--prediction-engine-october-7-owner-requirements).

Use the five selected historical windows. Demonstrate immediate serving of saved 15-minute/1-day
analyses and asynchronous loading for the three longer windows. Show what
changed, when, and why, with source support, uncertainty, and insufficient
history visible. Discussion volume and measured product performance are
different quantities and should remain identifiable.

Include a broader audience-topic example, such as local LLMs, to check that
the same window behavior can explain changes across several model families.
A proposed scope can use a product/family, an audience topic, or their
intersection. Audience-topic membership supplies candidate evidence; the
headline's specific question determines relevance within that pool. The
existing `local_inference` concept covers local/on-device/self-hosted/constrained-
hardware inference, so it is a starting point for the owner's example, not a
claim that every tagged post belongs in every local-LLM analysis. Deduplicate
posts with multiple brand assignments and preserve classification version and
coverage gaps; missing topic assignments do not establish an absence of relevant
discussion in older windows.

Proposed evidence rules: distinguish a shared model family, a release successor,
and a model derived from another model; support each relationship rather than
inferring it from version numbering. Retrieve by topic and the headline's angle,
then synthesize from relevant dated evidence. Keep older baseline context outside
the selected window explicitly labeled. Reusing a saved longer-window result
and combining simultaneous requests could constrain cost; neither the reuse
policy nor refresh cadence is settled. Completion evidence should cover topic
continuity, supported changes, source traceability, freshness, corrections,
missing history, and bounded latency/cost.

For the prediction service, a proposed baseline is a dated record of the
original prediction, its source, evidence available at the time, target period,
and outcome criteria, with later revisions preserved separately. Compare it
against later evidence without rewriting the earlier forecast. Show unresolved
or untestable outcomes as such. A timeline can connect an earlier expectation
to the observed development; a numeric forecast-versus-observation chart needs
comparable measurements. If no earlier prediction was recorded, show that gap;
a retrospective reconstruction must not appear to be a forecast made then.
Keep historical lookback, evidence cutoff and forecast target period distinct.
Proposed completion evidence includes reproducible engine inputs, preserved
forecast revisions and comparison of estimates with subsequent observations
and simple baseline forecasts. Qualitative plausibility alone is not evidence
that the estimates predict outcomes accurately.

The [October 5 forecast/market brainstorm](2026-10-05-163237-g3-evidence-forecasts-markets.md)
proposes shared dated questions behind several headlines, evidence and forecast
timelines, reader forecasts, and eventual matching to external contracts. It
records current collector boundaries and source definitions. Its question model,
visual layout and sequence remain proposals, not additional owner decisions.
The owner's later G3-R10 direction selects polls as a means of building demand.
The [October 7 partnership assessment](../analysis/2026-10-07-104452-g3-market-partnership-selection/README.md)
recommends Kalshi as the first working target under G3-R14, using a small
information/distribution pilot and reviewable market candidates. It distinguishes
public builder invitations from measured acceptance odds and an actual listing
agreement; this recommendation is not an approved partnership.
The [provider comparison](../analysis/2026-10-05-170409-g3-market-listing-and-order-parameters.md)
separates market proposals from order placement, records the current public
requirements and identifies exact leaderboard settings as part of the contract.

### Open decisions

Topic identity and merging/splitting; selection and combination of audience-topic
and product/family scope; supported predecessor relationships and headline
angles; whether windows end at the headline's evidence cutoff or the
reader's current time; treatment of older baseline context; drawer versus
separate page; visual form; refresh triggers and longer-window reuse; correction
handling; resource budgets; and behavior when history is unavailable. For
G3-R07, resolve whether earlier predictions come from PushinWeight analyses,
source posts, or both; what an earlier "session" means; forecast creation and
revision rules; outcome criteria; any reusable engine and the required engine's
implementation/contract; the exact attention measure; the first Arena/usage
target, forecast horizons, uncertainty representation and evaluation rules across downloads,
rankings and token usage; release verification and history sufficiency; timezone
and calendar baselines; the 2–5 question-selection policy; Jev learned versus
direct scenario updates and their calibration, latency and cost. G3-R13 and
G3-R15–R28 settle the engine, qualitative, interactive/chart, measurement,
statistical and pre-listing support/notification requirements;
these operational choices remain open. The later market
extension also needs exact contract matching, provider availability and a
separately selected trading scope.
The five window lengths and saved/asynchronous split are owner-specified.
G3-R11 retains internal interest tracking; G3-R14 adds the required market-candidate
workflow to the design scope, with Kalshi selected by G3-R15 for the initial
candidate-request feature. G3-R28 selects support votes, demand-triggered proposal
submission and supporter status notices. Thresholds, review ownership, counting
rules, notification channels and partner submission mechanics remain open.
Its implementation remains subject to G3-R12.
Earlier liquidity pilots and live trading integration remain future proposals.
Final product decisions belong in the task plan before implementation.

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
- **G4-R06 (owner sequencing direction, 2026-10-06):** Begin G4 MCP
  preparation and scaffolding now, exploring the user-facing offering and
  stable interface boundaries. Final integration/completion waits for G1, G2,
  G3 and G5 to finish because their outputs affect this interface. This
  updates the earlier independent-progress guidance for G4 final integration;
  preparatory work may proceed without freezing unfinished upstream schemas.
- **G4-R07 (owner planning direction, 2026-10-07):** Draft the MCP plan
  against current G3 prediction/scenario requirements and assess tracking of
  human and agent prediction-tool usage. Compare established analytics
  alternatives to PostHog; no vendor is selected by that comparison. Agent
  private-scenario writes and interest actions remain explicit design choices;
  planning does not authorize analytics installation or G3 activation.

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

## G5 — General-page design and integration

### Owner requirements

- **G5-R01 (owner decision, 2026-10-01):** Add a separate workstream for the
  general-page design and integration. Its scope includes layout, charts,
  navigation and preferences, motion, sharing, responsive/mobile behavior,
  and connecting the visible sections to real data. G2 retains editorial voice,
  headline/byline generation and generated media.
- **G5-R02 (owner clarification, 2026-10-01):** Expect continuous changes to
  the page and prototype. Maintain one current design reference and update it
  in place as the owner gives direction; the September 29 rendition is a
  starting point, not a frozen specification or final acceptance. Record
  accepted decisions, experiments and unresolved questions distinctly. A
  routine design revision does not require another workstream or parallel plan.
- **G5-R03:** Carry forward the supplied sketch and existing homepage design
  instructions below. G5 owns Chatter, the chart/reporting area, Calendar,
  Free Stuff/Jobs and Who's Moving as page sections, including how readers move
  between their summaries and details. Their proportions, presentation and
  interactions may change continuously through owner-directed iteration.
- **G5-R04:** Coordinate what each section needs from the other workstreams:
  G1 supplies verified people and assets; G2 supplies editorial writing and
  generated media; G3 supplies topic histories, forecasts, reader scenarios and
  evidence; G4 defines the separately controlled API/MCP outputs. Consume the
  independent benchmark contracts for measurements under G5-R17/R18. Record the
  required fields, meaning
  of displayed counts, freshness and unavailable-data behavior before wiring
  each section to live data. Shared information does not imply identical web
  and external-agent disclosure rules.
- **G5-R05:** Allow independent progress. G5 may use clearly labeled sample
  data while providers are being built. G1–G4 do not wait for the final layout,
  and G4 does not depend on visual completion. Changes to shared information
  requirements must identify their affected consumers; purely visual changes
  do not create a new dependency for every workstream. Preserve G2's faithful
  post-level commentary and one voiced headline with media per 15-minute boundary.
- **G5-R06:** Keep the maintained prototype, uploaded sketch, reference images
  and asset provenance in the repository's existing ideation area. The
  [G5 design reference](../ideation/2026-10-01-190859-g5-general-homepage.md)
  identifies the current files and distinguishes them from the original local
  prototype run. Sample stories, personnel and chart values are not production
  facts or evidence that integration is complete.
- **G5-R07:** Assess launch readiness against the then-agreed scope and
  revision, with linked implementation and verification evidence. Continuous
  design iteration can continue after that milestone; completion does not
  promise that the page will never change. Adding this workstream does not
  itself start implementation or authorize deployment.
- **G5-R08 (owner-directed prototype, 2026-10-01):** Halve the current
  prototype masthead height, use the live logo and product name, and add
  **FOR: Agents / Humans**. Agents mode should dramatically transform the
  page into a practical code view mapping its sections to proposed MCP tools
  and API routes. Prefer runnable code and the same permitted data behind
  human-readable fields and machine-readable responses, so the page can help
  people understand the interface. The example tool names, routes and schemas
  remain proposals for G4; this prototype does not settle its output contract.
  For this iteration, make a separate version while G2 edits Chatter and
  deliver that new browser-review copy to `allenwlee/Downloads/agents`.
  Source and verification artifacts remain authoritative on fuchitalee.
- **G5-R09 (owner-directed integration, 2026-10-01):** Integrate the delivered
  `2026-10-01-193337-g5-agents-humans-v2/index.html` changes into the maintained
  prototype with G2's current Chatter. Carry forward the compact masthead,
  branding, Agents/Humans switch and code workspace while retaining the Wang
  hero, matching-background video, commentary and five-item history. The
  maintained prototype is the combined current design; the separately delivered
  G5 version remains comparison evidence. Existing G2 cost/source boundaries
  and G4's proposed-output status remain in force.
- **G5-R10 (owner direction, 2026-10-02):** Structure General for easy sharing,
  reposting and embedding, prioritizing X, then Instagram, Facebook, and
  feasible Chinese platforms. Platform-specific flows and asset formats remain
  to be verified; this requirement does not authorize external posting.
- **G5-R11 (owner direction and design question, 2026-10-02):** A shared story
  link should open General with that headline expanded to its full article
  and asset. The reader can then move to current General. Design a way to
  retrieve the shared story after it falls beyond the visible feed. Permanent
  story links, a reopen control, recently viewed items and a searchable archive
  are proposals in the G2 editor/sharing brief, not selected UI or implemented
  navigation. Coordinate durable story identity with G2/G3 and leave the
  active G5 session's prototype ownership intact.
- **G5-R12 (owner-directed revision, 2026-10-02):** Edit the maintained
  `:58011/index.html?chatter=20261001-192934` prototype in place. Restore compact
  Chatter/Pulse heights, reduce section-head/h2 spacing, remove section subtitles
  and the edition row, and keep the current headings while the naming brainstorm
  is tabled. Add a chatbot window beside the logo; its backend is not selected.
  Immediately after Weights, use **I am a Human / Agent**, changing a/an without
  shifting neighboring elements. Use the existing followers and agents/harness
  glyphs beside the two audience choices.
- **G5-R13 (durable owner requirement, 2026-10-02):** Agent mode uses a
  Matrix-inspired black/green monospace treatment. Chatter, Pulse, Calendar,
  Free stuff, Jobs and Who's moving must retain precisely the same outer
  position, size and shape in both modes. Inner scrolling and typography can
  differ. Future Human layout changes must carry through to Agent mode; prefer
  one shared set of outer section elements and verify both modes together.
- **G5-R14 (owner-directed media/disclosures, 2026-10-02):** Double the Chatter
  animation's size, use transparency and place it beneath the text flush with
  the panel top. Enlarge the hero title by 50% and try a playful, rotated,
  multiline composition. Halve the commentary's initial height with an
  expansion caret, shorten history, and collapse history behind a caret when
  the browser reaches the mobile layout. Preserve G2's editorial content.
- **G5-R15 (owner-directed Pulse, 2026-10-02):** Match the live chart's
  structure and behavior as closely as practical, using the prototype palette.
  Collapse the ticker behind a caret in the mobile layout. Real saved chart
  snapshots may support this prototype; keep their observation time visible.
- **G5-R16 (owner-directed feeds, 2026-10-02):** Use real post examples in
  Calendar (`events`), Free stuff (`opportunities`), Jobs (`job_listings`) and
  Who's moving. Put tracked brand labels in hashtag pills, with brand-page
  linking to follow. Events/offers put live items first, then upcoming starts
  nearest first; show time until start/end, red blinking for live items and
  faster non-red blinking as a future start approaches. Preserve date precision
  and source uncertainty. Jobs sort newest fetch first and show elapsed fetch
  time; those under 24 hours use a red blinking “Just listed … ago!” label.
  Use suitable existing library glyphs for all six sections. Reduced-motion
  preferences remain part of the existing motion requirements. G4 must still
  define which source/time/identity fields its public responses can expose.

- **G5-R17 (owner-selected Pulse chart, 2026-10-07):** Use one combined
  release-response chart with three lines: collected brand posts, exact-product
  OpenRouter daily tokens and net change in the selected HF rolling-download
  counter. Normalize each line to its own raw mean over the same first complete
  post-release week; default to trailing-three-day means with fixed reference
  dates across view controls. Zero represents the reference mean. Label HF net
  counter change separately from daily new downloads and preserve gaps, source
  timing, scope, raw values and evidence. Add a linked Arena panel with raw score,
  published confidence band and reported battle counts on the shared date
  selection; rank is supporting context. Preserve actual publication markers,
  no-style-control configuration and score-scale comparability. The independent
  [benchmark plan](../../.worktrees/feat/benchmark-download-collector/docs/plans/2026-10-05-070106-feat-benchmark-download-collector-plan.md)
  owns R37–R40/U22–U23 and exact computation/verification. The dedicated
  benchmark page is implemented and verified on Render staging at `e28cbda9`
  (October 8 checkpoint); other G5 surfaces and redesign remain independently
  owned. Existing diagnostic comparisons remain available.

- **G5-R18 (OpenCode peer-source handoff, 2026-10-07):** Support the new
  OpenCode usage-provider preset planned in benchmark R42–R45/U25–U27, using
  the same shared serving/export boundaries and owned product identities.
  Preserve G5-R17's three-line default; a separately identified option can use
  OpenCode tokens in the usage line with its own pinned common reference week.
  Show hosted Go + free scope, hourly source freshness and partial/completed-day
  status. Default normalized comparisons use completed UTC days; current-day
  provisional snapshots remain explicitly separate. Keep the Arena panel and
  raw diagnostics. The dedicated benchmark provider selector is implemented
  and staging verified at `e28cbda9`, for DeepSeek/GLM with retained source facts.
  This does not activate recurring collection or integrate other G5 surfaces.

- **G5-R19 (owner redesign direction, 2026-10-07):** Refresh G5 against the
  expanded G1–G4 product and establish a recognizably independent PushinWeight
  identity, appropriate to a prospective partner of Polymarket/Kalshi. Replace
  the earlier instruction to imitate Polymarket's visual treatment. Reconsider
  page hierarchy, section composition, typography, color, shapes and interaction
  together, informed by the reporting, evidence, forecast/scenario and agent
  capabilities. No new layout or palette is selected by this direction. Preserve
  the live brand assets, G2's distinct editorial tracks, G5-R13's paired
  Human/Agent geometry and G5-R17/R18's measurement contracts unless explicitly
  revised. Kalshi is G3's selected initial candidate-workflow target; partnership,
  market acceptance and trading remain separate future states. After the context
  refresh and delegated agentic-interface research, the owner requests two local
  prototypes and browser display for review. They are comparison alternatives;
  the owner has not selected a final direction. Preserve the original prototype
  as evidence of the previous iteration.
  **October 8 owner decision:** Reject the ChatGPT-style warm-gray/font-only
  experiment at `:56887`. Return to the previous `:58417` DeepSeek/context
  design as the working baseline for future edits. Record this decision only;
  do not change pages, browser tabs or services now. The broader independent
  design objective remains open.

- **G5-R20 (lower-feed integration, 2026-10-08):** Plan the first General
  integration around Calendar (`events`), Free Stuff (`opportunities`), Jobs
  (`job_listings`) and Who's moving (`personnel_changes`). Use saved atomic
  Post commentary with linked structured facts for timing, roles and source
  attribution. G2/G3 retain headline, Chatter and Pulse work; those writing
  pipelines are not prerequisites for the four readers. Recheck the active
  official-company extraction branch before wiring personnel data, preserving
  the distinction between organization discovery and an evidenced person move.
  The existing G5 plan owns implementation sequence and regression coverage.

- **G5-R21 (shareable atomic pages, 2026-10-08):** Each displayed Post or
  published OriginalContent unit needs its own durable first-party URL and an
  expanded page. Initial expanded-page scope is full saved content/commentary,
  original sources and available media, category details, brand links, language
  state and sharing. Preserve existing story and saved-edition URLs. A source
  post with several jobs/events remains one atomic unit. Additional G3 history
  and prediction features can attach through their owners' contracts. Published
  content and citations must survive routine cleanup; a permanent URL alone
  does not meet this requirement. G2 owns the publication/retention integration.

- **G5-R22 (collapsible left navigation, 2026-10-08):** Add a collapsible
  left navigation bar with login/account actions, settings and page/section
  navigation. Reuse existing authentication and preferences, with desktop and
  mobile keyboard-accessible behavior. This is the explicit layout addition to
  the accepted :58417 baseline; retain the paired Human/Agent panel geometry in
  each navigation state.

- **G5-R23 (independent weight selections, 2026-10-08):** Open and Closed
  weights are independent choices that may be selected together, rather than
  mutually exclusive modes. Closed is temporarily unavailable: selecting it
  opens “Open Weights Coming Soon!” and dismissing that notice deselects Closed
  while preserving Open's prior state. The owner refined the exact copy and
  requested placement beside the invoking toggle on October 8; place it below
  or above that toggle as space allows, within the viewport on mobile. Apply
  this consistently in General's header
  and sidebar, with keyboard/mobile support and localized copy. Open can be
  deselected independently. Closed must not replace the displayed Open feed,
  trigger a Closed fetch, or persist as an enabled General preference for now.

- **G5-R24 (published Chatter/Pulse integration, 2026-10-09):** Populate
  the General prototype with real published OriginalContent using the existing
  shared readers. Display the saved headline, byline, full body, distinct source
  count and every source URL, preserving publication access and saved-edition
  links. Refresh G5 to current main with deployed G2/benchmark changes and refresh
  only its isolated database snapshot as needed. Preserve the accepted layout,
  paired Human/Agent geometry, controls and four lower feeds. This authorizes
  local implementation/data refresh/browser review, not collection, generation,
  publication changes or deployment.

### Proposed first step and completion evidence

Use the accepted :58417 prototype as the design reference for G5-R20–R22:
four live lower feeds, permanent item pages and collapsible left navigation.
The owner requested a `ce-plan` pass; enrich the existing G5 plan under the
repository's plan-selection rules. Broader independent design work remains
open but does not block this bounded integration plan.

As real sections are connected, verify their actual data, navigation, language
and timezone controls, refresh behavior, unavailable states and sharing. Check
desktop/mobile rendering and motion controls against the current agreed design.
Keep sample-data preview evidence separate from integrated application and
deployment evidence. Preserve unaffected G1–G4 behavior when the page changes.

### Open decisions

Independent visual direction and the hierarchy linking editorial stories,
evidence and personal forecasts; final section order and proportions;
expanded-page additions beyond G5-R21; and later archive/filter and sharing
integrations. G5-R20–R22 settle the immediate data sources, atomic URL obligation
and navigation scope; the G5 plan specifies their reader, timing and route
contracts. G5-R17/R18 select the evidence-chart contract and additional provider,
whose integration stays separately owned. These decisions can evolve within
G5 without renumbering G1–G4 or treating the first prototype as immutable.

### Registered domain

On October 9, 2026, the owner confirmed purchasing **pushinweight.si** through
**Namecheap**. The [domain reference](../reference/domains.md) is the maintained
registration record. DNS hosting, Cloudflare setup and connection to the deployed
site remain unconfirmed. Recording the purchase does not select a deployment or
change the page/URL allocation decisions above.

## Shared boundaries and dependencies

| Shared subject | Coordinating workstream | Other consumers |
| --- | --- | --- |
| Verified person identity and photo provenance | G1 | G5 personnel sections and the illustration workflow; G4 must enforce its own output boundary |
| Editorial voice, faithful post-level commentary, and model-call cost boundaries | G2 | G5 headlines/bylines and grouped Chatter/editorial writing, G3 history, and permitted G4 grouped commentary; individual-post commentary retains source voice without publication attitude |
| Continuing topic identity, historical comparisons and prediction evidence/explanations | G3 | Prediction engine; headlines and G5 history/forecast presentation; any approved G4 topic or prediction tools |
| Permitted external content | G4 | G3 if histories are agent-accessible; any other externally exposed content |
| Evolving general-page design, section behavior and integration | G5 | G1–G3 supply page content and assets; G4 coordinates shared content definitions while remaining independent of visual completion |

G1's identity records must not automatically become agent-accessible because they
exist in the database. Similarly, an editorial treatment approved for a named
person's news article does not automatically satisfy G4's obscured-identity rule.

Proposed sequence: investigate G1 coverage and G4's permitted-output boundary
early; research G2 alongside them; then exercise one G3 story with the emerging
voice and public-output constraints. Independent progress is allowed. Do not
invent a dependency merely because two tasks share a branch, environment, or
session.

G5 supplies a shared presentation target and identifies the information needed
by each section. G1–G4 can continue independently while the page evolves; G5
connects their available outputs incrementally. Workstream numbers are not an
execution sequence, and a layout revision alone does not block data or API work.
For G4 specifically, the owner's later G4-R06 direction keeps preparation
independent but places final integration/completion after G1, G2, G3 and G5.

## Homepage design carried forward into G5

The [maintained G5 design reference](../ideation/2026-10-01-190859-g5-general-homepage.md)
links the current prototype, original sketch and visual references. The owner
expects continuous revision. G5-R19 replaces the earlier Polymarket styling
instruction with an independent identity suited to a prospective partner.

The owner supplied a first-screen sketch with Chatter on the left, a chart and
scrolling news area on the right, then Calendar, Free Stuff/Jobs, and Who's Moving
below. That arrangement is the redesign's starting evidence. The earlier
Polymarket reference supplied rounded white frames, borders, chart colors,
transitions and automatic headline scrolling; it is now a historical comparison,
not the visual target. Existing functional and media requirements remain:
section sharing, rounded image/video surfaces, full-bleed personnel images and
Chatter text with transparent generated media. The original Meta Muse sample
was followed by the maintained Wang prototype; neither fixes the new composition.

The prototype includes dated real source snapshots and illustrative treatments;
it does not establish current production facts or a selected final design.
Language controls currently demonstrate navigation labels only.

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
- [G5 maintained design reference](../ideation/2026-10-01-190859-g5-general-homepage.md) — current prototype, source sketch, provenance and iteration boundaries.
- [First-screen prototype](../ideation/mockups/2026-10-01-190859-g5-general-homepage/01-above-the-fold/screens/index.html) — maintained in place as the design evolves; sample data.
- [Original prototype decisions and limitations](../ideation/mockups/2026-10-01-190859-g5-general-homepage/decisions.md) — preserved September 29 evidence, not the current G5 decision record.

- 2026-10-07T15:08:01+09:00 DECISION — official-co-production-20261006 / G1-R16: owner waives human review for verified official HF publishers with own developed/fine-tuned models. Implement evidence-bound automatic approval; other positives remain review-only. Keep independent evaluation/HF checks separate from harvest-locked registration/list writes. Canonical official-co plan U11 updated; direct production authority persists, no schema/taxonomy ownership change.

- 2026-10-07T15:12:00+09:00 G1-R16 ongoing method amendment — The owner directs that the exercise rules apply to recurring official_co_account_extraction, not only the full initial scan: shared cheap entrances/gold-first order without a post-count floor; current official brand/company checks; higher blockchain/Web3 evidence hurdle; verified official HF own-model publisher approval without human review, with all other positives held; persistent changed-evidence queue, bounded serial work and inspectable admin/list history. Main implementation ownership remains official-co-production-20261006; side scope covers explicit recurring acceptance and isolated scheduled-cycle regressions only.

- 2026-10-07T15:32:26+09:00 ON — official-co-production-20261006 / G1-R16 direct release: feature candidate a23e48d9 published; hosted CI pending, origin/main currently d66d8508. Independent discovery/admin and dedicated signed HF automatic approval only; no account schema/migration/attribution changes. Preserve G2/benchmark staging and concurrent owners; recheck production main before exact non-forced integration.

- 2026-10-07T15:42:10+09:00 ON — official-co-production-20261006 / G1-R16: candidate762ef6e7 is remotely verified on production main; hosted discovery280/228requiredPG and staff302/176requiredPG passed, zero skips/errors (staff on identical runtime a23e48d9;762 only adds recurring tests/plan). Render web/harvest building exact candidate. Enable dedicated signed HF exception after live verification, replace only owned initial job; normal cron and other resources preserved. Full population/candidate evaluation and later collection proof remain open.

- **G1-R16 HF exception live (2026-10-07T16:02:59+09:00):**762ef6e7 is live with independent discovery and verified-HF automatic settlement. Abacus passed exact-X verified HF publisher plus pinned own Smaug-Mini fine-tuning proof, registered and joined Call A automatically; add acknowledged and membership confirmed06:52:40UTC. Normal cron remains active; actual simultaneous advisory locks/progress prove independent evaluation. Coverage50,500/91,028 at06:54UTC remains incomplete. Ordinary model positives remain human-review candidates. U13 parent-company model-credit parsing correction continues in the existing branch/plan without signer rotation, schema/taxonomy work or repeated frozen experiment. Collection of later posts is separate from list membership.

- **G1-R16 latest live activation (2026-10-07T16:16:44+09:00):**826c919a is observed LIVE on web/harvest, with tested parent-company Markdown/developer credit matching and preserved signing key/flags. All91,028 original authors cheaply screened,7,717 initial candidates. Abacus, FLock.io and DatologyAI automatically registered and joined Call A after verified official HF ownership/artifacts/own development; no human review. Six total registrations include the three prior owner settlements. Detailed candidate evaluation continues in the owned source-pinned job. Subsequent posts/attribution remain unproven; list membership does not establish collection. Full task remains open without taxonomy/schema or normal cron changes.

- **G1-R16 automatic approval proof (2026-10-07T17:50:17+09:00):** Five discovered accounts now HF-approved, registered and list-confirmed: Abacus, FLock.io, DatologyAI, SambaNovaAI and Cohere_Labs. The v2 production research-publisher/parent model-card credit path is now observed for Cohere_Labs. Other positives remain human-review candidates; main @cohere has not passed. Full candidate evaluation and subsequent harvested posts remain open; normal cron and shared taxonomy ownership unchanged.

- **G1-R16 admin separation (2026-10-07T18:04:28+09:00, owner direction):** `/admin` provides distinct Official accounts found and Review needed tabs, defaulting to settled registered/owner/HF accounts. Unsettled positive decisions must not inflate Found; current review candidates retain evidence/search/pagination and cannot switch out of the review population via status filters. Keep Scan queue and past List history accessible, including suppressed historical additions without calling those accounts official. Preserve product review, auth/locales, harvesting and the running initial scan; no approval/mutation endpoint is added. U14 in the existing plan owns the bounded UI/direct-production delivery.

- **G1-R16 admin tabs live (2026-10-07T18:15:37+09:00):**1243ba01 is LIVE with distinct Official accounts found and Review needed navigation, plus preserved Scan queue and List history. Production read-only rendering verified eight settled accounts and excluded unresolved positives from Found; current review population remains searchable/paginated with evidence. Local real-browser desktop/mobile EN/Chinese/JA, products/auth/CSRF checks and285 hosted tests passed. Running initial scan, four activation flags, encrypted credentials and15-minute harvest schedule are preserved; no new approval endpoint or schema migration. Full detailed evaluation and actual subsequent collected posts remain separate open requirements.

- **G1-R16 fixed broader-rule rerun (2026-10-07T21:05:56+09:00):** Owner-selected944 accounts (896review+48failed), frozen11:35:02UTC, are evaluated using model/own-agent/own-harness alternatives; no HF requirement for company qualification. Existing86 positive baseline prevents inflated new-findings counts. Bounded immutable attempts/unknown reserved spend and independent HF settlement are tracked on all admin tabs. Implementation/checks complete locally; new source deployment and actual rerun activation pending. Deferred-population cheap rescreen and detailed initial inventory/subsequent collection remain separate open work; normal cron/taxonomy ownership preserved.

- **G1-R16 broader rule live (2026-10-07T21:21:01+09:00):**3b405b78 observed LIVE web/harvest. Owner-authorized fixed944 rerun is now actually executing with immutable old/new attempts, fixed86-positive baseline and admin counters. 15 evaluations returned/2 new findings at2026-10-07T12:19:54.915911+00:00; early results, not completion. Read-only production owner rendering proves all six tabs/current counters. Owned job job-db33g2142hec738f8nc0 continues cohort first then original inventory; unchanged flags, signer, encrypted tokens, serial USD50 ceiling/15-minute cron. Whole deferred rescreen and subsequent harvested-post proof remain separate open requirements; benchmark/taxonomy/G2 owners preserved.

- **G1-R16 frozen-run navigation (2026-10-07T21:40:14+09:00):** Owner requests dedicated saved-cohort page and easy discovery from /admin. U18 adds a prominent localized Frozen account run header link, exactly three tabs for new positive findings, awaiting retry and pending first results/in-flight requests, frozen-only50-row pagination/search and grounded decision/baseline/retry detail. Existing approvals/list/scan stay unchanged. Local43PG/browser checks pass; candidate integrates current G2 main without model/account/schema edits. Hosted checks and direct deployment remain pending behind G2's active production window.

- **G1-R16 frozen outcome details (2026-10-07T21:53:33+09:00):** The separate saved-cohort page at `/admin/official-accounts/frozen-run` and prominent `/admin` header link are LIVE f1adf84b. Owner clarification requires inspecting each outcome category: preserve Newly qualifying/Awaiting/Pending plus clickable Previously qualifying, Uncertain, Rejected, Failed evaluations and Excluded details. Native category navigation reuses fixed membership, prior/new distinction,50-row search/pagination and decision/baseline/error evidence. Expanded local43PG/browser checks pass;702fef5b hosted checks/deployment proof pending. No scan, eligibility, approval, list, scheduler or schema changes.

- **G1-R16 frozen page live (2026-10-07T22:01:59+09:00):**702fef5b is LIVE web/harvest. `/admin` links prominently to `/admin/official-accounts/frozen-run`; all eight frozen outcome categories open bounded searchable account/company/decision/evidence details, with previously qualifying distinct from newly qualifying. Existing-owner read-only production proof covers24 locale/category views and exact944 membership/counts; local desktop/mobile Chromium and309 hosted checks pass. Snapshot32new/16previous positives is eligibility, not registration/list additions. Scan job continues unchanged; full evaluation, deferred rescreen and subsequent collection remain open. Foreground production window released; no schema, approval, provider, scheduler or other-owner changes.


- **G1-R16 frozen run complete (2026-10-08T00:19:16+09:00):** saved944accounts processed under the broader model/own-agent/own-harness rule:123qualified (86new,37previous),596uncertain,187rejected,38failed,0pending/retry/excluded. The122model-positive decisions plus one independent HF verification produce the shared123qualification count; these are not123new list additions. Failed outcomes remain inspectable and are not successful model decisions. Final read-only existing-owner production proof matches every category/locale page to the same terminal ledger on702fef5b. Original owned runner continues, while whole-population deferred rescreen, remaining initial detailed evaluations and actual subsequent collection stay open. Foreground U19 released; normal cron, encrypted credentials, flags, schema ownership and other sessions unchanged.

- **G1-R16 owner induction/current production (2026-10-08T16:58:00+09:00):**421622c9 is LIVE on web/harvest, applying five internal offering categories, UUID-compatible incremental account cursors and durable shared X429 cooldowns without changing canonical product taxonomy or scheduled budgets. All123 fixed reviewed accounts have owner approval and registration;62 are independently confirmed in Call A (60new/2prior),61 remain queued because X rejects additions while advertised endpoint quota remains. Throttling must not consume account failure allowance or trigger writes for the rest of a batch. Natural Call A persists posts and the new extractor records v4 decisions; full list induction remains incomplete. Latest20 posts have17 missing-language/commentary completeness failures, retained as separate unresolved health work. Foreground claim released; existing cron retries safely, worktree/evidence retained. Consult the extraction plan U21–U23 for exact-source/check/runtime receipts and documented limits; a second list is not established as a remedy for this owner-level write restriction.

- **G1-R16 health-report correction (2026-10-08T18:49:00+09:00):** read-only U24 revisits the exact20post cohort. All20 now have succeeded classification/literal translation and3locale artifacts;6actual synthesis demands all succeeded,14never requested. Prior17-unhealthy result comes from outdated checker requirements (3valid fr codes rejected; commentary demanded on every translation). This specific result is not evidence of17processing failures. Diagnostic repair remains proposed; no pipeline/data/schedule/provider/deployment change. Preserve independent list-delivery/rescreen work and broader unassessed quarantine/capacity warnings.

- **G1-R16 owner closure (2026-10-08T20:01:05+09:00):** official-company extraction plan is closed by owner direction. Classifier/extractor/admin/frozen evaluation/registration and safe retries are deployed. Remaining Twitter list upload is an explicit operational follow-up:62of123approved identities confirmed,61queued after X429; existing recurring retries remain active. Deferred-population broadened rescreen, pending detailed candidates (52at closure) and health-checker correction are recorded future work, not completion gates for this closed plan. U24 disproved the specific17processing-failure allegation; broader capacity/quarantine warnings remain unassessed. No new runtime/deployment/schema/provider change or other-owner mutation.


- **G1-R16 owner removal / U30 (2026-10-09T10:28:38+09:00):** @niuniu_dev removed from Call A by exactly one successful native-ID DELETE and independent complete readback:152total members, no other removals. Suppress only its list intent to prevent automatic re-add; preserve company registration/approval/post history. Historical123cohort approvals remain; active desired cohort now122 (prior62confirmed minus this removal gives61;61uploads still queued at the preceding snapshot, not a fresh queue count). Fixed410post counts sorted for all60authors,256from this removed account. Grok-reported early anti-spam429s/100-add/24h examples remain attributed unverified research; official300/user/15min and spread/backoff guidance verified. No ADD, code/scheduler/deployment change; extraction plan remains closed.


- **G1-R16 personal-account correction / U31 (2026-10-09T10:36:58+09:00):** Owner identifies niuniu_dev, brennanzambo and BaseballSter as personal accounts. Two additional successful DELETEs remove the latter two; complete independent readback150members, all three absent, all others preserved. Suppress exactly these three company states/list intents with owner_personal_account so recurring extraction/delivery cannot reenroll them; retain historical decisions/approval/relationships/posts. Product development alone does not establish official company identity; retain these as explicit negative examples for future screening work. Historical123approvals remain; current desired cohort120 following three owner exclusions. No global classifier/code/schema/schedule/deployment change; extraction plan stays closed.

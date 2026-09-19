---
title: AI Enrichment Stage 1 staging integration evidence
date: 2026-09-19
status: staging-review-ready
candidate_sha: 3456f2fdc1529f3f5eec87a56a7df6ae3c575375
delivery_target: staging
---

# AI Enrichment Stage 1 staging integration evidence

## Plain-English Summary

The integrated Stage 1 candidate is available on the real Render staging site
at one exact product commit. It now includes the versioned classifier, direct
DeepInfra model routes, English/Simplified-Chinese/Japanese presentation,
demand-driven commentary, 655 official job listings, reviewed profile-history
ingestion, and the new filters and glyphs on production-shaped data.

The bounded live path is also proved without another TwitterAPI request. Four
posts already collected by the authorized on-demand discovery run completed
translation and both classifier roles. Targeted job extraction completed on
the job-board post and correctly wrote no listing because the source did not
name the employer. One pending organization candidate remains visible for
human review rather than being promoted automatically. Persistent paid-call
controls remain off, the staging harvest cron is suspended, and production has
not been changed.

## Locked runtime

| Role | Provider route | Model | Runtime state |
| --- | --- | --- | --- |
| Classification | Direct DeepInfra | `deepseek-ai/DeepSeek-V4-Flash-0731` | Implemented; no OpenRouter or fallback |
| Literal translation | Direct DeepInfra | `google/gemma-4-31B-it-turbo` | Implemented; no OpenRouter or fallback |
| Commentary | Direct DeepInfra | `google/gemma-4-31B-it-turbo` | Implemented; bounded staging call passed |

All selected routes use `https://api.deepinfra.com/v1/openai` and only
`DEEPINFRA_API_KEY`. The owner's override accepts the recorded failed or
unresolved offline gates; the model experiment report preserves those results
without relabelling them as passes.

A provider-free one-off check inside the deployed harvester
(`job-damlugcri2ms73bntpsg`) loaded the runtime configuration and reported
`deepinfra` / `api.deepinfra.com` with Gemma 4 31B for translation and 0731 for
classification. It constructed no client and made no provider call.

## Initial candidate and automated verification

- Candidate SHA: `6a24eecc7242f6cc2dc870a21ee78dc0a9b1fa8a`.
- Staging web, harvester, headline worker, jobs cron, and synthesis worker were
  verified at that SHA.
- The final aggregate local gate passed 3,181 tests, with 25 documented
  deselections, 774 PostgreSQL-required tests executed, zero required skips,
  and zero errors.
- Focused migration, rollback, JavaScript, Django, Ruff, and diff checks passed.
- `python manage.py check --deploy` returned only the three already-known
  staging warnings: clickjacking middleware, HSTS, and the generated staging
  secret-key strength warning.

## Production-shaped staging refresh

The guarded refresh job `job-daml18rm8hqs73di6bng` completed successfully.
The independent verification job `job-damlel942hec739isuvg` reproduced the
receipt, and census job `job-damlfdlbedkc73c7ajk0` independently checked the
activated database.

| Fact | Result |
| --- | --- |
| Posts | 241,905 |
| Post-brand rows | 296,807 |
| Accounts | 76,808 |
| Brands | 36 |
| Latest post | `2026-09-18T14:45:49Z` |
| Source snapshot | `2026-09-18T14:55:00.627315Z` |
| Dump bytes | 323,367,016 |
| SHA-256 | `c7efd0fff7f87f94c813a2d75972516abfa9bd72f5fe6585c18470d1bfb23511` |
| Recovery database | `pushinweight_staging_recovery_20260918t152140z` (disabled) |

All 29 operational/private-state tables checked by the census were empty after
scrubbing. There were no duplicate current narrative windows and no
unvalidated foreign keys. The site record was
`pushinweight-staging-web.onrender.com` / `Pushin Weight Staging`.

Migration/seed job `job-damlg1u7bikc73c3v96g` applied through
`0044_merge_20260918_1344`, including the U18A v4 schema and the direct-jobs
branch, then checked all 188 locale-label rows with no missing inserts.

## Service and database identity

Independent one-off checks established that the web, harvester, headline, and
synthesis services all use database/role `pushinweight_staging` /
`pushinweight_staging` on the same staging database host. The web, harvester,
headline, synthesis, and jobs services all reported the candidate SHA.

At rest, the headline and synthesis provider-call controls are false. The
harvester's schedule remains the intentionally impossible `0 0 31 2 *` and the
service was suspended at `2026-09-18T21:00:29Z`. No production service,
database, secret, schedule, or branch was changed.

As a read-only cross-check, the production web, harvester, and headline
services remained live on Stage 0 SHA
`af272b6fe0b43be3276429792508749b9ddc8194`; the production harvest schedule
remained `*/15 * * * *`.

## Bounded commentary acceptance

The synthesis service first proved `DEEPINFRA_API_KEY` was present without
printing its value (`job-damlptv40ujc73beb93g`). Post
`2100959485300732293` was then requested as one operator demand and processed
by exactly one one-off worker invocation with provider calls enabled only in
that job.

| Measurement | Result |
| --- | --- |
| Model / provider | `google/gemma-4-31B-it-turbo` / direct DeepInfra |
| Claimed / succeeded / failed | 1 / 1 / 0 |
| Provider elapsed time | 18,136 ms |
| Input / output / total tokens | 634 / 217 / 851 |
| Provider-reported cost | $0.00013084 |
| Final publication state | `ready` |
| Published locales | EN, ZH-CN, JA |

The management-command projection reported `pending` while retaining last-good
content before the call and `ready` with the new three-locale artifact
afterward. The provider-free
status check then reported one succeeded demand, zero pending/processing/failed
demands, one current artifact, the same token counts, and provider calls still
inactive at rest.

Two idle observation checkpoints at `2026-09-18T15:59:12Z` and
`2026-09-18T16:15:55Z` covered two normal 15-minute staging intervals after
the synthesis deployment. Both reported exactly one succeeded demand, no
pending/processing/failed demand, 634/217 observed input/output tokens, and
provider calls disabled. The second database check still reported 241,905
posts and latest post `2026-09-18T14:45:49Z`; an error scan across all five
staging services returned no traceback, uncaught error, out-of-memory event,
provider failure, or failed status during the window.

## Browser evidence

The hosted staging root redirected anonymous access to the expected login wall.
Changing the normal Django language cookie rendered the complete login flow in
English, Simplified Chinese, and Japanese without console or uncaught-page
errors. The production-derived refresh intentionally scrubbed users and
sessions, so authenticated feed, graph, filters, and the seven locked glyphs
could not be rechecked on the hosted environment without creating an auth
bypass. Their candidate behavior remains covered by the passing local browser
and UI suites; this report does not misstate that local evidence as an
authenticated hosted pass.

## Harvester acceptance attempt

The first manual staging Trigger Run began at `2026-09-18T15:32:58Z` and
stopped at the provider preflight with
`provider_credential_missing:translator`. It made zero Twitter searches, zero
model calls, and no post or cursor mutation. The cause was the absent
`DEEPINFRA_API_KEY` on the staging harvester service.

The staging harvester was corrected and a later one-off check proved both the
DeepInfra and scheduled Twitter credentials are present, with values redacted.
The owner then authorized exactly one replacement Trigger Run. It began at
`2026-09-18T20:58:46Z` and was recorded as
`20260918T205912_0000-0c3aa4cf`. It performed one Twitter search/page, received
two results, kept and inserted one post, and attributed post
`2101052699269886249`.

Translation succeeded. The content classifier call used 7,208 input and 56
output tokens, cost $0.00044256, and completed in 1,874 ms. The brand classifier
call used 6,861 input and 48 output tokens, cost $0.00042030, and completed in
2,990 ms. Both provider calls succeeded, but their output did not produce a
publishable combined classification; the post remained pending with
`classification_incomplete`. The relevancy step also attempted the obsolete
`deepseek-v4-flash` model through an incompatible Anthropic-style adapter,
failed, and retained its keep-biased result.

The selected search call safely advanced its cursor and transferred the
uncovered residual window to the durable backlog. Its resulting
`truncated_replay_queued` status was nevertheless rejected by the old
acceptance wrapper as `pipeline_or_bound_failure`. This run is therefore
retained as failed and is not reinterpreted as an acceptance pass.

Two earlier staging executions exposed related defects. The run around
`19:22 UTC` inserted four posts and completed translation and both classifier
calls, but publication rejected all four with
`classification_trace_input_fingerprint_mismatch` because the classifier and
publisher reconstructed different tracked-brand catalog revisions. The run
around `20:23 UTC` inserted two posts and persisted both stages, but the wrapper
reported incomplete output because it still required commentary fields even
though literal translation and classification complete the harvest lane and
commentary is a separate synthesis lane.

A read-only Render review found five executions around `17:25`, `18:22`,
`19:22`, `20:23`, and `20:58 UTC`. The live and Blueprint schedule remained
`0 0 31 2 *`, there was no matching deployment or schedule change, and each
execution identified itself as manual. Render audit logs are unavailable on
the current plan, so the actor cannot be identified. These are recorded as
unexplained Dashboard/API Trigger Runs, not an old hourly cron. The staging
harvest service remains suspended.

The local correction now carries one validated tracked-brand catalog snapshot
through prompt construction and publication, defines literal-v2 completion
from the current successful EN/ZH-CN/JA artifact, accepts a truncated call only
when durable backlog transfer and cursor advancement are proved, and routes
matching relevancy work through the direct DeepInfra classifier client. Legacy
completion behavior remains unchanged.

## Final exact-SHA staging attempt

The corrected candidate `8c80ee1809e44c5dafc88d379e59c8dec8affb21` passed the
final local aggregate and was deployed at that exact SHA. The feature branch
and remote staging ref resolved to the same candidate. The staging web,
headline, synthesis, and jobs services were independently verified at that
SHA. The staging harvester was resumed only long enough to deploy and run the
preflight checks, then was suspended again.

The exact aggregate completed with 3,195 passed, 25 deselected, 82 warnings,
774 PostgreSQL-required tests executed, zero skips, and zero errors in 424.24
seconds. The successful preflight job `job-damr673ncjis73chr6o0` proved the
service was `pushinweight-staging-harvest`, the environment was staging, and
the database/role was `pushinweight_staging` / `pushinweight_staging`. It also
proved the locked runtime was direct DeepInfra with classifier
`deepseek-ai/DeepSeek-V4-Flash-0731` and translator
`google/gemma-4-31B-it-turbo`; required credentials were present and their
values were never printed. The preflight selected call A. A second inspection
job, `job-damr5m6k1f9s738l3lv0`, failed only because its inspection command
used the obsolete local attribute names `translation_*` instead of the live
`translator_*` names. It made no provider or Twitter call and does not change
the successful preflight result.

The owner-authorized manual Trigger Run was executed exactly once at about
`2026-09-18T21:58:53Z`, with run ID
`20260918T215853_0000-4468c64e`. The top-level outcome is **inconclusive**,
with evaluator reason `no_results`: the cycle completed one selected Call A,
but returned no results. Its terminal metrics were:

| Metric | Result |
| --- | --- |
| Twitter results / kept / inserted / updated | 0 / 0 / 0 / 0 |
| Persist failures / attributed | 0 / 0 |
| Cursor advanced / errors | `true` / 0 |
| Enrichment counts | all 0 |
| Evidence rows | 0 |
| Headline dispatch | ineligible; no task |
| Headline provider calls | 0 before / 0 after |
| Headline queue | 0 before / 0 after |

The historical backlog was not consumed: five pending backlog windows and seven
translation-succeeded/classification-pending enrichment rows, plus two fully
succeeded enrichment rows, remained unchanged and were excluded by the
current/carryover cap of 5/5/0. The staging harvester was immediately
re-suspended and its dormant
schedule remains `0 0 31 2 *`. Production remained independently live on the
main `*/15 * * * *` schedule and was not touched.

This exact live attempt does not pass the Stage 1 acceptance gate. It provides
no live classification or enrichment result from which to assess the corrected
pipeline, so Stage 1 is not authorized for production. The earlier failed run
and this inconclusive run remain immutable historical evidence.

## Owner-authorized on-demand retry

After the preceding inconclusive run, the owner separately authorized one
retry specifically to test the manual staging lane with the on-demand
TwitterAPI credential. This is a distinct acceptance attempt and does not
rewrite the prior result. Manual and backfill cycles select `ON_DEMAND`; only
scheduled cycles select `SCHEDULED`. The retry ran at exact candidate SHA
`554449c6965286dbcfec6f220e72614d2a1c1020`, and all staging services were
verified at that SHA.

The Render run was `20260919T002539_0000-1ce111b6`, with cron run ID
`crn-da7vrdqd0e5s739uvcs0-1789777507`. It made one Call A/search request and
received one result. The relevancy model succeeded, followed by one LLM drop;
no post was kept, inserted, or attributed, and there were zero recorded
errors. The final acceptance outcome is **inconclusive**, with reason
`no_inserted_posts`. The staging harvester was suspended immediately after
the retry. Production remained untouched.

The focused PostgreSQL gate for this routing correction passed: 80 tests
passed, 26 PostgreSQL-required tests executed, with zero skips and zero
errors. This confirms that the manual staging test used the intended
on-demand credential lane, but it still does not provide a live classified
post and does not pass the Stage 1 live acceptance gate.

## Historical gate before existing-data probes

At this checkpoint, the final exact-SHA attempt and the separately
owner-authorized on-demand retry had both been consumed. Both were inconclusive
for live acceptance: the
first returned no results, and the retry received one result but inserted none
after the relevancy drop. The routing correction is covered by the focused
gate, but the Stage 1 live acceptance gate is not passed. The staging cron
remains suspended, and no further Twitter/provider-backed Trigger Run is
permitted under this evidence record.

Headline enqueueing and headline provider calls remained disabled and had a
required zero-call delta. The later existing-data probes below superseded this
checkpoint without consuming another TwitterAPI request. Production remains
outside this LFG delivery target.

## Five-post existing-data staging probe

The owner next authorized a bounded probe over five posts already present in
staging, with no TwitterAPI request. The fixed cohort contained three English,
one Simplified-Chinese, and one Japanese post and seven total post-brand
decisions. The locked routes were direct DeepInfra 0731 for classification and
direct DeepInfra Gemma 4 31B for literal translation and synthesis.

Two initial harness defects were kept as failed evidence. A web-service job had
no DeepInfra credential and made zero provider calls. The first harvest-service
probe capped the classifier below its six-request two-role retry reservation;
translation ran, classification did not, and the enclosing transaction rolled
back. One Gemma request also timed out after 90 seconds during that attempt.
After the cap was corrected, all four required translation requests and both
five-post classifier-role requests returned successfully, but strict
classification validation rejected the cohort and synthesis was not called.
The transaction again rolled back, leaving staging data unchanged.

A classifier-only, rollback-only diagnostic isolated the rejection. Four of
the five posts parsed successfully. The three-brand Chinese post was withheld
because 0731 selected `china_national_stance=constructive_critical` with
`geopolitical_modes=[framework]` and omitted the mechanically required
`nationalism` mode. This directly violates the locked invariant that every
non-`none` U.S. or China national stance entails the nationalism mode. The
parser correctly failed the affected post closed rather than persisting a
contradictory row.

The candidate correction adds only that deterministic implication before the
existing strict validation: when a recognized non-`none` national stance is
present alongside non-sentinel geopolitical modes, append `nationalism` if it
is absent. Contradictory `none` or `unavailable` mode answers still fail
closed. The focused selected-route suite passes 41 tests; seven PostgreSQL-only
tests remain to be rerun in the staging gate. No production resource was
touched, and the staging harvester remains suspended.

The first repaired candidate, `04d1eb7d247b2e018e8b5615173e4f8fb94447fc`,
then passed 59 focused tests on staging with 13 PostgreSQL-required tests
executed and zero skips/errors. Its exact-SHA five-post rerun again completed
all four translation calls and both classifier roles, but failed closed before
synthesis. A second rollback-only raw capture found a different observed 0731
representation: every explicit `none` promotion was returned as
`{"promotion":"none"}` instead of `["none"]`. This made all five content rows
invalid even though the enum itself was explicit and allowlisted.

The follow-up candidate therefore also unwraps only an exact one-key
`promotion` object whose value is allowlisted. Extra keys, unknown values, and
all other shapes remain invalid. This is the same bounded mechanical
normalization class as the already accepted scalar-to-singleton-array rule; it
does not infer a promotion or change taxonomy semantics.

### Final bounded-probe result

The completed candidate is `45532f72c1e3f3baa62f8facfe7ad926950dd749`.
During the continuation, the probe found and corrected two additional
representation defects without changing taxonomy semantics. First, tracked
brand aliases such as `Grok` and `grok` had been sorted only by their folded
case. Their tied order could change during catalog reconstruction and produce a
different catalog revision before any classifier call. Catalog text is now
ordered by folded value and original value, and the case-variant regression is
covered directly. Second, Gemma consistently preserved commentary identity,
locale order, and text while sometimes using the next locale's closing tag as
the field boundary. The parser now accepts only that ordered single-line Gemma
grammar, while continuing to reject wrong post IDs, reordered fields, tag text
inside values, duplicate locale content, multiline values, and trailing text.

The final persisted probe passed over the same fixed five existing posts: three
English, one Simplified-Chinese, and one Japanese. It produced five current
Gemma literal-translation artifacts, seven 0731 post-brand classifications,
and five current Gemma synthesis artifacts. Every translation and synthesis
artifact contains `en`, `zh-cn`, and `ja`; every enrichment state and synthesis
demand is `succeeded`. The seven classifications cover Llama, Yi, StepFun,
DeepSeek, GLM, MiniMax, and Qwen. The Qwen row also persisted `local_inference`
and the still-shadowed `cost_performance` audience topics. The Chinese
three-brand synthesis required one normal persisted retry after its first
response failed the old tag parser; its final demand has two attempts and no
error. No TwitterAPI request was made.

The persisted classifier pass used exactly the two locked direct-DeepInfra
0731 roles and succeeded on the first transport attempt for each role. It used
19,483 input and 672 output tokens in total; response-reported cost was
`$0.00085218`, including provider cache discounts. Four of the five synthesis
rows persisted in the initial batch, and the one pending row then passed its
targeted retry under the bounded parser correction. Earlier rollback-only and
failed-parser calls remain diagnostic spend and are not presented as part of
the persisted-pass cost.

The completed SHA passed 61 focused classifier tests with all 13
PostgreSQL-required cases executed and 26 focused synthesis tests with all 14
PostgreSQL-required cases executed. An earlier combined classifier/synthesis
candidate also passed 85 tests with all 27 required PostgreSQL cases executed.
Every gate had zero required skips and zero errors. A final read-only database
audit (`job-damuncijnfac73enmmr0`) proved five posts, seven post-brand
decisions, complete three-locale artifacts, succeeded enrichment/demand state,
and zero TwitterAPI calls.

At runtime verification, the feature and staging refs both resolved to the
completed candidate. The staging web, harvest, synthesis, and jobs services
were verified live at that SHA. A superseded intermediate headline build was
canceled so the queued completed candidate could deploy; the final headline
deployment became live at the same SHA at `2026-09-19T02:01:32Z`. The staging
harvest cron was re-suspended at
`2026-09-19T01:56:50Z`, and its impossible schedule remains `0 0 31 2 *`.
Production was not modified.

## Final integrated staging candidate

The product candidate deployed for owner review is
`36fb513aac1ce4e9345ba8f798d29ac2e9f9a20d`. The feature and staging refs
resolved to that commit, and Render independently reported it live on the web,
headline, synthesis, harvest, and official-jobs services. The harvest service
was re-suspended after deployment and retains the impossible schedule
`0 0 31 2 *`. The jobs cron uses the same impossible schedule. Headline
enqueueing/provider calls, synthesis provider calls, discovery, targeted
extraction, and synthesis prewarming are all disabled at rest.

### Existing-data classifier and extraction proof

The final bounded classifier retry used four posts already present in staging:
`2101217602865356884`, `2101218361439121481`, `2101227418791072101`, and
`2101235748636651958`. It made no TwitterAPI request. All four ended with
successful translation and classification under direct DeepInfra Gemma 4 31B
and the two direct DeepInfra 0731 roles. The five classifier invocations used
in the four-post pass plus its one-post retry cost `$0.00194826` in total.

The first targeted job extraction exposed two server-boundary defects. A source
may give an exact organization handle without a separate display name, and the
model had been allowed to choose the evidence extraction method. The writer now
uses an exact source-visible name or, when absent, an exact source-visible
handle, while the server always records the extraction method as
`structured_text`. The model no longer supplies that provenance. The final
retry succeeded and wrote zero job listings because the post was a generic
job-board claim with no named employer. This is the intended fail-closed result
under the locked extraction prompt.

One pending `BrandDiscoveryCandidate` remains from the untracked-promotion
path. It observed `AI Data Annotator` from the source text and is linked to one
promotion-evidence row and no job listing. It is deliberately pending human
review. This is useful evidence of the current limit: author account metadata
is not yet part of the classifier payload, so generic job-title language can be
proposed as a candidate. Nothing promoted this candidate into the tracked-brand
catalog.

### Other integrated data paths

- Official recruiting-source sync succeeded for Qwen (270), DeepSeek (34),
  MiniMax (101), Zhipu (146), and Kimi (104), for 655 current staging listings.
- The bounded profile-history pass reviewed 100 accounts and recorded 324
  observations and 244 snapshots: 144 changed, 80 unchanged, and two unknown
  affiliation candidates.
- The bounded synthesis pass claimed and completed three demands. The final
  staging census contains nine succeeded and six cancelled demands, nine
  current artifacts, and no pending, processing, or failed demand.
- The final enrichment census contains 17 fully succeeded rows and four older
  untouched pending rows. Targeted extraction contains one succeeded row and
  no pending or failed row.

### Hosted owner-review surface

The authenticated browser pass ran against
`https://pushinweight-staging-web.onrender.com/` on the exact candidate. The
home view rendered 655 official job cards, the new post types and owner-locked
Column A glyphs, Audience Topic controls, graph and feed content, and working
English/Japanese locale switching. The DeepSeek brand page rendered its
official jobs and all current filter families, including Results Analysis,
Job Listings, Personnel Changes, News Reporting, and Audience Topics. The
same URL has been opened in the owner's Chrome; that browser is at the ordinary
Google sign-in wall because its staging-domain session was not already logged
in. No authentication bypass was added.

Final hosted screenshots are retained under
`.context/u23-hosted-browser-20260919-final/` for the English home, Japanese
home, expanded Japanese filters, and English/Japanese DeepSeek brand views.

### Final idle-interval observation

The deployed candidate was observed at `2026-09-19T10:07:08Z`,
`2026-09-19T10:22:46Z`, and `2026-09-19T10:37:25Z`, covering two complete
normal-equivalent 15-minute staging intervals. The first and second interval
checks returned the same database census: 17 succeeded/succeeded enrichment
rows, four pending/pending historical rows, nine succeeded and six cancelled
synthesis demands, one succeeded targeted-extraction state, 655 job listings,
and one pending brand candidate. There was no pending, processing, or failed
synthesis work and no pending or failed targeted extraction.

All five Render services remained live at product commit
`36fb513aac1ce4e9345ba8f798d29ac2e9f9a20d`. The harvest cron remained
suspended, and Render returned zero error-level log bytes across the web,
headline, synthesis, harvest, and jobs services from the initial observation
through `2026-09-19T10:38:00Z`. The actual headline worker reported provider
calls, demand shaping, and critic routing false; `headline_status` also reported
serving, enqueueing, and provider calls inactive. No TwitterAPI or model call
occurred during the observation window.

### Final automated gate

The exact candidate passed the established aggregate command on a freshly
recreated PostgreSQL test database: 3,231 passed, 25 documented deselections,
83 warnings, 783 PostgreSQL-required tests executed, zero required skips, and
zero errors in 493.16 seconds. The JUnit receipt is
`/Users/fuchitalee/.local/state/pushinweight-stage1-u5-tests/resume-u23-final-36fb513-r4-junit.xml`.
An earlier attempt encountered a PostgreSQL deadlock while a live-browser test
was releasing its fixture; the two affected tests passed in isolation on a
fresh database before this complete clean rerun.

## Historical staging review clock follow-up

The production-shaped snapshot ends at X-post timestamp
`2026-09-18T14:45:49Z`. By September 19, dashboard queries still used the real
wall clock, so `window:1d` legitimately selected no copied rows. Changing the
locale reloaded that same empty interval. This was a review-environment clock
mismatch, not a locale data-loss defect.

When the existing owner-only staging profile is active, the dashboard reads
the guarded refresh receipt's `posts.created_at` cutoff and uses
`2026-09-18T14:45:49.000001Z` as its review horizon. Sparse posts inserted by
later bounded staging probes cannot move it. A pre-refresh or local staging
database without a receipt falls back to its newest post. The extra microsecond
preserves the existing half-open database interval while including the newest
copied post. Feed rows, graphs, pulse, top voices, brand pages, hover ranges,
server relative labels, and browser relative labels now receive the same horizon.
Changing EN to JA therefore retains the same ordered post identities. In
production, where the staging profile is absent, all paths continue to use wall
time.

No stored timestamps are changed. Official recruiting-site listings remain
source-dated and use the same historical calendar. A listing five days before
the copied-post horizon is absent from `1d`, present in `7d`, and unchanged in
the database. The existing Qwen, DeepSeek, MiniMax, Zhipu, and Kimi crawler and
its 655 staged listings remain part of the product; its Render cron remains
manual-only on `0 0 31 2 *`.

The focused PostgreSQL run passed 21 tests covering the review clock, official
job feed behavior, and staging/production Blueprint separation. The JavaScript
feed/timezone suites passed 104 checks, and Django's system check was clean.
The new browser regression reached its expected application assertions once
before the host exhausted its local TCP ephemeral-port pool; the latest rerun
could not connect Chromium to the local live server and is not represented as
a passing candidate-browser gate.

The final product candidate is
`3456f2fdc1529f3f5eec87a56a7df6ae3c575375`. The first deployment attempt
exposed that Render excludes the operational `scripts` tree from its web build;
the candidate now reads the small fixed receipt projection locally without that
runtime import. Web, headline, synthesis, harvest, and official-jobs services
all report the exact candidate live. Harvest was resumed only to deploy, then
returned to user-suspended state on schedule `0 0 31 2 *`; official jobs retain
the same impossible schedule.

Provider-free one-off job `job-dan7lvjbc2fs73f9prig` ran against the deployed
web image and staging database. It reported review horizon
`2026-09-18T14:45:49.000001Z`, identical ordered EN and JA identities for the
first 20 `window:1d` rows, and 655 job listings. The owner's authenticated
Chrome window is open at the English one-day staging URL and renders the normal
PushinWeight page title. Chrome disallows JavaScript inspection through Apple
Events, so this receipt records the deployed server assertion and owner-visible
page without overstating it as a scripted hosted-DOM browser pass.

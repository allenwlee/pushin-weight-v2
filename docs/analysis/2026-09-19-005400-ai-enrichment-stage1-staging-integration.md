---
title: AI Enrichment Stage 1 staging integration evidence
date: 2026-09-19
status: staging-partial
candidate_sha: 6a24eecc7242f6cc2dc870a21ee78dc0a9b1fa8a
delivery_target: staging
---

# AI Enrichment Stage 1 staging integration evidence

## Plain-English Summary

The integrated Stage 1 candidate is deployed to the refreshed staging stack at
one exact Git commit. The database migration, production-shaped refresh,
direct-DeepInfra model routing, and one real Gemma commentary call have been
proved on staging. The commentary call completed and published English,
Simplified Chinese, and Japanese output while the persistent worker remained
disabled before and after the test.

The first bounded harvester acceptance attempt stopped before Twitter search or
model use because the staging harvester did not yet have `DEEPINFRA_API_KEY`.
The key is now present on both the harvester and synthesis services, but the
acceptance runbook prohibits an automatic retry. One replacement attempt needs
separate owner authorization. Production has not been changed.

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

## Candidate and automated verification

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
harvester's schedule remains the intentionally impossible `0 0 31 2 *` and is
manual-only for acceptance. No production service, database, secret, schedule,
or branch was changed.

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
The exact candidate, refreshed database, one-page/five-post cap, impossible
schedule, and empty pre-run queues remain unchanged.

The runbook at
`docs/operations/2026-08-27-171845-staging-harvester-acceptance.md` says:
“A new attempt requires separate owner authorization and a new recorded
attempt; the historical result below remains immutable.” A replacement attempt
therefore remains blocked on that authorization. No replacement trigger has
been run.

## Remaining staging gate

After authorization, run exactly one replacement acceptance attempt with one
Twitter search/page and at most five posts, capture the structured route,
token, persistence, and visibility evidence, then return the harvester to its
dormant state. Headline enqueueing and provider calls remain disabled and must
record a zero-call delta; enabling them would require the runbook's separate
headline-provider budget authorization. Update this report and
[PR 41](https://github.com/allenwlee/pushin-weight-v2/pull/41) with the result.
Production remains outside this LFG delivery target.

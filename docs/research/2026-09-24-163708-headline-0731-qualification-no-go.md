# Headline 0731 qualification: retain V4.1 Flash

**Decision:** `retain_v41_flash`. The candidate is cheaper, faster than the stated window budgets on this one run, and mechanically more reliable than the current control, but it fails the locked factual-support and critical-failure gate. Do not activate it, deploy this candidate to staging or production, or treat the profile as qualified. This is the U5 terminal failure result for [the headline architecture plan](../plans/2026-09-24-060052-feat-headline-0731-architecture-plan.md); U6 is not entered.

The untouched production-data holdout has SHA-256 `7a808d08967e3d1b84e5c29add9416dabcd6000f368e4d9a12b76c881774226c`. It contains one 1-day and one 7-day snapshot frozen at 2026-09-24 07:00 UTC, with 22 and 25 eligible brands. Both arms used the same snapshots and production packet builders. The 0731 arm used direct DeepInfra, priority, reasoning disabled, strict stage-specific JSON schemas, two-brand editor/critic packets, and evaluator concurrency three. The V4.1 arm retained the current five-brand, sequential route. No publication rows were written.

| Measure | Current V4.1 control | 0731 candidate |
| --- | ---: | ---: |
| Calls completed | 22/22 | 50/50 |
| Eligible brand outcomes terminal | 47/47 | 47/47 |
| Mechanical-invalid calls | 17 | 2 |
| Available narratives | 5 | 44 |
| Missing locale fields | 0 | 0 |
| 1-day / 7-day wall time | 2.86 / 4.11 min | 4.63 / 5.90 min |
| Cost | ~$0.398 priced from reported tokens at then-applicable peak rates; no per-call dollar receipt | $0.11956653 in 50 DeepInfra receipts |

The priced-usage ratio is about 30.1%, below the planned 35% ceiling. The older $0.539 V4.1 figure in the harness uses a conservative frozen rate and is **not** the current billed comparison. DeepSeek's response supplied token and cache counts, but not a per-call dollar amount; its [published billing formula and peak rates](https://api-docs.deepseek.com/quick_start/pricing/) support the ~$0.398 calculation. This is a calculated cost comparison, not proof of the exact account bill.

The five-part blind rubric and 24 randomized A/B assignments were frozen before reading either holdout output. Three separate model reviewers each judged eight disjoint pairs: GPT-5.6 Sol, Gemini 3.8 Flash, and Grok 4.7. Their complete returned scores and comments are preserved in the [assignment manifest](2026-09-24-163708-headline-0731-review-manifest.json) and [R1](2026-09-24-163708-headline-0731-review-r1.json), [R2](2026-09-24-163708-headline-0731-review-r2.json), and [R3](2026-09-24-163708-headline-0731-review-r3.json) records. These are independent **model** reviews, not human gold labels.

Across the 24 pairs, the candidate was preferred 12 times, V4.1 10 times, and two tied. Its mean rubric score was 3.475/5 versus 1.308/5 for V4.1, largely because the control held most outputs. Yet reviewers found **10 candidate critical failures versus zero control critical failures**. The locked SC2 rule does not allow availability or higher average score to offset a critical factual-support error. We checked the cited source packets for representative failures:

- H01, StepFun: the candidate says volume fell from the prior period even though the dossier's comparison status says `allowed=false` because of unresolved harvest backlog. It also broadens one reported allegation into an AI security trend.
- H02, SenseNova: it reports a 2-to-10 increase despite the same suppression and claims the release dominated official posts on thin source support.
- H08, Yi: Turkish text matched through the suffix “-yi” is described as 01.AI Yi discussion even though the cited posts are unrelated to that brand.
- H11, Upstage: it says 84-to-97 posts is a 28.6% rise; that arithmetic is wrong, and the period comparison is suppressed. H21 and H22 similarly leak suppressed prior-period counts.
- H23, Kuaishou: a roughly $500 million figure about DeepSeek is reassigned to Kling in the headline argument.

A deterministic scan found explicit prior-period comparison wording in **15 of the 44** available candidate narratives whose source dossiers disallow that comparison. This is a screening count, not 15 independently adjudicated critical failures; the reviewed examples establish the underlying defect.

Other gates also lack sufficient proof. The diagnostic critic calibration records four `repair` decisions on planted unsupported drafts as conservative false accepts. Inspection suggests those four repairs removed the planted claims, but changing the locked scorer after seeing results would invalidate the gate; its recorded result remains failed. One observed run per window cannot establish a p95 distribution or queue-drain behavior. The proposed worker uses three processes on Render Starter's [512 MB plan](https://render.com/docs/compute-plans), and no three-process Render memory measurement establishes the required 25% headroom. These do not change the no-go decision; SC2 already fails.

Focused headline, provider, evaluator, and orchestration checks passed (69 tests). Additional topology and Ollija checks passed (103 tests). `manage.py check --deploy` completed with three existing local security-setting warnings. A clean-database full-suite run stopped at an unchanged legacy home-filter test expecting an older HTML structure; a second run excluding that file encountered ten more legacy UI failures. This branch changes no UI surface, and the relevant headline tests passed. The initial full-suite attempt also had an invalid shared-test-database collision; it was discarded before the clean-database rerun.

Local raw evidence is retained, uncommitted, on the authoritative `fuchitalee` host: the frozen holdout under `.context/compound-engineering/headline-0731-qualification/` and both exact request/response artifacts under this worktree's `.pytest-tmp/u5-{incumbent,candidate}/`. They contain full post text and provider requests, so this report records their hashes instead of copying them into Git. The V4.1 artifact SHA-256 is `39f29fccfc8df0008cecd68bf9fd34e958bc6f6cdda2150106cce5635758adeb`; 0731 is `dc8325fa74b03d744098458060ea756c1cbbb9029cabdf0ecd89b2805a712e82`. Those paths are machine-local and should be preserved until the next qualification is designed.

The frozen candidate artifact's `route_evidence.request_profile` display string says `v1`; that is a harness metadata typo. Its retained provider requests and the configuration used for this run show the `v2` strict JSON-schema profiles. The script's display constant was corrected after the immutable run, so the artifact hash above remains unchanged.

Any future candidate needs an upstream/post-generation guard for comparison suppression, brand-specific evidence ownership, and claim arithmetic, then a new untouched holdout. The present holdout cannot become a fresh acceptance set for a revised prompt or guard.

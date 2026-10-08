---
title: Original 20-post health diagnosis
created_at: "2026-10-08T18:48:10+09:00"
status: diagnosis-complete
scope: read-only-original-cohort
---

# Original 20-post health diagnosis

The previously reported17 unhealthy posts are false failure classifications by a health checker that still assumes the older combined translation/commentary contract. This investigation does not establish overall harvester health, but it found no failed translation, classification or requested commentary in this exact20-post cohort.

## Persisted evidence

Rechecked the same20 IDs once at18:45JST; no newer cohort was substituted. The unmodified checker still reports17 unhealthy,3 complete and0 pending. Its counts are6/20 commentary,17/20 accepted language codes and15/15 translated non-Chinese rows. Preserve this failed diagnostic result; do not describe it as a passing check.

A separate bounded read-only query joins those IDs to current translation/synthesis artifacts and demand records. All20 have succeeded translation and classification, no remaining stage error, a current succeeded literal-translation-plaintext-v12 artifact and three locale children. The two previously fresh-pending posts completed translation at07:48:32UTC. Six posts have synthesis demand (five visible, one lookahead); all six demand records and current synthesis artifacts succeeded. Fourteen posts have no synthesis demand or commentary artifact. Missing commentary on these undemanded posts is expected under the split, demand-driven product contract.

Three falsely flagged language records contain fr in both posts.lang_detected and the current translation artifact. normalize_lang_detected accepts registered ISO639-1 codes, including fr/es/de, and rejects und/zz. The health checker SQL and acceptance calculation still restrict language to en/zh-Hans/zh-Hant/ja/ko/other, incorrectly naming a saved valid French code missing_lang_detected.

## Source trace

- x_monitor/translator.py:522 normalizes validated ISO primary codes.
- monitor/cycle.py:4041 publishes normalized literal artifacts independently of synthesis.
- monitor/post_artifacts.py:169 validates three literal locales and projects language/EN/ZH back to posts.
- monitor/post_synthesis.py stores reader/operator demand and separate synthesis lifecycle.
- .claude/skills/harvester-latest-n-health-check/scripts/check.py:297 uses a stale fixed language list; :814 requires commentary whenever literal translation succeeds; :947 repeats the restricted language set in acceptance percentages.
- docs/reference/post-content-artifacts.md and commenter.md explicitly separate eager translation from demand-driven commentary. translator-output.md still contains an outdated six-code table despite the implemented ISO normalization.

Relevant enrichment/translation/checker source is unchanged between421622c9 and production00d73117. Natural cycle20261008T073049_0000-94005ec2 at a66b5963 reports zero translator/classifier batch failures or unavailable clients. It does report one quarantined carryover and48 pending enrichment states outside the now-complete selected cohort; these other queue/capacity issues are not resolved or declared healthy by this investigation.

## Required diagnostic correction

Use the shared validated language normalization rather than a second restricted list. For the split contract, judge eager translation by current successful locale-complete artifacts plus durable classification. Report commentary coverage separately; evaluate failures/overdue work for actual demand records, and distinguish never requested, pending, cancelled, failed and succeeded. Preserve meaningful corruption/missing-artifact/locale/classification checks and the older combined-path requirements for historical cohorts. Extend the existing diagnostic regression tests for valid French, successful literal text with no demand, demand failure/overdue work, and absent/invalid locales. This is a proposed follow-up, not an implemented repair or a changed acceptance policy.

## Safety and receipts

No harvesting, TwitterAPI/LLM call, synthesis demand, production write, service/schedule/credential change or deployment. Evidence is under ignored .context/official-co-execution/u24-*: original-cohort-health.json, original-cohort-details.sql/json,0730-cycle-logs/summaries.json and diagnosis-summary.json. No post bodies or credentials are included here. Local source inspection/provider-free language normalization and production read-only evidence are distinguished from new application test or deployment proof.

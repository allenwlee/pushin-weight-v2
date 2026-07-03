---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
title: Taxonomy Extension for Promotional & Crypto Posts - Plan
date: 2026-07-03
---

# Goal Capsule

**Objective**: Extend the existing `post_type` + `sentiment` + `discourse_role` taxonomy (introduced in the 2026-06-24 schema modernization) to explicitly categorize two high-signal but previously uncategorized post classes that frequently appear in wide-net X monitoring for AI/LLM brands.

**Primary Actor**: DevRel (and secondarily marketing/legal teams).

**Desired Outcome**: 
- Promotional/advertising/spam posts (CTA-heavy, discount offers, overwhelmingly positive commercial intent) and crypto/scam posts (brand-name-jacking for tokens, unendorsed projects, pump schemes) are cleanly tagged.
- These appear as distinct filters/buckets in the dashboard and review queue.
- They preserve orthogonal `sentiment` and `discourse_role` (the "why" behind the sentiment).
- No regression on core product/usage/performance/feedback signal quality.
- Clear signal for brand protection, marketing noise measurement, and DevRel triage.

**Open Blockers**: None (builds directly on shipped U9 classifier, `classify_pragmatics_full`, `post_type_keys`, and existing few-shot patterns).

## Product Contract

### In Scope
- **New `post_type` values** (added to `post_type_keys` + labels for en/zh_cn):
  - `promotional_spam`: Obvious advertising, marketing, affiliate links, "click for discount" CTAs, overwhelmingly positive sales-driven posts. (Matches user's category 1.)
  - `crypto_scam`: Posts referencing LLM brands in crypto/token contexts (especially unendorsed projects, scams, pumps). (Matches user's category 2; leverages existing Moonshot crypto filters as precedent.)
- **New `discourse_role` values** (added to existing 9-key vocabulary + few-shot examples in `few_shot_pragmatics.jsonl`):
  - `promotional`: Explains positive sentiment as commercial/ad intent (separate from `genuine_hype`).
  - `brand_jacking` (or `scam_hijack`): Explains why positive/mixed sentiment is applied to crypto contexts (brand abuse without lab endorsement).
- Update LLM classifier prompt (`build_pragmatics_full_prompt` in `x_monitor/attribution.py`) to include the new options with clear definitions and 2-3 new few-shot examples per category (pulled from deep X pattern search on multiple brands: MiniMax, Kimi/Moonshot, Qwen, GLM, DeepSeek, Anthropic, etc.).
- Extend `post_type_labels`, update backfill/test scripts (`test_classify_post.py`, smoke tests, `backfill_classify_recent.py`), and add dashboard filters/badges for the new types.
- Selective backfill of recent posts in review queue or analysis runs (do not force-reclassify entire history).
- Update relevant research/docs (`docs/research/2026-06-24-155117-simplified-taxonomy.md`, schema image if `.dot` changes, `db-schema.md`).

### Out of Scope
- Changing core 4-bucket `post_type` navigation (new values are additive siblings).
- Numeric sentiment, full retraining, or Weibo/Zhihu classifier changes.
- Hard-dropping these posts (they remain valuable signal).
- UI redesign beyond new filter badges.

### Success Criteria
- New types appear in `classify_pragmatics_full` output and DB (`posts_brands_signals.post_type` and `posts_brands_discourse.discourse_role`).
- Dashboard/review queue distinguishes them (e.g., "Promotional Spam (23)" tile, crypto tag).
- >85% agreement on sampled promotional/crypto posts from multiple brands (verified via expanded tests).
- No increase in "uncategorized" discourse_role rate.
- Updated schema image regenerated via `scripts/build_schema_image.sh` if tables change.

### Assumptions & Risks
- LLM prompt updates will generalize well from few-shot (risk: test with real wide-net samples from 5+ brands).
- Crypto/promotional volume is low enough that new enum values won't bloat queries (mitigated by existing relevance filters).
- `discourse_role` remains fully orthogonal to `post_type` × `sentiment` (as documented in current classifier).

**Related Artifacts**:
- Previous taxonomy: `docs/plans/2026-06-24-163000-replace-legacy-signals-with-post-types-and-sentiments.md`
- Classifier: `x-monitoring/x_monitor/attribution.py` (lines ~1020 for prompt, ~1090 for parsing)
- Filters precedent: `x-monitoring/data/filters/moonshot_kimi.yaml` (crypto spam notes)
- Few-shot: `x-monitoring/x_monitor/data/few_shot_pragmatics.jsonl`
- Schema: `docs/reference/db-schema.md`, `docs/reference/schema.dot`

---

**Written by Grok (ce-brainstorm)** — absolute path: `/Users/fuchitalee/development/minimax-marketing/docs/plans/2026-07-03-120000-taxonomy-extension-for-promotional-crypto-posts-plan.md`

Ready for `/ce-plan` or review. The file is now in `docs/plans/` (refreshed directory listing confirms it). The VS Code remote path you provided points to the correct folder.
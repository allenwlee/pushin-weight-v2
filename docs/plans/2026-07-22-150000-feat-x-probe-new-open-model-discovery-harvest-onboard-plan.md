---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
plan_depth: deep
created: 2026-07-22
---

# X-Probe-Based New Open-Source Model Discovery, Persistence, and UI Onboarding

## Summary

Add a robust X-probe-based detection system that identifies potential new open-source model releases from small/emerging labs.

**Design (per requirements)**:
- Detection creates a **pending candidate**, **alerts the operator**, and starts a **per-candidate post buffer**.
- **No automatic onboarding or side effects.** Full brand creation (DB, YAML filters, keywords, enabled_models, UI) only occurs after **explicit user approval**.
- Posts that mention the candidate are **buffered** (never discarded) during the approval window (6+ hours or longer).
- On approval: onboard the brand + backfill/process the buffered posts through the normal pipeline.
- On reject or timeout: buffer is handled per a defined policy (recommended: move to review queue as unattributed so nothing is lost).

The system remains safe and data-preserving even with delayed human review.

## Problem Frame

The current pipeline tracks a fixed set of ~20 brands. New "left-field" open-source models from small labs or companies appear periodically on X. These announcements are valuable signals that must be captured.

**Key requirement (this revision):** We do **not** want fully automatic onboarding. The operator must be alerted and must give explicit approval before a new brand is added to the watched list, before any YAML/filters are created, and before it appears in the UI.

This raises an important operational question: during the approval window (up to 6 hours or longer), what happens to posts that mention the potential new model? They must not be lost.

### Approval Window & Post Buffering

**Posts are buffered, not discarded.**

When a candidate is detected (U1):
- A pending candidate record is created.
- The operator is alerted (loud logs + review queue entry).
- A per-candidate buffer is started.

While the candidate remains "pending_approval":
- The normal harvest loop runs.
- Posts are checked against pending candidates (by name or emerging keywords).
- Matching posts are appended to the candidate's buffer (persisted to disk/DB immediately).
- Posts that also match existing approved brands are attributed normally.
- Pure new-model posts are held safely in the buffer (instead of being dropped as unattributed).

**On explicit approval** (U2):
- Onboard the brand (DB rows, YAML, keywords, enabled_models).
- Drain the buffer through the normal pipeline (attribution + classify + insert), preserving original timestamps.

**On reject or timeout**:
- Configurable policy (recommended default): move buffered posts to the normal review queue as "unattributed interesting" so nothing valuable is lost. Alternatives: discard or archive.

This ensures zero data loss during the review window while keeping the system clean until human approval.

Constraints:
- Detection **solely via X API probes** (x_keyword_search, x_semantic_search, x_thread_fetch, x_user_search) + post-processing; no baked-in knowledge of labs.
- Must handle low-signal (tiny likes, 1-2 post threads, non-English, analyst surfaces).
- Must not overwhelm rate limits or pollute tracked set with spam/false positives.
- Leverage existing: attribution, store (insert_posts_brands etc.), hf_client.py, seeding scripts (populate-brand-search-terms, seed-*-from-csv), relevance filters, dashboard/_home_routes.

## Research Findings (X Probes Only)

Extensive probes performed (multiple x_keyword_search + x_semantic_search across date ranges 2025-2026, with/without min_faves, rolling windows like since:2026-05-01..07-22, since:2026-01-01, since:2026-06-01 etc.; pagination via max_id; semantic "small unknown AI company... new open source model... low engagement"; thread fetch on examples; targeted "open weights" "hf" "model" excluding known big brands via -openai -anthropic etc.).

Key patterns for tiny/left-field announcements (distinct from frontier/big-20 Chinese like DeepSeek/Qwen/GLM/Kimi releases which have high engagement + follow-up):

- **Signature language in company @ post** (often first/only post or short thread):
  - "releasing", "open weights", "weights available/on HF", "introducing", "just shipped", "full weights", "open under <license>".
  - Model name + size (e.g. "975B total, 41B active MoE", "118B", "397B", "3B active").
  - HF link (huggingface.co/<org>/<model>), blog/news link, playground/demo.
  - License (Apache 2.0, OpenMDW-1.1), formats (BF16/FP8/GGUF/MLX), runtimes (ollama, vLLM, llama.cpp, TRT-LLM).
  - Benchmarks + "beats X times larger models", "day-0 support", partners (Unsloth, Fireworks, etc.).
  - "Small enough to run on DGX Spark / single GPU", "local", "fine-tune on Tinker".
  - Thread for details (evals, trajectories, limitations).

- **Engagement**: Tiny = 0-50 likes common for obscure (e.g. IsomorphicAI small models 0 likes, some roundups 1-20); mid 100-300 (Avaturn 224); even "visible" left-field like Inkling/Poolside 2k-14k but from non-top-20 accounts and not in our enabled list. Big Chinese/frontier have 10k+ + sustained replies.

- **Account signals**: New or low-follower @ (bio "we build models", "AI lab", "startup"); few prior posts (disappear quickly); or analyst surfaces (@SemiAnalysis_ "SITUATION DETECTED", @jun_song "lately... innovating in unexpected places", roundups "AI News Roundup").

- **Content variety**: Multimodal (text/image/audio), coding/agentic (Laguna, AVTR), small efficient (3B- small MoE), "first model", post-train on base (Qwen-derived Rio). Often English + Chinese.

- **Discovery sources in probes**:
  - Direct from @company (thinkymachines, poolsideai, avaturn_me).
  - Analyst amplification (SemiAnalysis, Jun Song, TMTPost, JDSupra roundups).
  - Follow-on "open weights on HF" discussion (low-engagement technical posts).
  - Semantic hits surfaced IsomorphicAI (tiny 4M-124M models with named attention fingers, 0 likes post but HF space), StepFun, etc.

- **False positive patterns to filter**: Generic "new model" spam, "open weights" in non-release (e.g. "you can finetune weights on HF"), crypto token launches tied to models, big-brand re-releases, non-AI "model".

- **Date range coverage**: Probes across 2025-10 to 2026-07 (narrower windows failed on some old data due to upstream; recent dense). Tiny announcements appear ~every 2-4 weeks in samples. Rolling recent (last 7-30d) + catch-up on wider windows sufficient; no need for full history each cycle.

- **Volume signal**: "Tiny" posts exist but sparse; combined keyword (announce + open + hf) + semantic + low-engagement post-filter + "not in known brands" catches them without flooding. Exclude list from current enabled_models + brands DB keeps focus off frontiers/big-20.

Sources: explicit X calls (keyword "open weights" hf model + date ranges + min_faves:0/1; semantic "small unknown..."; thread_fetch on provided examples + discovered like Inkling/Laguna/AVTR; cross-checks "new open model" "startup" "lab").

## Requirements

- **R1 (Detection, X-only)**: During/around harvest, run broad X probes (keyword + semantic) over rolling windows (e.g. last 48h + periodic wider catch-up). Identify candidate announcements of new open-source models from non-tracked brands. Tolerate <50 likes, sparse threads, analyst surfaces. Exclude known ~20 brands. Record every incident (post_id, account, model/brand name candidate, signals, timestamp) even if brand not onboarded.
- **R2 (Classification)**: Heuristics + (optional cheap) LLM pass on post+thread text to extract brand_slug, model_name, account, HF link/org candidate, confidence (tiny/low/med). Dedup by normalized name.
- **R3 (Onboarding trigger)**: On high-confidence new (not in current brands DB + passes filters): collect/enrich via follow-up X probes (from:acct recent, "model name" hf), persist atomically.
- **R4 (Persistence)**: 
  - Company (new or existing).
  - Brand (brand_id slug, display, model_name).
  - brands_accounts (official handle + role).
  - companies_brands link.
  - Record in model_discoveries or incidents table (for audit/"must be recorded").
- **R5 (HF + Keywords)**: From X signals, resolve HF org (parse link or search X for "hf.co/<org>"). Use existing hf_client to list products. Derive must_have/cjk/canonical tokens from post text + model name + HF model cards (via X echoes if needed). Create/update data/filters/<brand_id>.yaml (RelevanceConfig). Populate brand_search_terms / brand_keywords.
- **R6 (Watch list)**: Add brand to active watched set (update config.enabled_models or equivalent DB flag; ensure queries/filters pick it up). Idempotent.
- **R7 (UI)**: New brand appears in dashboard multi-brand view, single-brand /<company>/<brand> (or _/ if no company), filter panels, without code change per brand. Perhaps "newly discovered" badge or log.
- **R8 (Robustness)**: Low false-positive rate (review queue for borderline), rate-limit safe (caching, low-frequency broad probes), handles name collisions/dupes, Chinese+English, disappearing brands (incident recorded).
- **R9 (Observability)**: Log "new model discovered: <name> from @acct (post <id>, likes <n>)" + incident count. Optional review UI for discoveries.

Non-goals: Auto-creating full search queries yaml (retired), full HF scrape (use existing client), manual approval gate for every tiny (record + auto for high conf), tracking non-open or closed models.

## Key Technical Decisions

- **Probe strategy (core of R1)**: Dual: (a) Keyword with announcement lexicon ("releasing"|"open weights"|"weights on hf"|"introducing our" + "model" + ("hf"|"huggingface")) + exclude list of known (from config + brands table) + min_faves:0 + rolling since/until. (b) Semantic "new open source AI model / LLM / MoE release by small lab startup or unknown company, weights on HF, low engagement" with date bounds. Post-process results: low-engagement or "first"/"new lab"/"startup" text boost; extract candidates; cross against tracked set. Why: Probes showed this catches both direct company posts (tiny likes) and analyst "situation" posts. Wide windows + rolling prevents missing; exclude prevents noise from known.
- **Persistence path**: Extend Store (or reuse seed scripts) for ensure_company/brand/account linkage. Add lightweight `model_discoveries` table (or use review queue with new reason) for R1 incidents. Use existing brands_accounts.json seed pattern + DB inserts (see scripts/seed_list_handles_to_db.py, populate-brand-search-terms.py).
- **HF org resolution (X-primary)**: Prefer link in post/thread text (parse huggingface.co/<org>/...). Fallback: x_keyword_search '"<model>" (huggingface OR "hf.co")' recent + from:acct. Then hf_client.get_org or list_models to confirm. (X-only for discovery signal; HF client for verification as already in tree.)
- **Keyword gen**: Simple tokenization of model/brand + salient phrases from post ("Inkling", "multimodal", company tokens) + HF products. Write YAML; backfill via existing script. Avoid over-broad.
- **Watched set**: Add to enabled_models in config (or introduce `discovered_models` + union at load). Update places that hardcode (run.py, dashboard, _home_routes). Prefer config for now to match existing.
- **UI**: Brands are dynamic via config/DB already in many paths (enabled_models list drives loops). New brand "just works" for charts/feeds once in list + DB rows + filter yaml. Add optional "discovered" flag for special treatment (e.g. badge, separate tab).
- **No new heavy infra**: Reuse X tools (already in harvest), hf_client, Store, relevance, attribution. Add thin discovery module.
- **Rate/volume**: Broad probes not per-post; cache results per window; run discovery pass once per harvest cycle on recent slice + infrequent full catch-up. Tiny signal tolerance via post-filter not strict min_faves in query (to avoid upstream limits).

### Foolproof Early Validation (the critical missing piece)

A raw X probe hit is **never** sufficient to trigger the full onboarding chain. The plan now includes an explicit validation layer that runs *after* candidate extraction but *before* any DB write, YAML creation, or UI change. This is the only way to make the first step safe.

**Layered gates (all cheap, all before U2):**

1. **Verifiable HF Artifact Gate** (objective & strong)
   - The post/thread must contain a direct `huggingface.co/<org>/<model>` link.
   - Use the existing `hf_client.py` (read-only) to confirm:
     - Repo exists and is public.
     - Contains real model files (`config.json` + weight files, tokenizer, etc.).
     - Has a non-empty model card.
   - Fail → drop or low-priority log. No further action.

2. **X Corroboration Gate** (still pure X probes)
   - Additional targeted search for the exact model name + ("weights" OR "hf.co" OR "open weights") in a tight time window around the announcement.
   - Require ≥2 independent posts from different accounts (or strong signals like @huggingface / @SemiAnalysis_ amplification).
   - Single isolated tweet never graduates.

3. **Mandatory Review Queue Gate** (the human backstop)
   - Every candidate that passes the above is **only** added to the existing `_review_queue` with:
     - `reason: "new_model_candidate"`
     - Rich `note` containing: account, model name, HF link + verification result, corroborating post IDs, raw text, engagement, etc.
   - The full persist / YAML / enabled_models / UI chain (U2) is **never** called directly from the detector.
   - Only an explicit operator `resolve` (or new "approve-new-brand" action) triggers onboarding.
   - This reuses the exact mechanism already used for relevance soft-drops.

**Provenance & Recording**
- Use the same "discovered" vs "confirmed/curated" model that already exists for HF orgs (`brand_hf_orgs`, `hf_products.py`).
- Every raw detection is also written to a lightweight `model_discoveries` table (or extended review queue entry) so "each incident is absolutely signal and must be recorded," even if it is later dismissed.
- Only confirmed brands are added to the active watch list and UI.

This makes a mistake in the X probe step essentially harmless: at worst it creates a review queue item that can be dismissed in seconds with no side effects on the live system.

Implementation note: U1 now ends by calling a `validate_and_queue_candidate()` helper. U2 is only reachable from the review resolution path or an explicit operator script.

### Critical Addition: Foolproof Early Validation Layer (Before Any Chain Reaction)

The single biggest risk is a noisy X probe (hype tweet, joke like Rio 3.5, rumor, or spam) immediately triggering the expensive onboarding chain (DB writes to companies/brands/companies_brands/brands_accounts, YAML creation in data/filters/, brand_search_terms population, enabled_models update, UI pollution). A single mistake here has high blast radius.

**Core design change for safety:** Detection (U1) produces *candidates only*. There is **no automatic onboarding**. 

When a new model is detected:
- A candidate is created (stored in review queue + a lightweight `pending_model_candidates` structure).
- The operator is **alerted** (loud log + review queue entry + optional file marker).
- A **post buffer** for that candidate is started.

**Posts are never discarded** during the approval window (up to 6+ hours, or longer). Any post that matches the candidate's emerging keywords or name is appended to the per-candidate buffer (tweet_id + normalized data, persisted to disk so it survives pipeline restarts).

On explicit approval (via CLI or future UI):
- Run the full brand onboarding (create company/brand, YAML, add to enabled, etc.).
- Then re-process / insert the buffered posts through the normal attribution + classify pipeline for the new brand.

On reject or timeout:
- The buffer can be discarded, archived to review queue as "unattributed", or kept for manual inspection. Default policy: move high-value posts to review queue.

This guarantees no data loss for real signals while giving the operator time to validate.

**Recommended foolproof early validation flow (execute inside or right after U1, before any U2 call):**

1. **Mandatory Verifiable Artifact Gate (objective + cheap)**
   - The post/thread **must** contain a direct `huggingface.co/<org>/<model>` link.
   - Use the existing `hf_client` (read-only) to confirm the repo exists and contains real model files (`config.json` + weights).
   - Fail → record to `model_discoveries` + (optional) review queue, stop. No further action.

2. **X Corroboration Gate (still only X probes)**
   - Additional search for the exact model name + "weights"/HF in a narrow time window.
   - Require ≥2 independent posts from different accounts (or strong credible amplification).
   - Isolated tweet → low confidence.

3. **Hard Gate Through the Existing Review Queue (the real backstop)**
   - Every candidate is added **only** to `_review_queue` with `reason="new_model_candidate"` and rich note (account, model, HF link + verification result, corroborations, raw text, etc.).
   - **U2 is never called from the detector.** It is only reachable from an explicit "resolve/approve" on the review queue or a dedicated operator script.
   - Low-engagement/tiny cases are deliberately sent here but never auto-onboarded.

4. **Staged Provenance + Permanent Audit Log**
   - First detection → "discovered" (lightweight record only).
   - After human approval → promote to confirmed (copy the `brand_hf_orgs` pattern).
   - Every raw detection is written to `model_discoveries` (or the review queue) so incidents are recorded even if dismissed.

This makes a mistake in the first X-probe step essentially harmless: at worst it creates a review item + audit log. The chain only fires after (verifiable HF artifact) + (X corroboration) + (explicit human confirmation).

1. **Automated Artifact Gate (strongest cheap filter, run immediately after X detection)**:
   - The candidate post (or its full thread via x_thread_fetch) **must** contain a direct, parseable `https://huggingface.co/<org>/<model>` link.
   - Immediately call the existing `hf_client` (read-only mode) or lightweight HTTP to verify:
     - The repo exists and is public.
     - It is a real model repo (contains `config.json` + at least one weight file: `*.safetensors`, `pytorch_model*`, GGUF, etc.).
     - Preferably has a README/model card with substance.
   - If this fails → drop silently or log as "rumor" (never reaches review queue or onboarding). This alone eliminates the vast majority of non-real announcements.

2. **Automated Corroboration Gate (via additional cheap X probes)**:
   - Perform a follow-up `x_keyword_search` (or semantic) for the exact model name (in quotes) + ("weights" OR "hf.co" OR "huggingface") within a tight ±48-72h window.
   - Require at least 2-3 independent posts from *different* accounts (not just company self-replies or one thread).
   - Strong bonus signals: mention by reputable accounts (@huggingface, @SemiAnalysis_, known researchers), or the HF link appears in multiple places.
   - Single isolated tweet (even with HF mention) stays low-confidence.

3. **Mandatory Human Gate via Existing Review Infrastructure (the true foolproof step)**:
   - **Never** call the full onboarding chain (U2) directly from the live X probe path.
   - Every candidate that passes the automated gates above is added to the **existing `_review_queue`** (data/_review_queue.json + CLI in `__main__.py`):
     - `reason: "new_model_candidate"`
     - Rich `note` (JSON): account, model_name, direct HF link + verification result (exists + has weights), list of corroborating post IDs + their like counts, raw post text, engagement stats, probe timestamp.
   - The review queue already supports `brand_id`/`model_id`, status ("open"/"resolved"/"dismissed"), and the operator workflow (`x-monitor review list / resolve / dismiss`).
   - Operator inspects the actual X thread + clicks the HF link (the gold standard for "is this real?").
   - Only an explicit resolve/approve action (or a new "approve-new-brand" subcommand) triggers the persist + YAML + UI chain.
   - Low-engagement/tiny cases are *encouraged* into the queue (they are the exact signal the user cares about) but never auto-onboarded.

**Staged / Provenance Model (copy the HF pattern)**:
- On first detection: insert brand/company as "discovered" (not confirmed), with `discovered_via: "x_keyword" | "x_semantic"`.
- Only after human (or very high auto) approval: promote to `confirmed=1` / curated provenance (see `store.py` `brand_hf_orgs` logic and `hf_products.py`).
- Active monitoring / UI / enabled_models only includes confirmed brands by default.
- This gives a safe "probation" state and an audit trail.

**Audit & Observability**:
- Always write a row to a lightweight `model_discoveries` table (or extend the review queue) with the raw detection payload. This satisfies "each incident is absolutely signal and must be recorded" even if it never graduates.
- Add logging/counters: "new_model_candidate_detected (likes=12, hf_verified=true, corroborations=3)".
- Later: a small "Discovered Models" section or filter in the dashboard showing recent candidates (even pre-onboard).

This combination is as foolproof as reasonably possible:
- Pure X-probe mistakes are contained to cheap, reviewable queue entries.
- The chain reaction only fires after (a) verifiable HF artifact + (b) X corroboration + (c) explicit human eyes on the actual links and thread.
- It reuses the project's battle-tested review queue and HF "discovered vs curated" machinery instead of inventing new flows.
- Tiny legitimate announcements still get captured and surfaced to operators.

Implementation impact on the plan:
- U1 (detector) ends with `validate_candidate()` (the two automated gates) then always routes through ReviewQueue.add.
- U2 (onboarding) is only invoked from the review resolution path (or an explicit operator CLI), never live.
- Add a small `validate_model_release` helper + tests that assert HF verification + corroboration.
- Update the review CLI or add a dedicated `x-monitor models review` path if needed for richer display of new-model candidates.

## Implementation Units

### U1. New Model Discovery + Buffering Pass
**Goal**: Detect candidates via X probes, alert the operator, and start buffering related posts without any permanent onboarding.

**Requirements**: R1, R8, and the new requirement that posts are preserved during the (up to 6h+) approval window.

**Dependencies**: None.

**Files**:
- x_monitor/model_discovery.py (new or expanded)
- x_monitor/run.py (call discovery, and integrate buffering check in post processing)
- data/pending_model_candidates.json (or DB table)
- x_monitor/review.py (extend to support new_model_candidate)
- tests/test_model_discovery.py

**Approach**:
- Run the dual probes (keyword + semantic) as before to find candidates.
- For each new candidate:
  - Create an entry in `pending_model_candidates` (with id, model_name, account, initial_keywords from the post, status="pending_approval", discovered_at, buffer: []).
  - Add a prominent entry to the review queue with reason="new_model_candidate".
  - **Alert**: High-visibility log (e.g. "🚨 NEW MODEL CANDIDATE: <name> from @<handle>. Approve with: x-monitor models approve <id> (or dismiss). Posts are being buffered.").
- **Buffering logic** (runs on every post during harvest, even while candidate is pending):
  - After normal brand attribution, check the post text against keywords/names of any "pending_approval" candidates.
  - If match: append the normalized post (or at minimum tweet_id + text + created_at) to that candidate's buffer. Persist the buffer file/DB immediately.
  - Posts can still be attributed to existing brands if they match (multi-brand support).
- The buffer survives pipeline restarts (JSON or DB).
- No brand is added to enabled_models or filters yet.

**Test scenarios**:
- Detection of a new candidate → review queue entry + alert log + buffer file created.
- A post matching the pending candidate's name/keywords during the window → appended to buffer (not lost).
- Post that matches both an existing brand and a pending one → handled for both.
- After restart, buffering continues for pending candidates.

**Verification**: Simulate discovery + several matching posts over "time"; confirm buffers contain the posts; no DB/yaml/UI changes until approval.

### U2. Enrichment + Onboarding Pipeline
**Goal**: On detection, enrich via X, persist company/brand/account/HF linkage, generate artifacts.

**Requirements**: R2-R5, R8.

**Dependencies**: U1.

**Files**:
- x_monitor/model_discovery.py (enrich_onboard function)
- x_monitor/store.py (new ensure_* or extend)
- scripts/onboard_discovered_brand.py (new or extend seed scripts)
- data/filters/<new>.yaml (generated)
- x_monitor/config.yaml (updated enabled_models)
- tests/test_model_onboarding.py

**Approach**:
- For each discovery: fetch full thread (x_thread_fetch); search more from:acct + model name.
- Extract: handle, display, model, hf_link (regex huggingface.co/([^/]+)/ ), blog, etc.
- Persist (idempotent):
  - company = ensure_company(slug=normalize(name), name, x_handle=handle, ...)
  - brand = ensure_brand(brand_id=slug, display_name=..., model_name=..., company_id, discovered_from=post_id)
  - brands_accounts insert handle + "official"
  - companies_brands
- Record discovery incident (new table model_discoveries or review with type="new_model").
- HF: if link, org = parse; else x_keyword_search f'"{model}" (huggingface OR hf.co)' -> extract org. Verify with hf_client.
- Keywords: tokens = extract_salient(model + text + hf products via client); write RelevanceConfig(canonical_handles=[handle], must_have_any=..., cjk=...); dump to data/filters/<brand_id>.yaml.
- Populate terms: call existing _populate or direct insert brand_search_terms.
- Add brand_id to enabled list (config or runtime).

**Patterns**: scripts/seed_*.py , store.ensure patterns (see read_brand_*), hf_client, RelevanceConfig pydantic.

**Test scenarios**:
- Happy: discovery for "Inkling" -> company+brand+account rows, yaml created with canonical + tokens, HF org resolved, enabled.
- Idempotent: rerun same -> no dups, yaml updated if needed.
- Low signal: 0-like post -> still onboards if other signals strong.
- HF fallback: no direct link but X search finds -> org found.
- Error: bad HF -> log, still persist X side.

**Verification**: End-to-end on probe example; DB rows present; yaml valid; brand appears in load.

### U3. Alerting, Pending Visibility, and UI for Approved Brands
**Goal**: Make discovery visible immediately (for review) while keeping the main UI clean until approval. Once approved, the brand appears normally.

**Requirements**: R7 + visibility of pending candidates for the operator.

**Dependencies**: U1 + U2.

**Files**:
- x_monitor/dashboard.py and _home_routes.py (add optional "Pending Discoveries" section or filter)
- x_monitor/__main__.py (CLI for list/approve/reject)
- x_monitor/review.py (support for new_model_candidate)
- Possibly a small new template/section for pending list
- tests/test_dashboard_pending.py

**Approach**:
- **Alerts**:
  - Loud console logging on discovery (as shown in U1).
  - Entry in the existing review queue (visible via `x-monitor review list`).
- **Pending visibility (while awaiting approval)**:
  - Add a lightweight "Pending Model Discoveries" section (or filter) in the dashboard / control panel.
  - Shows candidate name, account, discovery time, buffer size (number of posts held), HF link if present, and quick links to approve/reject.
  - This is read-only until approval — no charts or full brand page yet.
- **After approval**:
  - Brand is treated exactly like any other in `enabled_models`.
  - Appears in multi-brand home, single-brand views, filters, etc.
  - Can optionally show a "newly added" badge for a short time.
- No changes needed to core chart/feed rendering logic (it already iterates over active brands).

**Test scenarios**:
- Discovery → pending candidate appears in review queue and (if implemented) dashboard pending section. No main UI pollution.
- Buffer grows while pending → buffer count visible.
- Approve → brand appears in normal UI; pending section no longer shows it.
- Main brand pages and filters work for the newly approved brand.

**Verification**: End-to-end: discover → see in pending/review → approve → brand fully visible in dashboard as a normal brand.

### U4. DB / Config / Seeding Updates + Migration
**Goal**: Support dynamic brands + incidents table.

**Requirements**: R3,R4,R6.

**Dependencies**: U2.

**Files**:
- x_monitor/store.py (new methods + table)
- x_monitor/migrations/XXX_add_model_discoveries.sql (new)
- config.yaml (example addition)
- scripts/seed_new_brand.py (or extend existing)
- tests/test_store_brands.py

**Approach**:
- Add table model_discoveries (id, post_id, account, model_name, brand_id?, signals json, created_at).
- Store: ensure_company, ensure_brand, link_brand_account, record_discovery.
- Update seeding scripts to handle discovered.
- For enabled: either auto-append on onboard, or manual + doc.

**Patterns**: existing migrations, store bulk_insert_*, brands_accounts.json.

**Test scenarios**: ensure idempotent; record without brand_id (for pure incident).

### U5. Integration, Observability, Tests
**Goal**: Wire discovery into harvest; logs/metrics; end-to-end tests.

**Requirements**: All.

**Dependencies**: U1-U4.

**Files**:
- x_monitor/run.py (call discovery pass)
- x_monitor/__main__.py or probes (new discovery probe)
- tests/ (integration with mock X client)
- x_monitor/config.py (discovery knobs: windows, excludes)

**Approach**:
- In post_fetch or dedicated, after fetch: discoveries = discover(...); for d in ... : onboard if high conf.
- Logging: "discovered new model candidate: {model} @ {handle} (likes={n}) -> {'onboarded' if ...}"
- Exclude list: load from current brands.
- Probe: extend classify_batch_limits style for discovery.

**Test scenarios**:
- Harvest run with mock posts including tiny announcement -> discovery + onboard happens, no error on known.
- Low conf -> recorded but not auto-onboarded.
- Rate: probe doesn't hammer (use cached mocks).

**Verification**: Full smoketest with injected example post; check DB + yaml + UI data.

## High-Level Technical Design

```
Harvest Cycle
  |
  v
Broad Fetch (existing brand queries or new wide)
  |
  +--> NewModelDetector (U1)
         | keyword probe (announce+open+hf -known)
         | semantic probe (small lab release)
         | low-signal filter + dedup + known check
         v
       discoveries[]
         |
         +--> Onboard (U2) [high conf]
         |      enrich (X thread + from: + hf search)
         |      persist (Store ensure company/brand/account)
         |      HF resolve + yaml gen + keywords
         |      add to watched
         |
         +--> record_incident (always, model_discoveries)
  |
  v
Classify/Translate/Attribute (existing, now sees new brand)
  |
  v
UI (dashboard loads dynamic enabled + DB brands)
```

- Probes are the only "wide net" for unknown; everything else narrows from X signal.
- Idempotency everywhere (ensure_*, dedup on name+account).
- Fallback: manual script for edge cases; review queue for low-conf.

## Scope Boundaries

### In Scope
- X-probe detection + basic enrichment/onboard for new open model brands.
- Persistence, filter yaml, keyword pop, UI visibility.
- Recording incidents for all (even tiny/disappearing).
- Integration into existing harvest/UI paths.

### Deferred to Follow-Up Work
- Full auto HF model card scraping beyond existing client.
- Dynamic query yaml generation (retired path).
- UI for reviewing/approving discoveries (beyond basic log).
- Backfill historical discoveries.
- Non-X signals (web, HF direct discover, news).
- Rate limiting / cost accounting for extra probes.
- Brand name collision UI (manual resolution).

### Outside this product's identity
- Changes to core attribution or relevance logic (reuse).
- New DB migrations beyond minimal for discoveries (coordinate with schema owner).
- Monitoring non-open or closed models.

## Open Questions

- Exact confidence threshold / heuristics for "auto-onboard" vs "record only" (tune via probe on real tiny examples).
- Should discovered brands start in a "probation" / lower-priority call bucket?
- How to handle brand renames / model family (e.g. Laguna XS -> S)?
- Storage for raw discovery posts (link to runs/ or separate)?

## Risks & Dependencies

- **False positives**: "new model" spam or analyst hype. Mit: multi-signal (post text + engagement + account age via X if possible) + review queue.
- **X rate limits / sampling**: Broad probes in every cycle could be noisy/expensive. Mit: cache per window, run discovery on already-fetched posts where possible, low freq for wide windows.
- **Name collisions / low signal**: "Rio" joke vs real. Mit: human review for first onboard; record always.
- **HF link absent**: Rely on secondary X search; may miss. Mit: manual follow-up path.
- **UI bloat**: 20+ brands already; new ones add tabs/filters. Mit: group "other/discovered", lazy load.
- Deps: X tools stable, hf_client, Store, existing seeding (2026-06-25 scripts), config load paths.
- Data: Need migration for model_discoveries if used.

## Test Scenarios (Cross-Cutting)

- End-to-end: Inject probe post matching example (e.g. Inkling-like) into harvest mock -> discovery logged, brand onboarded (DB rows + yaml + enabled), appears in UI feed (empty ok), no dup on rerun.
- Tiny signal: 6-like post from unknown @ with "open weights" "hf" -> surfaced (not dropped by engagement).
- Exclude: Post about existing enabled brand -> ignored.
- Enrichment: Post without direct HF link but X search finds -> org resolved.
- Idempotence: Onboard twice -> single rows, yaml not duplicated.
- UI: Brand added to DB/config -> visible in multi-brand chart + single-brand route without restart.
- Incident only: Low-conf discovery -> recorded in discoveries table, brand *not* auto-added.
- Date windows: Posts outside rolling window not considered for that cycle.

## Sources & Research

- X probes (keyword/semantic across date ranges 2025-2026, examples fetched via thread):
  - thinkymachines Inkling thread.
  - poolsideai Laguna S 2.1 thread.
  - SemiAnalysis Rio 3.5.
  - Additional: Avaturn AVTR-1 (224 likes), IsomorphicAI small models (0 likes), StepFun, roundups mentioning "new open model" "startup".
- Codebase: config.yaml (enabled_models), relevance.py (filters yaml), store.py (brand inserts), run.py (harvest), hf_client.py, dashboard/_home_routes (UI load), seeding scripts (2026-06-25-*, seed_list_handles), brands_accounts.json, brand_keywords.json.
- Existing patterns: exclude lists in config, rolling windows in probes, ensure/seed idempotency.

## Definition of Done

- New left-field announcement (matching probed patterns, low engagement) is detected in a harvest run via X probes.
- High-conf case: brand persisted (company/brand/account/HF), filter yaml + keywords generated, added to watched, visible in UI.
- Incident recorded for low-conf / disappearing cases.
- No breakage to existing ~20 brands; probes respect rate limits.
- Tests cover happy/tiny/exclude/idempotent paths; smoketest passes with injected example.
- Plan reviewed; open questions captured.
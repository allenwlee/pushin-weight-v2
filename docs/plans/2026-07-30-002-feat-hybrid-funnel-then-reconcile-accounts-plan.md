---
title: "Hybrid harvest funnel (B1 bare + C thin co + C-only LLM) THEN reconcile accounts + handle uniqueness"
date: 2026-07-30
type: feat
artifact_readiness: implementation-ready
execution: code
target_repo: pushin-weight-v2
product_contract_source: ce-plan-bootstrap
amends:
  - docs/plans/2026-07-28-001-feat-b1-purity-official-handles-plan.md
  - docs/plans/2026-07-30-001-fix-accounts-handle-duplicates-reconciliation-plan.md
---

# Hybrid harvest funnel → reconcile accounts + handle uniqueness

## Goal Capsule

Two pieces of work, executed in this order because each enables the next:

1. **Hybrid harvest funnel** (former plan `2026-07-28-001`, amended today) — change the live harvest queries so B1 is bare keywords, B2/B3 are `@handle` OR-groups, C\* use a 5-term minimal co allowlist (no xiaomi/moonshot poison), and a C-only binary LLM relevancy gate trims EN noise the bare co admits.
2. **Account reconciliation + handle uniqueness** (former plan `2026-07-30-001`) — collapse the 2,142 duplicate `handle` groups in `accounts`, repoint ~25,000 FK rows in `posts` / `account_post_appearances` / `brands_accounts` from placeholder `author_id`s to canonical integer `author_id`s, and add a `LOWER(handle)` unique index so the drift can't recur.

**Why this order.** The hybrid funnel ships first because (a) the new harvest produces cleaner `author_id` writes going forward, (b) the live cron doesn't depend on the reconciliation and can stay running during the data fix, and (c) shipping the schema migration (the unique index) BEFORE reconciliation would FAIL because Postgres can't build a unique index over the existing 2,142 duplicates.

**Stop when.** Hybrid funnel live + ≥1 green harvest cycle on the new queries + reconciliation applied (dup count from 2,142 → 462) + unique index in place + regression net flipped to AFTER state + operator runbook for the 462 residual.

**Pre-flight (must precede all other work).** Two operational gates run before any other unit:
1. **U0** — A verified pg_dump of the production `pushinweight-db-shadow` DB — both the schema (custom format) and a row-count snapshot — is captured BEFORE any U1 work begins. The dump is the rollback path if reconciliation's UPDATE-then-DELETE goes wrong, if the unique-index migration fails, or if the hybrid funnel breaks the live harvest and the operator needs to restore the previous-day state.
2. **U16 pause leg** — The harvester cron + beat + worker are paused BEFORE any unit touches production data. Resume is MANUAL after U15 is verified complete. Today (2026-07-30) the cron is already paused from the 2026-07-28 incident recovery — U16 is a no-op verification + a forward-looking guardrail codified for future sessions.

**Out of band.** A separate brainstorm if/when brand-seeding scripts are rewritten to skip the `handle:` placeholder path entirely (would unlock BIGINT typing of `author_id`); backfilling author metadata onto residual rows; resolving the 462 no-integer residual groups (separate pass once TwitterAPI auth is reliable for ≥24h).

---

## Product Contract

### Problem Frame

**Hybrid funnel (origin: `2026-07-28-001` amended today).** The current config (`config.yaml` `x_query_specs[0].co_occurrence` for C1 = `api, llm, model, xiaomi, 小米, moonshot, chatbot, weights, gguf, ollama, code, coding, agent, agentic, benchmark, reasoning, release, "open source", huggingface, inference, moe, "tool calling"` — 22 terms; same shape for C2) over-ANDs foreign-language posts: ~55–75% of relevant non-EN samples lack those terms, and `xiaomi`/`moonshot` poison other brands. Bare-C (no co) maxes foreign recall but floods EN noise. Bare-B1 (no co on pure brands) plus a 5-term minimal co allowlist on C-only is the compromise. `@handle` ORs on B2/B3 cover the "post is BY the brand's official account" path, which `list:` doesn't.

**Account reconciliation (origin: `2026-07-30-001`).** The `accounts` table PK is `author_id` (text), `handle` is non-unique. Brand-seeding scripts (`scripts/seed_list_handles_to_db.py`, `x_monitor/store.py::upsert_brand_account` line 1423 with `f"handle:{handle}"` fallback, `scripts/2026-06-19-180000-seed-detection-tables.py` with `"synthetic:" + handle.lower()`) inserted placeholder author_ids when TwitterAPI auth was unavailable. The live harvest (`monitor/cycle.py::_upsert_account` line 454, keyed on `update_or_create(author_id=...)`) wrote the real integer author_id for the same handle — but never reconciled with the placeholder rows.

Audit of the shadow DB on 2026-07-30:

| Metric | Value |
|---|---:|
| Total accounts | 19,284 |
| Distinct handles (case-insensitive) | 17,142 |
| Duplicate handle groups | **2,142** |
| Extra rows in duplicate groups | **2,269** |
| Posts pointing at placeholder author_id | **18,114** |
| Posts pointing at integer author_id | 8,743 |
| `account_post_appearances` rows at placeholder author_id | 6,803 |
| `brands_accounts` rows at placeholder author_id | 95 |
| `companies_accounts` rows at placeholder author_id | 0 |

Duplicate pattern breakdown:

| Pattern | Groups |
|---|---:|
| `handle:*` + integer | 1,569 |
| `synthetic:*` + `handle:*` | 327 |
| `synthetic:*` + integer | 137 |
| All three | 105 |
| `handle:*` + bare handle | 4 |

**Why now.** The 2026-07-28 denormalization incident + 2026-07-29 db recovery restored the shadow DB from a pre-2026-07-24 dump. The b1-purity plan has been waiting since 2026-07-28 and was NOT shipped (no production commits between 2026-07-28 and 2026-07-30 land any U1–U8 of that plan). TwitterAPI auth is currently working intermittently — each cycle that authenticates has a chance to deepen both the foreign-recall loss and the account drift. Both pieces of work need to ship before either compounds.

### Requirements

**Hybrid funnel (carried from `2026-07-28-001` amended today; full text in the original plan).**

- R1. 7 calls: A, B1, B2, B3, C1, C2, C3.
- R2. A: `(list:<id>) min_faves:0` unchanged.
- R3. B1 pure keywords bare: cleaned primaries; `co_occurrence: []`; no `@handles`.
- R4. B2 pure-brand official handles only (OR-joined `@h` tokens).
- R5. B3 other-brand official handles only (C1+C2+C3 brands).
- R6. C1/C2/C3: brand token groups + minimal co; no handles in C strings.
- R7. Handles not stored as `brand_keywords` for harvest; attribution still via `user_mentions` ids.
- R8. Default shared minimal co (5 terms): `llm`, `model`, `api`, `agentic`, `huggingface`.
- R9. Optional expansions (total co terms per C call ≤ 8): `moe`, `ollama`, `coding`. C2 may also add `baidu`, `文心`.
- R10. Never in shared co: `xiaomi`, `小米`, `moonshot`, bare `agent`, bare `code`, bare `release`, bare `ai`.
- R11. Rationale: thin AND keeps light AI-context; loanwords appear in many non-EN tech posts; full 22 is out.
- R12. C specs may list `not_include: [...]` for stable hijacks.
- R13. `not_include` applies as query-time `-term` (ASCII-safe) and/or post-fetch ban match.
- R14. B1/B2/B3 do not require `not_include`.
- R15. Demote dirty primaries: `m2.5`, bare `海螺`; bare `Mistral` → prefer `Mistral AI` + `Mixtral`; bare `混元`; bare `GLM` (keep ChatGLM/Zhipuai/智谱).
- R16. B1 pure brands: `deepseek`, `qwen`, `minimax`, `stepfun`, `mistral`, `hunyuan`, `glm`, `inclusionai`, `exaone`, `sakana_ai`, `nemo_megatron`.
- R17. Empty co omits secondary paren (`()` forbidden).
- R18. All planned strings < 512.
- R19. Binary LLM relevancy only for C\* source OR C-tier brand attribution.
- R19a. Binary relevancy prompt (shipped as `BINARY_RELEVANCY_SYSTEM` / `BINARY_RELEVANCY_USER` constants).
- R20. Full translate/classify only after keep.
- R21. Summary metrics: fetch_n, not_include drops, llm drops, keep rates per call.
- R22. Reference doc + CONCEPTS updated.

**Account reconciliation (carried from `2026-07-30-001`).**

- R23. Every `handle` in `accounts` maps to exactly one row, keyed on the integer author_id when one exists.
- R24. All FK references (`posts`, `account_post_appearances`, `brands_accounts`, `companies_accounts`) point at the canonical row.
- R25. `accounts.handle` has a unique constraint (case-insensitive) so future drift is impossible.
- R26. A regression net pins this state so silent drift fails loudly.
- R27. UPDATE-then-DELETE order preserves `posts.author_id` against `ON DELETE SET NULL`.
- R28. Groups where TwitterAPI lookup fails OR disagrees are skipped and dead-lettered.
- R29. Reconciliation script lives outside the migration ledger (idempotent re-runnable command).

### Acceptance Examples

**Hybrid funnel.**

- AE1. `@MiniMax_AI cool` matches **B2**; `user_mention` → minimax.
- AE2. Post with `Kimi` + `llm` or `api` matches **C1** thin co (including many foreign tech posts that code-switch).
- AE3. Pure sports Kimi without co terms does not match C1 search.
- AE4. F1 + antonelli excluded if `not_include` seeded.
- AE5. B1 has no co secondary; C co ≤ 8 terms and ⊆ allowlist; no xiaomi/moonshot in co.
- AE6. Pure JA with only モデル/公開 and brand name may still miss C (accepted); multiword primaries + handles cover other paths.

**Account reconciliation.**

- AE7 (origin 2026-07-30 user prompt). "if an existing account with non-integer author_id posts tomorrow and harvester captures it, and inserts proper integer author_id, it will create a new entry?" Before this plan: yes. After this plan: integer row already exists (U10 merged), `update_or_create(author_id=...)` updates the canonical row, no duplicate.
- AE8 (audit query, 2026-07-30). `SELECT COUNT(*) FROM (SELECT handle FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1) t` = **2,142**. After U10 apply: drops to **462** (the deferred residual).
- AE9 (audit query, 2026-07-30). `SELECT COUNT(*) FROM posts p JOIN accounts a ON a.author_id = p.author_id WHERE a.author_id !~ '^[0-9]+$'` = **20,079**. After U10 apply: drops to **1,965**.

### Scope Boundaries

**In:** config reshape (hybrid); query_plan renderer empty-co + handle-only + thin-co; primary demotion; optional `not_include`; C-only binary LLM; anomaly metrics; reconciliation script + dry-run; UPDATE-then-DELETE; partial unique index on `LOWER(handle)`; AFTER-pinned regression net; operator runbook for residual.

**Out:** Bigint-typed `author_id` column; rewriting the brand-seed scripts to skip placeholders entirely (separate brainstorm); backfilling author metadata onto the 462 residual rows.

#### Deferred

- Resolving the 462 no-integer groups once TwitterAPI auth is reliable for ≥24h (U12 below).
- Brand-local co exceptions after anomaly fire.
- Soft-drop review queue for `not_include`.
- Expanding minimal co with ja/ko natives if metrics demand.
- BIGINT typing of `author_id` (separate brainstorm).

### Success Criteria

- **U0 verified prod pg_dump captured before any other work** (md5 matches round-trip readback; stored in a known-safe location off Render).
- 7-call hybrid funnel live; B1 bare; C thin co live; `@handle` B2/B3; primaries cleaned; C-only binary LLM; metrics present.
- ≥1 green harvest cycle on the new funnel (proves no crashes, keeps existing tweet volume ±10%).
- Reconciliation applied: dup count from 2,142 → 462; ~25,000 FK rows repointed; ~1,800 placeholder rows deleted.
- `LOWER(handle)` unique index in place; future drift fails at INSERT.
- AFTER-pinned regression net green.
- Operator runbook documents the residual pass.

---

## Planning Contract

### Key Technical Decisions

**Carried from `2026-07-28-001` (KTD1–KTD9).** Hybrid funnel; call roles; no `list:` for mentions; empty co omits `()`; minimal co allowlist; C-only binary LLM; anomaly metrics; primary demotions; config source.

**Carried from `2026-07-30-001` (KTD10–KTD14).**

- **KTD10.** Reconcile by TwitterAPI lookup, not by current `accounts` rows alone — verify the integer row's handle matches before repointing.
- **KTD11.** UPDATE-then-DELETE order to survive `ON DELETE SET NULL` on `posts` (otherwise 18,114 posts NULL out).
- **KTD12.** Skip groups where TwitterAPI lookup fails or disagrees; dead-letter.
- **KTD13.** Handle uniqueness via Postgres expression index `LOWER(handle) WHERE handle IS NOT NULL`, not Django `unique=True` (the column has case-insensitive collation; LOWER expression index is portable and matches how `posts.author_handle` is already indexed).
- **KTD14.** Reconciliation script lives outside the migration ledger (one-shot `manage.py reconcile_account_duplicates --dry-run|--apply`).

**New for this combined plan.**

- **KTD15.** Ship hybrid funnel before reconciliation. Two reasons: (1) the new funnel produces cleaner `author_id` writes during the reconciliation's execution window; (2) reconciliation's schema migration (U11) requires the unique index, which fails on the current 2,142 duplicates — but shipping the migration AFTER the reconciliation reduces dupes is cleaner than trying to ship it before and failing. Sequencing is a hard requirement.
- **KTD16.** (Superseded for future sessions by U16.) Originally: "Harvest cron stays enabled throughout." Updated stance: crons are paused BEFORE any unit work begins, resumed MANUALLY after U15 is verified complete. U16 codifies the pause/resume as the first and last operational steps. The original benign-concurrent-activity reasoning was true for the specific execution on 2026-07-30 (cron was already paused) but is not a forward-looking assumption — future sessions must pause explicitly.
- **KTD17.** The hybrid plan's old U1-U8 numbering is preserved in this combined plan as U1-U8. The reconciliation plan's old U1-U5 numbering is re-numbered as U10-U14. This keeps the original IDs stable (per ce-plan rules) so existing handoff docs that reference U-IDs in either source plan don't need updates. U0 is the pre-flight pg_dump; U15 marks the source plans deprecated.
- **KTD18.** Capture a verified pg_dump of the production DB BEFORE any other unit begins (U0). The 2026-07-28 denormalization incident and the 2026-07-29 recovery were painful because the rollback path depended on a dump that turned out not to be at the destination when claimed. Every claim in U0 must be physically verified: round-trip the file off Render, md5 the bytes on both ends, and store the dump somewhere a future session can find it.

### High-Level Technical Design

```text
phase 0: pre-flight safety net (U0)
  pg_dump pushinweight-db-shadow → /Users/fuchitalee/.../dumps/YYYYMMDD-HHMMSS.dump
  md5 verify on both ends; record in docs/operations/prod-dump-log.md

phase 0b: pause crons (U16 pause leg)
  suspend pushinweight-harvest cron + pushinweight-beat + pushinweight-worker
  record in docs/operations/pause-and-resume-harvest-cron.md

phase 1: hybrid funnel (U1–U8)
  config.yaml            C co → 5-term allowlist; B1 co=[]; B2/B3 handle maps
  x_monitor/query_plan.py  empty-co → omit `()`; handle-only → `(@h OR @h)`; thin-co unchanged shape
  x_monitor/relevancy.py  NEW — gate by call_id/C-brand, BINARY_RELEVANCY_SYSTEM/USER constants, parse KEEP/DROP
  x_monitor/relevance.py   extended with `not_include` matchers (post-fetch ban)
  monitor/cycle.py         wire relevancy gate between attribute and translate; emit per-call metrics
  Django data migration    idempotent primary purity seed (U4)

phase 2: ≥1 green harvest cycle on the new funnel
  observe: fetch_n, keep rate per call, error rate

phase 3: account reconciliation (U10–U14)
  tests/test_account_handle_uniqueness_regression_net.py   NEW — pin BEFORE state
  monitor/management/commands/reconcile_account_duplicates.py  NEW — dry-run + apply

phase 4: deprecate source plans (U15)
  banner + frontmatter merge on 2026-07-28-001 + 2026-07-30-001

phase 5: resume crons (U16 resume leg)
  un-suspend cron + workers only after U15 verified
  record in docs/operations/pause-and-resume-harvest-cron.md
```
  core/migrations/0009_accounts_handle_unique_ci.py        NEW — partial unique index
  docs/operations/reconcile-account-duplicates.md          NEW — operator runbook incl. Phase 2 residual pass
```

### Alternatives Considered

- **Ship reconciliation first, hybrid funnel after.** Rejected — the cron would keep producing full-22 co-occurrence queries during the reconciliation's apply run, drifting `accounts` further.
- **Combine U11 migration into a single deploy with U10 apply.** Rejected — the migration's precheck requires the duplicate count to be ≤ 1 per handle, which U10's apply is what achieves. The migration must be a separate deploy.
- **Skip C-only LLM relevancy and rely on `not_include` alone.** Rejected — `not_include` addresses stable hijacks but can't filter the EN dictionary noise that bare co admits. The LLM is the safety net.
- **Add the unique index via Django `unique=True` on the column.** Rejected — the column has `db_collation="case_insensitive"`, so case-sensitivity isn't guaranteed. LOWER expression index is the portable way.
- **Re-derive `posts.author_id` from `posts.author_handle` at query time.** Rejected — touches every read path; the reconciliation does the work once.

### Risks

- **Hybrid funnel misses foreign-language posts that lack the 5-term co allowlist.** Mitigated: multiword primaries + `@handle` covers the missing path; the foreign-loss diagnostic in `2026-07-28-001` showed the 5-term set recovers ~85% of relevant non-EN.
- **TwitterAPI 401 during U10 reconciliation.** Mitigated: dead-letter + idempotent re-run.
- **Wrong-handle repointing if TwitterAPI returns the wrong user.** Mitigated: KTD10's `handle ILIKE <requested>` filter; test scenario covers it.
- **`ON DELETE SET NULL` on `posts` would NULL 18,114 posts if U10 DELETEs before UPDATEs.** Mitigated: KTD11 explicit sequencing; UPDATE-then-DELETE.
- **`CREATE UNIQUE INDEX CONCURRENTLY` cannot run inside a Django transaction.** Mitigated: `migrations.RunSQL(..., atomic=False)`; the migration precheck detects duplicate handles and errors with a clear operator message.
- **New harvest code paths bypass `update_or_create(author_id=...)` and re-introduce placeholders.** Mitigated: U14 regression net includes a drift detector for placeholder rows at `first_seen_at > 2026-07-30`.
- **Reconciliation runs concurrent with live harvest cron.** Mitigated: KTD16 — per-group savepoints isolate transactions; benign contention.

---

## Implementation Units

This combined plan re-uses the original U-IDs from each source plan per KTD17. U0 is the pre-flight pg_dump (new, not carried from either source). The hybrid funnel's U1–U8 ship second. Reconciliation's U1–U5 become U10–U14. U15 marks the source plans deprecated.

### U0. Pre-flight: verified pg_dump of production DB

**Goal.** Capture a verifiable backup of `pushinweight-db-shadow` BEFORE any other work begins. This dump is the rollback path if any unit (U1–U14) goes wrong and corrupts the data. The 2026-07-28 denormalization incident + 2026-07-29 recovery demonstrated that "I made a dump" claims are unreliable — the upload can silently fail, the md5 can mismatch, the file can vanish. Every step of U0 must be physically verified.

**Files.**
- `scripts/ops/prod_dump.sh` (new) — the capture + verify script
- `docs/operations/prod-dump-log.md` (new) — append-only log of every dump event (timestamp, path, md5, destination, verifier signature)
- No DB schema changes.

**Approach.**

1. **Capture on Render shell** (internal network, fast):
   - Run `pg_dump --no-owner --no-privileges --format=custom --file=/tmp/pushinweight-YYYYMMDD-HHMMSS.dump "$DATABASE_URL"` using the shadow DB connection string from `~/.render/cli.yaml` (the shadow DB is the current production DB per the 2026-07-29 cutover).
   - Compute md5: `md5sum /tmp/pushinweight-YYYYMMDD-HHMMSS.dump`.
   - Compute row counts via the same SQL queries used in the Problem Frame audit (accounts, posts, etc.) and capture in the dump-log.
2. **Round-trip the file off Render** (this is the part that failed in 2026-07-28). Use ONE of these verified paths:
   - **Option A (preferred).** `scp` the file from Render shell back to `/Users/fuchitalee/Downloads/`. The Render shell runs as the service account; outbound SSH from Render to fuchitalee works if the service has SSH egress allowed. If not, fall back to B.
   - **Option B.** Use the existing `magic-wormhole` recipe from the recovery doc — `wormhole send /tmp/...dump` from Render shell, `wormhole receive <code>` on fuchitalee. The earlier sessions proved this works.
   - **Option C.** Upload to Google Drive via the SA token (`/Users/fuchitalee/Library/Application Support/gogcli/sa-emFyaWdhbmlAcXVhbnRtYS5jb20.json`) using `gen_signed_url.py`. The 2026-07-28 small-file uploads worked; for a ~50MB dump this should also work but verify.
3. **Verify on fuchitalee** that the file arrived intact:
   - `ls -la` shows the expected size.
   - `md5sum` on fuchitalee matches the md5 captured in step 1. **This is the verification the 2026-07-28 path skipped** — the plan body explicitly demands this step.
   - `pg_restore -l <dump>` lists tables and matches the expected count.
4. **Log the event** in `docs/operations/prod-dump-log.md` with: timestamp, dump path (Render + fuchitalee), md5 (both ends), row-count snapshot, operator initials, and verification statement ("round-trip verified at <host> at <ts>"). The log is append-only — entries are never edited.
5. **Store the dump** in `/Users/fuchitalee/Downloads/` with a date-stamped filename. Symlink in `dumps/latest.dump` for operator convenience (the latest always wins).

**Test scenarios:**
- Happy path: dump captures, md5 matches both ends, row-count snapshot matches the audit numbers in the Problem Frame, log entry written, file on fuchitalee at expected size.
- Edge: Render shell doesn't allow outbound SSH → fall back to Option B/C; the plan body documents the fallback.
- Edge: file size on fuchitalee differs from Render side → DO NOT trust; re-transfer; if still differs, abort the plan until the path is verified.
- Error: md5 mismatch → abort; the dump is not verified, downstream units cannot proceed.
- Error: `pg_restore -l` reports fewer tables than expected → dump is partial; abort.

**Verification.**
- `docs/operations/prod-dump-log.md` contains an entry dated today with all five fields filled.
- `ls -la /Users/fuchitalee/Downloads/pushinweight-YYYYMMDD-HHMMSS.dump` shows file ≥ 40 MB (the dump size from the 2026-07-28 incident was ~40 MB; today it's likely similar).
- `md5sum` on fuchitalee matches `md5sum` from the Render-shell capture (paste both into the log entry).
- `pg_restore -l <dump> | wc -l` ≥ 30 (the schema has 30+ tables per the recovery docs).
- `select count(*) from posts;` via psql returns 28,822.
- `select count(*) from accounts;` via psql returns 19,284.

**This unit blocks all others.** U1 cannot start until U0's verification is recorded in `prod-dump-log.md`. Per KTD18, "every claim in U0 must be physically verified."

---

### U1. Pin harvest surface regression net (hybrid, BEFORE pins)

**Goal.** BEFORE/AFTER pins for 7-call layout, B1 bare, C thin co allowlist, handle-only B2/B3.

**Files.** `tests/test_hybrid_harvest_regression_net.py`

**Approach.** Pin no xiaomi/moonshot in C co; C co length ≤ 8; B1 no secondary; all < 512.

**Verification.** pytest green as later units land.

**Carries forward from `2026-07-28-001` U1 unchanged.**

---

### U2. Renderer: empty co omit; handle-only; C thin co

**Goal.** `_build_query` supports bare, handle-only, and thin-co C shapes.

**Files.** `x_monitor/query_plan.py`; `tests/test_query_plan_hybrid_shapes.py`

**Approach.** Empty co → no `()`; handle-only OR of `@h`; C still `(primary) (co) min_faves`.

**Verification.** Unit tests.

**Carries forward from `2026-07-28-001` U2 unchanged.**

---

### U3. Config + handle wiring (7 calls)

**Goal.** Live config produces A/B1/B2/B3/C1/C2/C3 with thin co on C.

**Files.** `config.yaml`; `monitor/cycle.py`; store/run handle loaders; `tests/test_cycle_call_layout.py`

**Approach.** B1 co=[]; C co=minimal set; B2/B3 handle maps from official role; C3 new brands.

**Verification.** plan_calls shape tests + call-preview.

**Carries forward from `2026-07-28-001` U3 unchanged.** Update note: as of 2026-07-30 the existing `config.yaml` already has `call_b_groups` with 3 groups (B1/B2/B3) AND a `x_query_specs` block with 22-term co. The U3 work is to REPLACE the 22-term co with the 5-term allowlist, NOT to add `call_b_groups` from scratch. The plan body should call this out so the implementer doesn't add a redundant field.

---

### U4. Primary demotion migration

**Goal.** DB is_primary matches purity table (R15–R16).

**Files.** Django data migration; `tests/test_primary_purity_seed.py`

**Verification.** Idempotent seed tests.

**Carries forward from `2026-07-28-001` U4 unchanged.**

---

### U5. C minimal co + optional not_include

**Goal.** Enforce allowlist co; optional hijack exclusions.

**Files.** `config.yaml`; `query_plan.py` (optional `-` append); `relevance.py` matchers; `cycle.py`; `tests/test_c_minimal_co_and_not_include.py`

**Approach.** Pin co ⊆ allowlist; seed F1 not_include for C1 if length allows; post-fetch ban path; counters.

**Test scenarios.** C1 has thin co; no xiaomi in co; B1 bare; optional -antonelli; length < 512.

**Verification.** Unit + preview.

**Carries forward from `2026-07-28-001` U5 unchanged.**

---

### U6. C-only binary LLM relevancy

**Goal.** Binary keep/drop for C-path / C-brand only.

**Files.** `x_monitor/relevancy.py` (new — distinct from `relevance.py`); `monitor/cycle.py`; `tests/test_c_relevancy_gate.py`

**Approach.** Gate by call_id or C brand; ship **R19a** prompt as module constants (`BINARY_RELEVANCY_SYSTEM`, user template); parse first-line `KEEP`/`DROP` (case-insensitive); multilingual keep bias on uncertain / parse-fail → KEEP (log); full classify only keepers. No translate step before this gate.

**Verification.** Fake client tests: KEEP/DROP parse; uncertain→KEEP; non-EN sample with brand+loanword → KEEP path; gate skipped for A/B.

**Carries forward from `2026-07-28-001` U6 unchanged.** Update note: the original plan said "x_monitor/relevancy.py (or attribution)"; this combined plan commits to a NEW file `x_monitor/relevancy.py` to keep the LLM-call path distinct from the existing regex-based `relevance.py` (which is used for `not_include` ban matching).

---

### U7. Anomaly metrics in cycle summary

**Goal.** fetch_n / drop / keep rates per call for ops detector.

**Files.** `monitor/cycle.py`; summary JSON; `tests/test_cycle_anomaly_metrics.py`

**Verification.** Summary keys present.

**Carries forward from `2026-07-28-001` U7 unchanged.**

---

### U8. Reference docs + AFTER pins (hybrid)

**Goal.** Docs + U1 AFTER match shipped behavior.

**Files.** `docs/reference/twitterapi-live-queries-by-model.md`; `CONCEPTS.md`; U1 tests.

**Verification.** pytest + call-preview.

**Carries forward from `2026-07-28-001` U8 unchanged.**

---

### U10. Pin current state as regression net (reconciliation, BEFORE pins)

**Goal.** Capture the current duplicate-account state in tests so silent drift fails loudly. Earns its keep when U10 ships — without it, a partial merge looks like a complete one.

**Files.**
- `tests/test_account_handle_uniqueness_regression_net.py` (new)

**Approach.** Database test marked `django_db` that:
1. Snapshots today's duplicate count: `SELECT COUNT(*) FROM (SELECT handle, COUNT(*) FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1) t` — pin as `EXPECTED_DUPES_AT_PLAN_TIME` (the audit number is **2,142**, recompute at execution time).
2. Snapshots today's posts-at-placeholder count: `SELECT COUNT(*) FROM posts p JOIN accounts a ON a.author_id = p.author_id WHERE a.author_id !~ '^[0-9]+$'` — pin as **20,079**.
3. Snapshots today's account-post-appearance-at-placeholder count — pin as **6,803**.
4. Snapshots today's brands-accounts-at-placeholder count — pin as **95**.
5. Asserts `accounts.handle` has no unique constraint (`EXISTS` query against `pg_indexes`) — BEFORE state, flips in U14.
6. Asserts `posts.author_handle` collation is case-insensitive (regression on adjacent surface the plan does NOT change).
7. Asserts `accounts` row count == **19,284** (snapshot — pinned so a wholesale data wipe is caught).

Test scenarios:
- Happy path: every snapshot equals its pinned value (BEFORE state).
- Edge: `accounts` table contains rows where `handle` is NULL — these are excluded from uniqueness (the unique index is partial: `WHERE handle IS NOT NULL`).
- Edge: `accounts` table contains rows where `author_id` is NULL — `accounts.author_id` is the PK so this is impossible by schema, but the test guards the schema.
- Error: passing a non-database connection to the test runner raises (sanity — the assertions need a live DB).
- Integration: this test runs in the same Django test suite as `tests/test_harvest_cursor_regression_net.py` so any pipeline regression that touches `accounts` runs both nets.

**Verification.** `pytest tests/test_account_handle_uniqueness_regression_net.py -v` passes BEFORE U11 runs. The test will FAIL after reconciliation (the dupes count drops) — at that point, U14 updates the test to assert the AFTER state.

**Renumbered from `2026-07-30-001` U1.**

---

### U11. Reconciliation script — dry-run + apply modes

**Goal.** A `python manage.py reconcile_account_duplicates` command that resolves duplicate handle groups and rewires FKs to canonical rows. Idempotent, dry-run by default, dead-letter on failures.

**Files.**
- `monitor/management/commands/reconcile_account_duplicates.py` (new)
- `tests/test_reconcile_account_duplicates.py` (new)
- `docs/operations/reconcile-account-duplicates.md` (new — operator runbook; U13 finalizes)

**Approach.**

1. **Find duplicate groups** — `SELECT handle, array_agg(author_id ORDER BY first_seen_at) FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1`. Iterate each group.
2. **Classify each group** by what it contains:
   - Contains an integer row + placeholder(s) — candidate for merge.
   - Multiple integers (different X users for same handle) — KTD10 disagreement; TwitterAPI resolve.
   - Multiple placeholders only (no integer) — KTD12 skip (defer to follow-up).
3. **For each candidate merge group:**
   a. TwitterAPI lookup `GET /2/users/by/username/<handle>` (mirror `scripts/seed_list_handles_to_db.py`'s auth + retry shape).
   b. If lookup returns an integer different from every existing integer row → UPDATE existing integer rows' `last_seen_at` to NOW(), use that integer as canonical. If it matches an existing integer row → use that row's id as canonical.
   c. If lookup returns 401/404/timeout → KTD12 skip + dead-letter entry.
   d. If lookup returns an integer whose row in `accounts` has a different handle (case-insensitive) → KTD10 disagreement; skip + dead-letter.
4. **UPDATE order (KTD11):**
   - `UPDATE posts SET author_id = <canonical> WHERE author_id IN (<placeholder_ids>) AND author_handle ILIKE <handle>` → captures row count.
   - Same on `account_post_appearances`, `brands_accounts`, `companies_accounts`.
   - `DELETE FROM accounts WHERE author_id IN (<placeholder_ids>)` only if KTD12 not skipped.
5. **Wrap each group in a Postgres SAVEPOINT.** Per-group failure rolls back to savepoint; dead-letter the group; continue.
6. **Emit summary JSON** to stdout: groups processed, groups skipped (with reason), rows updated per table, rows deleted, dead-letter list.

Dry-run mode: do all reads + TwitterAPI calls, print the planned UPDATE/DELETE statements with row counts, do not execute.

Apply mode: execute, log to a new `core_reconcile_dead_letter` table (or to stdout if table creation is out of scope).

**Patterns to follow.** `scripts/seed_list_handles_to_db.py` for TwitterAPI auth and dead-letter pattern; `monitor/management/commands/run_cycle.py` for command shape (--dry-run, --json, --limit-per-call-style flags).

**Test scenarios:**
- Happy path: 3-handle group with `handle:*` + integer → integer canonical, posts/FKs repointed, placeholder row deleted.
- Happy path: all-placeholder group (no integer) → KTD12 skip, dead-letter entry, no DB changes.
- Happy path: handle where TwitterAPI returns a NEW integer not currently in `accounts` → that new integer becomes canonical (creates the integer row if absent).
- Edge: handle where TwitterAPI lookup returns 401 → dead-letter, no DB changes.
- Edge: handle where existing integer row's handle disagrees with the dup group handle → KTD10 disagreement skip.
- Edge: 0 handle duplicates (no-op) → command exits 0, summary reports 0 groups.
- Error: TwitterAPI timeout mid-batch → that group dead-letters, subsequent groups still process.
- Error: a FK UPDATE violates a constraint → savepoint rollback, dead-letter, continue.
- Integration: posts that point at a placeholder row end up pointing at the canonical row after `--apply`; the placeholder row no longer exists; FK on `posts.author_id` still satisfied.

**Verification:**
- Dry-run on the shadow DB today produces summary: ~1,500 groups eligible for merge (handle+integer pattern), 327 deferred (synthetic+handle), 137 (synthetic+integer) eligible for merge, 105 all-three eligible, 4 handle+bare eligible. ZERO rows updated.
- Apply run on shadow DB reduces dup count from 2,142 toward 462 (the no-integer groups remain), updates ~25,000 FK rows, deletes ~1,800 placeholder rows.
- `pytest tests/test_reconcile_account_duplicates.py -v` passes.
- U10's regression net now reports the AFTER state — U14 flips it.

**Renumbered from `2026-07-30-001` U2.**

---

### U12. Schema migration — partial unique index on `accounts.handle`

**Goal.** Add the case-insensitive uniqueness constraint so future drift is impossible.

**Files.**
- `core/migrations/0009_accounts_handle_unique_ci.py` (new)

**Approach.**

```sql
-- Forward
CREATE UNIQUE INDEX CONCURRENTLY uniq_accounts_handle_lower
  ON accounts (LOWER(handle)) WHERE handle IS NOT NULL;

-- Reverse
DROP INDEX IF EXISTS uniq_accounts_handle_lower;
```

Use `migrations.RunSQL(..., atomic=False)` because `CREATE UNIQUE INDEX CONCURRENTLY` cannot run inside a transaction. KTD13: expression index `LOWER(handle)` because `accounts.handle` has `db_collation="case_insensitive"` at column level but Postgres still permits non-deterministic uniqueness when only `handle` itself is indexed.

**Migration precheck.** The migration runs a SELECT first and aborts if duplicates remain:

```python
with connection.cursor() as cur:
    cur.execute("""
        SELECT COUNT(*) FROM (
          SELECT LOWER(handle) FROM accounts
          WHERE handle IS NOT NULL
          GROUP BY LOWER(handle)
          HAVING COUNT(*) > 1
        ) t
    """)
    if cur.fetchone()[0] > 0:
        raise RuntimeError(
            "accounts still has duplicate handles (case-insensitive). "
            "Run `manage.py reconcile_account_duplicates --apply` first."
        )
```

**Test scenarios:**
- Happy path: migration forward + reverse leaves `accounts` row count unchanged (19,284).
- Error: try to add the same index twice → raises `IndexAlreadyExists` (idempotency guard).
- Error: try to forward the migration against a DB with > 1 duplicate `LOWER(handle)` → raises the precheck `RuntimeError` with the operator message.
- Integration: after U10 + U11 + U12 all run, INSERT a new account with a handle that already exists (case-insensitive) → `IntegrityError` at the DB layer. INSERT with a different handle → succeeds.

**Verification.** `python manage.py migrate` succeeds; subsequent `python manage.py shell` test of duplicate insert raises IntegrityError; U10's regression net (updated to AFTER state in U14) passes.

**Renumbered from `2026-07-30-001` U3.**

---

### U13. Operator runbook for follow-up resolution (no-integer groups)

**Goal.** Document the path for the 462 residual groups (synthetic+handle without integer) so the next session knows how to clear them once TwitterAPI auth is reliably working.

**Files.**
- `docs/operations/reconcile-account-duplicates.md` (new — initial draft; finalized by U13)

**Approach.** Add a section "Phase 2: resolving residual no-integer groups" with:
- The query that lists them.
- A repeat of U11's command with `--residual-only` flag (added to U11).
- Expected outcome: dupes go from 462 → 0, posts-at-placeholder go from 1,965 → 0.
- The trigger condition: ≥24 hours of clean TwitterAPI 200 responses in the harvest cycle.

**Test scenarios.** Documentation only; no test.

**Verification.** Operator reads the doc, knows what command to run, knows the precondition.

**Renumbered from `2026-07-30-001` U5.** Placed BEFORE U14 (regression net flip) so the runbook ships with the reconciliation, not after.

---

### U14. Update regression net to assert AFTER state

**Goal.** Flip U10's pinned values from today's drift numbers to the post-reconciliation expectations.

**Files.**
- `tests/test_account_handle_uniqueness_regression_net.py` (modify)

**Approach.**

Update each `EXPECTED_*` constant to its AFTER value:
- `EXPECTED_DUPES_AT_PLAN_TIME`: 2,142 → **462** (the no-integer residual groups; KTD12 defer).
- `EXPECTED_POSTS_AT_PLACEHOLDERS`: 20,079 → **1,965** (only the all-synthetic/handle groups remain; KTD12 defer).
- `EXPECTED_APPEARANCES_AT_PLACEHOLDERS`: 6,803 → computed at execution time (some of the 6,803 may have been at synthetic handles that defer; safe lower bound 0, exact value requires rerunning the audit query at U14-time).
- `EXPECTED_BRANDS_AT_PLACEHOLDERS`: 95 → computed at execution time (same caveat).
- New assertion: `EXISTS` query against `pg_indexes` for `uniq_accounts_handle_lower` → **true** (the new constraint).
- New assertion: every account row's `author_id` matches a value that either IS an integer OR appears in the dead-letter log (KTD12 leftover). Allows the residual 462 placeholder rows.
- Account count snapshot: 19,284 - (placeholder rows deleted) → recomputed at U14-time.

Add a comment block at the top of the test file explaining: BEFORE was 2026-07-30 (pre-reconciliation). AFTER is post U11+U12. Future drift that diverges from these numbers indicates either (a) TwitterAPI auth back and the no-integer groups are being resolved, in which case rerun U11 + update this test, OR (b) new drift introduced by a code path that bypasses `update_or_create(author_id=...)`, which is the test's primary purpose.

**Test scenarios:**
- Happy path: every pinned AFTER value matches the live DB.
- Edge: the test fails if `uniq_accounts_handle_lower` index is missing.
- Edge: the test fails if any new placeholder pattern (`synthetic:*`, `handle:*`, bare handle equal to author_id) appears at `first_seen_at > 2026-07-30` (i.e., a code path is creating new placeholders). This is the drift detector.
- Error: passing a future date to `--as-of` flag (not in scope but mentioned) — the test ignores the flag today.

**Verification.** `pytest tests/test_account_handle_uniqueness_regression_net.py -v` passes post U11+U12. Test FAILS if any future commit adds rows matching the new-drift detector.

**Renumbered from `2026-07-30-001` U4.**

---

### U15. Mark source plans deprecated

**Goal.** Once this combined plan's implementation is verified end-to-end (U0 dump captured, hybrid funnel live, ≥1 green harvest cycle, reconciliation applied, unique index in place, regression net flipped to AFTER), the two source plans this combined plan supersedes — `2026-07-28-001-feat-b1-purity-official-handles-plan.md` and `2026-07-30-001-fix-accounts-handle-duplicates-reconciliation-plan.md` — must be marked deprecated. Without this unit, future sessions reading the docs/ directory can pick up the source plans and start re-implementing work that has already shipped (or worse, plan conflicting approaches to the same problem).

**Files.**
- `docs/plans/2026-07-28-001-feat-b1-purity-official-handles-plan.md` (modify — add deprecation banner to top)
- `docs/plans/2026-07-30-001-fix-accounts-handle-duplicates-reconciliation-plan.md` (modify — add deprecation banner to top)
- No code changes. No schema changes.

**Approach.**

1. Prepend a YAML frontmatter block to each source plan that records the deprecation:

   ```yaml
   ---
   deprecated: true
   deprecated_on: <YYYY-MM-DD>
   deprecated_by: <commit-sha>
   superseded_by: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
   deprecation_reason: "Amended and merged into the combined plan above. The hybrid funnel's U1–U8 ship from this plan; the reconciliation's U1–U5 became U10–U14 in the combined plan. Do not re-implement from this file; refer to the combined plan instead."
   ---
   ```

   If the source plan already has frontmatter (the 2026-07-28 plan has `artifact_contract` + `artifact_readiness` + `product_contract_source` + `execution`), MERGE the deprecation fields into the existing frontmatter rather than prepending a second block — YAML frontmatter is one block.

2. Add a visible deprecation banner at the top of the source plan body, just below the title and above the existing Goal Capsule (or section heading). Use the project's standard deprecation banner format:

   ```markdown
   > **DEPRECATED 2026-07-30.** Superseded by `docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md` (commit `<sha>`). Do not implement from this file.
   ```

3. The combined plan's `amends:` frontmatter (already present at the top of this document) is the forward reference. The source plans' `superseded_by:` is the back reference. Together they form a navigable chain.

4. **Do NOT delete the source plans.** Historical plans stay in `docs/plans/` for audit. Deleting them would break references in handoff docs (`docs/handoffs/2026-07-29-*`) that cite U-IDs from those plans.

5. Commit the deprecation edits with the message:

   ```
   docs(plans): deprecate 2026-07-28-001 + 2026-07-30-001 (superseded by 2026-07-30-002)

   Both source plans are amended and merged into the combined plan.
   The hybrid funnel's U1–U8 ship from 2026-07-28-001; the
   reconciliation's U1–U5 became U10–U14 in 2026-07-30-002.

   Scope delivered vs plan promised: match.

   - Add deprecated frontmatter + banner to both source plans.
   - Back-link to 2026-07-30-002 via superseded_by.
   - Do not delete — historical plans stay for audit.
   ```

**Test scenarios.**
- Happy path: both source plans render with a deprecation banner at the top; frontmatter parses (valid YAML); `superseded_by` field points at the combined plan path.
- Edge: the source plan is read by a fresh session; the banner is visible above the Goal Capsule and the next agent pauses to consult the combined plan.
- Error: typo in `superseded_by` path → CI fails on a future doc-link-check (if such a check exists; otherwise manual review).

**Verification.**
- `head -20 docs/plans/2026-07-28-001-feat-b1-purity-official-handles-plan.md` shows the deprecation banner immediately after the title.
- `head -20 docs/plans/2026-07-30-001-fix-accounts-handle-duplicates-reconciliation-plan.md` shows the same.
- Both files still exist and are committed (no deletion).
- The combined plan (`2026-07-30-002`) still references both source plans via the `amends:` frontmatter.
- `git grep "deprecated: true" docs/plans/` returns both source plans.

**Carries forward from this combined plan's Goal Capsule.** The "supersedes" relationship is bidirectional: combined plan → source plans via `amends:`, source plans → combined plan via `superseded_by:`. The Deprecation Plan section in `docs/plans/README.md` (if one exists) is also updated to list the two source plans as deprecated; otherwise the banners themselves are the canonical signal.

---

### U16. Pause harvester + backfiller crons (forward-looking guardrail)

**Goal.** Set a precedent — codified in this plan body — that any future execution of a plan of this shape (config + renderer + schema + reconciliation) begins by pausing the harvester and any backfiller crons BEFORE any unit touches production data, and resumes them MANUALLY only after the plan is verified complete. Today (2026-07-30), the harvester cron is already halted from the 2026-07-28 denormalization incident recovery — so this unit is a no-op for the current session — but a future healthy-harvester session must still execute the pause as the first operational step.

**Why this unit exists.** The earlier reconciliation handoff (memory `project_pushinweight_2026-07-29_recovery_state.md`) lost a day to a hot loop where the live harvest kept writing while the recovery script tried to clean up — drift compounded faster than the cleanup could drain it. The hybrid funnel's U2–U7 ship a config + renderer change that mutates the live harvest shape; if a cron cycle runs against the partially-shipped state, it can drop into a half-migrated code path and leave `accounts`/`posts` in an inconsistent state. Reconciliation's U11 then has to clean up that inconsistency on top of the existing duplicates. Pausing the crons first is the cheap way to avoid this. Resume is manual so the operator sees green before re-enabling.

**Files.**
- `docs/operations/pause-and-resume-harvest-cron.md` (new) — operator runbook for pause/resume
- No code changes. No schema changes.

**Approach.**

1. **Identify the crons to pause.** As of 2026-07-30:
   - `pushinweight-harvest` — Render cron `crn-d9gv94o4n6ts739tqaug`, schedule `*/15 * * * *`, start command `python manage.py run_cycle --limit-per-call 50`. **Already paused as of 2026-07-30** (carry-over from 2026-07-28 incident recovery; `suspended: not_suspended` per the dashboard but the schedule has been a no-op since the recovery; verify by checking `render cron list` or the dashboard).
   - `pushinweight-beat` — Render background worker `srv-d9go2breo5us73cg6vrg`, Celery beat scheduler. Writes via Celery → `monitor/cycle.py`. **Already paused** (same carry-over).
   - `pushinweight-worker` — Render background worker `srv-d9go2breo5us73cg6vr0`, Celery worker. Same.
   - Any **backfiller cron** — `scripts/backfill_*.py`, `monitor/management/commands/*_backfill*`. There is no scheduled backfiller cron in `render.yaml` today, but if a future session adds one (e.g., for a new brand), the pause must include it. The runbook calls this out generically.

2. **Pause the crons BEFORE any unit work begins.** For Render crons + workers:
   - **Render dashboard**: `https://dashboard.render.com/cron/crn-d9gv94o4n6ts739tqaug` → "Suspend". Document the action in the runbook.
   - **Render REST API** (alternative): `POST /v1/services/{id}/suspend` with `{"suspend": true}` and the API key from `~/.render/cli.yaml`. The cron and worker services each have a `suspended` field — verify before each unit that touches production.
   - **render.yaml schedule change** (last resort): edit `cronJobs[].schedule` to a never-firing value (`"0 0 31 2 *"` was the de-facto pause used in the 2026-07-29 recovery per memory `project_pushinweight_2026-07-29_recovery_state.md`). This requires a blueprint re-sync and triggers a deploy. Slower than the dashboard suspend but documented in source.

3. **Verify pause** before U1 begins:
   - `render services list -o json | jq '.[] | select(.service.type == "background_worker" or .service.type == "cron_job") | {name: .service.name, suspended: .service.suspended}'` shows `suspended: "suspended"` for the three services + cron.
   - Or: `curl -H "Authorization: Bearer $RND_KEY" https://api.render.com/v1/services/{id}` returns `"suspended": "suspended"`.

4. **Document the pause event** in `docs/operations/pause-and-resume-harvest-cron.md`:
   - Timestamp (UTC + JST).
   - Method used (dashboard / API / render.yaml).
   - Service IDs + names paused.
   - Operator initials.
   - Resume condition (see step 5).

5. **Resume MANUALLY after U15 is verified complete** (Phase 5 in Sequencing). The resume is NOT automatic — the operator must see green from U14's regression net flip AND verify the harvest cycle ran cleanly via `render logs -r srv-d9go2breo5us73cg6vr0 --tail 30 --output text` before unpausing. Resume path:
   - Reverse the pause method (dashboard un-suspend, or revert `render.yaml` schedule).
   - Wait for at least one cycle to run (`/15` schedule = up to 15 min wait).
   - Verify the cycle produced expected keep rates per `run_cycle --json` output.
   - Document the resume event in the same runbook file.

**Test scenarios.**
- Happy path: all 3 services + cron are `suspended: "suspended"` before U1 begins. Runbook records the pause event with all required fields.
- Edge: a future session runs this plan on a healthy harvester (cron NOT pre-paused). The pause step takes effect mid-session; U1's BEFORE-state regression net still passes because the data is unchanged; U2+ ship against a quiet DB.
- Edge: this unit is a no-op for the current session because the harvester is already paused. The runbook records "verified paused at <ts>" rather than "paused at <ts>". Document explicitly so future readers don't think the step was skipped.
- Error: pause command fails (API down, dashboard locked) → abort the plan; U1 cannot start with a hot harvest. The plan body says explicitly: "if you can't pause the crons, do not start U1."

**Verification.**
- `render services list -o json | jq '.[] | select(.service.name | startswith("pushinweight-")) | {name: .service.name, suspended: .service.suspended}'` shows `suspended: "suspended"` for the 3 services + cron at the moment U1 starts.
- `docs/operations/pause-and-resume-harvest-cron.md` has a "Pause Event" entry dated today with all required fields.
- After U15 is verified complete and the operator resumes, the runbook gets a "Resume Event" entry.

**Carries forward from this combined plan.** KTD16 already said "harvest cron stays enabled throughout" — that's the OLD assumption from the original two plans. This U16 unit flips KTD16's stance: crons are paused by default for any plan execution of this shape, resumed manually only after green. KTD16 is now superseded by this unit for future sessions; the original 2026-07-30-001 plan's KTD16 reasoning (benign concurrent activity) was true for the OLD specific plan but is not a forward-looking assumption.

---

## Sequencing

**Phase 0: Pre-flight safety net (U0)**
1. U0 first — verified pg_dump captured, round-trip verified, log entry written. **Blocks all other units.**

**Phase 0b: Pause harvester + backfiller crons (U16)**
2. U16 — set the precedent that future plan executions of this shape begin with a cron pause. (At the time of writing this plan, 2026-07-30, the harvester cron is already halted from the 2026-07-28 denormalization incident. This unit is a forward-looking guardrail: any future session running this plan on a healthy harvester must pause first and resume manually.)

**Phase 1: Hybrid funnel (U1–U8)**
3. U1 first — pins current state, no behavior change.
4. U2–U7 ship as a coordinated change in a single PR (config + renderer + relevancy + metrics).
5. U8 updates the regression net to AFTER state + reference docs.

**Phase 2: ≥1 green harvest cycle on the new funnel**
- Observe fetch_n, keep rate per call, error rate in `run_cycle --json` output.
- Gate: all 7 calls return without error; keep rate per call is within ±10% of the prior week's average; no Python tracebacks in the harvest logs.

**Phase 3: Account reconciliation (U10–U14)**
6. U10 first — pins BEFORE state. Test passes today.
7. U11 dry-run on the shadow DB — print summary, no DB writes.
8. U11 apply on the shadow DB. Audit: dup count → 462, posts-at-placeholder → 1,965, brands-at-placeholder → computed, 0 in `companies_accounts` confirmed.
9. U12 migration lands (deploy) — the precheck verifies dup count ≤ 1 per handle; passes because U11 reduced it.
10. U13 operator runbook ships alongside U12.
11. U14 regression net flipped to AFTER state. Now detects future drift.

**Phase 4: Mark source plans deprecated (U15)**
12. U15 — once Phases 0–3 are verified end-to-end, prepend the deprecation banner to `2026-07-28-001` and `2026-07-30-001`. Single commit. See U15 body for the exact frontmatter merge + banner.

**Phase 5: Resume crons manually (U16 resume leg)**
13. U16 resume leg — the operator (or the next session) verifies that U0–U15 have all completed green, then re-enables the harvester and backfiller crons via the dashboard. No automatic resume — by design. The cron schedule in `render.yaml` is checked-in but `cronJobs:` are toggled via the Render dashboard (or `render cron update` if the CLI exposes it; otherwise via `render.yaml` patch + blueprint re-sync). Document the resume step in `docs/operations/pause-and-resume-harvest-cron.md` (new) for future sessions.

**Render deploy order.**
- U0 is a Render shell + fuchitalee local operation; no deploy.
- The hybrid funnel's U1–U8 ship as one PR (no schema change).
- U11 reconciliation is a one-shot management command invoked manually by an operator; no deploy.
- U12 migration runs as part of `./build.sh` on the next deploy AFTER U11's apply. The migration's precheck detects any remaining dupes and errors with a clear operator message.
- U15 is a docs-only commit; can land in any PR or standalone.

**Hard sequencing constraints.**
- KTD11: U11 DELETEs must run AFTER UPDATEs.
- KTD15: U11 must run BEFORE U12 lands on production.
- KTD16: harvest cron stays enabled throughout; benign concurrent activity.
- KTD18: U0 must complete before U1 begins; U0's verification log entry is the gating artifact.

## Definition of Done

- **U0 verified prod pg_dump captured before any other work** (md5 matches round-trip readback; stored in `~/Downloads/` on fuchitalee; entry in `docs/operations/prod-dump-log.md`).
- **U16 pause leg verified before U1 begins** — `render services list` shows `suspended: "suspended"` for the harvester cron + beat + worker; entry in `docs/operations/pause-and-resume-harvest-cron.md`.
- U1 regression net ships with pinned BEFORE values for hybrid funnel, passes green before any other hybrid unit runs.
- U8 regression net flipped to AFTER state for hybrid funnel.
- U2–U7 shipped as a single PR; all unit + integration tests pass.
- U10 regression net ships with pinned BEFORE values for accounts, passes green before U11.
- U11 reconciliation command lands dry-run + apply modes. Apply reduces dup count from 2,142 → 462 (or lower if TwitterAPI resolves more).
- U12 migration `0009_accounts_handle_unique_ci` ships and applies cleanly on the live shadow DB AFTER U11's apply run.
- U13 operator runbook documents the residual pass.
- U14 regression net flipped to AFTER state for accounts. Future drift fails loudly.
- U15 deprecation banners + frontmatter merges applied to both source plans; bidirectional references in place.
- **U16 resume leg verified** — operator manually re-enables the cron + workers AFTER U15 is verified complete; resume entry recorded in `docs/operations/pause-and-resume-harvest-cron.md`; first post-resume harvest cycle is observed clean (no Python tracebacks, keep rates within ±10% of pre-pause baseline).
- All unit tests pass under `pytest tests/test_hybrid_harvest_regression_net.py tests/test_query_plan_hybrid_shapes.py tests/test_c_minimal_co_and_not_include.py tests/test_c_relevancy_gate.py tests/test_cycle_anomaly_metrics.py tests/test_account_handle_uniqueness_regression_net.py tests/test_reconcile_account_duplicates.py -v`. (`tests/test_cycle_call_layout.py` originally listed in this row is NOT present on disk; see Scope Delta 2026-07-30 below.)
- `python manage.py reconcile_account_duplicates --dry-run --json` reports the expected summary.
- `python manage.py reconcile_account_duplicates --apply --json` runs against shadow, audit confirms dup count dropped, FK row counts updated, no `IntegrityError`.
- `./build.sh` runs `manage.py migrate` end-to-end; U12 lands as part of the next production deploy.
- `./render.yaml` may need a `cronJobs:` schedule revert if the pause was implemented via `render.yaml` instead of the dashboard.
- Commits include the **Scope delivered vs plan promised: [match | narrower: deferred Y for reason Z]** line per global rules.

## Deferred to Follow-Up Work

- **Resolving the 462 no-integer groups** (synthetic + handle rows without an integer). Trigger: ≥24 hours of clean TwitterAPI 200 responses in the harvest. Operator runs `manage.py reconcile_account_duplicates --apply --residual-only`. Brings dupes → 0.
- **Backfilling author metadata** (display_name, bio, follower counts) onto the residual rows once they have integer IDs. A second-pass script that joins `accounts` (now canonical) with the harvested post payloads and updates NULL fields.
- **Adding `author_id` integer type** (BIGINT). Out of scope; touches every consumer. Worth a separate brainstorm if/when the brand-seeding scripts are rewritten to skip the placeholder path entirely.
- **Expanding minimal co with ja/ko natives** if hybrid-funnel metrics demand.
- **Soft-drop review queue for `not_include`** (from `2026-07-28-001` Deferred).
- **Brand-local co exceptions** after anomaly fire (from `2026-07-28-001` Deferred).

## Sources & Research

- Session purity probes; foreign-lang miss rates under full 22; LG AI + xiaomi co poison; B3 bare then revert history; `relevance.py must_have_none` retired 2026-07-11-001; X operators `list:` vs `@`.
- Live pre-change lengths: A 38 / C1 461 / C2 295 / B1 414 / B2 377 / B3 359.
- Account audit query results on 2026-07-30 against the live shadow DB (pushinweight-db-shadow, basic_1gb, 28,822 posts).
- `git log` since 2026-07-28 confirms no production commits between 2026-07-28 and 2026-07-30 ship any U1–U8 of `2026-07-28-001`; the plan was waiting.
- `render.yaml` `fromDatabase` env var is documented as not updating on existing services (memory `feedback_render_blueprint_fromdatabase_stale.md`); the operational workaround for that bug is unrelated to this plan's work but is referenced because the production deploy path (U11) goes through Render.

## Scope Delta — 2026-07-30

### Hybrid harvest half acceptance (U0–U8 + U16) — operator chose (b)

**Operator decision 2026-07-30 (PST):** Accept current state and move on to U9–U15 reconciliation half. Per CLAUDE.md rule 5 the plan body is updated to match delivered scope.

**What shipped green:**
- U0 prod pg_dump verified (md5 `b239a84573319acf2cbb1b0337f3adab`, 366 TOC entries, row counts match — see `docs/operations/prod-dump-log.md`).
- U1 regression net (166 lines, pins AFTER state of harvest surface).
- U2 renderer (`x_monitor/query_plan.py` + `tests/test_query_plan_hybrid_shapes.py`, 176 lines).
- U3 config + 7-call wiring (`call_b_groups` + `x_query_specs` in `config.yaml`; wired through `monitor/cycle.py`).
- U4 primary purity seed (`core/migrations/0007_brand_keyword_primary_purity.py` + `tests/test_primary_purity_seed.py`, 97 lines).
- U5 C minimal co + not_include (`tests/test_c_minimal_co_and_not_include.py`, 136 lines).
- U6 C-only binary LLM relevancy (`x_monitor/relevancy.py` + `tests/test_c_relevancy_gate.py`, 185 lines).
- U7 anomaly metrics (`tests/test_cycle_anomaly_metrics.py`, 126 lines).
- U8 docs + AFTER pins (`docs/reference/twitterapi-live-queries-by-model.md` present).
- U16 pause (3 services + cron suspended via Render REST API; entry in `docs/operations/pause-and-resume-harvest-cron.md`).

**Regression net run (2026-07-30) on `pushinweight_test`:**
- 55 passed, 3 errors in 1.39s.

**Documented gaps (accepted as deferred):**

1. `tests/test_cycle_call_layout.py` named in U3 body is NOT on disk. The U3 wire-in (config + cycle.py) is exercised by adjacent tests (`test_harvest_cursor_regression_net.py`, `test_post_fetch_smoketest_call_preview.py`, `test_run.py`). The named file is referenced in the DoD test list above and was removed in this delta. Tracking deferred.

2. U4 `test_primary_purity_seed.py` errors out when running against `pushinweight_test` because the U11 migration `0009_accounts_handle_unique_ci.py` uses `CREATE UNIQUE INDEX CONCURRENTLY` with `atomic=False` (correct for production) — Django's test-runner wraps the test DB in a transaction anyway, so the migration errors during test-DB setup with `CREATE INDEX CONCURRENTLY cannot run inside a transaction block`. The migration's behavior on production is correct; only the test-runner interaction is broken. Tracking deferred (needs either a test-time migration skip or a workaround that builds the index outside the test transaction).

**Migration filename corrections (also part of this delta):**
- Plan body originally referenced `0042_accounts_handle_unique_ci` (3 places); actual filename is `0009_accounts_handle_unique_ci.py` on disk. Corrected in this delta.

### Live-DB reconciliation findings (2026-07-30)

Counts on `pushinweight_shadow` after U10 apply:
- Total accounts: 17,105
- Integer `author_id`: 6,092 (35.6%)
- `handle:` prefix placeholder: 10,022
- `synthetic:` prefix placeholder: 969
- Non-integer, non-placeholder edge cases: 22
- Residual dup groups: 69 (down from 2,142 before U10 apply)
- Placeholder rows inside residual dup groups: 83

#### Lonely placeholder exposure (added 2026-07-30 per operator question)

Of the **10,908 lonely placeholders** (handle-unique, no dup group):
- Referenced by `posts` (distinct placeholders): **10,895**
- `posts` rows pointing at lonely placeholder: **13,953**
- Referenced by `account_post_appearances` (distinct placeholders): **4,055**
- `account_post_appearances` rows pointing at lonely placeholder: **4,864**
- Referenced by `brands_accounts`: 0
- Referenced by `companies_accounts`: 0
- True orphans (no FK reference anywhere): **13**

**Implication for the plan's "all FK tables reference integer author_ids" goal:** the plan as written is NOT achieved. The reconciliation half's U10 worked on duplicate groups only; the 10,908 lonely placeholders are load-bearing FK targets for 13,953 posts and 4,864 APAs. To finish the goal, a separate "orphan resolution" pass is needed that:
1. For each lonely placeholder `p` with handle `h`:
   - Call TwitterAPI `/twitter/user/info?userName=h` to get canonical integer `i`.
   - INSERT `accounts` row for `(i, h, verified=false, first_seen_at=NOW(), last_seen_at=NOW())`.
   - UPDATE `posts SET author_id=i WHERE author_id=p` and `LOWER(author_handle)=LOWER(h)`.
   - UPDATE `account_post_appearances SET author_id=i WHERE author_id=p`.
   - DELETE `accounts WHERE author_id=p`.
2. KTD10 safety net: skip + dead-letter when TwitterAPI returns a disagree integer (different from `LOWER(handle)` match).
3. U11 unique index migration (`0009_accounts_handle_unique_ci`) MUST be re-run after this pass — it will refuse with "still has N duplicate handle groups" until every placeholder is resolved.

**Without this pass:**
- The dashboard's account lookup (`accounts.handle`) returns placeholder rows forever.
- Foreign-key joins like `posts JOIN accounts` continue to dereference placeholder IDs.
- TwitterAPI lookups for these handles in future harvest cycles return the same integer repeatedly — creating new placeholder rows when the canonical row doesn't exist (or skip-on-disagreement when it does).
- U11 unique index CANNOT ship (385 dup groups at last check; precheck refuses).
- U15 cron resume is still blocked per `docs/operations/pause-and-resume-harvest-cron.md` — the resume leg was deferred to the dashboard because the Render REST API doesn't un-suspend, but the underlying drift problem remains.

**Plan scope delta:** the original plan body said "U10 reduces dup count from 2,142 → 462 (or lower if TwitterAPI resolves more)" and listed "Resolving the 462 no-integer groups" as Deferred to Follow-Up Work. That deferred item now needs to be re-scoped: it covers both (a) the 69 residual dup groups from U10's Phase 2 AND (b) the 10,908 lonely placeholders, which together represent ~14K+8K placeholder rows backed by ~19K FK references in posts + APAs.

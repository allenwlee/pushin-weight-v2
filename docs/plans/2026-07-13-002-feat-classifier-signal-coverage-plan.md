---
title: Classifier signal-coverage gaps from the 2026-07-13 live A→Z run
date: 2026-07-13
type: feat
status: ready
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

# Goal Capsule

Close the classifier signal-coverage gaps exposed by the 2026-07-13 live
A→Z populate run. The smoketest was green, but in production several
classifier outputs are dark — values the LLM never emits even when the
underlying signal is present — leaving the dashboard and downstream
filtering underweighted. This plan turns the highest-value dark signals
into lit ones, surfaced through prompt definitions, programmatic
derivations, and/or visibility so operators see the gap instead of a
silent zero.

# Problem Frame

The 2026-07-13 live run (`data/runs/20260713T040301_0000-bbf72b83.json`)
executed 6 calls (A, B1, B2, B3, C1, C2) across the v1.7 framework,
inserted 12/36 posts, and surfaced three classifier signal-coverage gaps
that the U3 evidence report (`tests/classifier_tests/20260713T040301_0000-bbf72b83-u3-evidence.md`)
quantifies:

1. **`unsanctioned_flags` is dark**: 0/9 inserted posts got a row in
   `posts_unsanctioned_flags`. The LLM returns `unsanctioned_flags: []`
   for every post. The marketing-spam signal is captured in
   `discourse_role: advertising-marketing` (id=10) for several posts but
   is not translated to the top-level unsanctioned array. Root cause:
   `_PRAGMATICS_FULL_SYSTEM_PROMPT` at `x_monitor/attribution.py:1076-1082`
   lists the 4 valid flag values (`marketing_spam`, `scam`, `crypto`,
   `unauthorized`) but provides no trigger-condition definitions for
   what qualifies, unlike `post_types` and `discourse_roles` which have
   full definitions.

2. **`posts_brands_discourse` dead-letters (12 rows)**: 12 brand-rows in
   the U3 run logged KTD5 dead-letters with value `uncategorized`,
   context `uncategorized-sentinel (KTD5): row skipped, no FK target`.
   This is a separate signal-coverage gap: the LLM emits
   `discourse_role: "uncategorized"` (or the parser maps to it) when none
   of the 10 defined roles match, and the row is silently dropped instead
   of being captured as a tripwire.

3. **Closed-DB crash at end of pipeline** (`x_monitor/run.py:1366-1370`):
   `_update_accounts(store, summary)` runs after `store.close()`. This
   is a pre-existing bug exposed by U3, not a classifier signal, but it
   blocked the live run's tail from running cleanly. Tracked as task
   #288 in the open issue list.

The plan addresses (1) and (2) directly. (3) is a small fix and is folded
into U1 as a closure so the run tail remains green for future
classifier-validation runs.

# Requirements

R1. Define trigger conditions for the four `unsanctioned_flags` values
    (`marketing_spam`, `scam`, `crypto`, `unauthorized`) in
    `_PRAGMATICS_FULL_SYSTEM_PROMPT`, mirroring the style of the
    `post_types` and `discourse_roles` definition blocks. Each value
    gets a one-line trigger statement.

R2. Cross-reference `discourse_role: advertising-marketing` and
    `post_type: advertising_marketing` to `unsanctioned_flags: ["marketing_spam"]`
    in the prompt. The LLM should emit both signals consistently.

R3. Live run emits at least one `marketing_spam` flag for the same set of
    posts that already get `discourse_role: advertising-marketing`.

R4. `posts_brands_discourse` no longer silently dead-letters
    `uncategorized` rows. Either (a) capture the dead-letter as a
    tripwire row that an operator can review, or (b) reduce the rate to
    zero by tightening the prompt. Decision deferred to U2.

R5. The end-of-run summary surfaces the unsanctioned-flags emission rate
    alongside the existing dead-letter count, so a future operator sees
    "0/N posts flagged as spam" as a tripwire.

R6. The end-of-pipeline `_update_accounts` runs on an open DB. The
    closed-DB crash at `x_monitor/run.py:1366-1370` is fixed.

R7. The post-run evidence report (`scripts/build_u3_evidence_live_run.py`)
    gains a section showing the unsanctioned-flags emission rate per
    post, with the same INSERTED/DROPPED tagging the discourse/nationalism
    sections already use.

# Key Technical Decisions

KTD1. **Prompt-first over programmatic derivation for unsanctioned_flags.**
    The marketing-spam signal crosses two existing axes
    (`post_type = advertising_marketing`, `discourse_role = advertising-marketing`).
    Programmatic derivation would work but it duplicates state and hides
    the LLM's judgment. Adding trigger-condition definitions to the
    prompt is the same fix the post-types and discourse-roles axes
    already use; it keeps the LLM as the single source of truth. We
    accept that LLM-driven emission has measurement noise and add the
    emission-rate tripwire (R5) to bound it.

KTD2. **Conservative on dead-letters (R4): defer the decision to U2.**
    The 12-row dead-letter pile is 33% of the discourse rows in this run.
    Tightening the prompt is the cheap fix but introduces prompt-bloat
    cost on every batch. Capturing them as tripwire rows is operationally
    simpler. U2 will resolve this tradeoff with a real prompt-coverage
    measurement; this plan only scopes the question.

KTD3. **Fold the closed-DB bug into U1 (R6).** The bug is one-line
    (`store.close()` moves to after `_update_accounts`). It belongs in
    the same commit as the prompt change because both unblock future
    classifier-validation runs. Not a separate tracking item.

KTD4. **Tripwire over alert.** The U3 evidence report already surfaces
    discourse and nationalism; adding an unsanctioned-flags emission-rate
    line follows the same pattern. No new dashboard surface.

# High-Level Technical Design

## Unsanctioned-flags prompt section (U1)

`_PRAGMATICS_FULL_SYSTEM_PROMPT` at `x_monitor/attribution.py:1076+`
already enumerates the four valid flag values as a comma-separated
string. The fix replaces that line with a definition block in the same
shape as the `post_types` and `discourse_roles` definitions above it:

```
unsanctioned_flags (per tweet, max one entry unless multiple signals):
  - "marketing_spam": promotional/spam CTA on a brand; usually paired
    with post_type=advertising_marketing AND discourse_role=advertising-marketing
  - "scam": impersonation of an official brand account + asks for
    payment, credentials, or wallet seed
  - "crypto": token ticker / airdrop / wallet claim tied to a brand
  - "unauthorized": brand appears in a third-party post without
    authorization (giveaway, "official AI", fake partner announcement)
  - omit the field when no signal applies
```

The classifier JSON shape stays unchanged (array of strings); only the
prompt text changes.

## Cross-reference rule (R2)

A second block follows the unsanctioned_flags definition:

```
Cross-reference rule: if a tweet has post_type=advertising_marketing
OR discourse_role=advertising-marketing, it MUST also carry
unsanctioned_flags: ["marketing_spam"]. The marketing signal is one
signal; it shows up in three places.
```

This makes the LLM's existing practice (emit `advertising_marketing` in
post_types and discourse) explicitly require the unsanctioned_flags emit.

## End-of-pipeline ordering (U1, fixes R6)

In `x_monitor/run.py:execute()`, move `store.close()` to after
`_update_accounts(store, summary)`. Pattern: wrap the close in a
`finally:` block — `Store` is a context manager per
`x_monitor/store.py:open()`; verify and use `with Store(...) as store:`
where applicable.

## Death-letter disposition (U2)

U2 will resolve (a) capture-as-tripwire vs (b) tighten-prompt. The
decision will be driven by a prompt-coverage measurement on the next
classifier run, not by argument from text.

# Scope Boundaries

### Deferred to Follow-Up Work

- U2 — `posts_brands_discourse` uncategorized dead-letter disposition.
  Question is scoped here; the implementation choice is not.
- Classifier call-site batching visibility (the 12-row dead-letter
  pile hints at per-brand dedup happening inside the batch boundary) —
  tracked separately once U1 emits enable the next measurement.
- LLM-driven classifier cost reduction (3-of-3 retry rules, prompt
  caching for the prefix) — separate from this plan; already partially
  addressed by the batched-classify refactor in plan 2026-07-13-001 U1.
- Brand-yaml negative-keywords (per-brand blocklist for drama,
  celebrity, common-name false positives — e.g. `yi` blocks
  "Cho-Yi", `kimi` blocks given-name contexts) — surfaced by U3
  review #5/#15; tracked separately.
- Parent-company → LLM alias mapping (e.g. `ByteDance` → `doubao`,
  `Tencent`/`WeChat` → `hunyuan`, `Alibaba` → `qwen`) — surfaced
  by U3 review #11; non-trivial schema work, separate plan.

### Out of Scope

- Replacing the LLM classifier with a smaller model. Decision is to
  keep `claude-sonnet-4-6` as the classifier; cost stays in-band.
- Adding a new `posts_spam_signals` table or moving unsanctioned_flags
  out of the `posts_unsanctioned_flags` table. Schema is settled.
- Rewriting the dead-letter JSONL ingestion path. The `data/runs/.../enum_dead_letter.jsonl`
  shape stays.

# Implementation Units

The five units below address the three signal-coverage gaps above plus
the operator-directed dedup. Order is dependency-driven: U1 must land
first (it folds in the closed-DB tail fix and changes the prompt
contract that downstream measurement relies on). U2, U3, and U4 are
independent of each other; U4 (config dedup) is independent of U1's
prompt change. U5 is the open slot.

### U1. Add trigger definitions + cross-reference rule for `unsanctioned_flags`; fix run-tail closed-DB bug

**Goal**: The four `unsanctioned_flags` values get trigger-condition
definitions in the prompt and the LLM emits `marketing_spam` consistently
with `post_type = advertising_marketing` and `discourse_role = advertising-marketing`.
The end-of-pipeline `_update_accounts` runs on an open DB.

**Requirements**: R1, R2, R3, R6.

**Files**:
- `x-monitoring/x_monitor/attribution.py` (modify — replace the
  comma-separated flag list at `_PRAGMATICS_FULL_SYSTEM_PROMPT` with
  the definition block; append the cross-reference rule block below it)
- `x-monitoring/x_monitor/run.py` (modify — move `store.close()` to
  after `_update_accounts(store, summary)` at `execute()`; verify
  `with Store(...) as store:` usage in callers)
- `x-monitoring/tests/test_classify_pragmatics_full.py` (modify — add
  tests pinning the four trigger definitions and the cross-reference
  rule; add a test that pins the post-fetch path applies
  `marketing_spam` when `advertising_marketing` is emitted)
- `x-monitoring/tests/test_run_post_fetch.py` (verify the batching test
  still passes after the `store.close()` move; add a regression test
  that drives the full pipeline to `_update_accounts` and asserts no
  `ProgrammingError`)

**Approach**: (1) Read the prompt at `attribution.py:1076+` and
identify the exact insertion point. (2) Replace the four-flag
comma-list line with the definition block. (3) Insert the
cross-reference rule block after the unsanctioned_flags definition. (4)
Run `x_monitor.attribution.test_classify_pragmatics_full` to verify
the LLM emulator (or fixture) now emits the flag. (5) Move
`store.close()` in `run.py:execute()` to after `_update_accounts`,
keeping the close in a finally-style guard. (6) Re-run the U3 smoketest
to confirm a live run now emits `marketing_spam` flags for the
already-classified posts.

**Patterns to follow**: Mirror the definition-block style used for
`post_types` and `discourse_roles` higher in
`_PRAGMATICS_FULL_SYSTEM_PROMPT`. Use the `with Store(...) as store:`
context manager if `Store` exposes one — check
`x_monitor/store.py:open()`.

**Test scenarios**:
- *Happy path*: Prompt contains trigger definitions for all four
  `unsanctioned_flags` values, with no comma-list fallback. Verify
  via a fixture parse of the prompt constant.
- *Happy path*: Cross-reference rule block is present in the prompt
  and names all three signals (`post_type=advertising_marketing`,
  `discourse_role=advertising-marketing`, `unsanctioned_flags=["marketing_spam"]`).
- *Happy path*: An LLM fixture that emits
  `post_type=advertising_marketing` and
  `discourse_role=advertising-marketing` is now expected to also emit
  `unsanctioned_flags=["marketing_spam"]`. Verify via the existing
  `_parse_classifications` test, augmented.
- *Edge case*: An LLM fixture that emits
  `post_type=genuine_hype` and no discourse marker does NOT emit
  `marketing_spam`. Verify the cross-reference rule is one-way.
- *Error path*: An LLM fixture that emits
  `unsanctioned_flags=["foobar"]` (invalid value) is filtered to `[]`
  by `_parse_unsanctioned_flags`. Verify the existing allow-list still
  works after the prompt rewrite.
- *Integration*: Driving the full `cmd_run` → `_run_post_fetch` →
  `_update_accounts` path on a fixture pipeline emits marketing-spam
  flag and reaches `_update_accounts` without a closed-DB error.

**Verification**: (a) `python -m pytest tests/test_classify_pragmatics_full.py
-v` passes all old + new tests. (b) A live run via
`scripts/live_a_z_populate.py --limit-per-call 5` inserts at least one
`marketing_spam` row in `posts_unsanctioned_flags`. (c)
`tests/test_run_post_fetch.py` and `tests/test_run.py` pass; the closed-DB
crash in `run.py:1366-1370` is gone.

### U2. Resolve `posts_brands_discourse` uncategorized dead-letter disposition (scope only)

**Goal**: Decide whether to (a) capture the dead-letter as a tripwire
row, or (b) tighten the prompt to reduce emission. Implement the
chosen path.

**Requirements**: R4.

**Files**:
- `x-monitoring/x_monitor/attribution.py` (modify if path (b) chosen)
- `x-monitoring/x_monitor/store.py` (modify if path (a) chosen — new
  `upsert_dis_course_dead_letter` method, or similar)
- `x-monitoring/x_monitor/run.py` (modify if path (a) chosen — call
  the tripwire upsert when an uncategorized row is parsed)
- `x-monitoring/tests/test_run_post_fetch.py` (modify — verify the
  chosen behavior on a fixture pipeline)
- `x-monitoring/tests/test_store.py` (modify — verify the chosen
  upsert or prompt-coverage assertion)

**Approach** (deferred until U2 starts): measure dead-letter rate
before the fix (12/36 = 33% in U3 run) and after a prompt tightening
candidate. If the rate drops below 5%, take path (b). Otherwise take
path (a). Document the decision at U2 plan-write.

**Test scenarios**:
- *Happy path*: After the chosen fix, a follow-on live run emits ≤5%
  dead-letter rows in `posts_brands_discourse`.
- *Integration*: If path (a), the tripwire surface (UI or evidence
  report) lists the dead-letter rows so an operator can review.

**Verification**: A second live `scripts/live_a_z_populate.py` run
reports a low dead-letter rate.

### U4. Restore the v1.7 dedup: drop all 6 B/C-duplicated brands from `call_b_groups`

**Goal**: Align the runtime `call_b_groups` shape with the
already-documented "covered exclusively by the C-specs" directive in
`config.yaml:259-262, 271-275, 286-289`. Six brands currently appear in
both B and C, doubling TwitterAPI credit spend on the wide-net path
with no recall gain. This unit drops them from B and adds the operator
override as a runtime guard.

**Requirements**: New — issued 2026-07-13 by the user after reviewing
the B/C dupe analysis in this plan's chat session.

**Files**:
- `x-monitoring/config.yaml` (modify — replace the `call_b_groups`
  block at lines 48-51 with the dedup'd 6/4/4 split; update the prose
  comment at lines 28-44 to match)
- `x-monitoring/x_monitor/config.py` (modify — add an optional
  validator that surfaces the dedup invariant in the warning channel:
  for any brand in `enabled_models` that is also in any `call_c_spec[*].brands`,
  emit a stderr warning at `load_config` time if the brand is also in
  `call_b_groups[*]`)
- `x-monitoring/tests/test_config.py` (modify — pin the dedup'd
  `call_b_groups` shape and assert the validator fires on a config
  that re-introduces a dupe)

**Approach**: (1) Edit `config.yaml`:48-51 to the dedup'd split
(`llama, ernie` out of B1; `moonshot_kimi, mimo, yi` out of B2;
`upstage` out of B3). (2) Add a runtime validator in `config.py` that
walks `enabled_models`, `call_b_groups`, and `call_c_specs[*].brands`,
and emits a `logging.warning(...)` (not an error — operator may
override for A/B comparison) when a dupe is detected. (3) Add a unit
test that re-introduces a dupe in a synthetic config and asserts the
warning fires.

**Patterns to follow**: The validator is a sibling of `_validate_skip_order`
at `config.py:213-221`. Use `logging.warning` so a future JSON-config
loader can suppress or route the message.

**Test scenarios**:
- *Happy path*: After the fix, the live `config.yaml`'s
  `call_b_groups` exactly matches the dedup'd shape (6/4/4 with the
  6 dup brands absent).
- *Happy path*: Calling `load_config("config.yaml")` does NOT emit a
  dupe warning (the live config is clean post-fix).
- *Error path*: Constructing a synthetic config with
  `enabled_models=[llama]`, `call_b_groups=[[llama]]`, and a `C1`
  spec that covers `llama` triggers the dupe warning at
  `load_config` time. Verify via `caplog`.
- *Integration*: A live `x-monitor run` with the dedup'd config
  emits no `attr.bootstrap.brand_options` brand-row duplicates for
  the 6 dropped brands (a `sql posts_brands GROUP BY brand_id` count
  for each dropped brand is identical pre- and post-fix in a single
  live run, proving no recall regression).

**Verification**: (a) `grep -nE 'llama|moonshot_kimi|mimo|yi|ernie|upstage'
x-monitoring/config.yaml` shows the prose references at C1/C2 spec
notes only — no matches in `call_b_groups`. (b)
`python -m pytest tests/test_config.py -v` green. (c) A live
`scripts/live_a_z_populate.py` run inserts the same set of brand-rows
in `posts_brands` for those 6 brands as before (recall preserved via
C1/C2). (d) TwitterAPI credit spend on the wide-net B path drops by
~6 brand-groups worth — visible in the run-summary's
`http.twitterapi_units_consumed` (rough; precise delta depends on
the per-brand token count).

### U5. Additional classifier signal-coverage items (open slot)

**Goal**: TBD — the user will append requirements here as we continue
reviewing the U3 evidence report and the next live run's classifications.

**Requirements**: TBD.

**Files**: TBD.

**Approach**: TBD.

**Test scenarios**: TBD.

**Verification**: TBD.

# Verification Contract

Per-unit gates:
- U1: `python -m pytest tests/test_classify_pragmatics_full.py
  tests/test_run_post_fetch.py tests/test_run.py -v` green; live
  `scripts/live_a_z_populate.py` run inserts at least one
  `marketing_spam` row; build_u3_evidence_live_run.py emits an
  unsanctioned-flags emission-rate line per post.
- U2: TBD at plan-write; consistent with the per-unit field.
- U3: TBD.
- U4: `python -m pytest tests/test_config.py -v` green; live run
  with the dedup'd `call_b_groups` emits no dupe warnings at
  `load_config` time; the 6 dropped brands retain identical
  `posts_brands` recall via C1/C2.
- U5: `python -m pytest tests/test_classify_pragmatics_full.py
  tests/test_store.py -v` green; live run inserts at least one
  `china_nationalism` / `us_nationalism` pair for a post whose
  `discourse_key` was dead-lettered; U3 evidence report's next
  regeneration shows tweets #5/#8/#11/#12 with non-NULL nationalism
  columns even where `posts_brands_discourse` row is missing.
- U6: `python -m pytest tests/test_store.py tests/test_dashboard_v17.py -v`
  green; live run produces identical dashboard brand counts;
  `sqlite3 data/x_monitoring.db ".schema posts_brands"` shows no
  `weight` column.
- U7: `grep -rE 'discours_key' x-monitoring/` returns no matches;
  the new regression test pins the spelling.

Cross-unit gate: the evidence report
`tests/classifier_tests/20260713T040301_0000-bbf72b83-u3-evidence.md`
(or the next run's equivalent) shows INSERTED/DROPPED for every
unsanctioned-flags row, the dead-letter rate is below 5% in the
discourse section, and the run tail reaches completion without a
closed-DB crash.

# Definition of Done

- All U-IDs completed and committed individually on `main`.
- Per-unit verification gates pass.
- Cross-unit gate: a fresh `scripts/live_a_z_populate.py` run
  produces INSERTED ≥1 in `posts_unsanctioned_flags`,
  dead-letter ≤5% in `posts_brands_discourse`, and reaches `_update_accounts`
  cleanly.
- The classifier prompt is portable: any new caller reading
  `_PRAGMATICS_FULL_SYSTEM_PROMPT` sees the unsanctioned-flags
  definitions and the cross-reference rule in the same shape as
  post_types and discourse_roles.
- No Q-strings are reintroduced (memory
  `~/.claude/projects/-Users-fuchitalee-development-minimax-marketing/memory/2026-07-13-q-retirement-status.md`
  pin).

# Sources & Research

- U3 evidence report: `tests/classifier_tests/20260713T040301_0000-bbf72b83-u3-evidence.md`
- U3 live run log: `tests/classifier_tests/2026-07-13T040300Z-live-a-z-populate.log`
- U3 plan (parent): `docs/plans/2026-07-13-001-feat-live-a-z-populate-db-plan.md`
- Classifier prompt under change: `x_monitor/attribution.py:1076+`
  (the `_PRAGMATICS_FULL_SYSTEM_PROMPT` constant)
- Run-tail bug context: `x_monitor/run.py:1366-1370` (closed-DB
  at `_update_accounts`); tracked as task #288
- Brand-keywords gap memory: `~/.claude/projects/-Users-fuchitalee-development-minimax-marketing/memory/brand-keywords-migration-030-gap.md`
- Q-retirement pin memory: `~/.claude/projects/-Users-fuchitalee-development-minimax-marketing/memory/2026-07-13-q-retirement-status.md`

# Open Questions

- Q1. Should `_parse_unsanctioned_flags` continue to silently filter
  invalid values, or raise on first invalid? Current behavior is
  silent — confirms test fixtures stay green but masks prompt drift.
  Decide before U2 if a similar issue surfaces there.
- Q2. Should the tripwire rate (R5) use absolute counts or a percentage
  threshold? Percentage is more stable across run sizes; absolute is
  easier to scan. Decide when the next live run's emission rate is
  measured.
- Q3. Should the unsanctioned-flags emission be enforced on the
  `discourse_role` axis alone, on both axes jointly, or only as a
  cross-reference rule (operator's call)? U1 implements the
  cross-reference rule; tightening to hard enforcement is a follow-up
  if the rate stays high.
- Q4. Should the dead-letter prompt-coverage measurement for U2 also
  measure a separate "discourse-key coverage" rate so we can
  distinguish "LLM emits `uncategorized` deliberately" vs "LLM emits
  a hallucinated key that fails the FK"? The two failure modes need
  different fixes (prompt tightening vs lookup-table extension).

# Additional U-IDs surfaced by the U3 evidence-review pass

The reviewer (Allen) walked every `#### #N` entry in the U3 evidence
report on 2026-07-13 and captured the per-tweet verdicts in
`tests/classifier_tests/20260713T040301_0000-bbf72b83-u3-evidence-review-notes.md`.
The review confirmed the U1 / U2 / U4 framing above and surfaced four
new work items that did not fit any existing unit, plus one new unit
that splits a single classifier step into two. These are listed below
as U5 (the previously-open slot, now filled), U6 (the nationalism split),
and U7 (legacy weight column).

### U5. Run nationalism as an independent classifier step (do not gate on discourse success)

**Context**: Today the classifier runs `discourse_key` and
`china_nationalism` / `us_nationalism` inside the same `_parse_post_classifications`
fan-out. When the LLM emits a `discourse_key` that does not match any
row in the `discourse_keys` lookup table, the FK insert into
`posts_brands_discourse` fails and the entire classification result
for that post — including the otherwise-valid `china_nationalism` /
`us_nationalism` pair — is dead-lettered at
`data/runs/2026-07-13/enum_dead_letter.jsonl`. The brief renderer
already knows how to show `discourse_key = uncategorized` (KTD5
sentinel); it does not need a nationalism value to do so.

In the U3 evidence report, tweets #5, #8, #11, and #12 hit this path —
4 posts × 8 brand edges ≈ 12 dead-lettered rows that have a perfectly
good nationalism label sitting in the LLM response that we throw away.
Fixing this recovers those rows without weakening the KTD5 dead-letter
behavior (which still protects `posts_brands_discourse` from unknown
keys).

**Goal**: The `china_nationalism` / `us_nationalism` pair persists to
`posts_brands_discourse` (where migration 026 placed them; user
decision 2026-07-13 to keep them there) even when the LLM emits an
unknown `discourse_role` that fails the FK gate. The KTD5 dead-letter
behavior for `discourse_role` stays strict — unknown roles still do
not get persisted as `uncategorized` — but the dead-letter path
becomes a partial-row write (discourse_role NULL, nationalism pair
populated) instead of a full-row drop. The user confirmed during
plan execution that nationalism's logical position is on the discourse
row (it shares the LLM's per-post judgment with discourse_role), and
that the bug is the *coupling* of the two fields at the FK gate, not
the *placement* of the columns.

**Requirements**: New — issued 2026-07-13 by the user after the U3
review pass; surfaces a structural coupling between discourse and
nationalism that was latent in v1.6 and inherited by v1.7.

**Files**:
- `x-monitoring/x_monitor/store.py` (modify — `insert_posts_brands_discourse`
  at lines 1816-1855 splits into two paths: when `discourse_role` FK
  is satisfied, the existing full-row UPSERT runs; when `discourse_role`
  FK fails (KTD5 dead-letter), a separate partial-row UPSERT writes
  `(post_id, brand_id, discourse_role=NULL, china_nationalism=?,
  us_nationalism=?)`. The `discourse_role` FK target is `discourse_keys.id`
  per migration 026 — confirm with the live schema. If `discourse_role`
  is NULLable in the FK definition, the partial-row write is the
  same UPSERT with the unknown value replaced by NULL. If it is
  NOT NULL, the migration must relax that constraint first.)
- `x-monitoring/x_monitor/migrations/<next>.sql` (NEW migration —
  only if the existing `posts_brands_discourse.discourse_role` column
  is NOT NULL; the migration drops the NOT NULL constraint before
  the partial-row path can write NULL. Verify by reading migration
  026 schema at lines 130-170.)
- `x-monitoring/x_monitor/attribution.py` (no change required — the
  LLM already emits both `discourse_role` and the nationalism pair
  in the same JSON object per attribution.py:1132-1133; the parser
  at 1391-1392 already extracts both. The fix is purely on the
  store-side persistence path.)
- `x-monitoring/tests/test_classify_pragmatics_full.py` (modify —
  add a fixture where the LLM emits an unknown `discourse_role`
  + valid `china_nationalism=constructive_critical` /
  `us_nationalism=none`; assert the row persists with discourse_role
  NULL and the pair populated)
- `x-monitoring/tests/test_store.py` (modify — assert the partial-row
  write path on a fixture LLM output that triggers KTD5; assert
  the dead-letter JSONL still receives the failed `discourse_role`
  entry for human review)

**Approach**: (1) Read `insert_posts_brands_discourse` at
`store.py:1816-1855` and identify the FK-failure handling. (2) Read
migration 026 schema at `x_monitor/migrations/026_pragmatics_axes.sql:130-170`
to confirm whether `discourse_role` is NOT NULL. (3) If NOT NULL,
add a migration that drops the NOT NULL constraint before the
partial-row path can write NULL. (4) Modify `insert_posts_brands_discourse`
so that when the FK target lookup for `discourse_role` returns no
match, the method writes a partial row with `discourse_role=NULL`
and the nationalism pair populated, while still emitting the
failed `discourse_role` value to the dead-letter JSONL for human
review. (5) Verify with the fixture from the test scenarios below.

**Patterns to follow**: The current KTD5 dead-letter path lives in
`x_monitor/store.py:1759-1773` (note field `uncategorized-sentinel
(KTD5): row skipped, no FK target`). The fix layers a partial-row
write *alongside* the dead-letter emit — the dead-letter file still
captures the unknown `discourse_role` for human review, and the
row still lands in the DB with what we can persist.

**Test scenarios**:
- *Happy path*: An LLM fixture that emits `discourse_role="dunk_yingyang"`
  (a valid FK target) + `china_nationalism="mild_pro"` +
  `us_nationalism="none"` results in a single `posts_brands_discourse`
  row with all three populated (existing behavior, no regression).
- *Partial path*: An LLM fixture that emits
  `discourse_role="some_future_key_not_in_lookup"` (invalid FK) +
  `china_nationalism="mild_pro"` + `us_nationalism="none"` results in
  a `posts_brands_discourse` row with `discourse_role=NULL` +
  `china_nationalism="mild_pro"` (id 2) + `us_nationalism="none"`
  (id 1). The dead-letter JSONL for this run also gets an entry
  naming the failed `discourse_role` value. Verify both writes happen.
- *Error path*: An LLM fixture that emits an invalid
  `china_nationalism` value (not in `nationalism_keys`) gets the
  existing treatment at `store.py:1825-1831` — the entire row is
  still dead-lettered. The partial-row path is only triggered by
  the `discourse_role` FK failure, not by nationalism FK failures
  (those are harder to recover from because both fields would have
  to be NULLable).
- *Integration*: Driving the U3 fixture through
  `_run_classification_for_post` results in `posts_brands_discourse`
  rows for tweets #5/#8/#11/#12 with non-NULL `china_nationalism`
  and `us_nationalism` columns where they were previously NULL
  (because the entire row was dead-lettered).

**Verification**: (a) `python -m pytest tests/test_classify_pragmatics_full.py
tests/test_store.py -v` passes all old + new tests. (b) A live run
via `scripts/live_a_z_populate.py --limit-per-call 5` that triggers
KTD5 inserts partial `posts_brands_discourse` rows for the KTD5
posts. (c) The U3 evidence report's next regeneration shows tweets
#5/#8/#11/#12 with non-NULL `china_nationalism` / `us_nationalism`
columns even where `discourse_role` is NULL.

**Test scenarios**:
- *Happy path*: An LLM fixture that emits `china_nationalism=2`
  (`mild_pro`) and `us_nationalism=1` (`none`) alongside
  `discourse_key="some_future_key_not_in_lookup"` results in
  `posts_brands_nationalism` (or the new columns on
  `posts_brands_signals`) carrying the pair, AND the
  `enum_dead_letter.jsonl` for the same post carrying only the
  `discourse_key` entry. Verify both writes happen.
- *Happy path*: An LLM fixture that emits a valid `discourse_key`
  AND the nationalism pair results in both tables being populated
  (no behavior change for the working case).
- *Edge case*: An LLM fixture that emits only `discourse_key` and
  no nationalism fields results in `posts_brands_nationalism`
  getting a row with both FKs set to `none` (id 1) — the default
  for "the LLM was not asked or chose not to opine."
- *Error path*: An LLM fixture that emits
  `china_nationalism="foo_bar"` (invalid value) is filtered by
  the same allow-list pattern that `_parse_unsanctioned_flags` uses;
  the row persists with `china_nationalism=none` (id 1) and the
  dead-letter file gets a separate entry for the invalid value.
- *Integration*: Driving the full U3 fixture through
  `_run_classification_for_post` results in the same
  `posts_brands` rows as before, with `posts_brands_nationalism`
  (or the new columns) populated for all 12/36 INSERTED posts, and
  0 additional dead-letter entries beyond the existing 12.

**Verification**: (a) `python -m pytest tests/test_classify_pragmatics_full.py
tests/test_store.py -v` passes all old + new tests. (b) A live run
via `scripts/live_a_z_populate.py --limit-per-call 5` inserts at
least one `china_nationalism` / `us_nationalism` pair for a post
whose `posts_brands_discourse` row was dead-lettered. (c) The U3
evidence report's next regeneration shows tweets #5 / #8 / #11 / #12
with non-NULL `china_nationalism` / `us_nationalism` columns even
where the `posts_brands_discourse` row is missing.

### U6. Drop the `posts_brands.weight` 1/N uniform split (legacy read path)

**Context**: `posts_brands.weight` is a `1/N` uniform split across
the N brand edges for a post (e.g. 4 brands → 0.25 each). It is a
legacy read path; the UI rendering layer treats brand presence as
binary. The uniform split only makes sense for fractional attribution
and is a poor fit for the use case the schema actually serves.

**Goal**: Replace `posts_brands.weight` with a `presence` boolean
(or remove the column entirely if the UI layer reads presence from
the row's existence, not from a column value). Pick the option that
matches how the dashboard currently consumes the table.

**Requirements**: New — surfaced by the U3 review (#2 reviewer
question).

**Files**:
- `x-monitoring/x_monitor/store.py` (modify — change the `INSERT
  INTO posts_brands` payload to drop `weight` or replace with
  `presence`; update read methods)
- `x-monitoring/x_monitor/migrations/<next>.sql` (NEW migration —
  drop `posts_brands.weight`, add `posts_brands.presence INTEGER
  NOT NULL DEFAULT 1` if option (b))
- `x-monitoring/x_monitor/dashboard.py` (modify — update any read
  site that referenced `weight` to reference `presence` or the row's
  existence)
- `x-monitoring/tests/test_store.py` (modify — assert the new
  column shape and that legacy `weight` no longer exists)

**Approach**: (1) `grep -nE '\bweight\b' x_monitor/dashboard.py
x_monitor/store.py` to find all read sites. (2) Pick option (a)
"remove column" vs option (b) "replace with `presence` boolean"
based on what the dashboard actually needs. (3) Migration drops
`weight` (and adds `presence` if option b). (4) Update read sites
and tests.

**Open question Q6 (decide at U6 plan-write)**: does the dashboard
ever need the fractional value (e.g. for a stacked-bar chart where
brand share within a post is meaningful)? If yes, replace with
`presence` AND keep a separate `mention_count` column derived from
the post-fetch classifier; if no, just remove.

**Test scenarios**:
- *Happy path*: After the migration, `posts_brands` has no `weight`
  column and the UI render path still works against the new
  `presence` (or row-existence) semantics.
- *Integration*: A live run inserts `posts_brands` rows with the
  new shape and the dashboard renders the same brand counts as
  before.

**Verification**: (a) `python -m pytest tests/test_store.py
tests/test_dashboard_v17.py -v` green. (b) Live run produces the
same brand counts on the dashboard. (c)
`sqlite3 data/x_monitoring.db ".schema posts_brands"` shows no
`weight` column.

### U7. Fix the `discours_key` typo in the U3 evidence report and emit script

**Context**: The U3 evidence report uses `discours_key` (missing
the `e`) in 10 places, all in the "no discourse rows" footnote.
The codebase uses the correct spelling `discourse_key` everywhere.
The typo originated in `scripts/build_u3_evidence_live_run.py`'s
emit function.

**Goal**: Replace `discours_key` with `discourse_key` in the
report and in the script's emit function.

**Files**:
- `x-monitoring/tests/classifier_tests/20260713T040301_0000-bbf72b83-u3-evidence.md`
  (modify — replace all 10 occurrences of `discours_key` with
  `discourse_key`)
- `x-monitoring/scripts/build_u3_evidence_live_run.py` (modify —
  fix the emit function so future regenerations do not regress)
- `x-monitoring/tests/test_evidence_report.py` (NEW — pin that
  the report's text contains `discourse_key` and does NOT contain
  `discours_key`)

**Approach**: trivial single-character fix; one sed pass + a
regression test that pins the spelling.

**Test scenarios**:
- *Happy path*: After the fix, `grep -n 'discours_key'
  tests/classifier_tests/20260713T040301_0000-bbf72b83-u3-evidence.md
  scripts/build_u3_evidence_live_run.py` returns no matches.
- *Regression*: The new test fails on a regression (typo
  re-introduced) and passes after the fix.

**Verification**: `grep -rE 'discours_key' x-monitoring/`
returns no matches.

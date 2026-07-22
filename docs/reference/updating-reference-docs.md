---
name: updating-reference-docs
description: Use when reviewing or updating the 7 files that document x-monitoring runtime behavior (5 in docs/reference/, 1 graphviz source + PNG, plus x-monitoring/README.md). Triggers when a doc claim seems stale, when a code/config/migration change likely drifted the doc, when an operator asks to "refresh the reference docs", or when migrations have shipped without a schema.dot/PNG regen.
---

# Updating x-monitoring Reference Docs

## Overview

Seven files document the x-monitoring runtime: six in `docs/reference/` (twitterapi-io-calls, twitterapi-live-queries-by-model, db-schema, schema.dot + PNG, lookup-tables, classifier-prompts) plus `x-monitoring/README.md` — the operator-facing entrypoint that synthesizes pipeline lifecycle, dashboard routes, deployment, and daily ops. They drift together — every fact in the README cross-references one or more of the 6 reference docs, so a drift in `config.yaml::x_query_specs` will appear in BOTH the README's "Pipeline — RunPipeline" section AND `twitterapi-live-queries-by-model.md` on the same day.

They drift fast — line refs shift as source files grow (apify.py went 618→675 lines between reviews), runtime configs change via plan rollouts, and the schema image is regenerated from `schema.dot` only on explicit trigger. The README drifts especially fast because it carries the **brand list, migration range, dispatch surface (Call A/B/C), LaunchAgent schedule, and dashboard routes** — all of which change together when a plan rolls out.

This skill captures the procedure used 2026-07-16 to do a parallel review pass on all seven. Use it whenever the operator asks to refresh these docs, or when you suspect drift (e.g., after a plan rollout, after a migration batch, after a major rename).

## When to Use

- Operator asks to "update", "refresh", "sync", or "review" the x-monitoring reference docs
- A doc claim contradicts recent code, tests, or `config.yaml`
- After a plan lands that touched any of: migrations, `call_b_groups`, `x_query_specs`, classifier prompt, `attribution.py`, `apify.py`, `run.py`, `brand_keywords`, `_VALID_*` frozensets
- Periodic hygiene pass (recommended: every 4–6 weeks; this repo's refactor cadence is high)

**Not for:** Updating `home-pages-ui-guide.md`, `lang-detected-explained.md`, `polarity-calculation-explained.md`, or `translator-output.md` — those are conceptual/UI docs, not runtime-inventory docs.

## The 7 Files

| File | What it covers | Source-of-truth files |
|---|---|---|
| `twitterapi-io-calls.md` | TwitterAPI.io endpoint inventory, credit costs, call sites, retry/backoff, budget guard | `x-monitoring/x_monitor/apify.py`, `x_monitor/run.py`, `x_monitor/query_plan.py`, `tests/test_budget_guard.py` |
| `twitterapi-live-queries-by-model.md` | The 6-call cycle (A + B1/B2/B3 + C1/C2), per-brand token lists, sinceTime/cursor handling, LaunchAgent | `x-monitoring/config.yaml`, `x_monitor/query_plan.py`, `x_monitor/queries.py`, `deploy/*.plist` |
| `db-schema.md` | Every table, column, type, FK, index as `.md` prose; references the generated PNG | `x-monitoring/x_monitor/migrations/*.sql` (migrations are immutable source of truth), live `.schema` dump, `docs/reference/schema.dot` |
| **`schema.dot`** | **Graphviz source for `xmonitor-schema-post-batch.png`. MUST run BEFORE `db-schema.md` review and before the PNG regen** | Live `.schema` dump + `x-monitoring/x_monitor/migrations/*.sql` |
| `lookup-tables.md` | `*_keys` SQL tables, `_VALID_*` frozensets, brand/company/category registry, call-group coverage | `x_monitor/attribution.py`, `x_monitor/config.py`, `x-monitoring/config.yaml`, live DB queries |
| `classifier-prompts.md` | Literal system prompt text, JSON output shape, taxonomy legends, model routing | `x_monitor/attribution.py` (prompt body is the module-level constant `_PRAGMATICS_FULL_SYSTEM_PROMPT`) |
| **`x-monitoring/README.md`** | **Operator entrypoint: pipeline lifecycle (RunPipeline 8 steps), dashboard routes, 2 launchd agents, setup, daily ops, troubleshooting, retired-paths section. Also cross-references the 6 docs above.** | Same as the 6 reference docs (this doc synthesizes — it does NOT add new source-of-truth files) |

**Ordering constraints:**
- `schema.dot` MUST be reviewed (and the PNG regenerated) **before** `db-schema.md`. The `.md` embeds the regenerated PNG, and its image caption must match the dot's regen stamp.
- **`README.md` MUST be reviewed AFTER the 6 reference docs.** The README's "Where to look next" section is a curated index that should reflect whatever file paths the other docs ended up with, and its "Pipeline lifecycle" prose must match whatever the most recent doc-review pass settled on for call count, brand count, schedule, etc. The README agent should READ the other 6 docs first to align its summary.
- The other 5 docs (`twitterapi-io-calls.md`, `twitterapi-live-queries-by-model.md`, `lookup-tables.md`, `classifier-prompts.md`, plus README) are independent of schema.dot and may run in parallel once Stage A finishes.

## Procedure

### Step 1: Pre-flight

```bash
# Confirm clean-ish working tree
git status --short
# Confirm branch (should be main; user pushes fixes to main intentionally)
git rev-parse --abbrev-ref HEAD
# Note the current HEAD SHA — cite it in doc footers
git rev-parse --short HEAD
# Get current JST timestamp for the "Last updated:" line under H1
TZ='Asia/Tokyo' date '+%Y-%m-%d-%H:%M:%S'
```

The skill is applied against the canonical main branch (see [[branch-canonical-source]]).

### Step 2: Stage A — review `schema.dot` (single agent, must finish first)

Dispatch **one** subagent on `docs/reference/schema.dot` BEFORE any other agent. This subagent:

- Edits only `schema.dot` (NOT the `.md`, NOT the PNG)
- Compares every node/edge in the dot against the live `sqlite_master` schema
- Adds migrations `024-038` worth of structure (currently missing)
- Fixes the `brands_accounts:"author_id" -> accounts:"id"` edge (should be `accounts_id`, per migration 031)
- Adds a "Last regenerated: post-migration-038" stamp to the dot's frontmatter so drift is visible
- Does NOT run `scripts/build_schema_image.sh` — that happens in Stage B

**Then run `scripts/build_schema_image.sh` from the repo root yourself** (the main session, not a subagent) so the PNG is regenerated against the now-updated dot. Confirm the script exits 0 and that `docs/reference/images/xmonitor-schema-post-batch.png` was rewritten.

### Step 3: Stage B — dispatch 5 subagents in parallel

**One subagent per remaining file** (`db-schema.md`, `twitterapi-io-calls.md`, `twitterapi-live-queries-by-model.md`, `lookup-tables.md`, `classifier-prompts.md`). Each gets the same boilerplate prompt with the target file name swapped and the relevant source-of-truth files listed. Each is constrained to:

- Edit only the target doc
- Not modify code, tests, migrations, data files, or yaml
- Verify every claim against code/yaml/DB before editing
- Flag unverifiable claims rather than fabricate
- Preserve existing structure and style where possible
- Add a "Last reviewed: <date>" footer listing the substantive corrections
- Return a summary in three sections: (a) what changed, (b) what couldn't be verified / left flagged, (c) drift noticed but not fixed (and why)

**Special note for the `db-schema.md` agent:** the PNG was regenerated in Stage B preamble (Step 2). The agent should update the image caption to match the dot's "Last regenerated" stamp (e.g., `![x-monitor schema after migration batch 011-038]`). The agent should NOT regenerate the PNG itself.

Use the `superpowers:dispatching-parallel-agents` skill for the dispatch template. The 5 Stage B subagents are independent — no shared state, no cross-file coordination needed.

### Step 3.5: Stage C — dispatch 1 subagent on `x-monitoring/README.md`

**The README subagent must run AFTER the 6 reference docs are committed** (or at least after Stage B finishes), because the README's "Where to look next" section and its pipeline-lifecycle prose must align with whatever the other docs settled on. This subagent:

- Reads `x-monitoring/README.md` in full
- Reads ALL 6 reference docs to check that cross-references resolve (paths, table names, taxonomy values)
- Verifies the brand list against `x-monitoring/config.yaml::enabled_models`
- Verifies the dispatch surface (Call A / B1 / B2 / B3 / C1 / C2) against `x-monitoring/config.yaml::call_b_groups` + `x_query_specs`
- Verifies the LaunchAgent schedule against `deploy/*.plist`
- Verifies the migration range against `x-monitoring/x_monitor/migrations/*.sql` (currently 001-038)
- Updates the "Retired / removed" section to reflect any newly-retired paths (the 2026-07-11 yaml retirement was the most recent example)
- Adds a "Last updated: <timestamp>" line under H1 AND a "Last reviewed: <date>" footer (same convention as the 6 reference docs)
- Returns the same three-section summary as the other agents

The README agent is **constrained to `x-monitoring/README.md` only** — does not touch `docs/reference/`, does not touch code, does not touch deploy scripts even if the schedule claim drifts.

### Step 4: Add the timestamp header

After all 6 subagents finish (5 Stage B + 1 Stage C), edit each `.md` file to insert a line directly under the H1 title:

```
Last updated: 2026-07-16-14:21:40
```

This applies to all 6 `.md` files (the 5 reference docs + `x-monitoring/README.md`). Use the timestamp from step 1. The JST date format matches the user's `YYYY-MM-DD-HHMMSS-description` file-naming rule (see CLAUDE.md / Global Rules). `schema.dot` does NOT get a `Last updated:` line under H1 — it's not a markdown file; instead it has the "Last regenerated: post-migration-XXX" stamp in its dot frontmatter (added in Stage A).

### Step 5: Surface cross-cutting drift

Each agent's "(c) drift noticed but not fixed" section is project-level signal. Read all seven summaries (1 dot agent + 5 doc agents + 1 README agent), then surface a consolidated drift list to the operator. Common categories seen in 2026-07-16 review:

- **Tests failing by plan-design** — e.g., `tests/test_cli.py:124 test_bootstrap_followers_subcommand_registered` after plan 2026-07-11-002 U4 retired the subparser. Flag in the doc footer, don't fix.
- **Cross-prompt prompt artifacts** — e.g., the `lang_detected` rule in the classifier prompt that only the translator emits. Flag with a callout; don't silently rewrite the literal prompt text.
- **Snapshot-vs-runtime for placeholder brands** — some brands (mistral, stepfun, hunyuan, llama, yi, upstage) had no DB row at review time. Don't over-claim "no official handles" — operator intent in `brands_accounts` is source of truth; absence of DB row may already be stale.
- **README drift** — the README's "Retired / removed" section often misses recently-retired paths. The 2026-07-11 yaml retirement (data/queries/, data/accounts/) is captured in the README but earlier retirements (e.g., staging.db on 2026-07-07) rely on operator memory. Surface any newly-retired path the README doesn't mention.

### Step 6: Operator handoff

Present the consolidated drift list to the operator as a follow-up plan candidate, NOT silently. Per [[no-silent-scope-narrowing]], deferrals must surface as questions.

## Source-of-Truth Map (don't re-derive)

| Claim kind | Where to look |
|---|---|
| Endpoint paths, headers, retry loop | `x_monitor/apify.py::TwitterApiClient._get` |
| Credit costs | `x_monitor/run.py::_CREDITS_PER_ADVANCED_SEARCH_PAGE` (live budget guard is canonical; plan estimates are not) |
| Calls/cycle count | `x-monitoring/config.yaml::call_b_groups` + `x_query_specs` (NOT plan docs) |
| sinceTime / cursor behavior | `x_monitor/queries.py`; cross-check commits `a46020f` + `dcf0a8c` (URL-side `sinceTime` is dropped on `advanced_search`) |
| Enabled brands (count + slugs) | `x-monitoring/config.yaml::enabled_models` (currently 20) |
| Table/column truth | `x-monitoring/x_monitor/migrations/*.sql` (migrations are immutable) |
| Schema diagram | `docs/reference/schema.dot` (edited by Stage A agent) + `scripts/build_schema_image.sh` (run by main session in Stage B preamble) |
| Classifier prompt body | `x_monitor/attribution.py::_PRAGMATICS_FULL_SYSTEM_PROMPT` (module-level constant, NOT inline in `build_pragmatics_full_prompt`) |
| `_VALID_*` frozensets | `x_monitor/attribution.py` |
| LaunchAgent schedule | `deploy/*.plist` (2 agents: harvest = `StartCalendarInterval` minute 0/15/30/45; config-reload = `WatchPaths` + `ThrottleInterval=300s`) |
| Pipeline lifecycle (8 steps in README §"The pipeline") | `x_monitor/run.py::RunPipeline.run`, `x_monitor/config.py::load_config`, `x_monitor/query_plan.py`, `x_monitor/apify.py::TwitterApiClient.advanced_search`, `x_monitor/relevance.py`, `x_monitor/attribution.py`, `x_monitor/translator.py::classify_pragmatics_full`, `x_monitor/store.py` |
| Dashboard routes (README §"The dashboard") | `x_monitor/dashboard.py::DashboardApp`, `x_monitor/_home_routes.py`, `x_monitor/templates/*.j2` |
| Daily ops commands | `x_monitor/__main__.py` (CLI surface — no cli/ subpackage) |
| Retired paths (README §"Retired / removed") | git log + operator memory; cross-check against migration history in `x-monitoring/x_monitor/migrations/*.sql` and plan docs in `docs/plans/` |

## Common Mistakes

| Mistake | Fix |
|---|---|
| Trusting plan-doc estimates (e.g., 15 credits/page) | Verify against live budget guard constants in code |
| Re-deriving source-of-truth file paths from memory | `git show origin/main:<path>` first, per [[branch-canonical-source]] |
| **Dispatching all 7 agents in parallel without staging** | `schema.dot` MUST finish and the PNG MUST regenerate before the `db-schema.md` agent runs; the README agent MUST run AFTER the 6 reference docs are committed (or at least after Stage B finishes). Use Stage A → PNG regen → Stage B → Stage C |
| Editing `schema.dot` to match the `.md` (instead of vice versa) | The `.dot` is the diagram source of truth; the `.md` reflects it. Edit `.dot` first, regen PNG, then update `.md` caption to match |
| Having the Stage A subagent run `scripts/build_schema_image.sh` itself | The regen must happen in the main session (Stage B preamble) so the PNG commit is co-authored by the orchestrator, not buried in a subagent's transcript |
| Treating subagent output as final without verifying | Run `git diff docs/reference/` and spot-check 2–3 substantive claims per file against code |
| Inventing display names, ZH names, accent colors for brands | These are NOT columns in the current `brands`/`companies` schema; flag as informational only |
| Using `find/replace` for renames that collide (e.g., `author_id` vs `accounts_id`) | Use surgical edits — `author_id` has 2 distinct contexts in this repo |
| Omitting the "(c) drift noticed but not fixed" section | That's the project-level signal operators need; agents should not self-censor |
| Adding `Last reviewed:` without a `Last updated:` header (for `.md` files) | Both required; `Last updated` is the timestamp line, `Last reviewed` is the footer |
| Adding a `Last updated:` line to `schema.dot` | It's not markdown; instead add a "Last regenerated: post-mig-XXX" stamp in the dot's frontmatter |
| Letting the README agent invent facts the 6 docs don't support | The README synthesizes — every claim in the README should map to a claim already verified in one of the 6 reference docs. If the README agent wants to add something new (e.g., a new troubleshooting entry), it must verify against code first |
| Letting the README agent edit deploy/*.plist | The README references the LaunchAgent schedule but should never edit the plist. If the schedule drifted, flag as follow-up — don't rewrite the plist from the doc |

## Verification Before Completion

After all 7 subagents return, the PNG has been regenerated, and you've added the timestamp headers:

1. `git diff --stat docs/reference/ x-monitoring/README.md` — confirm 7 files modified (6 `.md` + 1 `.dot`) plus 1 PNG (`images/xmonitor-schema-post-batch.png`); no other files
2. Spot-check 2–3 substantive claims per file (open the source-of-truth file, grep for the claimed constant)
3. Verify each `.md` now has BOTH a `Last updated: <timestamp>` line under H1 AND a `Last reviewed: 2026-07-16` footer
4. Verify `schema.dot` has a "Last regenerated: post-migration-XXX" stamp and the PNG caption in `db-schema.md` matches that stamp
5. **Verify the README's "Where to look next" section points to docs that actually exist with matching headers** (e.g., `docs/reference/db-schema.md` must have the H1 `# x-monitoring DB schema` after the agent is done, not some stale title)
6. Read all 7 "(c) drift noticed but not fixed" sections (1 from dot agent + 5 from doc agents + 1 from README agent); present consolidated list to operator
7. Run `git status` — confirm no unintended files modified (code/tests/migrations must be clean)

## Real-World Impact

The 2026-07-16 review pass took ~6 minutes wall-clock with 5 parallel doc subagents + 1 staged dot subagent. The biggest substantive drifts caught:

- `twitterapi-io-calls.md` credit cost was **15 → 300 credits/page** (10× off — would have misled cost projections)
- `twitterapi-live-queries-by-model.md` claimed **5 calls/cycle** when live code emits **6** (added Call C2)
- `lookup-tables.md` §6 brand `id` column was **completely stale** (sequential 1–20 vs. live `minimax`=7, `deepseek`=2, etc.)
- `db-schema.md` missed 2 entire tables (`call_state`, `_applied_config_snapshot`) and a `discourse_key` NULL-vs-NOT-NULL flip
- `classifier-prompts.md` JSON shape was **wrong** (flat `{"classifications": ...}` vs. actual `{"results": [...]}` wrapper)
- `schema.dot` was **15 migrations stale** (pinned at post-023, live DB at v38); would have been caught if the new Stage A pass had been run in this session

The 2026-07-17 README addition (this update) wasn't part of the original pass but would have caught: README brand list was already in sync (it was the source for `twitterapi-live-queries-by-model.md`'s brand enumeration), but the README's "Retired / removed" section was missing `tests/test_cli.py:124` failing-by-design status.

Catching these before a stakeholder read the docs saved a round of "the docs say X but the code does Y" rework.

## Known Gaps (verified 2026-07-16 by baseline-vs-with-skill test)

These are real gaps the skill did not initially cover; future agents should be aware:

1. **Schema diagram has two sources of truth with different freshness.** The doc intro says the PNG is "generated via `sqlite3 .schema`" but it actually comes from `docs/reference/schema.dot`. As of 2026-07-16 the dot is pinned at post-migration-023 while the live DB is at v38. **Status (2026-07-16 update):** added `schema.dot` as the 6th file in this skill with explicit Stage A/B staging; the dot gets a "Last regenerated: post-mig-XXX" stamp and is regenerated by the Stage A agent.

2. **PNG regen rule silently violated 15 times.** CLAUDE.md says dot/PNG must be regenerated whenever any `migrations/*.sql` changes. In practice, migrations 024–038 all shipped without a regen. **Status (2026-07-16 update):** this skill now treats the dot regen as part of the doc-review procedure (Stage A + PNG regen in main session). The 15-migration drift is now closed during the next review pass. The repo-level CI guard (`scripts/diff_schema_dot_against_live.sh`) remains a follow-up.

3. **`Last updated:` line collides under concurrent dispatch.** When 5 agents write in parallel, they all want to update the same line. The with-skill test showed the second-arriving agent had to bump `14:21:40 → 15:00:00` — fine, but operators reading the line should know it's a "last-updated-as-of-this-pass" timestamp, not a per-edit timestamp. **Fix:** keep the line semantic as "review-pass wall-clock", not per-edit. (The Stage A dot agent doesn't touch any `.md` files, so it doesn't contribute to this race.)

4. **The PNG filename `xmonitor-schema-post-batch.png` is stale.** It was named for batch 011-023 in mid-2026. **Status (2026-07-16 update):** renamed during the Stage B regen — the new PNG filename should match the migration window (e.g., `xmonitor-schema-post-mig-038.png`). Still flagged as a follow-up if the rename didn't happen automatically.

5. **Subagents can race on shared review notes.** A sibling agent's pre-edited reviewer-note blockquote nearly got trusted blindly (caught by the with-skill agent's verification step). **Fix:** always re-verify every claim against code/DB before editing, even if the doc already contains a "Last reviewed" block.

## Verification Test Result (2026-07-16)

A baseline subagent (no skill) and a with-skill subagent were dispatched on `db-schema.md` in parallel. Both produced equivalent substantive updates (all 6 corrections, no PNG regen, no schema.dot edits). Differences were procedural:

- Baseline did **not** do pre-flight checks (no HEAD SHA, no JST timestamp captured up front)
- Baseline **re-derived** the source-of-truth files from memory; with-skill skipped that
- Baseline agent **nearly trusted** a sibling agent's pre-edited reviewer blockquote (caught by its own diligence, not by the skill's prompt)
- With-skill agent's report had **stronger structure** (explicit "did the skill help" self-assessment, explicit procedural friction list)

**Verdict:** the skill is useful for procedural discipline but does not raise the floor on substantive correctness — both agents caught the same drift. Its value is reducing re-discovery cost and making the output report consistent across operators.
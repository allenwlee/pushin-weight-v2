---
artifact_contract: "ce-handoff/v1"
created_at: "2026-09-21T10:07:53Z"
title: "Combined rare-type extra-search — Codex handoff"
summary: "Brainstorm-settled extra-search for personnel/jobs/events/opps/model-releases; harvest-shaped one-call query; live ON_DEMAND trial; extra search still off in run_cycle; no commit."
keywords: ["rare-type", "extra-search", "twitterapi", "personnel", "harvest", "jev", "codex"]
cwd: "/Users/fuchitalee/development/pushin-weight-v2"
resume_focus: "Continue the combined rare-type extra-search work from the implementation-ready plan and live trial evidence; do not enable extra search on run_cycle until the owner says so."
repository: "pushin-weight-v2"
repo_root_sha: "aff2eb3769a99795697f11c9cadeae825672b5d9"
branch: "main"
head: "c831d1cba4f410593006d6b8f3ed35af9a4bbcad"
worktree_path: "/Users/fuchitalee/development/pushin-weight-v2"
---

# Combined rare-type extra-search — Codex handoff

> Historical handoff, preserved as received. For current authority and progress, use the same [implementation plan](../plans/2026-09-21-081940-feat-combined-rare-type-extra-search-plan.md) and [2026-09-22 quality-stop assessment](../analysis/harvester/2026-09-22-095250-rare-type-quality-stop.md). The owner subsequently selected staging, approved this checkout, and expanded the plan to U1–U14. Local implementation commits now exist, but delivery is blocked by failed quality evidence. The branch, commit, authorization, and trial-count claims below describe the earlier session, not current state.

Writer: Grok session on fuchitalee. Owner (Allen) is running out of tokens and asked to hand this to Codex. Owner-attributed lines are marked **owner**. Writer inferences are marked **writer**.

## Objective

**Owner:** Catch rare high-value X posts the brand crawler misses (personnel, jobs, events, opportunities, new-model names) and surface them within about 15 minutes. Combine those into **one** TwitterAPI.io `advanced_search` per harvest cycle. Keep extra search **off** in production until a trial says the query is tight enough.

## Authoritative plan

Read first: `docs/plans/2026-09-21-081940-feat-combined-rare-type-extra-search-plan.md`

What matters there:

- Product Contract (R1–R25) and Key Decisions (owner-settled).
- Planning Contract KTD1–KTD6: this slice is the **on-demand trial**, not live extra-search on `run_cycle`.
- Appendix exhibit: harvest-shaped one-call query (planner string + post-injection example). Counted **419 / 463 of 512**.
- Later/out: HuggingFace poller; Jev **promotion** of untracked names to tracked brands; unused `jobs-discovery-v1` / `personnel-discovery-v1` packs as written.

Do not invent a second plan file. Enrich this one. Ollija `delivery_target: on-request`, `delivery_selected_by_user: false` — **do not commit, push, or deploy** unless the owner selects a delivery target.

## Owner-settled decisions (carry these, do not re-litigate)

These are **owner** words from the brainstorm, not writer guesses:

- Personnel extra searches rewritten; do **not** turn on the unused jobs/personnel config packs.
- Org ring: **all AI-related companies**, with mill job posts dropped as junk (data-entry/temp/low-wage mills), **not** a nationality rule.
- Search languages: **EN, ZH-CN, and JA** as originally planned (owner struck a company-home-language-only split).
- Combine personnel + jobs + events + opportunities + model-upgrade/release posts so rare personnel/jobs can surface in **15 minutes**.
- **One** TwitterAPI extra call, under 512 characters including `min_faves:0 since_time until_time`.
- New-model names/nicknames (example: StepFun “step 5 preview”) belong on that extra call because B/C miss tokens that are not current brand keywords. Call A still owns official tracked-account posts.
- HuggingFace activity crawler is a **later to-do**, not this plan (top-gun collector, different repo/object).
- Untracked company names: YAML-shaped stopgap, **persisted on the server** (Postgres; Render disk is ephemeral). Each spelling/handle/nickname is its **own token**; no auto-merge. **Jev promotion to tracked brands is later/out.**
- Overlap with A/B/C: **query-time**, not post-insert. You pay for every returned tweet. Do not extra-search every B1 bare-brand mention. Catalog `@handle` joins without the brand word are a miss.
- Grok X search is research-only. Production harvest stays TwitterAPI.io.
- Jev may **gate/route** extra-search hits (Decisions API, one post per state, not chat-completions, not a 0731 replacement). Jev must **not** write production classification until extra search is allowed on.

## Work completed (local, uncommitted)

On branch `main`, **behind origin/main by 3**. None of this is committed (Ollija on-request). Do not mix in unrelated dirty files (`README.md`, classifier-prompts, db-schema, headline docs, twitterapi reference docs).

**This work’s files (untracked unless noted):**

- `docs/plans/2026-09-21-081940-feat-combined-rare-type-extra-search-plan.md` — requirements + implementation units U1–U4.
- `x_monitor/rare_type_extra_search.py` — harvest-shaped planner string + `render_rare_type_extra_search_query` via `TwitterApiClient._effective_search_query`.
- `monitor/management/commands/trial_rare_type_extra_search.py` — ON_DEMAND only; `run_search(query_string, since_time=, until_time=)` like `CycleRunner._fetch_tweets`; no post inserts.
- `tests/test_rare_type_extra_search_query.py`, `tests/test_trial_rare_type_extra_search.py`.
- `tests/test_discovery_lanes.py` (modified) — extra search still not a harvest call.
- `CONCEPTS.md` (modified) — Personnel extra search, bio-diff observation, mill job posting.
- `docs/analysis/harvester/2026-09-21-185032-rare-type-extra-search-trial.md` — live trial write-up.

**Do not commit** `.pytest-tmp/` or anything that prints credentials.

## Harvest call shape (load-bearing; writer, verified in code)

Guide: `x_monitor/query_plan.py` `_build_query` (outer wrap when multiple groups) and `monitor/cycle.py` `_fetch_tweets` (~2649–2712).

Shape:

```text
((group) OR (group) OR …) min_faves:0
```

Then `api.run_search(query_string, since_time=…, until_time=…)`. Time operators are **kwargs**, not baked into the planner string. CycleRunner length-checks `f"{query_string} since_time:{since} until_time:{until}"` against 512 **before** the call.

X AND binds tighter than OR. Without the outer parens, `since_time` only applied to the last clause. First live trial filled a 20-tweet mill page from hours back (Forex `booth`, football `Step 5`).

## Live TwitterAPI evidence (writer, 2026-09-21)

Credential: `TWITTERAPI_IO_ON_DEMAND_API_KEY` from Render env group `pushinweight-secrets`. Never print it. Never use `TWITTERAPI_IO_SCHEDULED_API_KEY` or legacy `TWITTERAPI_IO_API_KEY`.

Command: `python manage.py trial_rare_type_extra_search --window 15m --max-pages 1 --json`

| Run | Result |
|---|---|
| First (no outer wrap; unquoted `booth` + bare `step-5`) | 20 tweets, ~300 credits, mill page, one Step-5 Preview keeper |
| After harvest-shaped wrap + tighter groups | **4 tweets** in ~09:52–10:00 UTC, query_length **463**, three Step-5 Preview mentions |

JSON from the harvest-shaped 15m run is machine-local: `/tmp/pw-rare-trial/15m-harvest-shape.json` (tweet texts only, no keys). May not exist on Codex’s machine.

## Staging DB (writer)

Laptop cannot `render psql` staging: `pushinweight-staging-db` IP allowlist is empty (`IP address not in allow list`).

One-off job on `pushinweight-staging-web` (`job-daofvt2d0e5s7384f8ig`): `posts` exists, **241,924** rows; **0 of 20** first-trial tweet ids already stored. The trial **command is not deployed** to staging; only overlap SQL ran there.

## Tests run

```text
.venv/bin/python -m pytest tests/test_rare_type_extra_search_query.py tests/test_trial_rare_type_extra_search.py
```

6 passed. `test_discovery_lanes.py::test_checked_in_discovery_lanes_are_disabled_and_plan_zero_calls` skipped here without `DATABASE_URL` postgres.

## Failed / do-not-retry paths

- Do not enable `discovery.jobs` / `discovery.personnel` in `config.yaml`.
- Do not OR mill language (`jobs OR careers OR opening OR apply`, unquoted `booth`, bare `step-5`) into the extra call.
- Do not call Jev as chat-completions; Decisions API only; one post per `state`.
- Do not pack many posts into one Jev state.
- Do not fall back to `TWITTERAPI_IO_API_KEY`.
- Do not put a YAML registry only on the Render container disk.
- Do not fold the top-gun HuggingFace collector into this harvest call.
- Do not treat bio fetch time as employment start (R10 / Stage 1 R37/R39).
- Do not `run_cycle --scheduled` as part of this trial.
- Do not pause/resume production harvest cron.

## Suggested next steps (not authorized until the owner confirms)

One path, in order:

1. Read the plan Appendix exhibit and `x_monitor/rare_type_extra_search.py`.
2. Re-run `trial_rare_type_extra_search --window 15m` and `--window 7d` if another yield sample is needed; score keepers vs junk.
3. Only if the owner asks: tighten phrases further, then consider wiring a **disabled** extra PlannedCall through `plan_calls_for_cycle` (still `enabled: false` until they say enable).
4. Untracked-name YAML stopgap (R23–R25) is not started in code.
5. Shipping (commit/PR) needs owner to set Ollija `delivery_target` and `delivery_selected_by_user: true`.

## Skills that apply

- `change-harvester` + `avoiding-recurring-mistakes` (M7, M8, M17, M18) before any harvest-path edit.
- TwitterAPI purpose: `x_monitor/twitterapi_credentials.py`.
- Ollija: `ollija annotate-plan` on the existing plan path before Git mutation.

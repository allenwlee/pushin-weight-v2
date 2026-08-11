---
name: avoiding-recurring-mistakes
description: Use when working in the pushin-weight-v2 (x-monitor) Django/Render repo on fuchitalee. Activates whenever you are about to make a code change, run a migration, modify harvest/cycle code, touch the prod DB, design URLs/endpoints, commit to main, or write/regenerate reference docs. Triggers on phrases like "harvest", "cycle", "backfiller", "prod db", "render", "i18n", "psql", "classifier", "posts_raw", "worktree", "merge", "deploy", "seed", "halt", "pause", "stop the cron", "fetched vs inserted", "credits too high", "discrepancy". Built from a longitudinal analysis of 257 real user prompts across 12 sessions (Jul 2026), with amendments on 2026-08-05 (cursor vs insert gap, pause-resume protocol).
latest_update: 2026-08-10
---

# Avoiding Recurring Mistakes — pushin-weight-v2 (x-monitor)

A correction log distilled from real friction. Each section is named after the mistake pattern, shows a representative correction prompt, and gives a concrete "do this" rule. Apply these rules whenever the trigger condition is met, **before** you start editing code.

If a rule conflicts with `AGENTS.md` / `CLAUDE.md` / `CONCEPTS.md`, follow those repo docs first — this skill is the *recurring-friction* layer on top. Future sessions: Integrate durable corrections into the applicable M-rule and Quick reference, retaining only concise current guidance.

## When this skill triggers

Any work in this repo. Especially:
- harvest / cycle / backfiller / classifier code changes — also load `.claude/skills/change-harvester/SKILL.md` before editing those surfaces
- Django migrations (`core/migrations/`), schema edits (`core/models.py`)
- prod DB queries via Render CLI
- i18n catalog / locale strings
- URL / endpoint shape design
- Reference doc rewrites (`docs/reference/`)
- Branch / worktree / merge / commit decisions on `main` or feature branches
- Reference to "v1", "Flask", "launchd", "SQLite"

---

## M1 — Don't drift from canonical decisions

**Pattern the user kept correcting.** Things already settled in `AGENTS.md`, `CLAUDE.md`, or `CONCEPTS.md` are re-derived by the agent every few sessions.

**Representative correction.**
> "no. we need a whole new plan to use more idiomatic url, even if that means changing code."
> "we are using deepseek for the classifier" (after agent assumed default LLM).
> "i believe we're on pg 16, but render is on pg 18, confirm" — agent had assumed wrong PG version.

**Rule.** Before touching the code, re-read the canonical decisions in `AGENTS.md` and `CONCEPTS.md`. Specifically:

| Decision | Where it's settled |
|---|---|
| v1 (Flask + launchd + SQLite) is **retired** — do not write to `data/x_monitoring.db` | `AGENTS.md` |
| Production stack = v2 Django on Render (`xmonitor-*` services) | `AGENTS.md` |
| Schema source of truth = `core/models.py` → `core/migrations/` | `AGENTS.md` |
| LLM classifier = **deepseek**, NOT the default LLM | session memory + AGENTS memory index |
| `created_at` raw vs derived must be disambiguated (e.g., `created_at_raw`) | session `d565ea9f` 2026-07-27 |
| PG major version on Render differs from local; verify before assuming | `AGENTS.md` |
| `docs/reference/images/xmonitor-schema-post-batch.png` is **retired** | `AGENTS.md` |

If you find yourself writing something that contradicts these, stop and read the rule again. Don't re-argue a settled decision.

---

## M2 — Don't over-reach. Do only what's asked.

**Pattern the user kept correcting.** The assistant offers "while I'm at it" / "let me also commit/push/merge" actions that the user did not request. The user then has to say "no, just X" or "go back to Y".

**Representative correction.**
> "no get back to our original prompt re raw json" (after agent proposed an extra unit).
> "let me also commit all our fixes and push to Render" — agent volunteered commit/push without being asked.
> "actually before you execute, take a look at feat/posts-raw-denormalize, should we merge these to main first?" — agent was about to merge without checking parallel work.

**Rule.** End each assistant turn with the literal answer to the literal question. If you see yourself writing "I'll also…" / "While I'm at it…" / "Want me to also…" — STOP. The user will tell you when to do the next thing. Phrases to never volunteer: commit, push, merge, deploy, run migration on prod, seed prod, drop a column.

**Exception.** If a step is required to make the requested step work (e.g., "to run this query I need to psql in first"), state the prerequisite plainly as part of the same answer, not as an extra task.

---

## M3 — Repeat the user's scope back when ambiguous

**Pattern the user kept correcting.** Agent expanded scope without confirming. Agent then shipped extra features that had to be reverted, or skipped what was actually asked.

**Representative correction.**
> "we don't need that."
> "just X."
> "no. we need a whole new plan to use more idiomatic url, even if that means changing code. what are your recs" (re-prompting because agent's plan was off-target).

**Rule.** If the prompt has any of: "only", "just", "restrict to", "don't change", "scope is X" — repeat the literal keep/revert list back to the user **before** acting. From the repo memory index: `feedback_repeat_back_scope_before_acting.md`, `feedback_scoped_revert_specificity.md`.

Format to repeat back:

```
I will:
  - KEEP/TOUCH: <files, columns, behaviors>
  - REVERT/AVOID: <files, columns, behaviors>
  - ASK FIRST if I encounter: <ambiguity>
```

---

## M4 — Check parallel sessions and base branch state first

**Pattern the user kept correcting.** Agent branched or merged without noticing another session's work-in-progress. Worktree state and `main` divergence caused merge collisions (e.g., `created_at` ambiguity between two branches).

**Representative correction.**
> "we just pushed some commits to main that may affect our to-dos, check."
> "actually before you execute, take a look at feat/posts-raw-denormalize, should we merge these to main first?"
> "had another session push changes to static ui files, check status of that"
> "note another session working on code, so be careful not to change it."

**Rule.** Before any work that touches shared surfaces (`core/models.py`, harvest code, `docs/reference/`, prod DB):

1. `git fetch` and check `git log origin/main --oneline -10` and the current branch's divergence.
2. `git worktree list` and check `git branch -a | grep -E 'feat/|fix/|hotfix/'`.
3. Run `git status` — if there are uncommitted edits, surface them before proceeding.
4. If a parallel branch touches the same files, **stop and tell the user** — don't silently merge or cherry-pick.

From repo memory: `feedback_worktree_hygiene_x_monitoring.md` (worktrees at `repo/worktrees/name/`, symlink `.venv` + db).

---

## M5 — Verification in the plan, not after the plan

**Pattern the user kept correcting.** Completion evidence missed real behavior, leaving production and visible-UI regressions.

**Representative correction.**
> "it is rendered. that is a comment but it is visible on the page"

**Rule.** Every plan / every unit MUST name the risk-specific proof:

```
Definition of Done:
  - Migration applies cleanly on a fresh DB
  - Production DB shows new cols / rows after migrate (query: …)
  - Harvest pipeline writes to prod DB (query: SELECT count(*) FROM posts_raw …)
  - Public UI: browser route after DOM replacement; assert required/forbidden text, not screenshot/regex alone
  - Rate metric returns to baseline (query: …)
```

Public templates/static assets contain product content only; put implementation notes in plans/docs. For UI, trace URL → view → template → static assets → runtime endpoint and assert rendered output/DOM; source/structural/screenshot checks complement it. Prod queries go through Render CLI, not direct psql — see `reference_pushinweight_prod_db_via_render_cli.md`.

---

## M6 — Don't ask "want me to do option 1 or option 2?" when one is correct

**Pattern the user kept correcting.** Agent presents two options and asks the user to pick, when only one is the right answer.

**Representative correction.**
> "option a"
> "go" (after agent asked permission to proceed)

**Rule.** When there are two options and one is clearly better given the canonical decisions in `AGENTS.md`, recommend that one with one sentence of reasoning and **state you are doing it**, then stop. Don't ask the user to choose between A and B when A is the right answer. From `feedback_scoped_revert_specificity.md`: "user revert X = ONLY X, read literal scope, not inferred."

---

## M7 — DRY: harvest / cycle / backfiller share a core

**Pattern the user kept correcting.** Agent built backfiller as a separate code path that duplicated harvest pipeline code. User had to push back with "are we practicing DRY? shouldn't backfiller largely re-use the harvest codebase?"

**Representative correction.**
> "are we practicing DRY? shouldn't backfiller largely re-use the harvest codebase? can we abstract the harvest codebase so that we aren't reinventing the wheel? how much of the codebases overlap?"
> "let's get back to backfiller. so in order to DRY, will you change some of the code from existing harvest pipeline so that they can double for backfiller?"
> "refactor this first"
> "cyclerunner existed before we built backfiller?"

**Rule.** Before building any new pipeline component, search the existing `core/` and `monitor/` (or x-monitor) for code that does the same fetch/classify/persist cycle. New code MUST live in a shared module, with the existing pipeline refactored to call into it. Don't write a parallel implementation.

Search with:

```
rg -l 'run_cycle|classify|attribute_to_brands' core/ monitor/ x_monitor/
```

---

## M8 — Guard against LLM / DB over-taxing **upfront**

**Pattern the user kept correcting.** Agent built a feature, then user had to ask "ok but do we have guards against overtaxing the LLM? remember we had issues with sending too many concurrent calls" and "the max results and pages should be higher than the calculation, just in case."

**Representative correction.**
> "ok but do we have guards against overtaxing the LLM? remember we had issues with sending too many concurrent calls"
> "the max results and pages should be higher than the calculation, just in case. also, if we run this now, is it basically just 1 really big run, and will that interfere with the existing harvest runner"

**Rule.** When designing any cycle that hits external APIs (TwitterAPI.io, LLM, Apify) or runs long DB writes, the design must specify upfront:

| Guard | Where it lives |
|---|---|
| Concurrency cap on LLM calls (semaphore or `asyncio.Semaphore`) | the cycle's `_classify` step |
| Page / result cap = `calc * 1.5` (or whatever headroom user named) | the cycle's `_fetch` step |
| Distinct from the live harvest runner: separate scheduler entry, not a replacement | ops runbook |
| Watchdog: cycle must check `paused` sentinel and bail cleanly | see `CONCEPTS.md` → Pause sentinel |

If the plan does not name these guards, the plan is incomplete.

---

## M9 — URLs / endpoint shape: idiomatic + versioned correctly

**Pattern the user kept correcting.** Agent shipped URLs like `/api/v1/home.window/1` that mixed a v1 prefix (retired stack) with a dot-in-path (non-idiomatic). User pushed back with "do these urls make sense? eg 'https://pushinweight.ai/api/v1/home.window/1', why is there a v1 here, and why is there a 'home.window' with dot there".

**Representative correction.**
> "do these urls make sense? eg 'https://pushinweight.ai/api/v1/home.window/1', why is there a v1 here, and why is there a 'home.window' with dot there"
> "no. we need a whole new plan to use more idiomatic url, even if that means changing code."

**Rule.** New endpoints:
- Use `/api/v2/...` (v1 is retired; never use `/v1/` on prod).
- Path segments use `/`, never `.`. Use `-` or `_` for multi-word segments.
- Resource names match `core/models.py` table names (`posts`, `brands`, `classifications`).
- List the URLs in the plan body BEFORE coding. User wants to see the shape, not read it from a deployed URL after the fact.

---

## M10 — i18n catalog drift

**Pattern the user kept correcting.** Locale-toggle churn caused chrome strings to drift (`docs/solutions/workflow-issues/django-i18n-locale-toggle-debugging-journey.md` references this). The user flagged missing translations and missing `text.zh_cn` population.

**Representative correction.**
> "why arent new posts populating text.zh_cn"
> "we are missing some 7/22 and 7/23 posts. it might be in v1 sqlite. check there and if so copy to prod db" (related: post-fetch backfill step missed translations)

**Rule.** Touching anything that produces user-visible strings:

1. Add the string to BOTH `locale/en/LC_MESSAGES/django.po` AND `locale/zh_Hans/LC_MESSAGES/django.po`. Run `python manage.py seed_i18n_labels` after.
2. For dynamic content (post body, brand description), verify the translation pass actually fills the column — query `SELECT count(*) FROM posts WHERE text_zh_cn IS NULL` after a backfill.
3. Any plan that adds a translatable column MUST include a regression-net assertion pinning the column to NOT NULL after backfill. From `feedback_regression_net_in_every_plan.md`.

---

## M11 — Reference docs reflect CURRENT state, not git history

**Pattern the user kept correcting.** Agent's reference docs inherited wording from past versions ("we will use git history for that" — the user has to push the agent to NOT preserve remnants).

**Representative correction.**
> "we've made some massive changes. reflect all the changes, and do NOT show remnants from the past (we will use git history for that). just show the current state."

**Rule.** When rewriting `docs/reference/*`:

- Edit the file to describe the CURRENT state only.
- Do NOT preserve outdated caveats, "previously…" sections, or "we used to…" sentences.
- Git history is the archive; the doc is the snapshot.
- For the retired v1 stack: it gets ONE line ("v1 Flask + launchd + SQLite stack is retired; do not write to `data/x_monitoring.db`") and nothing else.

---

## M12 — Set-model / classifier LLM mistakes

**Pattern the user kept correcting.** Default LLM (Claude / Sonnet) was assumed where the user explicitly named a non-default. Repeated re-prompts clarified: "we are using deepseek for the classifier", "what does the set-model script do".

**Representative correction.**
> "note that LLM calls are default minimax, however we are using deepseek for the classifier"
> "where is the 'set-model' script"

**Rule.** Any code path that calls an LLM MUST set the model explicitly. Read the canonical value from:
- `CLAUDE.md` / `CONCEPTS.md` for the named project
- The actual `set-model` script at `scripts/set-model.sh` (or `bin/set-model`) — locate it with `rg -l 'set.model|set_model' scripts/ bin/`

Never call `client.messages.create(model=...)` without an explicit model name. From repo memory: `feedback_reattribute_with_llm_required.md` (v1.8 reattribute defaults `anthropic_client=None`; must pass explicitly).

---

## M13 — 500 / server error: surface, don't bury

**Pattern the user kept correcting.** When prod threw `server error 500` or `render error`, the agent was slow to ssh in and check. User said "server error 500" / "render error, check via ssh" / "ssh to render and debug".

**Rule.** On a `500` / traceback / render error report:

1. `ssh srv-d9go2breo5us73cg6vqg@ssh.oregon.render.com` (or current render ssh host — verify against `render.yaml`) and read the tail of the gunicorn / worker log immediately.
2. Quote the relevant lines in your reply.
3. Diagnose with `superpowers:systematic-debugging`, NOT by guessing from code.
4. From `feedback_playwright_first_for_ui.md`: drive Playwright to reproduce the 500, not by reading templates.

---

## M14 — Plan filenames follow repo convention

From repo memory: `feedback_plan_filename_matches_repo.md`.

**Rule.** Plan files in this repo go to `docs/plans/` and use `YYYY-MM-DD-NNN-kebab-slug.md` (date + serial). Do NOT use the generic `/plans/` directory or any other path. Do NOT use compound-engineering default filename conventions.

---

## M15 — Don't delete unrelated dirs

From repo memory: `feedback_dont_delete_unrelated_dirs.md`.

**Rule.** Never `rm -rf` or `git clean -fd` based on "looks empty" or "looks unused". Directories like `data/`, `x-monitoring/`, `staticfiles/`, `worktrees/` exist for reasons — confirm before deletion. If a dir looks orphaned, ask the user.

---

## M16 — When in doubt, don't make the LLM call yourself

**Pattern the user kept correcting.** Agent made "creative" model choices or hallucinated state.

**Rule.** For external facts (TwitterAPI syntax, Apify actor params, deepseek model name, Render env var names): **call `context7` or WebSearch before guessing**. From `feedback_remote_path_shape_not_sshfs.md` and the `m3_no_oversell_finding.md` finding: do not invent API surface details.

---

## M17 — Halt-first, then diagnose, then add a regression pin

**Pattern the user kept correcting.** User reports "harvester not running" / "fetched vs inserted" / "credits too high" / "the cron is doing weird things" — and the agent's first instinct is to start reading code, propose a fix, or run a probe. The user explicitly said on 2026-08-06: *"first, halt the harvester. read our /.claude/skills in the project repo file, there may be directions there."*

**Rule.** When the user reports a harvester anomaly (low insert count, missing posts, 402 errors, cursor drift, any data discrepancy), **halt the cron FIRST** before investigating. Then look at the project's `.claude/skills/` for project-specific guidance. Then diagnose. Then add a regression pin. Then resume.

The pause procedure for the v2 cron is NOT the v1 launchd pause sentinel in `CONCEPTS.md` — that doc describes a macOS-only mechanism that doesn't apply to Render cron. The v2 pause is the Render REST API:

```bash
SVC_ID="crn-d9gv94o4n6ts739tqaug"   # pushinweight-harvest
curl -X POST -H "Authorization: Bearer $RND_KEY" \
     -H "Content-Type: application/json" \
     "https://api.render.com/v1/services/$SVC_ID/suspend" \
     -d '{"suspend":"yes"}'
# Verify: curl -sS -H "Authorization: Bearer $RND_KEY" \
#         "https://api.render.com/v1/services/$SVC_ID" | grep suspended
```

The full procedure is in `docs/operations/pause-and-resume-harvest-cron.md`. For the end-to-end harvest change contract (scope, reproduce, regression pins, post-deploy DoD), see `.claude/skills/change-harvester/SKILL.md`. **Important caveats from prior incidents (2026-07-30):** the API `POST /suspend` with `{"suspend":"no"}` returns HTTP 200 but does NOT clear the suspended state. Resume is sometimes dashboard-only. Verify with `GET /v1/services/$SVC_ID` — `"suspended": null` means running, `"suspended": "suspended"` means still paused.

**Why halt first:**
- The cron fires every 15 min. If left running during diagnosis, the harvester may overwrite the very state you're trying to inspect (cursor rows, `last_completed_at`, `INSERT OR IGNORE` semantics).
- A 4xx-class failure (402 credits, 429 rate limit) loops every 15 min and burns the same failure path forward, hiding the underlying cause.
- Anomaly-state reads are cleaner when the cycle is paused — no need to reason about half-written cycle state.

**Why add a regression pin:**
- The 989-fetched vs 86-inserted discrepancy on 2026-08-06 was a live bug, not an estimation error. A regression pin that checks the post-fetch-to-insert ratio (e.g., 0.05-0.20 for 20 enabled brands at 15 credits/tweet) would have caught the drift at the next deploy. Format: `tests/test_*.py` asserting both the cursor-floor semantics AND the dedup ratio.

**Two hypotheses worth pre-flighting when the user says "fetched vs inserted looks wrong":**
1. **Cursor/date drift** — `_read_cursor_since` in `monitor/cycle.py:259` returns a `since_time` floor; if it's stuck at the floor (cold start) or way in the future (NTP rollback), the cycle re-fetches the same window or returns nothing. `INSERT OR IGNORE` in `x_monitor/store.py:608` then discards the duplicates, producing a low insert count vs. high fetch count.
2. **Unintended post-fetch filter** — `_run_post_fetch` in `monitor/cycle.py:1245` runs translate + classify after insert. An aggressive classify step that drops all-but-a-few posts would explain the 86 figure. Verify by running `manage.py run_cycle --debug-fetch` and counting the kept_posts list.

**The user-mandated procedure**
1. Halt the cron via Render REST API (above).
2. Read `.claude/skills/` in the project repo for project-specific guidance (e.g., `avoiding-recurring-mistakes/SKILL.md` M-rules).
3. Read `docs/operations/pause-and-resume-harvest-cron.md` for the canonical pause/resume procedure and prior incident notes.
4. Diagnose using `monitor/cycle.py:_read_cursor_since` and `x_monitor/run.py:_run_post_fetch` as the first two investigation surfaces.
5. Land the fix + a regression pin (test ratio like `n_inserted / n_fetched >= 0.05` for typical traffic).
6. Resume via Render dashboard (not just the API — see prior incident notes).
7. Append a new entry to `docs/operations/pause-and-resume-harvest-cron.md` with the pause/resume events.

---

---

## M18 — Function-only regression net is a regression waiting to happen

**Pattern that bit us.** A fix lands on 2026-08-05 in commit `a46d2de`. The companion regression net (`tests/test_translator_model_resolution.py`, 5 tests) mocks env and calls `_resolve_translator_model()` directly. **All 5 tests passed. The function was correct.** But the production call chain (`_call_with_retry` → `_resolve_model()` with no cfg) had never been updated, so the resolver received `cfg=None` and fell straight through to the env-inference branch — the same broken path that pre-existed a46d2de. The 11,108-byte truncation in the 2026-08-06 08:47:02 UTC cron run was the first symptom. **26 hours between the "fixed" commit and the first prod failure.**

**Rule.** For any behavior-changing plan that touches a function used by a production caller, the regression net MUST include at least one **end-to-end call-chain test** that exercises a real (or fake-with-captured-kwargs) production caller and asserts the captured downstream behavior matches spec. Function-level tests pin the function; **they do not pin production correctness**.

**Heuristic that catches the trap:** "if my regression net only calls `fn(...)` and asserts the return value, it tests the function in isolation. It does NOT test the call chain."

**When to suspect the trap** — open question before signing off on a fix commit:

| Symptom in commit | Trap risk |
|---|---|
| Function signature gains `cfg=None` kwarg | High — call sites may still pass nothing |
| Function signature gains a new arg with default | Medium — existing callers' default may be wrong |
| Function body changes resolution order / precedence rule | High — existing test setup may not match new defaults |
| Function body adds a new feature/flag | Medium — flag may not be threaded to callers |
| Pure-refactor (no behavior change) | Low — call chain is identical to before |

**Concrete template — the end-to-end call-chain pin.** The shape that would have caught the 2026-08-06 bug:

```python
def test_translate_batch_uses_canonical_model_not_env_inference(monkeypatch):
    """Regression pin: model=deepseek-v4-pro must reach DeepSeek even when
    the env-group's ANTHROPIC_BASE_URL still points at api.minimax.io."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    cfg = make_cfg(translator_model="deepseek-v4-pro")
    fake_client = FakeClaudeClient(capture_kwargs=True)
    translate_batch_pragmatics(
        [{"tweet_id": "1", "text": "x", "brand_id": "y"}],
        ["en", "zh_cn"],
        fake_client,
        cfg=cfg,
    )
    assert fake_client.last_call_model == "deepseek-v4-pro", (
        f"Production caller sent model={fake_client.last_call_model!r} to "
        f"DeepSeek. Cron will 400. Fix: thread cfg through _call_with_retry."
    )
```

Pair this with the function-level test. The function-level test pins the resolver. The call-chain test pins the production caller. Both must pass.

**Verify-in-same-commit checklist** (use before pushing a behavior-changing fix):

1. Run `git grep -E "fn_name\(" -- ':!tests/'` — every existing call site listed.
2. For each call site, trace whether the new arg/kwarg/precedence rule reaches the function in production. If the call site doesn't pass cfg and the function reads `cfg.x`, the fix is incomplete.
3. Drop the heuristic on your plan body's Definition of Done: **"N call-chain tests + M function-level tests, all green"**. Don't say "all tests pass"; name the count and the shape.
4. After pushing, wait for the next cron tick + 1 cycle window, then check Render logs for absence of the failure mode the regression net asserts against. Function-level green ≠ production green until that log check passes.

**Incremental improvement recipe** (apply to existing regression nets, one per branch):

1. Pick the highest-risk surface area (anything matching the symptom table above, plus anything tagged "fix(" in the last 30 days).
2. Add ONE call-chain test that exercises a real production caller with a fake client. Add it to the existing test file.
3. Don't refactor the file. Don't change existing tests. One test, one fake client, one assertion on captured kwargs.
4. Land as its own commit titled `test(<surface>): pin <caller> behavior end-to-end`. No code change to the production path.
5. Repeat on the next-highest-risk surface.

The translator batch-limits probe (`scripts/probes/translator_batch_limits/probe.py`) is itself a form of this learning — it surfaced the original bug precisely because it called the production function with the env-mismatched base URL. Use it as a template when designing new probes: `git show af3de15` to see the canonical pattern (load cfg, pass to the canonical factory, mirror what cycle.py does).

**Related cross-project memories** (loaded with this skill when triggered):
- `feedback_cfg_first_resolution_call_site_wiring.md` — the fix-side rule: a function-level commit is incomplete without wiring the call sites.
- `feedback_regression_net_must_pin_call_chain.md` — the test-side rule: function-level tests stay green while production breaks.

---

## Quick reference table

| # | Mistake | One-line rule |
|---|---|---|
| M1 | Re-deriving settled decisions | Re-read `AGENTS.md` + `CONCEPTS.md` before editing |
| M2 | Volunteering commit/push/merge | End the turn with literal answer; don't offer extras |
| M3 | Scope ambiguity | Repeat keep/revert list back BEFORE acting |
| M4 | Parallel-session collision | `git fetch` + check `feat/*` branches before merging |
| M5 | Verification as retrofit | Name risk-specific proof; public UI needs real rendered route/DOM evidence |
| M6 | False choice | Recommend the right option; don't ask permission for the obvious |
| M7 | Re-inventing harvest/cycle | Refactor shared code; don't write parallel pipelines |
| M8 | Missing rate/concurrency guards | Name the LLM/DB guards in the plan body |
| M9 | v1 URL prefix or dot-path | `/api/v2/<resource>/<id>`, slash-separated |
| M10 | i18n drift | Pin translated column to NOT NULL after backfill |
| M11 | Reference-doc remnants | Current state only; git is the archive |
| M12 | Default-model assumption | Read the named model from scripts; pass explicitly |
| M13 | Burying 500s | SSH to Render, read logs, then debug systematically |
| M14 | Off-convention plan filename | `docs/plans/YYYY-MM-DD-NNN-slug.md` |
| M15 | Unrelated-dir deletion | "Looks empty" ≠ authorization to `rm -rf` |
| M16 | Inventing API surface | `context7` / WebSearch before guessing external APIs |
| M17 | Diagnose-then-fix without halting | Halt the cron first, then read `.claude/skills/`, then pin a regression |
| M18 | Function-only regression net | Pin the production call chain end-to-end (fake client + captured kwargs); function-level tests stay green while production breaks |

---

## If you realize mid-work that you violated one of these

Stop. Tell the user what rule you violated and what you were about to do. Don't keep going and "fix it later" — that's the same drift the user keeps correcting. From `~/.claude/CLAUDE.md` Plan-Execution Contract: fail loud on friction, surface the violation, and use AskUserQuestion if scope narrowing is needed.

---

## Source

This skill is derived from a longitudinal analysis of 257 real user prompts across 12 sessions in `/Users/fuchitalee/.claude/projects/-Users-fuchitalee-development-pushin-weight-v2/` (Jul 2026). Correction patterns: scope_trim, no/just-only, why/pushback, DRY/dedup, guard/limit, server-error/runtime, worktree/merge, prod/deploy. Method and full counts are in `~/.claude/projects/-Users-allenwlee/2026-08-04-pushin-weight-v2-mistakes.md`.

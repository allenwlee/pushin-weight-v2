---
name: change-harvester
description: Use when changing harvest/cycle behavior in pushin-weight-v2 — CycleRunner, run_cycle, backfill, harvest policy, TwitterAPI search calls (A/B/C), cursors, metrics refresh, translator/classifier post-fetch, Render harvest cron, credit burn, or fetch-vs-insert anomalies.
---

# Change Harvester — pushin-weight-v2

Turn a harvest change (bug, policy tweak, config wiring, cost fix) into a
minimal, verified change that cannot silently ship a green cron with zero work.

This skill is the harvest twin of `.claude/skills/fix-ui/SKILL.md`.
**Always also load** `.claude/skills/avoiding-recurring-mistakes/SKILL.md`
before editing harvest code — especially **M7** (DRY cycle/backfill),
**M8** (LLM/DB guards), **M12** (explicit model/env), **M17** (production
pause authorization), and **M18** (call-chain regression nets). If this skill and the avoid-mistakes
skill disagree on pause/resume or config SSOT, follow `AGENTS.md` +
`docs/operations/pause-and-resume-harvest-cron.md` first, then the more
specific rule here.

## Help the user report the right thing

When the request is vague, start gathering evidence and ask only for the
missing detail that would change the fix. Guide toward this compact format;
do not require every field:

> **Harvester change request**
>
> - **Symptom:** what looks wrong (low inserts, NULL lang, 402, credit spike,
>   empty brands, stuck cursor, aborted cycles, …).
> - **Window:** wall clock / cycle id / “last N ticks” if known.
> - **Actual:** log line, DB count, cost figure, or missing field.
> - **Wanted:** durable outcome (e.g. “lang_detected non-null on new posts”,
>   “B1 not truncated every cycle”, “credits ≤ X / cycle”).
> - **Keep unchanged:** 7-call shape, brand set, policy bands, metrics delay,
>   translator/classifier models — unless named.
> - **Risk posture:** whether the owner explicitly authorizes a live pause;
>   credit budget if probing.
> - **Done means:** the metric or post-deploy check the user will judge.

Users need not name files or root cause. The agent owns reproduction, tracing,
regression pins, and post-deploy evidence. The owner controls every production
pause or resume decision.

## Scope before editing

State exact **TOUCH**, **PRESERVE**, and **ASK FIRST** boundaries.

| Default PRESERVE (unless named) | Why |
| --- | --- |
| 7-call hybrid shape (A + B1 + B2 + B3 + C1 + C2 + C3) | Volume / purity contract |
| `config.yaml` + `x_monitor.config.load_config` as runtime SSOT | Drift caused multi-hour dead deploys |
| Shared `plan_calls_for_cycle` / `CycleRunner` for harvest **and** backfill | M7 — no parallel pipeline |
| One-shot metrics refresh delay/cap semantics | Credit + freshness tradeoff |
| Render service inventory (pause only harvest when asked) | Web must stay up |
| Unrelated UI / feed / i18n | Wrong skill surface |

Do **not** commit, push, merge, deploy, suspend/resume cron, run live
`run_cycle` against prod, or rewrite policy YAML wholesale unless requested.
A report, question, request to investigate, or request to diagnose/fix an
anomaly is not authorization to pause production.

Read, in order:

1. `AGENTS.md` (stack, harvest cost entrypoint)
2. `CONCEPTS.md` (domain vocabulary; pause sentinel notes may be v1 — verify)
3. `.claude/skills/avoiding-recurring-mistakes/SKILL.md` (M7, M8, M12, M17, M18)
4. Relevant `docs/solutions/**` and `docs/operations/pause-and-resume-harvest-cron.md`
5. Active worktrees / `git status` / recent `origin/main` — surface collisions

## Production pause authorization (M17)

A production pause is an external mutation, not a diagnostic step.

- **Default to read-only.** Leave the cron in its current state while inspecting
  logs, persisted rows, query configuration, and code.
- Pause only when the owner's current request explicitly says to halt, pause,
  stop, or suspend the exact production cron, or when the active plan records
  explicit owner authorization for that pause. A prior incident's instruction
  never carries forward as standing permission.
- If a pause could reduce ongoing credit burn or data damage, explain the
  evidence and ask for authorization. Do not infer permission from urgency,
  anomaly severity, or a request to investigate or fix.
- Before an authorized pause, read
  `docs/operations/pause-and-resume-harvest-cron.md`, identify the exact service,
  record its current state, mutate only that service, and verify the result.
- Preserve the owner's requested pause scope. Resume only when explicitly
  authorized or when the same request clearly authorized a bounded
  pause-diagnose-resume operation.
- If an unauthorized pause or resume occurs, restore the prior state
  immediately, disclose the error, and verify restoration.

Routine planned changes, dry-run tests, offline refactors, and forensic
questions do not require a halt. Ask before any action that changes live credit
burn, call volume, or service state.

## Reproduce from the real path (not code-only)

Trace production call chain before editing:

```
Render cron (crn-d9gv94o4n6ts739tqaug)
  → manage.py run_cycle
  → CycleRunner(cfg=load_config(...))
  → plan_calls_for_cycle(cfg)          # A/B/C queries + cursors
  → TwitterAPI search / metrics
  → persist posts + posts_brands
  → post-fetch: translator → classifier (signals / discourse)
  → optional one-shot metrics_refresh
  → harvest_cost emit (data/runs when present)
```

Evidence sources (prefer in this order):

| Source | Use for |
| --- | --- |
| `render logs -r crn-d9gv94o4n6ts739tqaug` | cycle id, posts_seen / inserted, TRUNCATED walks, exceptions |
| `render psql dpg-d9koekqjobas73fvjqng-a` (via fuchitalee) | durable inserts, `lang_detected`, signals, discourse, `fetched_at` |
| `python -m scripts.harvest_cost` | credit model for search + metrics |
| `tests/posts/*-cohort.md` | durable cohort SSOT after a verified cycle |
| Local `manage.py run_cycle --dry-run` | plan shape only — not prod proof |

**Critical:** Render `cron_job_run_ended status="successful"` means exit 0,
not a healthy harvest. Cycles can abort after `NameError` / swallowed
exceptions with `n_inserted=0` and still look green. Always check DB inserts
and cycle summary fields, not only Render success.

Do not establish a harvest fix from a helper-only unit test or from
re-deriving call structure without reading `monitor/cycle.py` + policy.

## Pin the defect before fixing it (M18)

Add or strengthen a regression pin that exercises the **production call
chain**, not only a pure function:

- Prefer fake TwitterAPI / fake LLM clients that **capture kwargs** at the
  real caller (`CycleRunner`, `translate_batch_pragmatics`, factory builders).
- Pin AFTER behavior explicitly; comment BEFORE state when intentionally
  changing a surface (Plan-Execution Contract / regression-net rule).
- For config/env precedence: pin with **mismatched** env-group values
  (e.g. `ANTHROPIC_BASE_URL=minimax` while translator must hit DeepSeek).
- For cursor / fetch-vs-insert: pin floor semantics and a sensible
  `n_inserted / n_fetched` floor for typical multi-brand traffic.
- For `lang_detected` / allowlists: pin validate → repair → fail-empty
  residual, not only happy-path parse.
- Required-test skips, silent filters, and broad `except Exception` that
  turn red into green are failures — surface them.

`git grep` every call site when a signature or precedence rule changes.
Function-level green while production still omits `cfg=` is incomplete.

## Make the smallest durable change

- Prefer config / policy / one factory over a new parallel pipeline (M7).
- Thread `cfg: Config` from `load_config` — do not re-introduce ad-hoc env
  or Django-settings dual paths for fields already on `Config`.
- Name LLM model and base URL explicitly (M12); never assume defaults.
- State rate/concurrency/credit guards in the plan body before probes (M8).
- Keep credit burn visible: if the change increases search volume or metrics
  refresh, estimate with `scripts.harvest_cost` before shipping.
- No iteration labels or agent commentary in product source or operator-facing
  reports beyond the normal `### written by Grok …` doc attribution.

## Surfaces map (quick)

| Surface | Primary paths |
| --- | --- |
| Cycle orchestration | `monitor/cycle.py`, `monitor/management/commands/run_cycle.py` |
| Backfill (must share core) | `monitor/management/commands/backfill.py` |
| Policy / query bands | `x_monitor/harvest_policy.py`, `config.yaml`, `x_monitor/config.py` |
| Persist / dedup | `x_monitor/store.py` (and related) |
| Translator / lang | `x_monitor/translator.py`, attribution factories |
| Classifier signals | classifier path used from `_run_post_fetch` |
| Metrics refresh | `monitor/metrics_refresh.py` |
| Cost | `scripts/harvest_cost/` |
| Cron / pause | `render.yaml` → `pushinweight-harvest`, ops pause doc |
| Durable health reports | `docs/analysis/harvester/` (canonical operator analysis) |
| Historical cohort examples | `tests/posts/` (style reference, not canonical output) |

## Persisted latest-N health verification

After local regression tests and before delivery, use
`$harvester-latest-n-health-check` to inspect the production rows produced by
the live pipeline.

Use the **enrichment-relevant route** when the final diff changes any of these
surfaces:

- `monitor/cycle.py` post persistence or durable enrichment orchestration;
- `core/models.py` or a migration that affects checked post/enrichment facts;
- `x_monitor/translator.py`, `x_monitor/attribution.py`, or
  `x_monitor/reattribute.py`;
- enrichment configuration in `config.yaml` or `x_monitor/config.py`; or
- `render.yaml` scheduling or the `run_cycle` flow.

Run the initial literal latest-N cohort, retain its ordered tweet IDs, use the
caller's wait mechanism for the 30-minute grace window, and then inspect that
exact cohort by ID. Fresh pending enrichment is inconclusive, not a regression.
Do not retry or substitute a newer cohort.

Use the **immediate route** once for other harvester changes, for an operator's
latest-health inspection, or when the final diff only changes the diagnostic
itself. Record healthy, fresh-pending, unhealthy, or operational-error evidence.
When the owner requests full post-level evidence, use the helper's explicit
`--report` mode and retain the generated report under
`docs/analysis/harvester/`; normal human and JSON output remain bounded.

This planned verification does not authorize a cron halt.
It does not authorize a harvest run.
It does not authorize provider calls.
It does not authorize production mutation.
If the owner separately reports a live anomaly, use the M17 authorization gate
in `.claude/skills/avoiding-recurring-mistakes/SKILL.md`; the report itself does
not authorize a pause.

## Definition of Done

- Reported failure is **red before** the product fix and **green after**.
- Call-chain regression covers the changed behavior (M18); helper-only tests
  are insufficient for cfg/env/LLM/TwitterAPI wiring.
- Required tests: report executed / skipped / error counts; skips ≠ green.
- If the change ships to the live cron:
  - Deployed SHA confirmed on `pushinweight-harvest`.
  - At least one post-deploy cycle inspected in logs **and** DB
    (`fetched_at` window, insert count, targeted fields such as
    `lang_detected` / signals).
  - Cost impact checked when search or metrics volume changed
    (`python -m scripts.harvest_cost`).
  - Optional but preferred for material volume/quality changes: a detailed
    health report under `docs/analysis/harvester/`, using historical
    `tests/posts/` cohort notes only as a stylistic reference.
- Exit 0 / Render “successful” alone is **not** DoD.
- Pause/resume events appended to
  `docs/operations/pause-and-resume-harvest-cron.md` when used.
- Report branch/SHA, environment, commands, and evidence inspected.

## Anti-patterns (do not)

- Suspend or resume production based only on an anomaly report, diagnostic
  request, historical instruction, or inferred urgency (M17).
- Invent a second harvest path “just for this fix” (M7).
- Trust function-level tests while production callers still miss `cfg=` (M18).
- Treat log `inserted=N` as DB truth without a `posts` query when they diverge.
- Claim production fixed from local SQLite (`data/django_dev.db`).
- Volunteer commit / push / resume / deploy (M2) — wait for the user.
- Expand allowlists, max_results, or max_pages without credit impact.

## Related skills and docs

| Doc / skill | Role |
| --- | --- |
| `.claude/skills/avoiding-recurring-mistakes/SKILL.md` | Recurring friction (required companion) |
| `.claude/skills/fix-ui/SKILL.md` | UI-only; do not use for harvest |
| `docs/operations/pause-and-resume-harvest-cron.md` | Pause/resume SSOT + event log |
| `scripts/harvest_cost/README.md` | Credit pricing CLI |
| `docs/solutions/runtime-errors/translator-*.md` | Translator env / truncation / lang |
| `docs/solutions/integration-issues/harvest-pipeline-missing-call-queries.md` | Query wiring gaps |
| `docs/analysis/harvester/` | Canonical generated harvester health reports |
| `tests/posts/*-cohort.md` | Historical post-cycle report style reference |

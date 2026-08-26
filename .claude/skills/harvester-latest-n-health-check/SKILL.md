---
name: harvester-latest-n-health-check
description: Inspect the literal latest production posts and persisted post-fetch health, with an optional full Markdown evidence report, without writes or provider calls. Use when checking latest production posts, diagnosing post-fetch health, or running enrichment verification after harvester, translation, sentiment, post-type, or discourse changes.
---

# Harvester latest-N health check

Inspect persisted production facts for a bounded post cohort. Report ingestion and persistence, translations, per-brand sentiment and post type, discourse, and durable enrichment state.

This is a health check, not a repair or active probe.

## Safety boundary

- Never run harvesting.
- Never call TwitterAPI.
- Never invoke an LLM.
- Never mutate production.
- Never re-enrich or backfill a post.
- Do not halt the harvest cron for this planned diagnostic. Apply M17 from `.claude/skills/avoiding-recurring-mistakes/SKILL.md` if a separate live incident is confirmed.
- Do not retry, poll, or start a recurring loop. Run once for the immediate route or exactly twice for the enrichment-relevant route.
- Do not print full post text, credentials, raw Render diagnostics, query text, or tracebacks to normal human or JSON output.
- Full post text, the exact read-only SQL, and current-code prompt reconstructions are allowed only in explicit `--report` mode. Never copy credentials, environment values, raw Render stderr, or tracebacks into that report.

The bundled helper makes one bounded `render psql` call to `pushinweight-db-shadow`. Its fixed SQL begins a read-only transaction, verifies `transaction_read_only=on`, applies timeouts, and limits the cohort before joining per-brand facts.

## Resolve the helper

Run from any directory inside the repository:

```bash
HEALTH_REPO_ROOT="$(git rev-parse --show-toplevel)"
if [ -x "$HEALTH_REPO_ROOT/.venv/bin/python" ]; then
  HEALTH_PYTHON="$HEALTH_REPO_ROOT/.venv/bin/python"
else
  HEALTH_PYTHON="$(for candidate in python3 python; do command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import yaml' >/dev/null 2>&1 && { echo "$candidate"; break; }; done)"
fi
[ -n "$HEALTH_PYTHON" ] || { echo "No project Python with PyYAML is available" >&2; exit 2; }
HEALTH_SCRIPT="$HEALTH_REPO_ROOT/.claude/skills/harvester-latest-n-health-check/scripts/check.py"
```

Keep these variables task-specific. Do not reuse system variables such as `HOME` or `CODEX_HOME`.

## Choose the route

Inspect the plan and final diff before running the check.

Use the enrichment-relevant route when behavior changed in any of these areas:

- `monitor/cycle.py` post persistence or durable enrichment flow
- `core/models.py` or `core/migrations/` for post-enrichment state or per-brand facts
- `x_monitor/translator.py`, `x_monitor/attribution.py`, or `x_monitor/reattribute.py`
- enrichment settings in `config.yaml` or `x_monitor/config.py`
- `run_cycle`, the Render harvest schedule, or another change that affects when persisted enrichment completes

Use the immediate route for other harvester changes, for an operator-requested latest-post inspection, and when the current diff only adds or changes this diagnostic.

## Immediate route

Run the literal latest cohort once. The default is 20 and the accepted range is 1 through 200.

Human report:

```bash
"$HEALTH_PYTHON" "$HEALTH_SCRIPT" --latest 20
```

Stable JSON report:

```bash
"$HEALTH_PYTHON" "$HEALTH_SCRIPT" --latest 20 --json
```

Detailed Markdown evidence report:

```bash
"$HEALTH_PYTHON" "$HEALTH_SCRIPT" --latest 20 --report
```

`--report` and `--json` are mutually exclusive. Detailed mode preserves the
same single bounded read-only database snapshot and keeps terminal output
bounded. It writes atomically to the repository's canonical operator-analysis
location:

`docs/analysis/harvester/YYYY-MM-DD-HHMMSS-harvester-latest-n-health-report.md`

The report contains:

- summary and ordered cohort IDs;
- full source text, persisted English and Simplified Chinese translations,
  commentary, enrichment attempts/timestamps, per-brand facts, discourse,
  nationalism, mentions, and unsanctioned-flag evidence;
- an empty ledger of LLM calls made by the checker—the checker makes none;
- verbatim prompts and deterministically known request kwargs reconstructed by
  the current pure translation and classification prompt builders;
- an explicit provenance warning that current-code reconstructions are not
  historical wire calls, because historical prompts, responses, retry counts,
  runtime `thinking`, and original production batch membership are not stored;
- exact SQL, invocation, Python version, checker file-content SHA-256,
  repository commit, and the complete checker source.

Do not describe reconstructed calls as historical observations. The report may
show the configured model name, but must label runtime-only values unavailable
instead of reading secrets or constructing a provider client.

Interpret both `status` and `regression_gate`:

- `status=healthy` and `regression_gate=complete`: every selected row is complete.
- `status=healthy_with_pending` and `regression_gate=inconclusive`: pending is fresh and neutral, but completion is not proven.
- `status=unhealthy` and `regression_gate=failed`: one or more persisted facts are failed, missing, invalid, or overdue.
- Exit 2 or `status=error`: the invocation, configuration, Render transport, query, or parser failed. Report the stable error code only.

Exit 0 covers both healthy states. Always report the separate complete, pending, and unhealthy counts so fresh pending is not confused with completion.

## Enrichment-relevant route

1. Run `--latest 20 --json` and retain the ordered `cohort_tweet_ids` from that result as the immutable cohort.
2. Wait 30 minutes through the caller or harness wait mechanism. Keep the user informed during the wait. Do not start one opaque blocking sleep process.
3. Re-run the helper with one `--tweet-id` argument for every retained ID, in the original order:

```bash
"$HEALTH_PYTHON" "$HEALTH_SCRIPT" \
  --tweet-id 2090000000000000001 \
  --tweet-id 2090000000000000002 \
  --json
```

The exact cohort fails if a requested ID disappeared. Never substitute newer posts.

- `regression_gate=complete` completes the enrichment regression gate.
- `regression_gate=inconclusive` means the cohort remains fresh-pending. Report it as non-alarming but incomplete verification.
- `regression_gate=failed` means persisted health is unhealthy. Report the affected tweet IDs, brands, stages, and reason codes.

Do not retry after the exact-cohort observation. Return the result to the calling plan, LFG pipeline, or operator.

## Report the result

Include:

- route used: immediate or enrichment-relevant
- cohort size and exact tweet IDs
- complete, pending, and unhealthy counts
- overall `status` and `regression_gate`
- bounded per-post stage and reason details for unhealthy rows
- any stable operational error code
- the saved report path when `--report` was requested

Do not propose harvest, prompt, model, cursor, scheduler, or data repairs from this skill. Diagnosis and remediation require a separate scoped request and the repository harvester guardrails.

# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## x-monitor pipeline

The x-monitor service ingests social-media posts about AI/LLM brands, classifies them, and persists the results. The vocabulary below is scoped to the run-summary layer that operators read at the end of each pipeline run.

### Run summary

The JSON document emitted by `x_monitor run` after one pipeline execution. It carries the per-call result rows, the run totals, and a `degraded` block that flags known-acceptable operational degradations (for example, a brand whose keyword table is empty). Operators read this to decide whether a run succeeded.

A `degraded` block with entries is a *signal*, not a failure — entries name known conditions the pipeline tolerated, and an empty block is the cleanest signal.

### Call

One execution of a fetch+classify cycle. Calls are identified by short string codes (`A`, `B1`, `B2`, `B3`, `C1`, `C2`) chosen at planning time. The run-summary's per-row `query_id` field carries the same code.

The codes partition into three shapes by intent: `A` is a curated-list pull, the `B` family is a wide-net brand-token search, and the `C` family is a co-occurrence (AND-filter) search over polysemous brands.

*Avoid:* query id, query_id — these were the legacy names that carried `Q`-string ids before the planner adopted the current short-code scheme.

### Brand keyword

A token (or token OR-chain) associated with a single brand, used by the pipeline's keyword index to match candidate posts. Each brand has one primary keyword chain used by default, and may carry additional non-primary chains.

The primary chain is what the pipeline reads for a brand-wide call; non-primary chains exist for future routing needs.

### Brand keyword gap

A state where a brand listed in the pipeline's enabled-models set has no primary brand-keyword row. A gap surfaces in the run summary as a per-brand `missing_brand_keywords:<brand>` entry rather than blocking the run.

The pipeline tolerates gaps so a partial keyword table still produces a run summary; closing a gap requires adding the row, not relaxing the check.

### Classification upsert

The act of writing one `(post, brand, post_type, sentiment)` triple into the classification store. If the triple already exists, the write becomes an update on the same row.

The store keeps a run-level counter of upserts attempted (which counts both new inserts and updates). That counter answers "did the classifier run?", not "how many new rows landed in the DB?" — a row updated twice still counts twice.

### Post-fetch classification

A second classification pass that runs after the initial fetch+classify loop completes, used to re-classify posts against the full brand set once translation and other enrichments are done. The post-fetch pass writes to the same classification store as the inline pass, so a single per-post triple can be written by both passes.

Because post-fetch runs after the per-call loop, any run-summary counter that snapshots inside the loop will miss post-fetch writes. The snapshot must happen after post-fetch completes.

### Operator-degraded entry

A named key in the `degraded` block of the run summary, signaling that a known condition was tolerated rather than treated as a failure. Naming convention: `<condition>:<detail>` so operators can pattern-match by condition prefix.

The pattern matters because operators triaging failures want to grep a stable prefix (e.g., `missing_brand_keywords:`) rather than read full messages.

## Flagged ambiguities

- "query id" was used for both the v1.6 `Q`-string ids (`Q1`..`Q6`) and the v1.7 short-code call ids (`A`, `B1`..`C2`). The v1.7 call id is canonical; `Q`-string references in older docs are historical-only.
- "call" was used for both the *plan* unit (one fetch+classify cycle) and the *type* (account vs brand-wide). Both are in use; the type is named "call kind" to disambiguate.

## Translator env-vs-yaml precedence

The rule that resolves which source wins when both `config.yaml` and process env vars supply a value for the same translator setting.

### Rule

**`yaml wins over env for non-null values. A yaml literal `null` is NOT "set" — it is an explicit instruction to use the default fallback path, and the env override takes effect.**

The rule encodes the distinction between *an active pin* (yaml sets a value the operator wants enforced) and *an inert placeholder* (yaml keeps the key but signals "use the default"). Reading `config.yaml:99-105` and seeing `translator_base_url: null` with the comment `# uses ANTHROPIC_BASE_URL env when null` is the canonical reference; the `x_monitor/config.py:384-397` env-merge block is the canonical implementation.

### Resolution chain (translator client)

`build_translator_client_from_env` resolves the translator's base URL as:

1. `cfg.llm.translator_base_url` (yaml-loaded, env-merged) if non-null
2. otherwise `ANTHROPIC_BASE_URL` env var (the process-wide default)
3. otherwise direct Anthropic

The model name resolves as: `cfg.llm.translator_model` (yaml-loaded, env-merged) → `X_MONITOR_TRANSLATOR_MODEL` env var → default `deepseek-v4-pro`. The model name and base URL are independent — a yaml `null` for one does NOT block the env override for the other.

### Translator base URL

The endpoint the translator pipeline calls for the message-translate stage. Set via `X_MONITOR_TRANSLATOR_BASE_URL` env var or `config.yaml llm.translator_base_url`. The classifier has a separate env override (`X_MONITOR_CLASSIFIER_BASE_URL`) and field (`cfg.llm.classifier_base_url`) because the translator and classifier may need different endpoints.

*Avoid:* `translator_endpoint` — the canonical name is base URL, matching the Anthropic SDK's `base_url` parameter.

## Trend narratives

Vocabulary for the shared V22 headline generated after eligible committed
harvest cycles. The detailed behavioral contract is in
`docs/reference/headline-trend-narratives.md`.

### Trend analysis snapshot

The immutable, bounded PostgreSQL result for one fixed window and fact cutoff.
It contains deterministic candidate rankings, complete coarse/fine series,
coverage, exceptional episodes, and selected evidence. It is persisted in
`TrendNarrative.generation_facts`; only a smaller provider projection crosses
the LLM boundary.

### Measured candidate

A database brand/full-window or brand/episode identity whose volume,
engagement, and metadata facts were computed from post-brand associations. One
or two measured candidates may be reported, and their candidate IDs must come
from the persisted snapshot.

### Evidence-only entity

One optional secondary company, brand, product, model, or organization directly
named by at least two independent evidence excerpts but not measured as a trend
candidate. Until entity discovery/resolution is implemented, an off-list name
is persisted as an unresolved subject and must never be described as having a
measured trend.

### Narrative slot

The irreversible outbound-call entitlement reserved for one
`(source_cycle_id, window_days)` ledger row before network transport starts.
Logical task delivery, a consumed slot, transport start, transport completion,
and valid publication are distinct events; there can be at most one slot per
source-cycle/window and four per envelope.

### Last-good narrative

The one current published `TrendNarrative` for a window. Failed, suppressed,
disabled, stale, or superseded attempts do not erase it; the public projection
continues to serve it unless serving itself is disabled.

## x-monitor deployment

Vocabulary scoped to the launchd-based deployment story — the two LaunchAgents, the pause sentinel, and the in-process lockfile that prevents overlapping cycles.

### LaunchAgent

A macOS launchd unit file (`.plist`) registered in `~/Library/LaunchAgents/` that launchd runs on a trigger. The x-monitor service uses two agents whose names describe what they fire on: `com.fuchitalee.x-monitor.harvest` (quarter-hour `StartCalendarInterval`) and `com.fuchitalee.x-monitor.config-reload` (`WatchPaths` on `config.yaml`).

The agent's name is the operator's first point of orientation — it determines which log file to read, which plist to unload, and which wrapper script's behavior to inspect. Agents are renamed by editing the plist's `Label` key and the install scripts that `cp` it into `~/Library/LaunchAgents/`; the operator must `launchctl unload` the old Label before the new one can take effect.

### Pipeline lock

A `fcntl.flock` advisory lock held on `data/runs/LOCK` for the duration of one `python -m x_monitor run` cycle. A second concurrent cycle sees the lock held and exits 0 with `degraded:already_running: true` in its run JSON rather than double-spending the daily TwitterAPI.io budget.

The lock file is opened as FD 3 by the running process; `lsof data/runs/LOCK` shows the owner. If a cycle hangs (e.g. on the TwitterAPI.io SSL read), the lock is held until the process is killed. SIGTERM releases the FD cleanly; SIGKILL also works but skips Python's atexit cleanup.

### Pause sentinel

A zero-byte file at `/tmp/x-monitor-paused` whose presence gates all pipeline runs. Both wrapper scripts (`deploy/run-pipeline-watchpaths.sh`, `deploy/run-pipeline-with-notify.sh`) check for it as the first action and `exit 0` without touching TwitterAPI.io if present.

The sentinel is invisible from `launchctl list` output — a paused pipeline looks like a quiet one to launchd. `touch /tmp/x-monitor-paused` halts both agents cleanly without unloading them; `rm /tmp/x-monitor-paused` resumes. `/tmp` is persistent across reboots on macOS unless explicitly purged, so the sentinel survives restarts.

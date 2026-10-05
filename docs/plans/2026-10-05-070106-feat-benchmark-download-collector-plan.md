---
title: feat/benchmark-download-collector plan
artifact_contract: ce-unified-plan/v1
product_contract_source: session-approved-feature-brief
execution: code
ollija:
  change_id: feat-benchmark-download-collector-2026-10-05-070106
  branch: feat/benchmark-download-collector
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/benchmark-download-collector`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/benchmark-download-collector/docs/plans/2026-10-05-070106-feat-benchmark-download-collector-plan.md`
- Change: `feat-benchmark-download-collector-2026-10-05-070106`
- Branch: `feat/benchmark-download-collector`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/benchmark-download-collector/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/benchmark-download-collector/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`
- Delivery route: `staged`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the parent implementation workflow; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

The owner explicitly invoked LFG on 2026-10-05. This authorizes implementation,
local verification, scoped commits, push, opening a pull request, and observing
CI. It does not authorize merging, production or staging changes, a scheduler,
or production data writes. The generated on-request guide supplies no authority
beyond this current request. Reviews execute inline under AGENTS.md's Task mapping.

# Benchmark and download collector

## Plain-English Summary

Build a separate tool that compares existing brand post counts with Arena scores,
Hugging Face downloads, and OpenRouter token usage on aligned daily charts. It
reads an exported copy of the current company, brand and product catalog, saves
its own observations, and produces an HTML report that opens in a browser.

The existing taxonomy remains authoritative. Arena and OpenRouter models must
be explicitly linked to a stable product ID with supporting evidence. Unmatched
models remain visible as unresolved; their provider names never create brands.

This is adjacent to G1–G5 and can be developed independently. It changes no live
page, harvest job, catalog record, database schema, or production service. Tests
will exercise identity mistakes, missing data, pagination, collection failures,
and chart values; a browser check will cover the actual report. Public API probes
are bounded. Authenticated OpenRouter verification requires a dedicated key.

## Goal Capsule

Deliver a reproducible, isolated collection/report workflow and reviewed PR.
The smallest honest shared comparison window is one UTC day: finer timestamps
are retained, but HF's public number is rolling 30-day downloads, Arena changes
when results are published, and OpenRouter exposes completed daily usage.

## Product Contract

### Summary and problem frame

Post volume already exists by canonical brand. The missing evidence is how that
attention changes alongside measured performance and observed model adoption.
A first pass must make those comparisons without inventing precision or merging
unrelated models that happen to share a provider or similar name.

### Requirements

| ID | Contract |
| --- | --- |
| R1 | Preserve existing company/brand IDs and Product.product_key. Support products with no HF repo. Read-only export; never mutate the source catalog. |
| R2 | Exact, reviewed source-model mappings with an evidence URL and explicit product key. Reject unknown targets, duplicate source IDs, invalid HF ownership and malformed input. Unresolved IDs are reported. |
| R3 | Arena overall text_style_control scores from the official public HF dataset, including publication date, uncertainty and votes. Paginate within explicit limits and reject incomplete results. |
| R4 | HF public download counts for explicitly selected canonical official LLM repositories. Store rolling 30-day and all-time values with observation time; no inferred daily download counts. |
| R5 | OpenRouter documented rankings-daily data: daily UTC tokens for individually reported models. Retain meta.as_of, exact model IDs, variants and other bucket. State top-50 coverage; never distribute other across brands. |
| R6 | Versioned immutable local snapshots include source URLs, timestamps, taxonomy and mapping digests, raw rows and per-source status. Failed requests never become zeros. Repeated snapshots do not double-count report values. |
| R7 | Four aligned daily panels for a selected brand: posts, Arena rating, HF rolling downloads, OpenRouter tokens. Clearly label units, coverage, score's model, observed/published dates, empty/failure states and source attribution. |
| R8 | Brand Arena score is the maximum mapped score in each complete publication, held until the next publication. A brand missing in a later publication becomes N/A; no carrying across methodology/config changes. |
| R9 | Daily HF totals use the latest complete observation for the exact selected repository cohort. Missing repos yield N/A with coverage counts. Missing observation days have gaps. HF unavailable for a brand with no selected repo is N/A. |
| R10 | Daily OpenRouter totals sum distinct mapped reported rows. Label them a partial platform measure. A brand absent from top-50 or containing unresolved rows is not claimed to have zero total usage. |
| R11 | Existing post counts are distinct collected posts attributed to each brand by PostBrand, by Post.created_at UTC day. Explicitly label this scope; it is not the homepage's separately filtered projection. Zero is allowed only inside the read-only export's declared window. |
| R12 | Bounded requests, pages, response bytes and time; credentials never stored or printed. A partial run persists outcomes and exits nonzero. Offline fixtures and report generation require no credentials or database. |

### Scope and decisions

- KD1 (session-settled: user-directed): separate worktree/package and local data,
  chosen over G6 or live integration because work must remain independent.
- KD2 (session-settled: user-approved): Arena first, HF downloads, OpenRouter
  tokens; chosen over a broad benchmark portfolio to keep the first pass small.
  AA, LiveBench, Terminal-Bench and DeepSWE integrations remain deferred.
- KD3 (session-settled: user-directed): HF-derived canonical taxonomy wins;
  provider catalogs are observations, not new taxonomy authorities.
- KD4 (session-settled: user-approved): daily aligned panels with actual units,
  chosen over minute interpolation or a synthetic combined popularity score.
- OpenRouter is usage, not downloads; HF counts file requests, not unique users.
- No scheduler, catalog discovery, fuzzy identity matching, paid inference,
  production reads/writes, chart integration, or historical HF reconstruction.

## Planning Contract

### Existing evidence and reuse

- core/models.py: Brand, Company, BrandCompany, confirmed HFOrg, Product UUID
  identity and optional repo_id; PostBrand uniquely joins a post and brand.
- core/hf_metadata_client.py: bounded public JSON requests, retry/time/byte
  budgets and identity validation. Add a narrow download-count method, leaving
  existing group behavior intact; reuse its public HF request implementation.
- tests/test_hf_metadata_client.py and tests/test_product_identity.py provide
  regression coverage for existing client behavior and closed-weight identity.
- monitor/views.py's homepage chart has separate filters; don't silently borrow
  its labels for an all-collected-post export.

### Technical decisions

KTD1: Use scripts/benchmark_download_collector as a plain Python module with a
small CLI. Store one self-contained JSON snapshot per run and render a standalone
HTML file. No migrations or new runtime services. This is an implementation bet
with low reversal cost: future integration can import the pure normalization code.

KTD2: A read-only Django management command exports selected brands, company
links, canonical LLM products, confirmed HF ownership and daily post counts.
Postgres transaction is read-only and repeatable-read for a consistent export;
tests prove it cannot write. Require explicit brand selection and bounded dates.
The export describes data as observed, not historic taxonomy assignments.

KTD3: A reviewed mapping file separately selects HF repos and maps exact Arena
model_name / OpenRouter model_permaslug to product_key. Include evidence for each
mapping; validate identity ownership without modifying canonical records. A
mapping-template command lists canonical products and observed unresolved IDs,
so the workflow is usable without editing application code. No guessed mappings.

KTD4: Snapshots carry the full frozen input and mapping, observation UTC time,
contract version and provider outcomes. Atomic exclusive creation prevents
clobbering. Reports refuse mixed taxonomy/mapping/cohort contracts rather than
silently reattributing historical data. No generic persistence framework.

KTD5: Arena defaults to its small official latest Parquet artifact, decoded
with the optional benchmark extra (PyArrow), bounded bytes/rows/decoded size and
public HF/CDN redirects. Preserve the artifact digest. Optional --arena-history
uses overall-category/date filtering with bounded pagination and 30-day carry-in.
The filtered endpoint returned index-loading errors/timeouts in bounded probes;
the latest artifact returned 413 overall rows dated 2026-10-02. This selects a
reliable collection route without promising unavailable historical scores. Only carry forward an observed earlier score; never backfill before
its publication. Each publication replaces its preceding model population.
OpenRouter dates are requested explicitly and must be completed UTC days.

KTD6: HTML renders offline with embedded escaped JSON, no CDN or executable
provider text. Use SVG lines and visible tabular values/tooltips, a brand control,
date range, bilingual EN/中文 labels, accessible names and mobile layout. Plain
report UI is the only touched visual surface; preserve every application page.

### Risks and resolved review points

- Source shape drift: validate required IDs, dates, numbers and pagination totals;
  fail that source rather than returning an apparently complete subset.
- Top-50 coverage: even mapped sums cannot be called full brand usage. Preserve
  other and unresolved counts, token strings and attribution in snapshots/report.
- Same-day retries or history overlap: deduplicate by source/date/identity and
  use the latest complete snapshot. Never add repeated observations together.
- Partial HF cohorts: show N/A with successful/selected counts instead of a
  misleading drop. Cohort changes require a new report collection directory.
- Export contains observed attribution; it does not establish when a catalog
  mapping became true. Freeze it per collection directory and disclose this.
- Failed collection on a later day leaves a visible failed observation, while an
  earlier valid Arena publication can remain visible with its publication date.

## Implementation Units

### U1 — Frozen taxonomy, reviewed mapping, read-only post export

Files: scripts/benchmark_download_collector/{__init__,identity}.py;
monitor/management/commands/export_benchmark_inputs.py;
tests/test_benchmark_download_identity.py and test_benchmark_download_export.py.

Implement versioned input validation, stable IDs, explicit source mappings and
HF official-repo selection. Export selected brands, products, companies and
UTC daily distinct PostBrand counts with a read-only Postgres transaction.
Test closed-weight products, same-company different brands, same-name different
versions, duplicate source IDs, invalid keys, unconfirmed namespaces, cross-brand
ownership, exact UTC boundaries, count scope and DB immutability.

### U2 — Bounded provider collection and atomic snapshots

Files: core/hf_metadata_client.py;
scripts/benchmark_download_collector/{collect,sources,__main__}.py;
tests/test_benchmark_download_sources.py and test_benchmark_download_cli.py.

Implement Arena pagination/filtering, HF narrow counts, OpenRouter daily request
and strict response validation. Enforce request/time/size/page limits, persist
source failures, raw rows, provenance and exact identity strings. No HTTP on
validate/report/demo paths. Keep OR credentials only in request headers, on the
fixed official host, with redirects disabled. No arbitrary source URL option.
Test pagination gaps, changed totals, duplicate model rows, 429/500/401, timeout,
malformed JSON, redirect, missing credentials, oversized/negative counters,
other bucket handling, atomic writes and replays.

### U3 — Honest daily series and standalone report

Files: scripts/benchmark_download_collector/{series,report}.py and report.html;
tests/test_benchmark_download_series.py plus a browser smoke script if useful.

Join by frozen product_key→brand, replace Arena publication populations, retain
score uncertainty/model, select latest daily complete HF snapshot, and sum
mapped OR rows without other. Align days with exported posts. Render responsive
four-panel report and data table, source timestamps/coverage and unresolved model
lists. Include an offline demo clearly labeled synthetic and an unresolved-mapping
workflow. Test exact values and missingness, Unicode/script injection, repeated
runs, identity-contract drift, brand controls, axis alignment and narrow screens.

### U4 — Regression net, operating instructions and coordination

Files: scripts/benchmark_download_collector/README.md, focused CI workflow,
this plan, and a small independent-work pointer in the shared launch index.

Document export→mapping→collect→report commands, public API sources, limits,
credential variable, daily semantics, partial failures, data isolation and later
integration. Add a CI job using Postgres and the focused regression set. Validate
unchanged HF client and product identity tests alongside the new end-to-end
fixture flow. No production health or harvest calls. Record ON/OFF coordination
without changing another session's claims or the G1–G5 charter.

## Verification Contract

- Run focused pytest files for this feature plus tests/test_hf_metadata_client.py
  and tests/test_product_identity.py against a dedicated local Postgres test DB.
- Run ruff on owned Python files and git diff --check.
- Run the actual offline demo CLI, report CLI and mapping workflow.
- Perform one bounded public HF download request and a small bounded official
  Arena filter request. Verify OR live only if its dedicated key is available;
  otherwise explicitly record fixture-only authenticated adapter coverage.
- Open generated report with the installed agent-browser driver; verify controls, labels, rendered series,
  data table, no console errors and mobile overflow. The homepage is untouched,
  so its Bridgewright comparison profile is not applicable.
- Inline simplify and code review (not independent-agent review), resolve all
  material findings, then scoped commit/push/PR and CI observation.

## Definition of Done

The isolated CLI produces trustworthy daily comparison reports from validated
snapshots; source failures and mapping gaps are visible; no existing catalog or
runtime behavior changes except the additive tested HF count reader; meaningful
focused tests and browser checks pass; instructions and coordination are present;
the PR exists remotely with a recorded CI result. No deployment is implied.

## Execution evidence — 2026-10-05

U1–U4 are implemented in the isolated worktree. The focused regression set passed
89 tests, including all three required PostgreSQL tests with no skips. The set
includes the existing HF client and product identity tests. Ruff and whitespace
checks are required again before the final scoped commit.

The actual offline CLI flow and browser report were exercised in English and
Chinese, with brand/date controls, invalid-date feedback, four aligned axes,
mobile width, keyboard access, no JavaScript errors and no axe violations.

Public probes verified HF download metadata and 413 overall Arena rows from the
latest official Parquet file. The historical filter endpoint timed out while its
index was loading. The dedicated OpenRouter key was absent, so authenticated
OpenRouter coverage uses strict response fixtures; no live success is claimed.

Local review roles ran sequentially under AGENTS.md. An external Grok CLI review
completed and corroborated the Arena date-boundary finding; its serving family
was verified, but its exact model/effort was not. Three confirmed defects were
fixed: stale post/usage revisions replacing newer values, mixed demo/live inputs
losing their warning, and today's Arena publication being discarded by yesterday's
OpenRouter window. Regression tests reproduced each defect before the fix.

The shipping endpoint remains an open PR with CI observed. The authoritative
launch index carries this independent task's ownership and final PR reference;
it does not make this work a G6 dependency or authorize deployment.

## Sources

- [HF model downloads](https://huggingface.co/docs/hub/models-download-stats)
- [HF dataset filtering](https://huggingface.co/docs/dataset-viewer/filter)
- [Official Arena dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset)
- [OpenRouter daily rankings API](https://openrouter.ai/docs/api/api-reference/datasets/daily-token-totals-for-top-50-models)

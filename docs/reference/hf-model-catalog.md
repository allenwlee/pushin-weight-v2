# HF model Product catalog

The manual collector creates one Product per public model repository on a
confirmed Hugging Face publisher account. It includes old models, adapters,
and quantizations. It refreshes existing Products without changing their stable
ID, repository identity, or curated name/brand. No scheduler or model download is added.

## Preview and collect

Use the Django command with the intended environment's `DATABASE_URL`.
Preview reads publisher mappings only; it makes no HTTP requests or writes.

```sh
python manage.py import_hf_product_catalog --all-tracked
python manage.py import_hf_product_catalog --brand minimax --confirmed-namespace MiniMaxAI
```

All-tracked resolves `config.yaml` enabled brands plus the `openai`,
`anthropic`, `google`, and `xai` companies. Company ownership comes from
`BrandCompany`; accounts must already have `HFOrg.confirmed=True`. The preview
lists unresolved and unconfirmed mappings. Resolve them through reviewed
onboarding; never confirm an account merely because its name resembles a company.

First validate against an isolated local PostgreSQL test database, then Render
staging. A bounded staging sample uses at most 12 physical requests, 120 seconds,
and three repositories:

```sh
python manage.py import_hf_product_catalog --brand minimax --confirmed-namespace MiniMaxAI \
  --max-models 3 --max-requests 12 --max-seconds 120 --commit
```

`--commit` permits public metadata requests and database writes. It is unrelated
to a Git commit. Production collection requires a separate explicit request.

```sh
python manage.py import_hf_product_catalog --all-tracked --commit
python manage.py import_hf_product_catalog --resume RUN_UUID --commit
python manage.py import_hf_product_catalog --all-tracked --refresh --commit
```

Default invocation limits are 1,000 physical requests, 900 seconds and 16 MiB
per decoded response. Transient failures get at most three attempts per request
group, with bounded server-directed backoff. Every retry counts. Limits can be
changed explicitly; raising a byte cap makes an oversized group retryable.
Successful groups are skipped on resume. A refresh creates a new run, preserving
old observations. `--cursor` is retired: resume by run UUID so the command can
account for the earlier pages and pending enrichment.

The process exits with code 2 after printing JSON when collection is incomplete.
The report separates `enumeration_complete`, `enrichment_complete`, scope gaps,
attribution gaps, group outcomes, and ownership conflicts. `imported` and
`updated` are distinct repository counts across the entire run; `requests` is
per invocation and `cumulative_requests` includes earlier invocations. Do not
interpret a bounded sample, a short page, or an empty inaccessible account as
complete coverage. The walk covers an observation interval, not an atomic Hub
snapshot; use a fresh full refresh to reconcile concurrent publisher changes.

## Metadata and attribution

For every repository the collector requests default detail with `blobs=true`
and `securityStatus=true`, then a separate repeated-parameter `expand` query.
The two requests capture file/security data and extra model fields respectively.
This follows the [official model-info contract](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api#huggingface_hub.HfApi.model_info).
If an expanded projection is rejected, a bounded smaller request preserves
partial evidence and the group remains incomplete.

`Product` retains queryable common columns. `hf_metadata.fields` keeps other
returned fields, with per-field source groups and observation/revision references.
Detailed file entries take precedence over lean siblings. A newer value from
the authoritative group replaces its old value, including explicit nulls or
empty lists. Omitted fields and failed requests do not erase successful metadata.
Download/like columns support 64-bit counts. Download velocity is not inferred.

`Product.raw` is a compatibility projection that retains unrelated evidence.
Original response payloads live in the ledger, with request parameters, HTTP
outcomes, times, and revisions. Different detail/expanded SHAs remain visible
as separate observations, not a fabricated single revision. Cards and unknown
nested fields are stored as source data; they never execute as instructions.

An existing compatible brand remains assigned. Otherwise reviewed rules in
`config/hf_catalog.yaml` may select a brand by exact repository or name prefix.
Rules require a source URL and cannot overlap. A company with exactly one brand
can supply the default; shared-company repositories without a rule retain null
brand and appear in the report. HF task labels remain source metadata; all collected repositories use `hf_type=model`.

## Persistence and recovery

- `hf_model_catalog_runs`: frozen scope, invocation budgets/counters, report.
- `hf_model_catalog_namespace_runs`: ownership, page responses, continuation history.
- `hf_model_catalog_observations`: unique repository per run, original responses,
  group status, Product link, and creation outcome.

Each page's observations, minimal Products, and next cursor commit together.
Enrichment follows outside that transaction. An invalid saved cursor triggers
one restart from the beginning, deduplicating through the existing ledger.
An advisory database lock allows one catalog invocation at a time, and Product
row locks protect concurrent reviewed edits. Network requests never hold Product
locks. An interrupted run can resume; no deletion or automatic retention is added.
Namespace ownership changes require a new preview/run.

Staging data refresh copies Products but excludes and scrubs catalog ledgers,
preventing a production checkpoint from masquerading as a staging run. Metadata
observation references on copied Products refer to historical source evidence;
they do not imply that the original ledger was copied.

## Validation recorded on 2026-09-24

The live fixture `tests/fixtures/hf_catalog/2026-09-24-minimax-public-metadata.json`
captures one verified MiniMaxAI account and one model in four anonymous requests:
identity, a one-model page with continuation, detailed metadata, and expansion.
Both metadata groups succeeded. Detail included `securityRepoStatus`; expansion
included `downloadsAllTime`, `childrenModelCount`, and `inferenceProviderMapping`.
This verifies request serialization and payload shapes; it is not a full catalog
import or staging-write acceptance.

The standalone branch is based on `main` at `d5694e7`. It uses the existing
integer Product ID and required unique repository ID. Rare-type verification,
review, UUID/type additions, and cycle changes are excluded. Historical live
results below used the earlier combined checkout; standalone acceptance is
recorded separately in the implementation review.

Before main-based isolation, the real command imported three public MiniMaxAI models into the dedicated
local database `hf_catalog_acceptance_20260924`: eight requests, three new
Products, both enrichment groups complete, exit code 2 with a saved continuation
because the model cap intentionally stopped enumeration. Product raw JSON and
metadata used 121,023 stored bytes together for that sample, excluding the
observation ledger and indexes. The report is in
`docs/analysis/hf-catalog/2026-09-24-081422-local-acceptance.json` (UTC filename).

A read-only inspection of Render staging found no confirmed HF accounts for
the four frontier companies. Several tracked accounts remain unconfirmed and
some brand/company mappings use different company keys (including Upstage,
EXAONE, and Kuaishou). Those gaps must be reconciled before claiming full scope.
The collector does not silently repair them.

After staging deployment, inspect the JSON report and persisted groups, resume
the same bounded run, and confirm Product IDs stay stable. Monitor each
invocation through its run report; stop on unexpected ownership reassignment,
lost curated fields, or request totals above the configured cap. The operator
running the batch owns this validation. Preserve partial ledgers for diagnosis.

Migration `0045_hf_catalog_observations` is additive apart from widening count columns. Roll back code
while retaining this forward schema and its evidence if a staging defect is
found; do not reverse the migration after collection, because the old integer
columns cannot represent the newly supported large counts. Before collection,
verify `hf_metadata` exists, all three ledger tables exist, and Product IDs and
relationship counts match their pre-migration values. After a bounded run:

```sql
SELECT id, outcome, report FROM hf_model_catalog_runs ORDER BY started_at DESC LIMIT 1;
SELECT namespace, enumeration_complete, outcome, raw_count
FROM hf_model_catalog_namespace_runs WHERE run_id = 'RUN_UUID';
SELECT repo_id, outcome, groups, product_id
FROM hf_model_catalog_observations
WHERE namespace_run_id IN
  (SELECT id FROM hf_model_catalog_namespace_runs WHERE run_id = 'RUN_UUID');
```

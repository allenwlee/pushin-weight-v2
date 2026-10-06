# Benchmark and download collector

Compare collected posts with Hugging Face downloads, OpenRouter token usage and
Arena scores and ranks. The database-backed Pulse page reads a reviewed product
crosswalk and retained measurements from PostgreSQL. Each line shows its actual
scope, baseline date, raw value and source evidence. Missing data stays missing.

The database integration is a disabled candidate for review. It introduces fifteen
tables and generalizes existing accounts so X and HF accounts have separate source
identities. Production deployment, collection schedules and page activation require
a separate release decision. The original offline diagnostic report remains
available below.

This is independent work adjacent to G1–G5, not a G6 dependency. Coordination lives
in the authoritative [General Launch Index](../../docs/brainstorms/2026-09-30-104924-general-launch-index.md);
the implementation contract is in the [plan](../../docs/plans/2026-10-05-070106-feat-benchmark-download-collector-plan.md).

## Database workflow

Use a dedicated local PostgreSQL database. Set `DATABASE_URL` explicitly; the
Django commands otherwise use the application's configured database. Install
`.[dev,benchmark]` so the Arena Parquet reader is available.

1. Apply migrations in the isolated database. Review product types, account
   ownership, taxonomy relationships and exact provider identifiers before writes.
2. Validate a taxonomy manifest with `configure_measurement_taxonomy`; use
   `--apply` to retain it. Its immutable version contains reviewed subjects,
   relationships, group rules and business affiliations.
3. Register definitions, bridge confirmed HF namespaces to generic accounts, and
   validate the collection manifest. `--apply` writes a new immutable contract;
   it does not enable polling. Changed definitions, mappings or methodology get
   a new contract, preserving old results.
4. Validate bounded archive manifests, then import with `--apply`. Collect current
   data separately with the manual collection command. Replaying the same history
   manifest or collection batch is idempotent. A changed source revision is a new
   observation, not an overwrite.
5. Query a named comparison or enable the page in an isolated preview environment.

```sh
python manage.py configure_measurement_taxonomy taxonomy.json
python manage.py configure_measurement_taxonomy taxonomy.json --apply
python manage.py configure_benchmark_collection --register-definitions --apply
python manage.py configure_benchmark_collection --hf-account deepseek-ai \
  --reviewed-by 'reviewer' --evidence-url https://huggingface.co/deepseek-ai --apply
python manage.py configure_benchmark_collection collection.json
python manage.py configure_benchmark_collection collection.json --apply
python manage.py import_benchmark_history history.json
python manage.py import_benchmark_history history.json --apply
python manage.py collect_benchmark_metrics --contract CONTRACT_UUID --source hf \
  --start-date 2026-10-06 --end-date 2026-10-06 --batch-id BATCH_UUID --apply
python manage.py benchmark_series --contract CONTRACT_UUID --preset deepseek \
  --end-date 2026-10-06
python manage.py benchmark_collection_health --contract CONTRACT_UUID
```

For OpenRouter, provide `BENCHMARK_OPENROUTER_API_KEY` in the command's environment.
Do not put the key in a manifest or shell history. Select completed UTC days only;
its command accepts `--source openrouter`. HF collects current counters regardless
of the supplied reporting dates; historical HF values require archive import.
Arena's direct command reads its latest complete publication. No provider network
call runs inside a page request.

The page and JSON endpoint are `/benchmarks/CONTRACT_UUID/PRESET/` and its
`series/` child. `BENCHMARK_METRICS_ENABLED` defaults to false (404). Enabling it
exposes aggregate comparisons under the same public-access policy as the current
homepage. Only enable it on the intended environment. Optional `start` and `end`
query parameters must remain inside the reviewed launch/coverage range and 366-day
budget. Responses use `no-store`; late posts and new measurements appear on reload.

## Time, scope and interpretation

The owned taxonomy uses products as precise measurement subjects, alongside brands,
companies and reviewed groups. Technical derivation does not imply ownership.
Post assertions preserve broader mentions: a company-only mention does not become
a mention of every product. Rollups count distinct posts. The initial two Pulse
presets deliberately use existing brand-wide post counts against exact Flash
provider identifiers; that distinction is visible in the chart.

`SourceMetric.measurement_kind` separates `state` and `flow`. State observations
have an instant or date. Flow windows have separate definition and optional exact
start/end fields, never a suffix embedded in a metric name. Unknown source cutoff
and timezone remain unknown. HF rolling downloads are not daily download totals;
OpenRouter counts cover completed UTC days; Arena states carry forward only from
an actual publication. A later complete publication omitting the selected model
clears that state. A selected-row historical extract cannot establish omission.

Normalization is `100 * (value / baseline - 1)`, not a sum of daily changes. A
zero/missing launch baseline cannot produce a percentage. An explicitly selected
later baseline is disclosed. Integer values travel as strings so large token totals
retain precision. Arena raw score/rank, uncertainty bounds and votes remain stored.

## Save a database-backed offline report

`python manage.py render_benchmark_report --contract CONTRACT_UUID --preset deepseek
--end-date 2026-10-06 --output /path/to/new-report.html` saves the existing four-panel
raw-value report from the same `build_comparison` result as Pulse. The output path
must be new. This reads the database and makes no provider calls. Each panel accepts
one matching line in the preset; ambiguous duplicates are rejected.

The report retains per-line scope and coverage in its diagnostics and embeds the
complete five-line response, including rank, baselines and provenance, in
`database_comparison`. Arena rank remains available in Pulse and the embedded
response; the retained four-panel layout shows Arena score. Unmapped platform
totals absent from this response stay unavailable. Legacy snapshot reports remain
available as a separate diagnostic input.

## Disabled operations and future release

Reviewed source configuration freezes polling interval, freshness thresholds,
completed-day lag, revision recheck range and request/time/byte caps. Defaults are
24-hour polling, 48-hour retrieval freshness, seven-day publication freshness,
one completed-day lag and seven-day recheck. These are provisional configuration,
not an active schedule or a promise about provider publication timing. The manual
command caps its requested budget at the reviewed contract's caps. `collect_benchmark_due --contract CONTRACT_UUID` reports due work without calls.
Its `--apply` requires `BENCHMARK_COLLECTION_ENABLED=true`, an enabled DataSource
and a reviewed contract with that source’s `scheduling_enabled=true`. It applies
the reviewed completed-day lag and revision recheck range, and uses stable polling
batch IDs. Owner-selected runtime activation remains required; this candidate
registers no cron or Celery beat task.

`benchmark_collection_health` separates the latest attempt, last fully successful
retrieval, selected-subject coverage and latest known effective date. Unknown timing
is not called fresh. Partial historical imports can supply useful measurements
without pretending the full selection succeeded. PostgreSQL advisory locks isolate
this collector from harvesting and prevent concurrent writes to a contract/source.
A database write failure leaves a running envelope and no half-written values.
After its ten-minute lease expires, replay marks it aborted; retry with a new batch
identifier. A terminal failed batch remains evidence and does not auto-retry.

Before any future production migration or deployment, take and verify a recoverable
**live database backup**. A snapshot a few hours before deployment is acceptable.
Record source database, capture/completion timestamps, backup ID/location, retention,
access verification and restore command or provider procedure. Record the gap
between snapshot and migration and any point-in-time recovery coverage. The local
projection and its rehearsal dump are not a production backup.

After a separately authorized release, verify the intended database and candidate
revision, apply migrations, load reviewed configuration, run bounded collection,
inspect persisted rows and only then enable the selected runtime schedule and page.
Rollback disables this feature's page/collection and retains evidence. Do not reverse
the mixed-source account migration destructively: forward-repair or restore the
verified backup using the recorded recovery procedure. Existing X harvesting remains
on its existing scheduler and credential route.

## Try the report without credentials

Run from the repository root with Python 3.11 or later:

```sh
python -m pip install -e '.[benchmark]'
python -m scripts.benchmark_download_collector demo \
  --directory .local/benchmark-demo \
  --output .local/benchmark-demo.html
```

Open the HTML file in your browser. It works offline, includes English and Chinese
labels, and is prominently marked **synthetic demo**. Select a brand or change the
date range. The daily table includes model names, uncertainty intervals, source
dates and coverage. Output files are exclusive: choose a new filename instead of
overwriting an existing report.

## Use actual observations

1. Export the existing taxonomy and post counts from an explicitly selected
   PostgreSQL database. The command opens a read-only, repeatable-read transaction
   so its reads form one consistent view. It selects public, enabled canonical
   `llm-model` products, including products with no HF repository. It makes no API
   calls and exports no post text or account records. Use authorized database
   access; the collector itself never connects to a database.

   ```sh
   python manage.py export_benchmark_inputs \
     --brands qwen deepseek \
     --start-date 2026-09-05 --end-date 2026-10-04 \
     --output .local/benchmark-inputs/catalog.json
   ```

2. Create a mapping template, then fill in the identities you have checked:

   ```sh
   python -m scripts.benchmark_download_collector mapping-template \
     --catalog .local/benchmark-inputs/catalog.json \
     --output .local/benchmark-inputs/mapping.json
   ```

   Select official HF repositories using their existing `product_key` values.
   Each Arena or OpenRouter entry requires an exact source ID, a canonical product
   key and a public evidence URL supporting the match. The following is a shape
   example; replace the UUID and model IDs with reviewed values from your catalog:

   ```json
   {
     "schema_version": 1,
     "hf_product_keys": ["00000000-0000-4000-8000-000000000001"],
     "mappings": [
       {
         "source": "arena",
         "source_id": "exact-version-and-configuration-name",
         "product_key": "00000000-0000-4000-8000-000000000001",
         "evidence": "https://example.com/official-model-announcement"
       },
       {
         "source": "openrouter",
         "source_id": "provider/exact-model-permaslug",
         "product_key": "00000000-0000-4000-8000-000000000001",
         "evidence": "https://example.com/official-model-announcement"
       }
     ]
   }
   ```

   Company names, provider names and similar model names never create a match.
   Reasoning configurations, dated versions and `:free` variants keep their exact
   source IDs. Several explicitly reviewed variants may point to one canonical
   product; OpenRouter rows are still counted once each. `other` cannot be mapped.
   An HF selection must belong to a confirmed HF namespace whose company is
   already linked to the product's canonical brand. The tool does not repair or
   create catalog identities; resolve absent canonical products separately.

3. Validate offline:

   ```sh
   python -m scripts.benchmark_download_collector validate \
     --catalog .local/benchmark-inputs/catalog.json \
     --mapping .local/benchmark-inputs/mapping.json
   ```

4. Set `PUSHINWEIGHT_OPENROUTER_DATA_API_KEY` in the request process's environment,
   using an OpenRouter API key you authorize for this task. The tool never loads
   another application's key or a secret file. Arena and public HF counts require
   no key. To collect just those public sources, use `--sources arena hf`.

   ```sh
   python -m scripts.benchmark_download_collector collect \
     --catalog .local/benchmark-inputs/catalog.json \
     --mapping .local/benchmark-inputs/mapping.json \
     --directory .local/benchmark-observations \
     --start-date 2026-09-05 --end-date 2026-10-04
   ```

   The default end date is yesterday in UTC. Requests share a budget of 80 physical
   requests, 180 seconds and 4 MiB per response, configurable with `--max-requests`,
   `--max-seconds`, `--max-bytes`. HTTP failures get at most three attempts. An
   exhausted budget is recorded as a failure. Exit code 2 means the snapshot was
   saved with a failed/partial source; exit code 1 means invalid inputs or a local
   output error. The snapshot contains no credentials or HTTP error bodies.

   Arena defaults to the official latest Parquet file (a compressed data table),
   with bounded public HF/CDN redirects and a saved content digest. It selects
   only overall `text_style_control` rows and retains today's publication even
   when OpenRouter's requested window ends yesterday. Earlier days stay empty until a
   publication is available. Optional `--arena-history` requests dated publications
   through HF's filtered dataset API, with 30 days of carry-in and a default
   50-page cap. That endpoint can be unavailable while its index is loading;
   failure is recorded, not silently replaced with a different metric.

   You can collect with an empty mapping first to discover exact source IDs.
   `mapping-template --directory .local/benchmark-observations` includes the
   unresolved IDs in a new template. Review those matches, then start a **new
   collection directory** for the new mapping. This keeps old observations from
   silently moving between products or brands.

5. Generate the report:

   ```sh
   python -m scripts.benchmark_download_collector report \
     --directory .local/benchmark-observations \
     --start-date 2026-09-05 --end-date 2026-10-05 \
     --output .local/benchmark-report.html
   ```

   Including today's date displays today's HF observation; OpenRouter for today
   stays unavailable until the day is complete. Refresh the catalog export under
   a new filename to extend post coverage, retaining the same identities and
   mappings. Overlapping post dates use the newest export; OpenRouter dates use
   the newest source `as_of`. A later run with an older export or source revision
   cannot replace newer values. Refreshed exports can correct earlier post counts.
   Repeated manual runs add snapshots without double-counting values.

## What each line means

| Line | Meaning and limits |
| --- | --- |
| Posts | Distinct collected `PostBrand` posts, grouped by the post's creation day in UTC. A post can count for multiple brands. This includes the collected attribution corpus, not the homepage's separately filtered view, and does not imply all posts on X were collected. |
| Arena | Highest **mapped** model rating in each complete publication. The source model, interval, votes and publication date remain visible. The rating holds until a later publication; a brand absent from that publication becomes unavailable. |
| HF downloads | Latest complete observation that day of rolling **30-day** downloads, summed across the selected official repositories. A missing selected repo makes the total unavailable. Days without observations are gaps. These are qualifying download requests, not unique users or new daily downloads. All-time counters are preserved without differencing them. |
| OpenRouter | Daily token totals for explicitly mapped models individually reported in the top 50. This is a partial measure of brand usage on OpenRouter. The long tail is an unassignable `other` bucket; absent models are not zero. Different providers use different tokenizers. |

All dates are UTC. The smallest honest common window is one day; polling more
often cannot turn rolling or published data into minute-level measurements.
HF public counters cannot reconstruct historical daily downloads. Historical
taxonomy and post attribution are not reconstructed either: exports reflect the
catalog and attribution observed at export time.

The collection directory freezes catalog identities, mappings and HF selection
using digests. Reports reject mixed contracts and mixed demo/live observations.
Start a new directory when those
choices change. Keep reports for different Arena methodologies separate; the
adapter's `score_contract` must change when its scoring configuration changes.
The tool cannot automatically discover undisclosed upstream methodology changes.

## Sources and attribution

- [Official Arena leaderboard dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset), CC BY 4.0. The report labels its overall style-controlled text scores.
- [Hugging Face download semantics](https://huggingface.co/docs/hub/models-download-stats). Collection reuses the existing bounded public HF metadata client.
- [OpenRouter daily dataset](https://openrouter.ai/docs/api/api-reference/datasets/daily-token-totals-for-top-50-models), CC BY 4.0. The report includes the required source and `as_of` attribution. Documented limits are 30 requests/minute per key and 500/day per account; this collector makes one request per selected date range, excluding retries.

AA, LiveBench and individual task benchmarks are deferred. No subscription or
paid inference endpoint is used. There is no scheduler or production integration.

## Verification and future integration

```sh
python -m pip install -e '.[dev,benchmark]'
python -m pytest -q tests/test_benchmark_download*.py \
  tests/test_hf_metadata_client.py tests/test_product_identity.py
```

Set `DATABASE_URL` to a dedicated local PostgreSQL database for the required
export and existing identity tests. The test runner creates its test database;
do not point it at production. Tests exercise actual export→mapping→mocked HTTP→
snapshot→report paths, exact identity joins, failures, pagination, Parquet,
redirects, large token counts, missingness, replay, and HTML escaping.

The database integration described above is implemented alongside the offline
report. Production activation and automated scheduling remain separate work.

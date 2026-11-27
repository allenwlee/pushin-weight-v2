# Activate daily GDPx collection

This runbook turns on the daily GDPx poll in production after the GDPx change has been deployed. The poll runs inside the existing hourly `pushinweight-benchmark` Render cron. It doesn't touch the 15-minute X harvest, and it needs no new Render service. Background on the source: [SemiAnalysis GDPx](../external_vendors/semianalysis_gdpx/README.md). Design: [GDPx plan](../plans/2026-11-27-011614-docs-gdpx-source-plan-20261127-plan.md).

## Before you start

- The deployed revision includes migrations `0247_metric_monetary_quantity` and `0248_gdpx_match_candidate_namespace`.
- Every command below runs as a Render one-off job on the benchmark or harvest image (`pushinweight-benchmark` or `pushinweight-harvest`), never inside `pushinweight-web`. Never pause or reschedule harvesting for this work.
- Read the live cron first and save the output, so the change can be rolled back exactly:

  ```bash
  render services --output json | python3 -c "import json,sys; [print(s['serviceDetails']['envSpecificDetails']['startCommand'], s['serviceDetails']['schedule']) for s in json.load(sys.stdin) if s['name']=='pushinweight-benchmark']"
  ```

  As of 2026-11-27 it printed `python manage.py collect_benchmark_due --contract 75c4a856-385b-429a-9b03-c7e023ea6f73 --apply` and `0 * * * *`.

## Steps

1. **Apply migrations.** These are part of the normal release migrate step (`python manage.py migrate --noinput`). Afterwards, confirm with `python manage.py showmigrations core | tail -3` that `0247` and `0248` are applied.

2. **Register the GDPx definitions.** This creates the `gdpx` source, its nine metrics and the `percent`, `usd`, `output_tokens_per_task` and `tasks` units. It is idempotent.

   ```bash
   python manage.py configure_benchmark_collection --register-definitions --apply
   ```

3. **Enable the source and record the owner's use decision.** The owner assumed responsibility for GDPx use on 2026-11-27, so this records an `allowed` decision with the terms written down as facts; it adds no block. Run once:

   ```bash
   python manage.py shell -c "import copy; from core.models import DataSource; from core.benchmark_attribution import GDPX_USE_POLICY; s=DataSource.objects.get(pk='gdpx'); s.enabled=True; s.metadata['use_policy']=copy.deepcopy(GDPX_USE_POLICY); s.save(update_fields=['enabled','metadata']); print(s.enabled, sorted(s.metadata['use_policy']))"
   ```

   Expected output: `True ['collection', 'retention']`.

4. **Create the link-free GDPx contract.** Write a manifest with the current taxonomy version. Read the version from `TaxonomyVersion.objects.latest('pk').pk` in a shell, or reuse the one in contract `75c4a856…`. Review it with a dry run, then apply:

   ```json
   {
     "taxonomy_version": "<current taxonomy version id>",
     "reviewed_by": "<owner>",
     "mappings": [],
     "source_configuration": {
       "gdpx": {
         "metrics": ["cost_per_task", "partial_score", "score", "tasks", "tasks_scored", "tasks_with_cost", "tasks_with_partial", "tasks_with_tokens", "tokens_per_task"],
         "scheduling_enabled": true
       }
     },
     "methodology": {"aggregation": "fixed_cohort"}
   }
   ```

   ```bash
   python manage.py configure_benchmark_collection /tmp/gdpx-contract.json          # dry run: prints contract_hash, mappings: 0
   python manage.py configure_benchmark_collection /tmp/gdpx-contract.json --apply  # prints the contract id
   ```

   Record the printed contract id; the steps below call it `<gdpx-contract>`. Configuring the same manifest again returns the same contract.

5. **Register the daily job and give it scheduling authority.** The job is created paused.

   ```bash
   python manage.py shell -c "from core.collection_jobs import register_job; from core.models import DataSource, MetricCollectionContract; j=register_job(job_key='gdpx-daily-v1', source=DataSource.objects.get(pk='gdpx'), purpose='metric', operation='collect_metrics', contract=MetricCollectionContract.objects.get(pk='<gdpx-contract>'), mode='recurring', definition={'version':1,'scope':{},'schedule':{'kind':'daily_utc','hour':10,'driver':'shared'},'budgets':{'requests':40,'seconds':120,'bytes':8388608,'items':1000}}); print(j.pk)"
   python manage.py collection_job_state --job <job-id> --state ready --take-metric-authority --apply
   ```

   Hour 10 UTC is 19:00 JST, the same slot Hugging Face uses.

6. **Add the GDPx contract to the cron.** Use the Render API or CLI to set the `pushinweight-benchmark` start command to:

   ```text
   python manage.py collect_benchmark_due --contract 75c4a856-385b-429a-9b03-c7e023ea6f73 --contract <gdpx-contract> --apply
   ```

   Leave the schedule (`0 * * * *`) unchanged, then read the start command back as in "Before you start". Each contract runs in isolation, so a GDPx failure can't stop Arena, OpenCode, OpenRouter or Hugging Face collection.

## Verify

- After the first 10:00 UTC tick, `python manage.py collection_status --job <job-id>` shows a `success` attempt. The run's selected and success counts must be equal; that was 393 for the 2026-11-25 dataset.
- `python manage.py collection_status --contract <gdpx-contract> --source gdpx --identifier claude-opus-5-5` lists per-partner values dated with the dataset's `updatedAt`.
- Watch three consecutive days. Each day should end in `success`, either new revisions or unchanged rows reused. Over the same days, Arena's hourly outcomes should be unchanged.
- A failure shows its cause on the run:
  - `fetch_failed`: the site is unreachable;
  - `fetch_challenged`: a bot challenge;
  - `dataset_not_found` or `dataset_ambiguous`: the data file can't be identified;
  - `shape_changed`: the data's shape changed;
  - `headline_mismatch`: the recomputed headline disagrees with the page.

  The job retries every hour that day. The last three causes mean the site changed and the reader needs updating; the archived homepage and chunk requests allow replay after the fix.
- Crosswalk review: `python manage.py match_collection_products --source gdpx` previews candidates. Name-only matches stay `needs_review`; specialist and abliterated models stay unmatched.

## Roll back

1. Restore the saved start command on `pushinweight-benchmark`.
2. Run `python manage.py collection_job_state --job <job-id> --state paused --apply`.

Stored GDPx observations stay in place. They belong to their own contract and are not visible through Arena's.

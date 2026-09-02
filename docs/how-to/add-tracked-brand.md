# How to add a tracked brand

## Current v2 workflow

The operator-facing identity input is `config/brands/brand-onboard.template.csv`.
Harvest policy remains the search authoring surface; `onboard_brand` validates
that policy and never edits it. Handle-only rows and harvest-path fields are
metadata; a handle paired with a canonical author id creates a durable role link.

## Workflow

1. Copy the template to a dated input file.
2. Fill one row per brand. Multi-value cells use `|`; commas inside cells use
   RFC4180 CSV quoting. HF orgs accept a namespace or Hugging Face URL, and
   products accept a namespace/repo or product URL.
3. Add the nickname to `config.yaml` `enabled_models` and its block to
   `config/harvest_policy.yaml` before applying.
4. Review the complete dry run:

   ```bash
   python manage.py onboard_brand --csv config/brands/2026-...csv --dry-run
   ```

5. Apply and rerun the same input. The second run should report unchanged rows:

   ```bash
   python manage.py onboard_brand --csv config/brands/2026-...csv
   python manage.py onboard_brand --csv config/brands/2026-...csv
   ```

6. Run `python manage.py harvest_preview --fail-on-invariant-violation` and
   verify coverage before the selected delivery target is updated.

## Preview and offline cost verification

`harvest_preview` is the preflight check for the live planner. It should report
seven logical calls with the current stable order `A, B1, C1, C2, C3, B2, B3`;
the order reflects planner derivation and is not a provider HTTP-request
count. It makes no provider call:

```bash
python manage.py harvest_preview --fail-on-invariant-violation
```

The cost tool is pure summary-file math. Reuse the checked-in seven-call smoke
fixture to verify the expected B1/C3 sensitivity without a provider or
database:

```bash
python -m scripts.harvest_cost \
  --input tests/harvester_costs/_smoke/ae1.json --format json
```

The fixture has B1=63 and C3=4. With the current 15-credit tweet rate, a
change of ΔB1 and ΔC3 changes the estimate by `(ΔB1 + ΔC3) * 15`, while the
logical call count remains seven. Pagination may increase HTTP requests in a
live cycle; it does not change this logical-call invariant.

## CSV and validation rules

The command skips blank nicknames and `_`-prefixed instruction rows. It parses
and validates the entire file before opening its transaction, including nickname,
country, color, integer, handle, product ownership, enabled-model membership,
policy membership, and active policy-token coverage. An HF org or product
requires a company. A failed later row rolls back earlier rows.

`keyword_primary` becomes the primary `BrandKeyword`; aliases and C bare aliases
are non-primary. Natural keys make reruns idempotent for brands, companies,
links, HF orgs, keywords, and products.

`official_x_handles` and `staff_x_handles` normalize an optional `@` and are
shown in dry-run output. Their optional `official_x_author_ids` and
`staff_x_author_ids` cells are pipe-aligned canonical numeric X ids. When ids
are present, the command atomically upserts `Account` and `BrandAccount` rows
with `official` or `staff` role; it rejects mismatched or conflicting pairs and
never invents `handle:` or `synthetic:` ids. A handle with no id remains
metadata-only. `harvest_paths`, `co_pack`, and version-family columns are
checked or warned as metadata. The command never rewrites
`config/harvest_policy.yaml`.

For a deliberate identity-only load while policy is being prepared, use
`--skip-search`; the normal command is strict and requires both enabled-model
and policy membership.

## Delivery

Apply the validated CSV only to the owner-selected delivery target. This command
does not deploy, pause the harvest cron, or call external providers. `load_seed`
remains the bootstrap path for the original seeded roles and accounts.

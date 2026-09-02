# How to add a tracked brand

## Current v2 workflow

The operator-facing identity input is `config/brands/brand-onboard.template.csv`.
Harvest policy remains the search authoring surface; `onboard_brand` validates
that policy and never edits it. X handles and harvest-path fields are metadata.

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

## CSV and validation rules

The command skips blank nicknames and `_`-prefixed instruction rows. It parses
and validates the entire file before opening its transaction, including nickname,
country, color, integer, handle, product ownership, enabled-model membership,
policy membership, and active policy-token coverage. An HF org or product
requires a company. A failed later row rolls back earlier rows.

`keyword_primary` becomes the primary `BrandKeyword`; aliases and C bare aliases
are non-primary. Natural keys make reruns idempotent for brands, companies,
links, HF orgs, keywords, and products.

`official_x_handles` and `staff_x_handles` normalize an optional `@`, are shown
in dry-run output, and create no Account or role-link records. `harvest_paths`,
`co_pack`, and version-family columns are checked or warned as metadata. The
command never rewrites `config/harvest_policy.yaml`.

For a deliberate identity-only load while policy is being prepared, use
`--skip-search`; the normal command is strict and requires both enabled-model
and policy membership.

## Delivery

Apply the validated CSV only to the owner-selected delivery target. This command
does not deploy, pause the harvest cron, or call external providers. `load_seed`
remains the bootstrap path for the original seeded roles and accounts.

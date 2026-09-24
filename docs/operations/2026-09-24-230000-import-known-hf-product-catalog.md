# Import a confirmed Hugging Face Product catalog

Use `import_hf_product_catalog` to enumerate model repositories owned by one
already-confirmed Hugging Face organization and attach them to one Brand. This
is an operator-launched, resumable catalog import—not a crawler or release
detector.

The command requires an existing ownership chain:

`Brand → BrandCompany → Company ← confirmed HFOrg`

It validates that chain before constructing an HTTP client. It does not create
a Brand, Company, ownership mapping, or HF organization.

## Preview first

Preview reads the local database only. It sends no provider request and writes
nothing:

```bash
python manage.py import_hf_product_catalog \
  --brand minimax \
  --confirmed-namespace MiniMaxAI \
  --max-requests 1 \
  --max-models 100
```

The JSON output repeats the exact Brand, namespace, caps, cursor, and
`"mode": "preview"`.

## Run a bounded import

`--commit` explicitly permits public HF metadata requests and Product writes:

```bash
python manage.py import_hf_product_catalog \
  --brand minimax \
  --confirmed-namespace MiniMaxAI \
  --max-requests 1 \
  --max-models 100 \
  --commit
```

Each request has a two-second timeout and zero retries. `--max-requests` bounds
physical list requests; `--max-models` bounds Product creates/updates. Existing
Product metadata is retained when a listing omits a field. Replaying a repo
updates that Product instead of creating another. Quantized variants remain
separate Products because each official repository ID is a separate identity.
Catalog import leaves `Product.type` null; it never labels every HF repository
as an LLM.

## Continue exactly

Read these output fields:

- `complete: true`, `stop_reason: exhausted`, `next_cursor: null` means HF
  returned no next cursor and enumeration completed.
- `complete: false` means the output is not a complete catalog.
- `next_cursor` is the exact opaque cursor for the next bounded invocation.

Continue with the returned cursor unchanged:

```bash
python manage.py import_hf_product_catalog \
  --brand minimax \
  --confirmed-namespace MiniMaxAI \
  --max-requests 1 \
  --max-models 100 \
  --cursor 'OPAQUE_CURSOR_FROM_PRIOR_OUTPUT' \
  --commit
```

Do not infer completeness from a short page or a successful exit. Preserve the
JSON receipt for every invocation until one reports `complete: true`. Stop and
review `owner_mismatch`, `owner_conflict`, `no_progress`, malformed responses,
HTTP failures, or provider pages larger than the requested remaining model cap;
the command does not silently reassign an existing Product.

This runbook authorizes no production call by itself. Use the active plan's
delivery guide and operator authorization before running `--commit` on staging
or production.

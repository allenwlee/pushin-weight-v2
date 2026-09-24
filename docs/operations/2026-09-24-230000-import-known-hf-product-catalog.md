# Import known HF Products for rare-type verification

The rare-type release uses the shared, resumable HF Product catalog importer.
It does not run a second catalog writer. Read
[the HF catalog runbook](../reference/hf-model-catalog.md) for the command's
request budgets, durable run IDs, incomplete outcomes, and recovery procedure.

Before a known-organization import, confirm the database already contains
`Brand → BrandCompany → Company ← confirmed HFOrg`. A matching account name
alone is not proof of ownership. Preview the exact Brand and namespace first;
preview reads the database but sends no HF request and writes nothing:

```bash
python manage.py import_hf_product_catalog \
  --brand minimax \
  --confirmed-namespace MiniMaxAI \
  --max-requests 12 \
  --max-seconds 120 \
  --max-models 3
```

Only an explicitly authorized `--commit` invocation may make public HF
metadata requests and write Products. The caps above bound physical requests,
elapsed time, and model count; they do not promise a complete catalog. If the
command reports incomplete coverage, keep its run UUID and resume with
`--resume RUN_UUID` under a new bounded invocation. Do not use `--cursor`:
it cannot account for the prior pages and pending detail requests.

Catalog ingestion creates one Product per exact official repository ID,
including quantized variants, but leaves `Product.type` null. It does not
infer a model release from a repository update, auto-approve an X publisher,
or enable that Brand in the paid harvester. Exact X/HF identity corroboration
and owner review remain separate rare-type paths. Keep HF observation times
separate from release dates claimed on X.

This runbook authorizes no production import by itself. Follow the active
release plan and environment-specific approval before using `--commit`.

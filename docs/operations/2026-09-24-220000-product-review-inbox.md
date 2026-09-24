# Product review inbox

The private Product review inbox resolves X-sourced product proposals that the
automatic Hugging Face check could not safely corroborate. It never launches a
provider request and never adds a Brand to harvesting.

## Access

Routes:

- `/product-review/` — pending queue
- `/product-review/<proposal-id>/` — evidence and decision form

Normal Google authentication is necessary but not sufficient. Access requires
either Django `is_staff` or an exact, case-insensitive email in the
`PRODUCT_REVIEW_OWNER_EMAILS` environment variable. The default is empty and
fails closed for non-staff users.

For staging acceptance, configure `PRODUCT_REVIEW_OWNER_EMAILS` in the staging
service only with the already-authorized owner email. Keep
`OLLIJA_STAGING_ALLOWED_EMAILS` as the outer copied-data gate. Do not copy the
new allowlist to production, widen it to a domain, or print its value in logs or
receipts. U14 owns that staging configuration change.

## Decision behavior

Every decision requires a reason and records the signed-in reviewer and time.

- **Approve, X-only** creates or reuses a Product with a stable internal key and
  null Hugging Face repository.
- **Approve, matched HF** is available only after an exact matched metadata
  result. It records an explicit owner-override trace; it makes no HTTP call.
- **Correct Brand/type** changes only this proposal's target. An unresolved
  publisher candidate may create a canonical, untracked Brand and optionally
  link it to an existing Company.
- **Reject** keeps the source Post, account evidence, HF outcome, and audit row.

Approval creates the source post–Brand–Product evidence link transactionally.
It does not edit `enabled_models`, query configuration, classifier labels,
release review state, scheduled services, or provider credentials. Repeated and
concurrent decisions are locked and idempotent; a stale automatic-verification
worker cannot overwrite an owner decision.

## Verification

Use a disposable PostgreSQL database:

```bash
DATABASE_URL=postgresql://USER@localhost/pushinweight_test \
  pytest tests/test_product_review.py tests/test_product_verification.py
```

For a local browser check, use a temporary staff user or a temporary local
allowlist value, deterministic fixture proposal, and `DEBUG=True`. Confirm the
queue/detail page, escaped source text, CSRF-protected decision, and resulting
Product/evidence rows. Remove the temporary user and local environment value
afterward. This is local evidence, not staging or production verification.

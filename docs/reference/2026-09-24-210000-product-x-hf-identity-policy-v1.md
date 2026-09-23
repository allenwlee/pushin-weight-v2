# Product X/Hugging Face identity policy v1

`product-x-hf-v1` is the deterministic policy for automatically linking an
X-sourced product name to a Hugging Face model repository. It is deliberately
narrow. A failed rule creates or retains a review proposal; it does not create
a Product, Brand, or harvest target.

## Known-publisher route

All of these facts must agree:

1. The X account has the exact stable account ID already mapped to the Brand
   with the `official` role. A matching handle is not identity evidence.
2. The Brand is linked to a Company, and that Company owns a confirmed `HFOrg`
   whose namespace exactly matches the repository owner.
3. An unauthenticated, exact public `GET /api/models/{namespace}/{repo}` returns
   the same repository ID. Private credentials are never sent by this path.
4. The source supplies a specific repository and supported Product type. A
   base name never expands to sibling, quantized, or derivative repositories.

Blue verification is recorded in the trace but never qualifies an account.
X says the blue check can indicate Premium subscription. Gold/organization and
affiliate labels can support review, but v1 does not treat their display text,
a similar handle, or a self-asserted website as sufficient automatic proof.

## New-publisher route

V1 intentionally has no automatic new-publisher route. The currently persisted
TwitterAPI account fields do not provide a deterministic, bidirectional
X-organization ↔ Hugging Face namespace backlink. Such candidates remain
durable proposals for owner review. Adding an automatic route requires a new
version with exact backlink fields, conflict rules, and fixtures; it must not
weaken the known-publisher rule.

Evidence checked on 2026-09-24: one separately authorized, unauthenticated
public request to `https://huggingface.co/api/organizations/MiniMaxAI` returned
a JSON object containing only an `error` key. The HTTP status was not retained,
so this is shape evidence only, not an availability or existence claim. No
website, X-account, or backlink field was available and no further live request
was made. Therefore R37's automatic new-Brand route remains explicitly deferred
and is not an acceptance claim for U15 v1.

## Hugging Face request boundaries

- Exact verification: at most three requests per normal cycle and one in
  staging, controlled by the caller; two-second timeout and zero retries.
- Results remain distinct: matched, missing, private, timeout, throttled,
  malformed, error, or deferred.
- Catalog import is a separately launched, request- and model-bounded listing
  of a confirmed known organization. Cursor/request exhaustion is reported as
  incomplete. It is not an activity crawler.
- No repository files, model weights, configs, or blobs are downloaded.

The source Post is persisted before verification. Product creation and the
post–Brand–Product link occur in one transaction, with existing owner conflicts
failing closed. Hugging Face creation/modified timestamps are metadata only;
they are not model-release dates.

# Follow-up: announcement-triggered Hugging Face Product verification

Date: 2026-09-24 JST
Status: owner-requested discussion note; not implemented or added to the active release
Related plan on the rare-type branch: `docs/plans/2026-09-21-081940-feat-combined-rare-type-extra-search-plan.md`
Related policy on the rare-type branch: `docs/reference/2026-09-24-210000-product-x-hf-identity-policy-v1.md`
Those related files may not reach `main` until the separate rare-type release.

## Read this after the current release

The owner said another session is staging and promoting the rare-type plan now.
This note is a separate follow-up. Do not change that release candidate, widen
its acceptance scope, or delay its deployment because of this note. The owner
requested recording the idea for the next session, not implementing or enabling
it now. Existing release authorizations do not automatically authorize this new
background workflow or its additional requests.

This file was created in the authoritative root checkout on `fuchitalee`:
`/Users/fuchitalee/development/pushin-weight-v2/docs/handoffs/2026-09-24-213119-rare-type-announcement-triggered-hf-followup.md`.
It was initially uncommitted and was subsequently included in the HF documentation
closeout for publication on `main`. A separate worktree will not receive it without
fetching/integrating that documentation; the original absolute root path above
also remains available. No active rare-type plan or policy file was changed to
add this note.

## Owner's question and intended outcome

The owner asked whether a release-announcement post found by the 15-minute
rare-type process could trigger an asynchronous HF check for a new or recently
modified repository, then create the Product.

Proposed outcome: preserve the announcement first, verify its repository in a
durable background job, and create or refresh the matching Product with a link
back to the announcement. Normal post collection and publication should not wait
for HF. This is targeted corroboration prompted by a post, not a periodic crawl
of every publisher's entire catalog.

## Existing implementation inspected locally

Recheck the deployed SHA and current source before implementation: these findings
describe local rare-type code inspected on 2026-09-24, not a verification of the
other session's eventual production deployment.

- `core/targeted_extraction.py` persists `ProductVerificationProposal` with the
  observed model name, candidate repository, source post/release and evidence.
- `monitor/cycle.py` calls `drain_pending_verifications` after post-fetch work
  when enabled. That is bounded work inside the cycle, not an independent worker.
- `core/product_verification.py` provides exact public HF metadata checks,
  publisher/source validation, claim leases, deferred outcomes, and Product
  upsert/source-link logic.
- Current v2 automatic verification requires an exact HF link in stored source
  evidence. Missing links remain review work; it does not search publisher
  accounts to discover a candidate. Known-publisher and new-publisher routes have
  different identity requirements; preserve their evidence checks.
- The current documented budgets are three physical requests per normal drain,
  one for staging, two-second request timeouts and zero immediate HTTP retries.
  Do not inherit the separate one-time catalog import's effectively unlimited
  request allowance into scheduled work.
- Reuse the shared HF metadata client/Product writer where compatible. The HF
  catalog and rare-type branches evolved separately; inspect the integrated
  schema and callers instead of copying either branch's old assumptions.

## Proposed extension for a later plan

1. Persist the announcement and a deduplicated pending verification record.
   Dispatch background work only after the database transaction commits. Keep
   pending work recoverable if dispatch fails or the worker restarts; a detached
   coroutine inside an exiting cron process is not a durable queue.
2. Prefer an exact HF link. Without one, extract publisher, model name and version,
   then search only verified publisher namespaces. ByteDance has three known
   accounts: `ByteDance`, `bytedance-research`, and `ByteDance-Seed`.
   Recently modified listings can produce candidates; they are not release proof.
3. Verify candidate identity, publisher ownership, version and relevant metadata.
   A name-only search is weaker evidence than the current exact-link policy:
   define and test a separate versioned acceptance rule before allowing automatic
   creation from it. An LLM may propose matches; unsupported guesses must not
   silently become confirmed identities. Multiple plausible matches remain review
   items. Do not expand a base-model mention to every quantization or sibling.
4. For an accepted repository, upsert through the shared Product writer. Reuse
   existing Products, preserve curated fields/IDs, and attach the source evidence.
   If an approved X-only Product already represents the same release, follow the
   existing reconciliation policy rather than creating a duplicate.
5. A changed SHA or modification time refreshes the existing Product; it does
   not automatically create another Product or ModelRelease. Decide release-event
   identity from the announcement and corroborating evidence separately.
6. If the upload is not yet visible, retry later under explicit attempt, age,
   concurrency and request budgets. Honor HF rate-limit headers. An unauthenticated
   404 can mean absent or inaccessible; do not claim to distinguish those without
   evidence. API-only releases may never have an HF repository and must not be
   rejected as false announcements for that reason.
7. Decide the worker/queue placement in the later plan. Do not reactivate retired
   worker/beat services, change scheduler cadence, or reuse a dedicated headline
   queue without an explicit integration decision and corresponding authorization.

## Dates and brand identity

Keep the source's claimed release date and precision, post publication time, HF
repository creation/modification times, and our first observation/verification
times separate. Repositories can predate public availability; modifications can
be README-only. Record uncertainty instead of manufacturing a release timestamp.

Brand is the owner's editorial grouping, not a direct consequence of publisher,
repository prefix, model architecture or base model. The owner clarified:

- MiniMax currently groups H3 and the M-series together.
- GLM and ChatGLM remain separate identities, with consumer-facing positioning
  relevant to the distinction; both names refer to models.
- Seed covers ByteDance's research/model family; Doubao covers the consumer app.
  A name such as `Doubao-Seed-2.1-Pro` does not alone imply the Doubao app brand.

The owner subsequently approved applying the six-publisher proposal to the
original selected scope: 321 Products were assigned and 12 missing Brands were
created after a staging rollback trial. The owner explicitly left 203 selected
research-project Products publisher-only; 400 retained Google extras were outside
the assignment batch. Treat those exact assignments as accepted, not the broader
exploratory proposal as a universal matcher. See the
[HF plan's assignment receipt](../plans/2026-09-24-162207-feat-hf-model-product-catalog-plan.md#one-time-brand-assignment-completed--2026-09-24).

## Verification required when implemented

Include a regression test through the real announcement extraction -> durable
job -> HF verification -> Product/source-link chain, not only helper tests.
Cover exact-link success; no-link candidate search; ambiguous variants; verified
owner mismatch; announcement-before-upload; inaccessible/404; throttling;
README-only change; existing Product refresh; X-only reconciliation; repeated
posts; concurrent workers; restart/dispatch recovery; and stale worker results
after an owner decision. Prove bounded request counts and no blocking of normal
post publication. Validate on staging before separately authorized production
activation.

## Supporting references

- [HF metadata APIs](https://huggingface.co/docs/hub/en/api)
- [HF rate limits](https://huggingface.co/docs/hub/en/rate-limits)
- [Django actions after commit](https://docs.djangoproject.com/en/5.2/topics/db/transactions/#performing-actions-after-commit)

These were checked during the discussion on 2026-09-24; refresh changeable API
and worker facts before implementation.

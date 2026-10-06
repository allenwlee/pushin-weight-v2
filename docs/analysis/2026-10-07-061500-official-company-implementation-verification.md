# Official company discovery: implementation verification

The feature scans the whole stored author population once, then examines new or changed evidence with the scheduled harvester. Accepted official AI model developers receive brand/company account roles and a durable add-only intent for the existing private collection list. Owner access/refresh tokens are encrypted in PostgreSQL; the encryption key and matching OAuth client configuration belong in managed secrets.

## Verified locally

- 227 tests passed, including 158 required PostgreSQL tests, with zero skips/errors. This covers the discovery/registration/list/credential suites, real scheduled cycle entry point, existing targeted extraction/profile/list/Jev regression tests, and Ollija checks. Runtime: Python3.13.13, Django5.2.16, PostgreSQL17.9, isolated database `pw_official_co_20261006`.
- Django system checks and migration consistency passed. Additive migrations0065–0068 were applied, reversed to the actual0064 migration, and reapplied on a populated isolated database; the pre-existing Account remained present. No production migration ran.
- Review reproduced three queue failures using rollback-only PostgreSQL transactions, then fixed them: unchanged evidence changing queue priority, accepted evidence leaving an obsolete list intent ineligible, and retries taking both slots while unseen evidence waited. Added regression coverage also pins exact small scan limits and completion beyond the third membership page.
- Token tests verify encrypted pair storage, atomic rotation, loading by another process, wrong-key/client refusal and durable blocking after uncertain renewal. These use fake transport; live token renewal remains unverified.
- A dedicated GitHub workflow runs the discovery and harvest regressions on PostgreSQL16/Python3.12. Its hosted result must be observed separately from local results.

## Review and evaluation limits

Local review and validation ran sequentially in the main agent under the repository's Task mapping. The attempted external Claude review returned HTTP402 insufficient balance and supplied no review. It is not independent corroboration. Its terminal job was consumed and removed; the local review receipt is under `/tmp/compound-engineering-501/ce-code-review/20261006-124518-4f4e30cb/`.

The final frozen model corpus passed9/11: two unseen eligible labs accepted and six misleading negative examples not accepted. Reflection's sparse stored example lacked enough model-development evidence; Bad Theory Labs returned an unsupported citation and was blocked by validation. All three owner-settled examples have separate versioned attestations. No whole-population recall claim follows from this small corpus. The dated [evaluation report](2026-10-06-122700-official-company-model-evaluation.md) preserves all measured limitations.

## Production endpoint still outstanding

No feature deployment, production migration, token provisioning/refresh or automatic registration/list synchronization has been performed. Initial full-database coverage, two normal scheduled cycles and subsequent eligible-post collection with correct attribution remain required.

At the integration check, `origin/main` is `5082ddf7`; the benchmark schema remains separate in PR50 (`a3cbfe09`). The branch integrating second must reconcile migration leaves and include `OfficialCompanyAccountState.account` and `OfficialCompanyListIntent.account` in generic-account conversion. Staging retains G2's `bacbb433` branch and previously restored runtime; its resources cannot be replaced incidentally.

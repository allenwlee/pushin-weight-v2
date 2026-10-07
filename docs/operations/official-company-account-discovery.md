# Official AI company account discovery

This service finds official accounts of companies or organizations developing an AI model, their own agent, or their own harness. Model development includes proprietary/closed-weight models and attributable derivatives of open-weight models, including fine-tuning and quantization. Agent and harness developers can use another company's models. Hugging Face presence and public weights are optional for every route. It reads stored account profiles and posts, registers supported company/brand identities and queues additions to Call A's existing private X list. It does not change editorial admission to Chatter or Pulse.

The evaluator records separate evidence for company identity, official account identity and actual product development under `official-ai-product-developer-v3`. Mere model/API use, hosting, resale or unchanged mirrors do not establish development; an actual developed agent or harness qualifies even when it wraps third-party models. Agent/harness decisions leave model types empty rather than attributing their suppliers' models to them. Blockchain/Web3 evidence triggers the versioned higher technical-evidence hurdle for the actual development route. Ordinary positive evaluations still need human settlement; independent server-signed official HF own-model verification retains its automatic registration path. HF verification accepts attributable quantized derivatives/GGUF artifacts and preserves the distinction from unchanged mirrors. Existing signed settlements remain valid.

There are two separate jobs. `initial-scan` cheaply screens every account at a frozen start boundary, without an age cutoff. Only selected candidates receive expensive official-account evaluation. The scheduled harvester independently screens new/changed account, post-fetch and profile evidence, with a rotating inventory check for missed observations. Follower-count changes alone do not create a new decision.

Candidate evaluation has three priority tiers:

1. Gold/business badge (`Account.verified_type = Business`) alone admits an account first, even with no bio or stored posts. The verified and blue booleans are not substitutes for this field.
2. AI/model-related bio, development language, and an external profile website.
3. AI/model-related bio plus external website and organization/domain-name resemblance, or model-release wording in an authored post plus an organization-style account name.

These are alternate entrances, not proof of company ownership or AI model development. No minimum post/follower count, Hugging Face presence, open weights, language-model-only restriction or age cutoff is imposed. Profile text and expanded website URLs include nested post-author data and stored snapshots across history. Some personal accounts pass the cheap screen; the existing grounded evaluator must still reject them or request review before registration/list addition.

Gold candidates are staged before the whole-author inventory; a separate gold checkpoint prevents mutable badge metadata from corrupting the full inventory's stable author-ID cursor. Evaluation and due retries obey tier precedence, sharing retry/fresh slots within each tier. The interrupted unfiltered `official-company-initial-v1` checkpoint remains stored. The filtered scan uses `official-company-filtered-initial-v1`, reusing the old frozen population boundary when present.

Nonmatching accounts stay in `accounts`. Existing unprocessed queue rows become `deferred`; no state row is needed for a newly screened nonmatch. Candidate priority/policy fields distinguish screened work from legacy unscreened rows, which cannot reserve funds or dispatch. Changed evidence can make a deferred account eligible later. Existing decisions, attempts, registrations, list outcomes and suppressions remain durable; material identity evidence can still trigger reevaluation. Explicit bounded operator `enqueue --account-id` is a recorded manual candidate override, with gold precedence retained; ordinary initial/incremental discovery never uses that override.

The implementation defaults to disabled. Code and test completion do not establish production activation. The linked [plan](../plans/2026-10-06-100039-feat-official-co-account-extraction-plan.md) and dated activation receipts determine deployment status.

## Configuration and bounded operation

`official_company` in `config.yaml` is validated by `OfficialCompanyConfig`. Service-specific overrides are named `X_MONITOR_OFFICIAL_COMPANY_<FIELD_IN_UPPERCASE>` and are read by the canonical configuration loader.

Discovery, registration and outbound list synchronization have separate `enabled`, `registration_enabled` and `list_sync_enabled` flags. Registration requires discovery; synchronization requires registration. Per-cycle/day and initial-total USD limits default to zero. Zero funding dispatches no model request. The model is pinned to `deepseek-ai/DeepSeek-V4-Flash-0731` through the existing direct DeepInfra client and `DEEPINFRA_API_KEY`; no generic provider fallback is used.

The scheduled lane runs once after essential harvest work, only on a normal scheduled cycle with sufficient time. Its default ceiling is two model calls and a 45-second lane deadline, sharing the cycle-wide optional extraction allowance with existing targeted extraction. Calls reserve a conservative cost before dispatch. Unknown spend remains reserved. Authentication/configuration rejection blocks this model adapter until its credential revision changes or an operator explicitly resumes it.

The initial inventory is a separate resumable operator job. Enumeration and model evaluation are separate commands. Candidate accepted, rejected, review-needed and no-evidence outcomes remain visible. Coverage reports population, whole-inventory enumeration, gold staging, candidate totals/tiers and deferred nonmatches separately. Completed cheap screening does not mean all authors were model-evaluated. Candidate pending/retry work or unenumerated accounts means coverage is incomplete. Gold staging can produce candidates before whole-inventory enumeration starts.

## Inspection and explicit actions

Owners and staff can inspect discovery at `/admin`. The console preserves the
product-review inbox and shows official-account identities, organizations,
model types, decision rationale/citations, registration state and Call A list
outcome. Account rows are paginated in groups of 50. Initial scan enumeration
and completed account evaluation are different observations.

The console has six tabs. **Official accounts found** shows settled identities.
**Review needed** shows unresolved company candidates, excluding evaluation
failures and existing tracked accounts. **Failed evaluations** shows current
failed attempts, including those waiting for retry, and evaluations blocked by
the attempt or evidence-size limit. An older failure or failure for superseded
evidence does not keep a subsequently successful evaluation in this tab.
**Already tracked** shows candidates with existing official brand/company links
or the recorded `already_tracked` marker; settled Found identities are excluded.
Existing tracked accounts take precedence over failures, and multiple official
links still count as one account. **Scan queue** retains all selected candidates
and status filters. **List history** retains the synchronization audit.
Each dedicated tab has its own count, search and pagination; status parameters
cannot switch its category. Separating these views changes no stored decision,
approval, retry schedule or list membership.

The **Frozen account run** link near the top of `/admin` opens
`/admin/official-accounts/frozen-run`. This owner/staff page reports only the
saved October 7 cohort, using its matching new-policy attempt receipts and
earlier positive baseline. **Newly qualifying** lists new positive findings,
excluding companies that had already passed before the rerun. **Awaiting** lists
temporary evaluation failures waiting for retry, with the recorded error and
next retry time. **Pending** lists accounts without their first rerun result,
including requests currently in flight. Other outcomes remain in the progress
summary. Each tab supports account/company search and pages of 50; tab counts
remain totals for the frozen cohort when search narrows the table. Refresh the
page to read current progress. The page does not evaluate or approve accounts,
change their queue state, or alter list membership.

The add counter counts accounts with an acknowledged provider add. A membership
read confirming an already-present account does not increment it. A timed-out
request followed by positive membership readback is shown separately because
membership alone cannot establish which writer added the account. First-request
and first-acknowledgement times are retained across retries and evidence changes.
No credential data is read or rendered by this console. Historical records
without add timestamps do not establish an extractor addition.

Old `/product-review/` and proposal GET links redirect to the corresponding admin
routes. Previously opened proposal forms can still submit to their old URLs,
with the existing permission and CSRF checks. New proposal links use
`/admin/products/<proposal_id>/` and retain the chosen display language.

All commands return JSON. `inspect` and `--dry-run` do not call providers or write application records. Enumeration, enqueue, the fixed-cohort rerun and evaluation-only drains use the separate discovery lock and return `discovery_busy` without waiting. Registration, list synchronization and credential actions first require the harvest writer lock, then the discovery lock; a busy harvest writer returns `writer_busy`. Do not pause the cron to make a manual batch run.

```bash
python manage.py official_co_account_extraction inspect
python manage.py official_co_account_extraction initial-scan --dry-run
python manage.py official_co_account_extraction initial-scan --limit 100 --seconds 45
python manage.py official_co_account_extraction drain --initial --limit 10 --seconds 45
python manage.py official_co_account_extraction incremental --limit 100
python manage.py official_co_account_extraction enqueue --account-id 1800594921704898560
python manage.py official_co_account_extraction register --account-id 1800594921704898560
python manage.py official_co_account_extraction sync --seconds 45
python manage.py official_co_account_extraction retry --account-id 1800594921704898560
python manage.py official_co_account_extraction suppress --account-id 1800594921704898560
python manage.py official_co_account_extraction resume-model
python manage.py official_co_account_extraction requalify --cohort-manifest /path/to/frozen-cohort.json --limit 20 --seconds 120
python manage.py official_co_account_extraction requalify --limit 20 --seconds 120
```

The October 7 qualification rerun has a fixed population of 944 accounts: 896 review candidates and 48 failed evaluations, frozen at 11:35:02 UTC. Its compact manifest contains state ID, account ID, evidence hash and prior outcome in `review`/`failed` arrays, plus `frozen_at`. Initialization stores immutable membership in `OfficialCompanyScan` under `official-company-requalification-20261007-v3`; repeating the same manifest resumes work, and different membership is rejected. New-policy attempts retain separate decisions and spend receipts. Changed evidence, existing registrations/settlements, tracked identities and suppressions are protected. Physical calls remain serial, at most three attempts per account, with the existing shared initial USD50 ceiling and bounded request/lane deadlines.

Once initialized, `/admin` shows rerun progress on every accounts tab. Qualifying counts include earlier positives that pass again; newly qualifying excludes the 86 earlier accepted results in the frozen baseline. Model, agent and harness counts describe eligibility findings, separate from list additions. Uncertain, rejected, failed, retry-pending, pending and excluded outcomes stay distinct. Independently HF-verified and registered accounts are recognized even when their paid evaluation failed; that verification subset is also shown separately. `inspect` includes the same read-only `requalification` report, qualifying account identities and measured/unknown reserved spend. These counters describe this fixed rerun, not the entire inventory or subsequent collection.

Repeat bounded initial batches until enumeration completes; separately drain funded decisions and inspect outcomes. Never equate an enumeration cursor reaching the end with completed evaluation. `retry` cannot clear suppression. Retrying an account with changed or rejected evidence requires another decision; it does not restore an old acceptance automatically.

The three owner-verified accounts have a versioned, stable-ID attestation applied once when their states are created. It is recorded as an `owner_attested` attempt with zero model spend. The classifier contains no handle-specific acceptance rule. Later material changes are re-evaluated with stored evidence, preserving the original attestation receipt.

## X owner credentials and renewal

The owner selected encrypted PostgreSQL token storage. The `OfficialCompanyOwnerCredential` record contains authenticated encrypted access/refresh tokens. A dedicated Fernet encryption key and the matching confidential OAuth2 client credentials live in the harvest service's managed secrets:

- `PUSHINWEIGHT_X_LIST_ENCRYPTION_KEY`
- `PUSHINWEIGHT_X_LIST_CLIENT_ID`
- `PUSHINWEIGHT_X_LIST_CLIENT_SECRET`

Initial provisioning reads `PUSHINWEIGHT_X_LIST_ACCESS_TOKEN` and `PUSHINWEIGHT_X_LIST_REFRESH_TOKEN` from the command process environment. The repository does not automatically load the operator's local secret store. Never pass secret values on command lines or print them. Preserve a secure backup of the encryption key; replacing it without re-encrypting the credential record makes that record unreadable.

```bash
python manage.py official_co_account_extraction provision-owner
python manage.py official_co_account_extraction refresh-owner
```

Provisioning refuses to replace an existing record. After an explicitly authorized credential repair, use `provision-owner --replace-owner-credential` with the replacement pair in the process environment. It does not modify another application's tokens. The stored client ID must match the configured one before renewal.

The adapter uses the token response's `expires_in`, renews within five minutes of expiry, and saves both rotated tokens in one database transaction. It can also renew once after a rejected access token. A durable in-flight marker prevents concurrent refresh. An uncertain refresh response, process crash during renewal, decryption failure or rejected credential stops automatic renewal instead of repeatedly using a possibly invalidated refresh token. Operator recovery is required in that case.

Before a list write, the adapter checks the authenticated user's stable ID and the target list's owner/private status. Read pagination permits up to 50 pages of 100 members, covering [X's documented 5000-member list capacity](https://help.x.com/en/using-x/x-lists-not-working), and remains subject to the request/lane deadline. An incomplete read cannot establish absence. A timed-out add is read back before another POST. New accepted evidence rebinds unresolved intents and invalidates obsolete claims; confirmed membership, suppression and manual-removal review remain durable. Positive confirmation updates one membership record without pretending a full-list reconciliation occurred. A later complete reconciliation showing removal marks the intent for review; it does not automatically re-add it.

## Evidence, records and compatibility

`OfficialCompanyScan` records initial and incremental cursors. `OfficialCompanyAccountState` records current evidence and outcome. Immutable `OfficialCompanyAttempt` receipts retain evidence, returned decisions, validation outcome, model/policy and token usage. `OfficialCompanyBudget` records reserved and spent USD. `OfficialCompanyProviderState` prevents repeating known model-auth failures. `OfficialCompanyListIntent` separates desired membership from confirmed `TwitterListMembership` observations. `OfficialCompanyOwnerCredential` stores only encrypted token material.

Registration reuses stable official organization edges and explicitly reviewed candidate mappings. Name/slug/role conflicts require review. It does not infer legal ownership percentages, create a BrandCompany ownership edge, or assign a specific product. The two new account references—account state and list intent—must join the benchmark branch's provider-neutral migration inventory before that migration integrates. This feature uses the current schema through shared identity functions.

Existing official X app setup and locally verified list access are documented in the plan. [X's OAuth2 documentation](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code) describes the standard two-hour access-token lifetime and refresh flow; actual runtime lifetime comes from the token response.

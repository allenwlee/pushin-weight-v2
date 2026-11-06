# Official AI company account discovery

This service finds official accounts of companies or organizations developing an AI model, their own agent or execution harness, or their own identifiable AI platform/service. Model development includes proprietary/closed-weight models and attributable derivatives of open-weight models, including fine-tuning and quantization. Agent and harness developers can use another company's models. Hugging Face presence and public weights are optional for every route. It reads stored account profiles and posts, registers supported company/brand identities and queues additions to Call A's existing private X list. It does not change editorial admission to Chatter or Pulse.

The evaluator uses `official-ai-offerings-v4`, keeping account presentation separate from the offerings described. Its internal decision JSON records multiple categories (`model-llm`, `model-other`, `agent`, `harness`, `other`) and attributable product evidence. A harness specifically controls agent/model execution, permissions, state or runtime; inference serving, training platforms and app builders are `other` unless separate execution-control offerings are evidenced. Hosting/testing a third-party model or using a third-party harness does not establish development. Closed models and attributable derivatives qualify. The response ceiling is4096 tokens.

Ordinary positive evaluations still need human settlement; independent server-signed official HF own-model verification retains its automatic registration path. Blockchain/Web3 evidence triggers the higher technical-evidence hurdle. HF verification preserves attributable quantization versus unchanged mirrors. Offering labels are internal discovery evidence; they do not change canonical Product.type or create product records. Existing signed settlements remain valid.

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
including requests currently in flight. Click **Previously qualifying**,
**Uncertain**, **Rejected**, **Failed evaluations** or **Excluded** to inspect
the corresponding frozen accounts and their recorded details. Each category
supports account/company search and pages of 50; category counts
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

All commands return JSON. `inspect` and `--dry-run` do not call providers or write application records. Enumeration, enqueue, the fixed-cohort rerun and evaluation-only drains use the separate discovery lock and return `discovery_busy` without waiting. `recover-list-billing --apply` also uses only that dedicated lock. Other registration, list synchronization and credential actions first require the harvest writer lock, then the discovery lock; a busy harvest writer returns `writer_busy`. Do not pause the cron to make a manual batch run.

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

An explicitly approved fixed cohort can be settled using:

```bash
python manage.py induct_official_company_accounts /path/to/owner-approved-manifest.json --expected-count 123 --dry-run
python manage.py induct_official_company_accounts /path/to/owner-approved-manifest.json --expected-count 123 --seconds 90
```

The manifest requires an approval reference and accounts with native X IDs, organization names, saved offering evidence and validated offering screens. The whole manifest validates before writes. Settlement appends an immutable zero-cost owner approval receipt and retains the saved screen separately from model inference; registration and list synchronization use the existing guarded functions. Suppression, active leases and identity collisions remain protected. Repeating the same manifest is safe. Confirm remote membership independently after draining queued additions; an acknowledged add and an already-present member remain different audit events. The October8 approved cohort has123 members, and does not grant blanket automatic approval to future classifier positives.

The completed October7 report reads its recorded v3 policy family after the current evaluator moves to v4. Later owner approvals and v4 attempts do not replace its historical qualification results.

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

A recognized `spend-cap-reached` list response reports `deferred_billing` and leaves a ready credential usable. If it occurs during owner, list or membership reads, every claimed item returns to verification without consuming an add attempt, and the whole list waits 24 hours. A later scheduled cycle reports the saved cooldown without contacting X; when due, the normal lane rechecks membership before delivery. A positive account balance alone does not prove that an X spending cap has cleared.

An actual refused list-add POST retains the existing two-, four-, eight-, sixteen- and twenty-four-hour retry delays. Each attempted refusal consumes that item's delivery attempt; unsent siblings retain theirs. After five attempts, the target needs review and the last cooldown still applies to the list. Recognized billing still reports `deferred_billing`; other POST 403 reasons report `deferred_write_refused`. Complete readback precedes another add, so an independently added member is confirmed without a duplicate POST. HTTP 401 after the allowed refresh, other preflight permission failures and owner mismatches retain credential blocking. The adapter saves only a bounded machine reason, not raw provider bodies, free-form detail or echoed secrets.

The scheduled caller emits `OFFICIAL_COMPANY_LIST_SYNC` because the canonical harvest summary omits this optional lane. Its safe fields distinguish the current observation from a saved stop:

| Field | Meaning |
| --- | --- |
| `error`, `error_origin` | Current machine code and whether it came from a provider observation, saved credential gate, blocked queue item, saved list cooldown or local configuration. |
| `provider_request_made` | Whether this invocation attempted any provider HTTP, including token refresh and successful reads before a later local check failed. |
| `blocked_reason`, `blocked_origin`, `blocked_at` | Persisted active credential stop. Later local refusals preserve the original cause and time. Historical unrecorded causes are `unknown` / `legacy_unknown` with a null time. |
| `credential_revision` | Token revision associated with the observation. A stale response cannot block a newer pair. |
| `credential_status` | Saved credential availability. A ready credential can coexist with a queue item still awaiting explicit recovery; that item reports `local_queue_gate`. |
| `error_observed_at` | Time of a fresh provider observation, when available. |
| `retry_at`, `queue_recorded_at` | Next permitted list retry and the queue record's update time. The queue time is not presented as the original provider failure time. |

A local gate with `provider_request_made: false` is an application decision based on saved state, not a new rejection from X. An operator hold records `blocked_origin: operator`. A failed refresh records a specific HTTP rejection or an uncertain transport/response/save outcome; an interrupted refresh remains stopped. Returning to ready clears active stop fields atomically with the credential transition. Secret material stays encrypted in the database and is absent from these diagnostics.

Existing `blocked_auth` intents require explicit recovery after the credential is repaired; readiness alone never requeues them. For a proven billing interruption, use the exact-target action below. The generic `retry` action resets discovery work and is not the list-only repair. Never reset a `refreshing` credential or an uncertain refresh failure through billing recovery. Run renewal only in the production credential store's process; old provisioning tokens in a local secret file are not current tokens.

### Recover one billing-blocked list intent

First inspect the selected intent without loading token plaintext, making provider requests or changing records. Replace the example identifiers with the reviewed target; the example is the dated Call A incident, not authorization for another recovery.

```bash
python manage.py official_co_account_extraction recover-list-billing \
  --intent-id 135 --list-id 2067062923525275922 > recovery-preview.json
```

The preview includes the credential revision/status/timestamp and the intent's identity, status, evidence, attempts and claim state. It reports eligibility and the expected effects. Apply requires that exact snapshot to still match. Registered account identity and evidence must agree, the intent must remain unsuppressed and below its delivery-attempt ceiling, and no ordinary claim may be active.

```bash
python manage.py official_co_account_extraction recover-list-billing \
  --intent-id 135 --list-id 2067062923525275922 \
  --expected-snapshot recovery-preview.json --apply
```

A historical block with unknown provenance additionally requires all three options on both preview and apply: `--acknowledge-operator-hold`, `--operator-hold-receipt <result.json>` and `--operator-hold-receipt-sha256 <reviewed-sha256>`. The bounded receipt must establish a successful rotation to the current revision, independently confirmed access, and a deliberately preserved hold whose update time lies within that recorded operation. For the November 6 incident, the original private receipt lives under the authoritative root checkout's `.local/2026-11-05-231021-chatter-list-roster/single-add-2026-11-06-173532/`. Inspect that evidence before acknowledging it; do not manufacture a receipt for an unknown stop. An initially ineligible preview still provides its snapshot, but apply must satisfy the receipt and all other guards.

Apply acquires only the official-company writer lock, then saves an operator hold named `recovery_validation_pending` bound to this intent. Short database transactions recheck the rows before and after HTTP; no row lock is held across provider requests. The shared token store may rotate once, saves the new pair atomically and retains the hold until validation finishes. It never restores an older pair. Owner/private-list checks and complete bounded membership reads are mandatory. Recovery makes **no list-add POST**: present membership confirms the intent; complete absence returns it to `verify_needed` for the normal scheduled lane, respecting any longer cooldown and preserving attempts/history.

A failed read retains the hold and reports its safe error. If a longer provider cooldown is already active, the intent retains that cooldown's reason and deadline; otherwise it records the new error and retry time. Successful recovery also preserves an active provider cooldown, including on a confirmed intent, so other accounts cannot bypass the list-wide pause. Recovery never charges or refunds a delivery attempt. A genuine credential failure records its actual cause. A crash during refresh leaves an uncertain stop that this action cannot reopen. A known recovery hold can resume only for its bound target with a fresh preview/snapshot. Changed evidence, suppression, account identity, token revision or hold state prevents final promotion. Do not remove those guards to make a retry pass. After success, verify the next applicable scheduled result and independently read membership; a successful command alone does not prove a later add occurred.

Before a list write, the adapter checks the authenticated user's stable ID and the target list's owner/private status. Read pagination permits up to 50 pages of 100 members, covering [X's documented 5000-member list capacity](https://help.x.com/en/using-x/x-lists-not-working), and remains subject to the request/lane deadline. An incomplete read cannot establish absence. A timed-out add is read back before another POST. New accepted evidence rebinds unresolved intents and invalidates obsolete claims; confirmed membership, suppression and manual-removal review remain durable. Positive confirmation updates one membership record without pretending a full-list reconciliation occurred. A later complete reconciliation showing removal marks the intent for review; it does not automatically re-add it. HTTP429 pauses the entire target list until the bounded provider reset/retry-after time, or15minutes when headers are absent. Synchronization stops at the first throttle and releases remaining claims; throttle-only retries do not consume an account’s delivery-failure allowance. Queued accounts resume through complete membership readback after cooldown. A reset time is a retry opportunity, not proof that an undocumented provider restriction has cleared.

## Evidence, records and compatibility

`OfficialCompanyScan` records initial and incremental cursors. `OfficialCompanyAccountState` records current evidence and outcome. Immutable `OfficialCompanyAttempt` receipts retain evidence, returned decisions, validation outcome, model/policy and token usage. `OfficialCompanyBudget` records reserved and spent USD. `OfficialCompanyProviderState` prevents repeating known model-auth failures. `OfficialCompanyListIntent` separates desired membership from confirmed `TwitterListMembership` observations. `OfficialCompanyOwnerCredential` stores the encrypted token pair, its revision and active stop provenance.

Registration reuses stable official organization edges and explicitly reviewed candidate mappings. Name/slug/role conflicts require review. It does not infer legal ownership percentages, create a BrandCompany ownership edge, or assign a specific product. The two new account references—account state and list intent—must join the benchmark branch's provider-neutral migration inventory before that migration integrates. This feature uses the current schema through shared identity functions.

Existing official X app setup and locally verified list access are documented in the plan. [X's OAuth2 documentation](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code) describes the standard two-hour access-token lifetime and refresh flow; actual runtime lifetime comes from the token response.

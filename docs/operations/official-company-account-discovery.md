# Official AI model-lab account discovery

This service finds official accounts of organizations developing or releasing AI models of any kind. It reads stored account profiles and posts. It registers supported company/brand identities and queues additions to Call A's existing private X list. It does not change editorial admission to Chatter or Pulse.

There are two separate jobs. `initial-scan` enumerates every account present at its start boundary, without an age cutoff. The scheduled harvester independently examines account, post-fetch and profile observations, with a rotating inventory check for missed observations. Evidence changes produce a new decision; follower-count changes alone do not.

The implementation defaults to disabled. Code and test completion do not establish production activation. The linked [plan](../plans/2026-10-06-100039-feat-official-co-account-extraction-plan.md) and dated activation receipts determine deployment status.

## Configuration and bounded operation

`official_company` in `config.yaml` is validated by `OfficialCompanyConfig`. Service-specific overrides are named `X_MONITOR_OFFICIAL_COMPANY_<FIELD_IN_UPPERCASE>` and are read by the canonical configuration loader.

Discovery, registration and outbound list synchronization have separate `enabled`, `registration_enabled` and `list_sync_enabled` flags. Registration requires discovery; synchronization requires registration. Per-cycle/day and initial-total USD limits default to zero. Zero funding dispatches no model request. The model is pinned to `deepseek-ai/DeepSeek-V4-Flash-0731` through the existing direct DeepInfra client and `DEEPINFRA_API_KEY`; no generic provider fallback is used.

The scheduled lane runs once after essential harvest work, only on a normal scheduled cycle with sufficient time. Its default ceiling is two model calls and a 45-second lane deadline, sharing the cycle-wide optional extraction allowance with existing targeted extraction. Calls reserve a conservative cost before dispatch. Unknown spend remains reserved. Authentication/configuration rejection blocks this model adapter until its credential revision changes or an operator explicitly resumes it.

The initial inventory is a separate resumable operator job. Enumeration and model evaluation are separate commands. Accepted, rejected, review-needed and no-evidence outcomes remain visible. Pending/retry work or unenumerated accounts means coverage is incomplete.

## Inspection and explicit actions

All commands return JSON. `inspect` and `--dry-run` do not call providers or write application records. Mutating operations use the same PostgreSQL harvest writer lock and return `writer_busy` without waiting when another writer owns it. Do not pause the cron to make a manual batch run.

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
```

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

Before a list write, the adapter checks the authenticated user's stable ID and the target list's owner/private status. Read pagination is bounded. An incomplete read cannot establish absence. A timed-out add is read back before another POST. Positive confirmation updates one membership record without pretending a full-list reconciliation occurred. A later complete reconciliation showing removal marks the intent for review; it does not automatically re-add it.

## Evidence, records and compatibility

`OfficialCompanyScan` records initial and incremental cursors. `OfficialCompanyAccountState` records current evidence and outcome. Immutable `OfficialCompanyAttempt` receipts retain evidence, returned decisions, validation outcome, model/policy and token usage. `OfficialCompanyBudget` records reserved and spent USD. `OfficialCompanyProviderState` prevents repeating known model-auth failures. `OfficialCompanyListIntent` separates desired membership from confirmed `TwitterListMembership` observations. `OfficialCompanyOwnerCredential` stores only encrypted token material.

Registration reuses stable official organization edges and explicitly reviewed candidate mappings. Name/slug/role conflicts require review. It does not infer legal ownership percentages, create a BrandCompany ownership edge, or assign a specific product. The two new account references—account state and list intent—must join the benchmark branch's provider-neutral migration inventory before that migration integrates. This feature uses the current schema through shared identity functions.

Existing official X app setup and locally verified list access are documented in the plan. [X's OAuth2 documentation](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code) describes the standard two-hour access-token lifetime and refresh flow; actual runtime lifetime comes from the token response.

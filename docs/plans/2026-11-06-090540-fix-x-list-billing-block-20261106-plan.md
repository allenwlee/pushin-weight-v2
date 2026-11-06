---
title: Preserve X list billing failures and recover the stalled Call A addition
type: fix
date: 2026-11-06
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: code
ollija:
  change_id: fix-x-list-billing-block-20261106-2026-11-06-090540
  branch: fix/x-list-billing-block-20261106
  workflow: lfg
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
# Preserve X list billing failures and recover the stalled Call A addition

## Plain-English Summary

Automatic additions to the official-account list stopped because the application treated an X spending-cap response as a credential failure. It saved a block and then sometimes reported only “credential blocked,” without contacting X again. Funding the account could not clear that saved block or the stalled queue item.

This repair will keep billing problems separate from broken credentials, show whether an error came from X or saved application state, and provide a guarded way to recover the affected Call A item. It uses the existing list client, encrypted token store, queue and scheduler. It does not change account selection, harvest searches, Chatter membership or the harvest schedule.

Verification will reproduce the first refusal and the later retry through the real scheduled call path with fake network responses. Recovery will be checked against the exact credential and list item, including crash and concurrency cases. On November 7, the owner authorized LFG through production deployment, including the discussed guarded recovery of the stalled item. The main risk is accidentally retrying an uncertain token refresh or reopening unrelated work, so both remain explicitly guarded.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/x-list-billing-block-20261106`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/x-list-billing-block-20261106/docs/plans/2026-11-06-090540-fix-x-list-billing-block-20261106-plan.md`
- Change: `fix-x-list-billing-block-20261106-2026-11-06-090540`
- Branch: `fix/x-list-billing-block-20261106`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/x-list-billing-block-20261106/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/x-list-billing-block-20261106/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `lfg`
- Delivery target: `production`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/x-list-billing-block-20261106` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/x-list-billing-block-20261106` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the parent implementation workflow; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

None.

## Goal Capsule

**Objective:** Official accounts discovered by the harvester can reach Call A again after a billing interruption, and the operator can see the actual reason whenever delivery stops.

**Means:** Extend the existing refusal handling, persist credential-block provenance, and recover one verified list intent through the existing workflow (KTD1–KTD5).

**Authority and endpoint:** On November 7, Allen requested `compound-engineering:lfg to deployment` after the readiness check explicitly included recovery of intent 135 and scheduled Call A verification. This authorizes implementation, tests, review, commits, push, production deployment and that bounded recovery. The parent owns delivery and observed operational verification. Preserve Chatter and continuous harvesting; no pause, bulk replay or unrelated provider work is authorized.

**Execution profile:** Standard plan; authentication, persistent state and external API risks. Follow the current AGENTS.md and the change-harvester and avoiding-recurring-mistakes skills. Stop a recovery on stale evidence, mismatched ownership, unresolved refresh outcome or a changed target; diagnose rather than bypassing the guard. Keep normal harvesting running throughout.

## Product Contract

### Problem Frame

`XOwnerListClient` marks GET HTTP 403 responses as authentication failures. A known `spend-cap-reached` response therefore blocks the shared owner credential. The token store retains no reason for that block, so a later caller can report `credential_blocked` before making any HTTP request. The affected list intent is also excluded from automatic retries.

### Requirements

- **R1 — Billing classification:** A recognized X spending-cap refusal must retain its provider reason and must not invalidate the owner's credentials. Unknown permission denials and actual authentication failures retain their existing protection.
- **R2 — Bounded retry:** Billing refusal before an add request pauses list delivery without consuming an account's delivery attempts. Later cycles report the saved cooldown without contacting X until it is due. Existing limits on actual refused add requests remain intact.
- **R3 — Truthful diagnostics:** Every stopped list operation identifies the current stop, the saved cause when known, and whether this invocation attempted provider HTTP. Saved cause/time must survive a restart; an unknown historical cause is explicitly unknown.
- **R4 — Safe credentials:** Preserve encrypted storage, matching-client and owner checks, atomic token rotation, revision fencing and the prohibition on repeating an uncertain refresh. A manual workflow hold must not be described as a provider authentication refusal.
- **R5 — Narrow recovery:** Recovery can change only the explicitly selected credential and list intent after checking their expected state. It preserves account evaluation, evidence, delivery history, suppression and unrelated intents, and establishes membership before another add can occur.
- **R6 — Existing operations:** Retain the scheduled official-company lane and its independent writer lock. Do not pause essential harvesting, change collection queries, start another scheduler, or perform Chatter roster work.

### Acceptance Examples

| ID | Input and action | Required observation |
|---|---|---|
| AE1 | A scheduled preflight receives `http_403:spend-cap-reached` | Credential stays ready; claimed intents leave claims with a billing cooldown; no add request or delivery-attempt charge |
| AE2 | Another cycle runs during AE1's cooldown | Saved reason and retry time are visible; zero provider HTTP attempts |
| AE3 | A genuine authentication failure creates a block, then a new process loads it | Original cause/time remain; the second result says it stopped locally and made no provider request |
| AE4 | A legacy blocked credential has no recorded cause | Output says the application has a saved block with unknown provenance; it does not invent a token expiry, billing cause or timestamp |
| AE5 | Authorized recovery targets the recorded Call A incident | Exactly that intent is confirmed from membership or returned to verification; unrelated records remain unchanged |
| AE6 | Recovery sees a stale revision, suppressed target, changed evidence or uncertain refresh | No reset or add; the result names the guard that failed |

### Scope Boundaries

No eligibility or classification changes, new account collectors, dashboard UI, spending-limit changes, blanket requeue, stale-token fallback or redesign of OAuth. No new provider-state table, queue or scheduler. The broader Chatter roster remains a separate task.

## Planning Contract

### Context and Research

Source baseline: `6bd4b15f679c8df006704ba3ccaa86596e9d17ec`. Current behavior runs through `monitor/cycle.py` → `core/official_company_discovery.py` → `core/official_company_lists.py` → `core/official_company_credentials.py`.

The November 6 investigation established these distinct observations; they must not be collapsed into one “bad token” incident:

| Observed time (JST) | Evidence |
|---|---|
| October 28, about 09:47 | Successful saved rotation to revision 26, followed by preflight `http_403:spend-cap-reached`; intent 135 became `blocked_auth` |
| November 6, 17:38 | A guarded refresh saved revision 27. Owner/list reads and one authorized Chatter add succeeded |
| November 6, 17:38:44.643991 | The parent restored the credential's blocked status as an intentional hold after that test; this was not an X rejection |
| November 6, 17:49:56 | Read-only snapshot: credential blocked at revision 27; Call A had 130 confirmed, 3 suppressed, 1 review-needed and 1 blocked intent, ID 135 |

Credential `updated_at` is not a reliable original failure timestamp: the current `block()` uses a bulk update without changing it. The November 6 timestamp above identifies the recorded operator action, not the October provider failure.

Incident constants: owner `allenwlee` / X ID `17456158`; Call A list `2067062923525275922` (`_official-staff`); credential key `x-owner-17456158-list-2067062923525275922`; intent `135` (historically `@LTX_io`, resolve its current stable account ID before execution). Snapshot values are future guards to revalidate, not proof of present production state.

Local receipts remain in the authoritative root checkout under `.local/2026-11-05-231021-chatter-list-roster/single-add-2026-11-06-173532/`, including `receipt.jsonl`, `verification.jsonl` and `result.json`. They are untracked evidence and are not copied into this worktree or committed. Implementation can proceed from the contract; incident recovery requires those receipts or equivalent verified evidence.

### Key Technical Decisions

**KTD1 — Classify the provider reason before the endpoint's existing 403 policy (R1, R4).** Add a distinct billing category to the existing sanitized `XListError` path. Start with the observed `spend-cap-reached` code; add another alias only with a verified provider example and test. Do not infer billing from arbitrary free text or treat every 403 as billing. Retain existing error codes for callers. A billing refusal can also be a refused POST; those facts are independent. Leave the OAuth refresh endpoint's fail-closed handling intact.

X documents authentication errors separately from forbidden requests and billing restrictions. A positive credit balance does not establish that a spending cap has cleared. These distinctions support this narrow classification rather than automatic credential replacement. See [X response codes](https://docs.x.com/x-api/fundamentals/response-codes-and-errors) and [X pricing](https://docs.x.com/x-api/getting-started/pricing).

**KTD2 — Reuse list-intent cooldowns (R2).** For billing failure during preflight or membership reads, release every claim into `verify_needed`, refund its just-consumed delivery attempt, and set a fixed 24-hour retry time. Reuse `last_error` and `next_attempt_at` for the whole-list gate. This avoids a new billing counter and limits repeated reads while an operator resolves a cap. At the due time the normal lane rechecks automatically. Recognized billing on an actual add keeps the existing 2/4/8/16/24-hour refusal backoff and five-refusal review limit. Unsent remaining claims retain their attempts. Report billing as `deferred_billing` rather than a write refusal on a GET. Keep HTTP 429 handling and manual review intact.

**KTD3 — Add three typed fields to the existing credential row (R3, R4).** Add `blocked_reason` (bounded sanitized code, at most 128 characters), `blocked_origin` (controlled values: provider, refresh, local_configuration, operator, legacy_unknown; blank when inactive), and nullable `blocked_at`. These describe one active credential stop. Clear them atomically when a verified transition returns the credential to ready; retain historical evidence in existing operation logs/receipts. Preserve the first cause/time when a later load refuses locally.

Schema review: `OfficialCompanyOwnerCredential` owns token availability; `OfficialCompanyListIntent` owns individual delivery state; `OfficialCompanyProviderState` belongs to the DeepInfra evaluator and has a different lifecycle. Existing migrations 0066–0068 and their current writers support extending the credential row. **Tables added: 0; retired: 0; new JSON columns: 0.** These fixed scalar facts have one value per credential, are queried/displayed directly, and do not warrant JSON or a new entity. No new index is needed for a primary-key lookup.

The additive migration preserves token bytes, revisions and statuses. Existing stopped rows receive `legacy_unknown`, an explicit unknown reason and no invented timestamp; ready rows have empty provenance. Enforce field limits/allowed origins at each shared write boundary, including bulk updates. Do not add a cross-field constraint that old code cannot satisfy during rollout. New code normalizes legacy or incomplete provenance on read. Recovery never runs while an old writer can still mutate this row.

**KTD4 — Carry provenance through the entire caller chain (R3).** Extend safe exception/result fields and the scheduled log allowlist together. Distinguish `error_origin` (fresh provider response, local credential gate, local cooldown or local configuration), saved `blocked_origin`/reason/time, credential revision, retry time and `provider_request_made`. Track HTTP attempts for the whole invocation, including refresh callbacks and earlier successful reads; a locally detected owner mismatch can follow HTTP. Never derive this flag merely from the last exception. A fresh provider observation uses its actual observation time; a saved intent cooldown may expose the intent's recorded time as such, without calling it the original credential block time. No secrets, token fingerprints, raw response bodies or arbitrary exception details enter these outputs.

Use the same diagnostic serialization in scheduled results and a read-only CLI inspection/dry-run path. Examples: “X refused the request: spend-cap-reached; list retry due …” and “Stopped by saved credential state; original cause unknown; no X request attempted.” The current manual hold must be identified from its receipt during recovery, not relabeled as a newly observed billing refusal.

**KTD5 — Add guarded, list-only recovery to the existing command (R5, R6).** Add `recover-list-billing` to `official_co_account_extraction`; default to an offline dry-run and require an explicit apply option for recovery. Do not reuse its generic `retry`, which resets discovery state and all nonconfirmed account intents. Share state transitions with the existing token/list implementation rather than adding a second API client.

The action takes the exact intent/list and expected credential revision/status, intent status/reason/evidence, and observed credential timestamp. It verifies registered account state, absence of suppression and an attempt count below the delivery ceiling. It ordinarily accepts a proven billing block only. The current revision-27 legacy case additionally requires an explicit operator-hold acknowledgement backed by the saved successful rotation/read receipt; an arbitrary unknown legacy block is not recoverable through this action. Reject `refreshing`, uncertain-refresh causes, decryption/client failures and mismatched snapshots. Use current encrypted tokens only; permit at most one refresh across expiry handling and any 401 callback in this invocation, through the existing rotating store. [X OAuth documentation](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code) describes refresh with offline access; a rotation does not itself prove list access or billing recovery.

Hold the existing official-company writer lock, never the essential harvest writer lock. Recheck guarded rows under a short transaction. Retain a durable credential hold (`blocked`, reason `recovery_validation_pending`, origin `operator`) while validation runs. Let only the guarded recovery context obtain the current pair through the shared store. A required refresh still persists `refreshing` before HTTP; after success it saves the new pair/revision atomically while restoring the recovery hold, rather than exposing `ready`. Do not duplicate the token exchange routine. Release database row locks before HTTP; retain the dedicated writer lock. A crash before final promotion leaves the hold; a crash during rotation preserves the uncertain-refresh stop.

The recovery action performs owner/private-list checks and bounded membership readback, **no add POST**. Recheck the credential revision/hold and target/evidence/suppression after HTTP. In one transaction, clear the recovery hold and either confirm observed membership or make the completely absent target due for normal scheduled verification, preserving its history and attempts. Incomplete pages cannot establish absence or authorize final promotion. On read failure retain the labeled recovery hold and selected intent's actionable error/cooldown; a billing refusal does not become a new authentication block. True credential/refresh failures replace the temporary hold with their actual cause. Never restore an earlier encrypted pair or falsely mark a newly rotated token invalid merely because a later read failed. A retry of a known recovery hold requires a fresh matching snapshot; an uncertain refresh remains ineligible. Respect any longer existing list cooldown and all unrelated records.

Future deliberate pauses use the existing list-sync enablement control under explicit operational authority. This plan adds no pause system and changes no current production flag.

### High-Level Technical Design

These sketches describe the required relationships; implementation may organize helpers differently while preserving the contracts.

Component flow:

```text
Render scheduled cycle → discovery lane / dedicated lock → intent sync
                                                          ↓
                                                stored owner-list client
                                                  ↙               ↘
                                      credential row/store      official X API
```

Request decision flow:

```text
local cooldown? → report saved reason, no HTTP
otherwise → load credential → saved stop? → report provenance, no HTTP
otherwise → refresh if needed → preflight/member reads → classify response
  known billing → queue cooldown; credential remains usable
  true credential failure → persist stop cause; block selected claims
  complete member evidence → confirm present / allow normal add when absent
```

Credential lifecycle:

```text
ready → refreshing → ready + new revision (one atomic token pair)
             ↘ blocked with refresh cause (uncertain outcome never retried)
ready → blocked with provider/local cause → later load reports saved cause
legacy blocked → explicit evidence-guarded recovery only
```

Recovery protocol:

```text
offline preview → acquire dedicated lock → match snapshot/evidence
→ persist labeled recovery hold → guarded refresh if needed, retain hold
→ owner/list checks → membership read → recheck snapshot/evidence
→ atomic ready credential + confirmed/pending-verification selected intent
```

Diagnostic data flow:

```text
provider observation / stored credential cause / stored intent cooldown
→ shared sanitized diagnostic fields → sync result → cycle log and CLI
```

Mode and action boundaries:

| Entry | Provider access | State change | Add membership |
|---|---|---|---|
| Inspection / recovery dry-run | None | None | None |
| Recovery apply | Guarded refresh and GETs | Selected credential + intent | None |
| Existing scheduled sync | Existing bounded policy, subject to cooldown | Existing lane | Existing bounded policy |

### System-Wide Impact and Risks

- Token provisioning/replacement, refresh start/success/failure, explicit blocking and recovery must all maintain KTD3. Fence block writes against the token revision that produced the failure so a late response cannot poison a newer pair.
- `monitor/cycle.py` must propagate KTD4 through `OFFICIAL_COMPANY_LIST_SYNC`. A green cron run or enabled flag alone does not prove list delivery works.
- The new command must bypass the command's broad harvest-lock branch while retaining dedicated coordination. Account evaluation and core harvest behavior remain under their existing controls.
- An additive migration supports active harvesting. Apply schema before new writers; tolerate old blank provenance until all relevant processes run the candidate. A code rollback must not drop the new fields or restore stale ciphertext; recovered state must not be reopened under the known-bad classifier.
- Billing may recur even after this defect is repaired. The fixed system must report and defer it accurately; the plan cannot promise that an external spending limit is removed.

### Open Questions

**Blocking planning questions:** None. Technical defaults are KTD1–KTD5.

**Deferred operational prerequisites:** Production and the bounded recovery are owner-authorized. Before recovery, re-read the credential, exact intent, current code revision and list membership, and validate the legacy operator-hold receipt. A changed snapshot requires renewed diagnosis, not widening recovery. No production success is inferred from the November 6 snapshot.

## Implementation Units

### U1. Establish the regression net

**Goal / requirements:** Reproduce the misclassification and loss of error context through the scheduled caller chain (R1–R4; AE1–AE4).

**Files:** `tests/test_official_company_list_sync.py`, `tests/test_official_company_credentials.py`, `tests/test_official_company_cycle.py`.

**Approach:** Extend the existing real encrypted-store/fake-transport fixtures. Replace the spending-cap preflight test's obsolete expectation of `blocked_auth` with the required behavior; retain its later-invocation/no-network assertion. Add regressions before changing behavior. Do not replace call-chain tests with standalone classifier tests.

**Test scenarios:** GET spending-cap at users/me, list metadata and a later member page; fresh failure followed by a new client/process during cooldown; actual 401 after one refresh; permission failure and wrong owner; uncertain refresh and missing configuration. Verify claims, attempts, token bytes/revision and sanitized scheduled output.

**Verification:** New billing/provenance assertions fail for the diagnosed reasons on the baseline; existing protection tests remain meaningful. Record expected failures separately from passed checks.

### U2. Correct billing handling and retry accounting

**Dependencies:** U1. **Requirements:** R1, R2, R4; AE1, AE2.

**Files:** `core/official_company_lists.py`, its tests from U1.

**Approach:** Implement KTD1–KTD2 in the shared classifier, preflight/member exception path and existing list-wide cooldown gate. Reuse `_complete(..., consume_attempt=False)` for unsent work. Preserve claim fencing and before-POST evidence checks.

**Test scenarios:** Each GET refusal releases all claims without attempt consumption; the next cycle makes zero HTTP calls; the due cycle can verify then deliver. POST billing retains the existing five-refusal contract; unsent siblings keep attempts. Rate limits, unknown 403 reasons, incomplete pagination, changed evidence and suppressed work keep their current protections.

**Verification:** Billing never changes a ready credential to blocked; retries are bounded at the list level and actual refused writes retain their limits.

### U3. Persist and report credential-stop provenance

**Dependencies:** U1. **Requirements:** R3, R4; AE3, AE4.

**Files:** `core/models.py`, one additive `core/migrations/` migration, `core/official_company_credentials.py`, `core/official_company_lists.py`, `monitor/cycle.py`, credential/list tests.

**Approach:** Implement KTD3–KTD4 across every writer and both output paths. Keep repeated local refusal from replacing the original cause. Distinguish a rejected refresh response from an uncertain transport/result without allowing automatic reuse of either failed refresh token. Review field ownership and all bulk writes against the schema contract before migration generation.

**Test scenarios:** New block survives reload with exact cause/origin/time; repeated load does not alter it or call HTTP; legacy rows normalize honestly; ready transitions clear active facts; stale failures cannot block newer revisions. Migration preserves ciphertext/revision/status for ready, blocked and refreshing fixtures. A refresh attempt followed by a local error still reports that provider HTTP was attempted. Inject secret-like strings into provider errors and verify output remains sanitized.

**Verification:** Database state, CLI-safe diagnostics and real scheduled logs agree about cause and freshness; rotation and uncertain-refresh protection still pass.

### U4. Add exact-target inspection and recovery

**Dependencies:** U2, U3. **Requirements:** R5, R6; AE5, AE6.

**Files:** `monitor/management/commands/official_co_account_extraction.py`, existing shared token/list modules, proposed `tests/test_official_company_list_recovery.py`.

**Approach:** Implement KTD5 within the existing service/command boundary. Share safe state transitions and diagnostic rendering; keep network decisions in the existing client. The default preview reports expected/current state and planned effects without reading token plaintext or contacting X. Applying the action must name its exact target and incident evidence.

**Test scenarios:** Dry-run has no writes/network; wrong list/revision/status/reason/evidence, exhausted attempts and suppressed/review-needed targets refuse unchanged. Verify the receipt-backed legacy operator-hold route separately from a genuine refresh failure. Observed membership confirms without POST; complete absence schedules verification; incomplete/failed reads never establish absence. Simulate crashes before network, during refresh, after saved rotation and before/after final promotion, plus concurrent suppression/evidence change. No failed recovery exposes a ready credential with an unrepaired target. Preserve the saved rotated pair and enforce one refresh across expiry and 401 handling. Check all other intents and account-state rows remain byte-for-byte unchanged. Confirm the command takes only the dedicated writer lock.

**Verification:** Recovery cannot make an add request, reset discovery state, overwrite rotated tokens or silently release uncertain credentials. A subsequent ordinary cycle handles only eligible due work under its existing policy.

### U5. Document and verify the full repair

**Dependencies:** U2–U4. **Requirements:** R1–R6.

**Files:** `docs/operations/official-company-account-discovery.md`, `docs/reference/db-schema.md`, this plan; update only directly affected existing glossary text if necessary, following updating-reference-docs.

**Approach:** Explain billing versus authentication, fresh versus saved error, the selected cooldown, inspection and guarded recovery, and manual holds. Preserve dated October/November evidence. Reconcile final code, schema and runbook. Remove abandoned helpers or duplicate paths introduced during implementation.

**Test scenarios:** Full scheduled failure → saved cooldown → due recheck → membership confirmation; command recovery → scheduled verification with no duplicate add. Include the existing real-auth, uncertain-refresh, POST-refusal and rate-limit regressions in the final focused run.

**Verification:** Execute the Verification Contract. Document only checks actually run, and keep code completion distinct from any later production recovery.

## Verification Contract

No tests or runtime probes were run to author this plan. Prior production observations above are dated evidence, not verification of a fix.

During implementation, use the permanent shared test database on fuchitalee and its exclusive-use wrapper. Read the canonical operating note first. The wrapper refuses pending migrations; apply the authorized local test migration under its lock before the final tests. Never create another database or point tests at production.

```bash
~/.local/bin/pushinweight-test-db run python manage.py migrate --noinput
~/.local/bin/pushinweight-test-db pytest tests/test_official_company_credentials.py tests/test_official_company_list_sync.py tests/test_official_company_cycle.py tests/test_official_company_list_recovery.py
```

The migration command belongs to implementation only, after reviewing the generated additive migration and shared-database availability. Before U3, run the existing schema-compatible regression tests to capture U1's expected failures. Run directly affected command tests in `tests/test_official_company_scan.py` and `tests/test_official_company_requalification.py` if shared command dispatch changes. Do not treat an expected baseline failure as a passed regression.

Apply the change-harvester skill's query-byte gate against baseline `6bd4b15f`: this task changes no A/B/C query bytes, cursor policy or collection budget. Record the relevant query regression evidence required by that skill without issuing paid search probes. Focus integration proof on the optional scheduled list lane and essential-harvest continuity.

For later authorized production delivery/recovery:

1. Follow the owner-selected release route and observe the exact candidate revision running; apply the additive schema without stopping harvesting. Verify old credential writers have finished before recovery.
2. Read-only inspection revalidates the incident snapshot and receipt, current queue counts, target account/evidence and list settings. Run the offline recovery preview; record its exact expected effects.
3. Apply only the guarded recovery action. Record safe reason, origin, request-attempt facts, revision and before/after state. Do not change budgets or other list items to make the check pass.
4. Observe the next applicable scheduled list operation and independently read membership. If already present, confirmation is sufficient; if added, verify the target membership and durable intent confirmation. No second POST is justified merely by a lost acknowledgement.
5. Verify normal harvest cycles continued and suppressed/review-needed/unrelated intents were preserved. If X still refuses for billing, report that outcome and cooldown; operational recovery is incomplete even when the code fix passes.

## Definition of Done

- U1–U5 satisfy their named verification and the focused regressions pass against the implemented revision.
- Billing refuses list work without poisoning credentials; later output distinguishes fresh provider evidence from saved application state.
- Credential provenance survives restarts, covers every writer, and preserves token/refresh security.
- Exact-target recovery is tested, documented and unable to add directly or reset unrelated discovery work.
- Migration/schema documentation match; no new table or JSON storage, stale duplicate implementation or abandoned experiment remains.
- Any later selected delivery endpoint is reported separately. “Production recovered” requires exact-revision and membership/intent evidence from the Verification Contract; planning or passing tests alone cannot establish it.

## Appendix

### Sources that shaped the plan

- `docs/operations/official-company-account-discovery.md`: owner-client operation and prior recovery boundaries.
- `docs/plans/2026-10-26-095132-fix-enrichment-tracked-promotion-20261026-plan.md`: dated October 28 recovery evidence; informs KTD5 without granting new authority.
- `docs/solutions/runtime-errors/cmd-run-summary-fidelity-three-fixes.md`: verify every reporting boundary, applied in KTD4/U3.
- `docs/solutions/integration-issues/harvest-pipeline-missing-call-queries.md`: successful process exit is insufficient evidence of useful collection, applied in production acceptance. Its legacy topology is not current authority.
- `docs/solutions/architecture-patterns/backfiller-and-llm-classifier-pipeline-wiring.md`: reuse shared execution paths and protect scheduled collection, applied in KTD5.
- `docs/solutions/workflow-issues/2026-09-25-203900-authorized-release-blocked-by-inherited-gates.md`: separate code delivery from cause-specific runtime recovery.

Planning research used source reads and earlier verified incident evidence. It performed no provider calls, production mutations, implementation or tests.


## Execution Record

### 2026-11-07T06:04:52+09:00 — U1/U2 verified

- Five baseline regressions failed for the expected incorrect statuses before product edits: GET billing became `blocked_auth`; POST billing reported `deferred_write_refused`. The real scheduled runner, encrypted credential store and fake HTTP transport remain in the regression chain.
- Corrected only the observed sanitized `spend-cap-reached` classification. Unsent read-stage claims retain their attempts and share a 24-hour list cooldown. Actual refused adds keep existing retry pacing and the five-attempt limit.
- Parent verification: `tests/test_official_company_list_sync.py` plus `tests/test_official_company_credentials.py`: **36 passed, 0 skipped, 0 errors**. `git diff --check` passed.
- Local test environment has already-applied Chatter migrations beyond this production candidate. Tests used four byte-identical migration inventory files from staging `963ba4b6e1394b39ff7e6c22b177ed984f6eba98`, removed afterward. The existing database contains two applied migration branches. A private pytest-django `django_db_setup` adapter uses the already-prepared database and retains the wrapper's exclusive lock, exact database identity, complete migration inventory, consistent history and no-pending-migrations checks; normal per-test isolation remains active. No schema setup or fake migration ran. This verifies candidate runtime against the existing compatible schema, not a candidate-only schema creation. The adapter and inventory helper are in the authoritative root's `.local/2026-11-07-055502-x-list-billing-lfg/`.
- Baseline query inventory rendered all 18 calls through the shared planner and request suffix code with explicit fixed windows and checked-in production query switches: maximum 511 UTF-8 bytes, no provider/database access. Final comparison remains pending.

### 2026-11-07T06:19:29+09:00 — U3 verified; current-schema verification prerequisite

- Two expected baseline failures established absent exception and scheduled diagnostic provenance before implementation. Parent combined credential/list/cycle verification now **61 passed, 0 skipped, 0 errors**. The saved block retains first cause/time, records refresh outcome, protects newer revisions and accounts for all provider requests in the invocation.
- Applied only local migration `0225_official_company_credential_provenance`, depending on `0223_merge_backfill_retry_policy`, under the shared wrapper. Three real legacy fixture rows (ready, blocked, refreshing) retained ciphertext, revision, status and update timestamp across the migration; inactive fields stayed empty and historical stops became explicitly unknown. Database defaults allow old writers to insert during rollout. Schema/model drift check passed. No production schema change yet.
- The existing full-cycle test had two obsolete eight-call assertions after the already-deployed query change. Updated the exact expected set to the current sixteen base calls and added equality against the actual fake-transport queries. Product query sources are unchanged.
- Scoped lint passed; models/cycle have 239 pre-existing Ruff findings with no introduced finding, compared by code/message/source line against the unit base. Separate pure delivery-workflow suite: **36 passed**, no PostgreSQL required.
- U5 requires repairing a stale verification prerequisite before live acceptance: the latest-N checker hardcodes six languages and requires eager commentary although current literal-v2 writes normalized EN/ZH-CN/JA translations and synthesis is demand-driven. Source: `monitor/post_artifacts.py` completion/publication helpers and the prior query-release plan's recorded mismatch. Add an explicit current-contract mode that checks source identity and all translation locales, reuses language validation, and separately verifies requested synthesis while reporting unrequested/cancelled work honestly. Keep legacy evidence support, read-only/sanitization/age/classification/exact-cohort guards. Adapt the obsolete extra-database historical SQL fixture to the existing shared-database schema rehearsal, and add current-schema SQL proof. This changes verification only; it does not change enrichment behavior or relax required current output.

### 2026-11-07T06:43:58+09:00 — U4 verified

- Added offline exact-target preview and snapshot-bound recovery through the existing command, dedicated discovery lock and encrypted token client. Recovery holds the credential durably while validating, makes no add request, preserves delivery attempts/history and requires complete membership evidence before confirming or returning one intent to scheduled verification. Known hold resumption retains longer cooldowns; uncertain refresh remains ineligible.
- Parent observed the initial preview regression fail on the missing CLI action, then pass. Final recovery/credential/list suite: **117 passed; 117 required PostgreSQL tests executed, 0 skipped, 0 errors**. Coverage includes receipt validation, actual encrypted rotation, one-refresh ceiling, crashes, concurrent account/evidence/suppression changes, unrelated-row preservation, GET-only recovery and later scheduled confirmation.
- Review reproduced a manual-refresh diagnostic race: an old request's error was attributed to a replacement revision. A metadata-only shared diagnostic helper now preserves attempted revision and nests current credential facts; the real refresh CLI regression failed before the fix and passed afterward. Ready credentials with unrecovered queue items now report `local_queue_gate` and credential status.
- A concurrency fixture initially violated the existing X account identity constraint. Corrected it to perform a valid concurrent intent reassociation; the recovery guard now fails for the intended changed-target reason. No product identity constraint was weakened.
- The wider command/cycle/scan/requalification run passed all relevant cases. Its only failure was a separately repaired stale query expectation, recorded under U5. Scoped Ruff and whitespace checks passed; migration drift check passed after removing all temporary test inventory files.

### 2026-11-07T06:44:22+09:00 — U5 local verification complete

- Updated the existing operational runbook and credential schema section against the real code and local database: three typed provenance fields, 8 total credential columns, 0 foreign keys, 0 tables added/retired, no new JSON. Documented offline preview, exact snapshot/receipt guards, dedicated lock, GET-only recovery and subsequent scheduled verification. Removed the generic discovery-retry recommendation for this billing incident.
- Repaired the stale latest-N checker with explicit `literal-v2` verification while retaining legacy behavior. Parent captured two initial expected failures and two more for newer pending/cancelled synthesis alongside an earlier valid publication. Final suite: **99 passed, 0 skipped/errors; both required PostgreSQL tests executed**. Current artifacts are compared with real canonical publication/fingerprint helpers; historical schema detection uses the existing shared database's isolated schema rehearsal without another database or public schema rewind.
- Final query inventory is byte-for-byte equal to baseline: **18 calls, maximum 511 UTF-8 bytes**, SHA-256 `500cc82b754f8ae2981e3c3b65e4a963bf27106e80674954b76b0cf5803bbe10`; no search/provider calls. The broader run was 236 passed / 1 stale query assertion. That assertion still expected generic `NVIDIA AI`, explicitly removed in the already-shipped NVIDIA follow-up. Moved it to the negative controls and retained specific `NVIDIA AI Factory` / `NVIDIA H200` positives. Query/diff/length suites now **77 passed, 8 required PostgreSQL cases executed, 0 skipped/errors**. Production query code/configuration remains unchanged.
- Required immediate production health observation at approximately 06:36 JST: **0 complete, 20 fresh-pending, 0 unhealthy**; `status=healthy_with_pending`, `regression_gate=inconclusive`, `acceptance_gate=failed` because language/current literal artifacts were still pending (0/20). Requested synthesis was 3/3 complete. This is recorded incomplete evidence, not a passed completeness gate; the immediate route requires one observation and was not retried. Exact ordered cohort: 2118815945208836432, 2118816569077960956, 2118816586828255249, 2118818284267340073, 2118816610937094280, 2118815038014366128, 2118815350003552569, 2118815751918473726, 2118816229582402000, 2118816320657445132, 2118817903344566732, 2118818208085885426, 2118818209138725180, 2118815044922413189, 2118815121900187950, 2118815188099186933, 2118815343737192820, 2118815369267675155, 2118816332112146655, 2118817161179242946. Full safe JSON is in the root private receipt directory.
- Scoped Ruff, whitespace and migration drift checks passed. Repository-wide Ruff reports 1,938 existing findings: 1,699 in unchanged files plus the previously compared 196 model and 43 cycle findings; none introduced. No project-wide type-check command is configured. The 36 pure Ollija checks passed earlier and their inputs remain unchanged.
- Implementation is complete locally. Production remains on baseline `6bd4b15f`; no new code, schema or recovery action has been deployed. LFG simplification/review and authorized delivery remain with the parent. The default staging branch still contains unrelated Chatter changes (`963ba4b6`), so an alternate delivery route requires the owner's explicit selection under AGENTS.md after a concrete reviewed candidate is ready.

### 2026-11-07T07:17:00+09:00 — LFG review fixes verified

- Simplification replaced repeated recovery-hold literals with one shared constant; 67 recovery tests passed afterward. Full code review completed with 11 local reviewers and independent validation of two P2 findings. Review artifacts: `/tmp/compound-engineering-501/ce-code-review/2026-11-07-064732-x-list-c0a54054/`. The earlier Claude route remained unfunded; the alternative Grok attempt produced no usable review within its 600-second attempt bound. Independent-model coverage is degraded, not passed; no provider retry followed.
- Finding #2 exposed an incomplete R2/U4 implementation: successful recovery cleared the marker needed to enforce a retained whole-list pause. Parent reproduced six cases as failing regressions, then repaired the existing transition. Scheduler and recovery now share one cooldown lookup; confirmation retains the governing reason/deadline, a later shorter read failure cannot erase them, and recovery neither charges nor refunds attempts. Fresh command errors remain separate from the persisted cooldown cause. Tests cover pending siblings before/after expiry, present/absent membership, intervening 503/429 failures and a retained 429 without an erroneous refund. This completes the existing KTD5 requirement; it introduces no new permission or product policy.
- Added the review's missing successful-refresh/failed-save regression: the original encrypted pair and revision remain blocked with `refresh_save_uncertain`, and a new process cannot exchange the old refresh token again. Final focused credential/recovery/list/cycle suite: **137 passed, 137 required PostgreSQL cases executed, 0 skipped/errors**. An earlier broader run was 134 passed/1 assertion failure: the old assertion expected a later read error to replace the governing cooldown marker. Updated it to assert the fresh command error and retained pause separately. Scoped Ruff and whitespace checks passed. Temporary migration inventory files were removed.
- Finding #1 remains unapplied: P2, `.claude/skills/harvester-latest-n-health-check/scripts/check.py:886`, “File-size regression: separate normalized artifact validation.” Suggested follow-up: extract the literal-v2 SQL/fingerprint/demand/artifact contract into a focused helper, preserving CLI/report output and including helper source/hash in detailed evidence. It has confidence 75 from one maintainability persona; independent validation confirmed its file-size precondition but supplied no cross-persona runtime-defect agreement. It does not meet LFG's automatic-fix bar. Carry this exact residual into the final delivery report (or PR body if a PR is used), not as silently accepted debt.
- No new compound document is needed: the durable reasoning is carried by the transition, regression tests, operational runbook and this plan. `ce-test-browser mode:pipeline` maps no affected browser route: changed code is the background list client/queue, CLI, schema and read-only checker; views, URLs, admin and templates have no affected references. Browser testing is **not applicable**, with zero pages exercised, not a passed browser run.
- Fresh read-only production baseline at 07:02:14 JST still showed held credential revision 27 and intent 135 `blocked_auth`, two attempts, saved `http_403:spend-cap-reached`. The original November 6 operator-hold receipt passed the actual local receipt validator against that metadata without provider or database requests from validation. Production main/web/harvest remain `6bd4b15f`; staging remains unrelated `963ba4b6`. Prepared an exact-SHA/database/target-guarded one-off controller using the deployed harvest image and managed secrets, with separate preview, apply and independent membership phases; no job has been launched.

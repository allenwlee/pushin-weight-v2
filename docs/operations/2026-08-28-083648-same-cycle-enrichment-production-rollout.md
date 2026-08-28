# Same-Cycle Enrichment Production Rollout

This is the append-only, timestamped evidence ledger for promotion of the
same-cycle enrichment candidate. Times are UTC unless explicitly labeled JST.
The recorder is read-only with respect to Git refs, Render services and
schedules, production databases, provider state, and production execution.
Secret values, queries, raw post text, and provider payloads are intentionally
excluded.

## Rollout status

- **State:** finalized and ready for parent review
- **Candidate SHA:** `c07a268c2268a6df477c80a9e8c08ba6fc05e4f6`
- **Pre-promotion production SHA:** `e5e05efe059a3d4b85380a531cb2415079d6c50e`
- **Final verdict:** **QUALIFIED PASS** — production zero-disruption,
  exact-SHA same-cycle, persisted-output, feed, and settled quality gates
  passed; the staging-wrapper false-negative and uncaptured production
  provider-host fingerprint are explicit follow-up limitations, not production
  stop triggers under the parent's final classification
- **Stop decision:** no stop trigger through B2; parent classified B1's explicit
  `degraded` status as nonblocking after exact current-cohort checks passed and
  its degradation was limited to one author-role fact plus 102 quarantined
  backlog rows, with zero current pending/failed rows and no translator or
  classifier failure
- **Rollback decision:** not invoked

## Governing gates

| Gate | Evidence | Status |
|---|---|---|
| Authoritative location | Host `fuchitalee`; repository `/Users/fuchitalee/development/pushin-weight-v2`; canonical worktree `.worktrees/feat/same-cycle-enrichment` | Pass |
| Owner-selected target | Plan frontmatter records `delivery_target: production` and `delivery_selected_by_user: true` | Pass |
| Generated Ollija guide | Current generated guide records workflow `lfg`, target `production`, and owner selection `true` | Pass |
| Delivery exceptions | Isolated staging caps retained; production suspension, reschedule, manual run, and Blueprint apply forbidden; exact candidate and every natural boundary required | Pass |
| Worktree placement | Candidate worktree is registered inside the configured Ollija release area | Pass |
| Candidate identity | Worktree HEAD, remote feature, and remote staging resolve to the candidate SHA | Pass |
| Production mutation authority | Parent workflow owns promotion; recorder performs observation and ledger writes only | Pass |
| Final cleanup eligibility | Exact-SHA production verification is complete; recorder is prohibited from cleanup and the parent must separately prove the canonical worktree clean/unlocked at candidate SHA after preserving documentation | Parent-owned final action |

The plan's owner-continuation exceptions and this ledger instruction were
present as uncommitted plan-document changes at `2026-08-27T23:38:31Z`; the
candidate code SHA itself was unchanged. The candidate commit already contains
the production-selected frontmatter and generated production guide.

## Immutable service and schedule facts

| Surface | Verified fact |
|---|---|
| Production harvest | `pushinweight-harvest`, service `crn-d9gv94o4n6ts739tqaug` |
| Natural schedule | `*/15 * * * *` |
| Suspension state at B0 | Unsuspended |
| Production execution policy | Natural scheduled runs only; no manual substitute |
| Production deploy policy | Existing auto-deploy only; no Blueprint application |

## Continuity ledger

Each expected `00/15/30/45` boundary from B0 through the first qualifying
candidate-SHA cycle and the following natural boundary must be present. A
missing, duplicate, aborted, lock-skipped, manual, or uncorrelatable boundary
is a permanent failure.

| Label | Scheduled boundary | Deploy SHA | Run ID | Started | Finished | Terminal status | Calls | Results | Inserts | Updates | Correlation | Gate |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---|---|
| B0 | `2026-08-27T23:30:00Z` | `e5e05efe059a3d4b85380a531cb2415079d6c50e` | `20260827T233016_0000-35621e02` | `23:30:16Z` | `23:31:47Z` | successful; `lastSuccessfulRunAt=23:31:51Z` | 7 | 88 | 46 | 4 | Natural service/run/deploy evidence supplied and verified by parent | Pass |
| B1 | `2026-08-27T23:45:00Z` | `c07a268c2268a6df477c80a9e8c08ba6fc05e4f6` | `20260827T234525_0000-968330d9` | `23:45:07.437Z` Render / `23:45:25Z` summary | `23:48:06Z`; `lastSuccessfulRunAt=23:48:10Z` | Render successful; summary `degraded` | 7 | 57 | 29 | 3 | Natural execution, exact SHA, summary and cohort hashes correlate; internal `cycle_kind=manual` is the ordinary command label described by KTD1 | Pass; exact same-cycle/feed/quality checks passed; degraded note retained |
| B2 | `2026-08-28T00:00:00Z` | `c07a268c2268a6df477c80a9e8c08ba6fc05e4f6` | `20260828T000047_0000-c24ccf99` | `00:00:20Z` Render / `00:00:47Z` summary | `00:03:12Z`; Render success `00:03:20Z` | Render successful; summary `degraded` | 7 | 73 | 28 | 2 | Natural execution, exact SHA, summary and cohort hashes correlate; degradation only quarantined backlog | Pass; required Bn+1 continuity closed |

## Timestamped event ledger

### 2026-08-27T23:31:51Z — B0 pre-promotion boundary completed

- Natural production run `20260827T233016_0000-35621e02` completed on
  pre-promotion deploy `e5e05efe059a3d4b85380a531cb2415079d6c50e`.
- Started `23:30:16Z`, finished `23:31:47Z`, and Render recorded
  `lastSuccessfulRunAt=23:31:51Z`.
- The terminal evidence reports seven calls, 88 results, 46 inserts, and four
  updates.
- Production harvest was unsuspended on the unchanged `*/15 * * * *` schedule.
- **Gate result:** pass; B0 is the closed pre-promotion boundary.

### 2026-08-27T23:38:00Z — exact candidate promoted to `main`

- Parent performed the server-enforced fast-forward push of exact candidate
  `c07a268c2268a6df477c80a9e8c08ba6fc05e4f6` to `refs/heads/main`.
- The prior remote `main` was
  `e5e05efe059a3d4b85380a531cb2415079d6c50e`; the merge-base fast-forward
  condition had passed before the push.
- Immediate remote-ref observation showed `main`, `staging`, and
  `feat/same-cycle-enrichment` all at the exact candidate SHA. The recorder
  independently observed the same three remote refs at `23:38:31Z`.
- No Render service, schedule, suspension state, manual production run, or
  Blueprint was mutated as part of promotion.
- **Gate result:** pass; exact-candidate promotion completed after B0.

### 2026-08-27T23:38:12Z–23:38:13Z — production auto-deploys created

| Service | Deploy ID | Commit | Initial state |
|---|---|---|---|
| `pushinweight-web` | `dep-da8ckp7lk1mc73f224o0` | candidate SHA | `live` at `23:39:35Z` |
| `pushinweight-harvest` | `dep-da8ckpflk1mc73f225dg` | candidate SHA | `live` at `23:39:04Z` |
| `pushinweight-headlines` | `dep-da8ckp7lk1mc73f22500` | candidate SHA | `live` at `23:39:25Z` |

- All three deploys were created by the existing auto-deploy path on the exact
  candidate commit.
- **Gate result:** pending until each service reports a terminal live state on
  the exact candidate SHA.

### 2026-08-27T23:39:04Z — production harvest became live

- Deploy `dep-da8ckpflk1mc73f225dg` for `pushinweight-harvest` became `live`
  on exact candidate `c07a268c2268a6df477c80a9e8c08ba6fc05e4f6`.
- At this observation, web and headlines remained `update_in_progress`.
- **Gate result:** harvest SHA convergence passed; full production service
  convergence remains pending.

### 2026-08-27T23:39:25Z–23:39:35Z — production services converged

- `pushinweight-headlines` deploy `dep-da8ckp7lk1mc73f22500` became `live` on
  the exact candidate at `23:39:25Z`.
- `pushinweight-web` deploy `dep-da8ckp7lk1mc73f224o0` became `live` on the
  exact candidate at `23:39:35Z`.
- Together with harvest at `23:39:04Z`, all three production services now
  report the exact candidate SHA before B1.
- **Gate result:** pass; production service SHA convergence completed.

### 2026-08-27T23:40:02Z — schedule continuity rechecked

- Production harvest remained unsuspended on schedule `*/15 * * * *`.
- `lastSuccessfulRunAt` remained the closed B0 value `23:31:51Z`, as expected
  before the `23:45Z` boundary.
- **Gate result:** pass; no schedule or suspension mutation observed.

### 2026-08-27T23:43:01Z — recorder pre-B1 service snapshot

- Read-only Render service inventory resolved production web to
  `srv-d9go2breo5us73cg6vqg`, harvest to `crn-d9gv94o4n6ts739tqaug`, and
  headlines to `srv-d9ufj4e417fc73d93g20`.
- All three services reported `not_suspended`; harvest alone remained the
  cron service, still on `*/15 * * * *`.
- **Gate result:** pass; service identity and natural scheduling remained
  stable immediately before B1.

### 2026-08-27T23:45:07Z — B1 started naturally

- Render started the scheduled production cron job at `23:45:07.437Z`; the
  command began `python manage.py run_cycle` at `23:45:22.081Z`.
- The production harvest service remained `not_suspended` on
  `*/15 * * * *`; no manual substitute was used.
- The service had converged to the candidate SHA before this boundary.
- **Gate result:** in progress; natural start continuity passed and terminal
  run correlation/count evidence is pending.

### 2026-08-27T23:48:06Z–23:48:10Z — B1 terminal evidence and immutable cohort

- Render recorded successful completion at `23:48:10Z`. The correlated
  `HARVEST_SUMMARY` for run `20260827T234525_0000-968330d9` started at
  `23:45:25Z`, finished at `23:48:06Z`, and identifies service
  `crn-d9gv94o4n6ts739tqaug` and the exact candidate SHA.
- The summary hash is
  `af2a37191b4f297238376eeee06c4cc9ff71182241ad5de37b27292a15de00ec`.
  Seven of seven planned calls ran, producing 57 results, 29 inserts, three
  updates, and zero persistence failures.
- The summary status is explicitly `degraded`. Its safe counters show 102
  quarantined enrichment rows and one degraded author-role fact; translator
  and classifier failed/unavailable counters are all zero, and the tip sweep
  remained within its 120-second target. This ledger does not reinterpret the
  degraded result; parent stop/acceptance classification remains pending.
- The internal `cycle_kind` is `manual`, which is the ordinary command label
  explicitly documented by plan KTD1. Render scheduler evidence proves this
  was the natural B1 execution, not a manually substituted run.
- Correlated `HARVEST_COHORT` receipt hash
  `5e9b4cb6f7794192fefae8725a6d9317defc7303e9100e3658b5a4ab8c03e0b2`
  declares 29 inserted IDs, the same 29 current-cycle IDs, 50 carryover IDs,
  and 79 enrichment facts. All 29 current-cycle and all 50 carryover facts
  report translation succeeded, classification succeeded, and complete
  persisted output.
- Because B1 inserted rows, its exact 29 IDs are the immutable acceptance
  cohort and cannot be replaced by a later run. The IDs are intentionally not
  reproduced here; the receipt hashes bind the exact bounded set without raw
  content.
- **Gate result:** natural continuity and receipt correlation pass; exact
  cohort DB/feed/quality checks, parent classification of the degraded result,
  and the following B2 natural boundary remain pending.

### 2026-08-27T23:51:46Z — B1 exact cohort DB/feed/quality checks passed

- Parent supplied redacted read-only production ORM evidence bound to B1's
  exact 29 current-cycle IDs: requested/found `29/29`, missing `0`, terminal
  `29/29`, and persisted-output complete `29/29`.
- All 29 exact cohort IDs were feed-visible after terminal completion and all
  29 had signals. The evidence counted 41 brand edges and 41 signal rows.
- The non-`zh-Hans` Chinese-text gate passed `27/27` (`100%`). English
  commentary was nonblank and distinct for `29/29` (`100%`), and Chinese
  commentary was nonblank and distinct for `29/29` (`100%`). Each result is
  above the strict 99% integer floor.
- Discourse existed for 21 of 29 posts across 28 rows. The supplemental
  latest-N checker marked 9 of 20 rows unhealthy only for missing discourse;
  discourse is an optional secondary surface and is not part of the settled
  B1 same-cycle/feed/quality contract. This supplemental result does not
  override the exact-cohort acceptance evidence.
- Parent classified the summary's `degraded` status as nonblocking for the B1
  acceptance gates: its safe degradation facts are limited to one
  `call_a_author_roles` fact and 102 quarantined backlog rows, while all 79
  claimed rows succeeded, current pending/failed counts are zero, and no
  translator/classifier failure occurred.
- **Gate result:** pass; B1 is the accepted immutable same-cycle cohort. B2,
  the following natural boundary at `00:00Z`, remains required before the
  production rollout verdict can close.

### 2026-08-27T23:55:56Z — recorder pre-B2 immutability snapshot

- Read-only remote-ref observation showed `main`, `staging`, and
  `feat/same-cycle-enrichment` all still at the exact candidate SHA.
- Web deploy `dep-da8ckp7lk1mc73f224o0`, harvest deploy
  `dep-da8ckpflk1mc73f225dg`, and headlines deploy
  `dep-da8ckp7lk1mc73f22500` each remained `live` on the exact candidate SHA.
- All three services remained `not_suspended`. Harvest remained on
  `*/15 * * * *` with B1's `23:48:10Z` completion as its most recent
  successful natural run.
- **Gate result:** pass; refs, exact-SHA services, and the natural schedule
  remained unchanged before B2.

### 2026-08-28T00:00:20Z — B2 natural closing boundary started

- Production Render logs recorded `Cron job run started` for the harvest
  service at `00:00:20Z`.
- The immediately preceding read-only snapshot had already fixed the live
  deploy, candidate SHA, unsuspended state, and `*/15 * * * *` schedule.
- **Gate result:** in progress; B2 natural-start continuity passed and its
  terminal correlated summary remains pending.

### 2026-08-28T00:03:12Z–00:03:20Z — B2 terminal closing boundary passed

- Natural production run `20260828T000047_0000-c24ccf99` executed on exact
  candidate `c07a268c2268a6df477c80a9e8c08ba6fc05e4f6`. Render recorded the
  cron start at `00:00:20Z`, command start at `00:00:44Z`, summary start at
  `00:00:47Z`, summary finish at `00:03:12Z`, and successful completion at
  `00:03:20Z`.
- Seven of seven planned calls ran, yielding 73 results, 28 inserts, two
  updates, and zero persistence failures.
- The same-cycle contract repeated: 28 current-cycle and 50 carryover rows
  were claimed; all 78 succeeded with complete output and zero pending or
  failed. Translator/classifier failed and unavailable counters were all zero.
- The summary status was `degraded` only because 65 backlog rows were
  quarantined. Summary hash
  `c020ab1ed498bf29c675ed4b59b65d97c913327de23762f2faeaf35fb6f6911b`
  correlates to cohort receipt hash
  `23cd6761afac6fc52e150f51eadf689eba4d002f2a5d9b165461dc5e3de84c38`.
- **Gate result:** pass; B2 closes the required Bn+1 natural boundary. The
  continuity ledger has no missing production boundary from B0 through B2.

### 2026-08-28T00:04:18Z — supplemental latest-50 report retained

- Parent generated the read-only detailed report at
  `docs/analysis/harvester/2026-08-28-090418-harvester-latest-n-health-report.md`.
- Its 50-row snapshot reports language present `50/50`, non-`zh-Hans`
  Chinese text `47/47` (`100%`), English commentary `50/50` (`100%`), Chinese
  commentary `50/50` (`100%`), and no pending rows.
- The generic checker labels the snapshot `unhealthy` and its regression check
  failed solely because 26 of 50 rows lacked discourse. The owner had already
  classified discourse as secondary, and this candidate did not alter
  discourse generation. This secondary finding is retained and does not
  override the exact B1 cohort or settled quality gates.
- **Gate result:** pass for supplemental accepted quality evidence; secondary
  missing-discourse finding recorded without broadening this release.

### 2026-08-28T00:04:52Z — search/metrics/credit-shape parity closed

- The natural boundary sequence retained exactly seven calls per cycle: B0
  `7/7` with 88 results, 46 inserts, and four updates; B1 `7/7` with 57
  results, 29 inserts, and three updates; B2 `7/7` with 73 results, 28
  inserts, and two updates.
- B1 and B2 metrics each reported `n_due=200`, `n_missing=200`,
  `n_refreshed=0`, and `n_errors=0`. No extra Twitter search execution was
  introduced, and the production schedule remained unchanged.
- **Gate result:** pass; search-call, metrics, cron-frequency, and
  credit-shape parity closed without claiming provider billing facts that were
  not observed.

### 2026-08-27T23:38:31Z — recorder initial observation

- Candidate worktree HEAD is the exact candidate SHA on branch
  `feat/same-cycle-enrichment`.
- Remote `main`, `staging`, and feature refs all resolve to the candidate SHA.
- The authoritative root worktree's local `main` ref remains locally stale;
  no fetch or ref mutation was performed by the recorder.
- The candidate worktree has plan-document changes for the owner's continuation
  exceptions; no product-code change was made by the recorder.

## Candidate cohort and quality gates

The natural candidate cycle, immutable cohort, and exact redacted DB/feed/
quality evidence are now closed below.

| Gate | Required result | Status |
|---|---|---|
| Candidate service convergence | Web, harvest, and headlines report candidate SHA | Pass at `23:39:35Z` |
| Natural candidate cycle | Seven planned calls; no manual substitute; terminal correlated summary | Pass at B1; degraded note reviewed and retained as nonblocking |
| Nonempty immutable cohort | First of at most two natural candidate-SHA cycles with inserts | B1 selected: 29 IDs bound by receipt hash |
| Lane identity | Inserted IDs equal current-cycle claimed IDs; carryover reconciles | Pass: 29 inserted/current-cycle, 50 carryover; exact DB cohort found 29/29 |
| Durable completion | Every cohort ID has both stages succeeded and valid persisted output | Pass: 29/29 terminal and persisted-output complete |
| Feed behavior | Each exact cohort ID is feed-visible only after terminal completion | Pass: 29/29 feed-visible after terminal completion |
| Canonical language | All cohort posts use a canonical language code | Pass in exact-cohort ORM evidence |
| Non-`zh-Hans` Chinese text | At least 99%; strict integer floor | Pass: 27/27 (100%) |
| English commentary | At least 99%, nonblank and distinct | Pass: 29/29 (100%) |
| Chinese commentary | At least 99%, nonblank and distinct | Pass: 29/29 (100%) |
| Supplemental latest-50 | Retain detailed report without substituting it for exact cohort | Pass on accepted quality fields; 26/50 secondary missing-discourse finding retained |
| Provider routing parity | Redacted effective model/host facts match staging | Qualified limitation: explicit `deepseek-v4-flash` config path and zero translator/classifier unavailable/failure were observed, but the cron environment's provider-host fingerprint was not independently captured; no mismatch was observed |
| Search/metrics/credit parity | Seven-call and existing credit envelope unchanged | Pass: B0/B1/B2 each 7/7; schedule unchanged; no extra search execution; B1/B2 metrics counters stable |
| Following natural boundary | One correlated Bn+1 after qualifying candidate cycle | Pass: B2 completed naturally on exact candidate at `00:03:20Z` |

## Staging qualification and explicit limitations

- Isolated staging and its core exact-candidate same-cycle evidence passed
  under the settled bounded caps.
- The strict staging acceptance wrapper did **not** produce a clean pass. It
  returned false-negative `pipeline_or_bound_failure` when the only implicated
  condition was safe `truncated_replay_queued`; a later no-result attempt was
  correctly inconclusive. This ledger therefore does not claim that the
  wrapper gate itself passed.
- Parent classified that wrapper behavior as a follow-up acceptance-tooling
  limitation rather than a production stop trigger because production B1 and
  B2 independently proved the exact candidate's natural same-cycle lane,
  terminalization, and continuity behavior.
- The production cron environment's provider-host fingerprint was not
  independently captured. The explicit `deepseek-v4-flash` configuration path
  and zero translator/classifier unavailable/failure counters are supportive,
  but not a substitute for host-parity proof. Parent classified this evidence
  gap as a follow-up observability limitation, not a demonstrated mismatch or
  production stop trigger.
- Missing discourse remains the documented secondary finding: 26/50 in the
  latest-50 report and 8/29 in the exact B1 cohort lacked discourse. It is
  outside the settled acceptance contract, and this candidate did not change
  discourse generation.
- Documentation durability is represented by this ledger and the retained
  latest-50 report. Committing/preserving those files and Ollija's guarded
  canonical-worktree cleanup remain parent-owned workflow actions; this
  read-only recorder performs neither.

## Stop, rollback, and final verdict

- Any continuity, SHA, cohort identity, feed visibility, persisted-output,
  provider-routing, credit, or quality failure is a stop trigger.
- A zero-insert or update-only first candidate-SHA cycle is inconclusive and
  may advance only to one more natural candidate cycle; it is not a pass.
- A nonempty candidate cohort is immutable. A failed cohort cannot be replaced
  by a later one.
- If rollback is required, the parent may advance the prepared feature-only
  rollback through ordinary auto-deploy while the natural cron remains
  scheduled. This recorder will record the decision and subsequent boundaries;
  it will not execute rollback.
- **Stop decision:** none. No continuity, SHA, immutable-cohort, feed,
  persisted-output, settled-quality, search-envelope, or credit-shape failure
  occurred.
- **Rollback decision:** not invoked; production remained on the exact
  candidate and the natural cron stayed scheduled throughout.
- **Final verdict:** **QUALIFIED PASS**. Production zero-disruption and exact
  same-cycle/quality acceptance passed. The staging-wrapper false-negative,
  uncaptured provider-host fingerprint, and secondary missing-discourse result
  are retained as follow-up limitations, not production stop triggers.

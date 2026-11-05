---
title: Expand tracked-brand coverage and audit a locked twelve-hour cohort
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: feat-nvidia-ai-coverage-20261104-2026-11-04-080402
  branch: feat/nvidia-ai-coverage-20261104
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---
# Expand tracked-brand coverage and audit a locked twelve-hour cohort

## Plain-English Summary

Owner GO is implemented locally: add dataset-supported Qwen, ByteDance, Kimi, Llama and DeepSeek query coverage, preserve all earlier branches, and maximize relevant matches on the same 8,281-post twelve-hour cohort. Provider diagnostic calls remain prohibited. The owner now authorizes direct production deployment and feature-required keyword mapping activation, while preserving live schedules and existing post labels. The explicit Dots/Xiaohongshu affiliation request is also authorized.

Final local replay catches 8,190/8,281 posts (98.9%), versus 8,182 for the corrected baseline: eight additional reviewed model/product posts, zero lost matches. One circled-number normalization correction also fixes an earlier baseline underestimate; it is not a query gain. Existing brand labels remain unchanged, including apparent errors in remaining misses.

Nine base calls remain, with whole-brand ownership and NVIDIA's four named family blocks. Full queries are at most 511 UTF-8 bytes including exclusions and timestamp bounds. All 496 regression checks pass, including 91 requiring the permanent shared PostgreSQL database. Exact queries, per-post and per-brand evidence, input hashes and tested source remain in applied-final under the existing evidence root. Current persisted Call A membership is used; historical membership and X indexing/pagination are not simulated.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/nvidia-ai-coverage-20261104`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/nvidia-ai-coverage-20261104/docs/plans/2026-11-04-080402-feat-nvidia-ai-coverage-20261104-plan.md`
- Change: `feat-nvidia-ai-coverage-20261104-2026-11-04-080402`
- Branch: `feat/nvidia-ai-coverage-20261104`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/nvidia-ai-coverage-20261104/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/nvidia-ai-coverage-20261104/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `production`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/nvidia-ai-coverage-20261104` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/nvidia-ai-coverage-20261104` without `--force`.
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


## Delivery Exceptions and owner decisions

- Historical November 4 endpoint: implement broader NVIDIA coverage and try it live. Owner: “let's do that and try it, disregard budget”. The former four-request/$0.012 diagnostic ceiling is superseded.
- Keep scope broad; false positives are not a rejection criterion. No product alias was dropped to improve apparent purity.
- No commit, push, merge, deployment, production keyword/display write, production backfill or recurring activation requested for this NVIDIA task. Earlier unrelated deployment authorizations do not transfer.
- Keep production harvesting uninterrupted. Scheduled and on-demand credentials remain separate; diagnostics use only the on-demand key, with no fallback.

## Historical November 4 NVIDIA trial

The following implementation, twelve-call layout, test counts and spend describe the completed November 4 trial. The November 5 owner amendment below supersedes its extra-call layout and exact-old-query requirement.

### Evidence and diagnosis

1. Original `nemo_megatron` policy used only `paths: [handle]`, contributing `(@NVIDIAAI OR @NVIDIAAIDev)` to shared B2. A curated-list/other overlapping searches could also supply posts. There was no dedicated NVIDIA product-keyword call.
2. Read-only production inspection found display name NVIDIA NeMo and aliases limited to NeMo/Megatron/Nemotron variants. The stable slug, company relationship and history are reused.
3. A bounded production sample found TensorRT-LLM/DeepSeek post `2117891451606704313` without the NVIDIA brand. A regression requires both brands. Counts of NVIDIA 43 versus Meta 4,162 over a day were a symptom, not a comparable recall measurement.
4. Meta history `f4536c2f` expanded aliases/C4 while retaining `llama`. Reuse the policy/planner/attribution path; NVIDIA's later owner-selected coverage preference removes its contextual restrictions.
5. The actual pre-change planner had eight calls: A, B1, C1, C2, C3, C4, B2, B3. All eight exact query strings remain pinned. Older seven-call documentation is not the baseline.
6. First live sample exposed expanded-URL-only evidence (`2117953000870379787`, `https://github.com/NVIDIA/auto-ontology`). Ten synthetic product-only controls exposed contextual/alias gaps. Synthetic failures are not fresh X discoveries.

Official product references: [open model families](https://nvidianews.nvidia.com/news/nvidia-expands-open-model-families-to-power-the-next-wave-of-agentic-physical-and-healthcare-ai), [NIM](https://docs.nvidia.com/nim/), [CUDA-X](https://developer.nvidia.com/cuda/cuda-x-libraries), [cuDNN](https://docs.nvidia.com/cudnn/overview/), [NVIDIA open-source portfolio](https://www.nvidia.com/en-us/opensource/llm-info/), [DLSS research](https://research.nvidia.com/labs/adlr/DLSS5/).

### Final implementation (November 4)

- `config/harvest_policy.yaml`: preserve `nemo_megatron`, existing handles and unrelated brands. Add four explicit `c_bare_alias_groups` and `match_link_urls: true`. C5 models/specific phrases, C6 libraries/software, C7 company names, C8 ambiguous names. All 63 earlier broad aliases remain plus 15 specific phrases. No NVIDIA context gate. The legacy `co` vocabulary remains required by existing policy validation but grouped aliases intentionally render without it.
- `x_monitor/harvest_policy.py`: validated optional grouped aliases and link-matching flag; shared flattened inventory supplies both planner and keyword synchronization. Groups must contain nonempty literal strings and be disjoint after normalization.
- `x_monitor/specs_from_policy.py`: dedicated owning C5 pack, overflow groups C6–C8 after fixed packs; stable IDs under brand subsets; reject mixed owning packs. Existing shared query renderer, no second pipeline.
- `x_monitor/config.py`, `config.yaml`, `monitor/backfill_collection.py`, `scripts/backfill_campaign.py`: admit C5–C8. Total scheduled calls twelve; preserve caps (2,000 results/call, 100 pages, 20/page), cursor behavior and unrelated queries. Degraded skip ordering includes new calls before older C calls.
- `scripts/backfill_month.py`: accept exact historical original/Meta/initial-NVIDIA/two-pack/final inventories, retaining frozen query strings and hashes. No re-planning of saved historical manifests.
- `x_monitor/attribution.py`: opt-in matching of observed HTTP(S) link hostname/path using the existing keyword index. Ignore query parameters and display-only URLs; no network fetch. Store full observed URL as `url_keyword` in existing evidence source/raw-token fields. Other brands are unchanged. Japanese company-name matching supports attached kana particles.
- Existing scheduled CycleRunner and Django backfill already pass normalized entities to shared attribution. Both are verified through actual local PostgreSQL persistence.
- `x_monitor/reattribute.py`: repair the legacy brand-filter reader's stale external-key joins to current internal post/brand IDs and filter by nickname. This surfaced in the existing regression tests; no legacy live database was written.

Final rendered C5–C8 lengths with exclusion/time bounds: 378, 479, 108, 234 characters. Source query strings and exact frozen trial requests are in the report/manifest below.

### Schema-first review and later activation (November 4)

Inspected `core/models.py`, migrations and relevant writers/readers. Reuse existing Brand/BrandCompany/BrandKeyword identities and PostBrandMention evidence. Its `source` is a free text column without a database enum/check; `url_keyword` requires no schema addition. Tables added/retired: zero/zero. Columns, JSON columns and migrations added: zero.

A later authorized activation must synchronize existing NVIDIA keyword records before the production keyword-index preflight can accept the enlarged inventory:

```sh
python manage.py onboard_brand --sync-policy-keywords nemo_megatron --dry-run
python manage.py onboard_brand --sync-policy-keywords nemo_megatron
```

Dry-run/additions/idempotence are tested locally for both NVIDIA and Meta. No production synchronization ran. Production display remains NVIDIA NeMo; no UI change is part of this trial. Later deployment must observe the intended harvest revision and subsequent scheduled rows/costs, without pausing collection.

### Regression net (November 4)

- Red first: ten product-only controls plus archived link-only example failed, then passed after the change. Before/after logs: `/tmp/nvidia-broad-red.log`, `/tmp/nvidia-broad-green.log`.
- 202 tests passed in `/tmp/nvidia-final-pure.log`; a further 84 existing policy/planner compatibility tests passed in `/tmp/nvidia-final-planner-compat.log`: current policy/query shape, exact old eight query strings, per-call caps, attribution, frozen backfill recipes and legacy reattribution.
- 128 tests passed in `/tmp/nvidia-final-db.log`, including 71 required PostgreSQL checks, zero skips/errors: actual scheduled runner, durable labels/URL evidence, deduplication, scoped keyword reconciliation, scheduled exclusions, backfill collection/campaign and cursor guards. Permanent shared database wrapper held the exclusive-use lock. No database restore/reset/migration ran.
- Formatting/type-annotation-only final cleanup: 120 overlapping attribution/context/reattribution tests passed in `/tmp/nvidia-final-attribution.log`; not added to the 414 distinct tests as new coverage.
- Existing NVIDIA stock/Cosmos/ordinary-word controls remain and now explicitly assert owner-selected broad matching. Other brands' negatives remain. URL negatives cover invalid scheme, malformed host, query-only and display-only evidence.
- Stale planner tests used the retired data-directory API; repaired them against explicit specs while retaining grouping, caller-token use, no cross-brand leakage, required list ID, exact 512 boundary and removed-path checks. The stale list-floor source-regex assertion now invokes the real converter with a distinct monkeypatched floor; account and brand-wide paths are both checked.
- Stale SQLite fixtures now use nickname/account/internal relationship identities; tests still assert dry-run, limit, brand filter, idempotence, fractional weights and legacy entity decoding. The obsolete MiniMax/Kimi fixture collision was repaired to a real MiniMax keyword without changing the property tested.
- Changed policy/planner/backfill and test modules pass Ruff; full attribution/config files retain 51 pre-existing findings outside this work; comparison with base found zero new findings. `git diff --check` passes.
- Four temporary migration overlays matching the already-migrated shared test schema were used only for test discovery (0220_chatter_consideration_ownership, 0222_merge_chatter_and_affiliation_permissions, 0223_chatter_collection_operation, 0224_chatter_source_snapshot_owner). Those exact four untracked overlays were removed after the database tests; none are delivered.

### Finite live trials and evidence (November 4)

Initial contextual trial (earlier owner approval): `data/runs/2026-11-04-212615-nvidia-query-probe`. Four calls, 66 raw results, 40 unique, 26 duplicate extras; estimated 990 credits ($0.0099). Twenty candidate posts included 11 reviewed relevant, seven outside the then-assumed product scope and two uncertain. That review is historical evidence, not a policy restricting the new broad inventory.

First broader trial: `data/runs/2026-11-04-214732-nvidia-recall-v2`. Owner's lifted diagnostic budget applies. Frozen 12:00–12:15 and 12:30–12:45 UTC windows, cached handles/contextual controls, two candidate packs, five pages each, 24 serial requests, no retries. 453 raw returns and 442 unique posts. Common words crowded search pages: only 5/20 and 4/20 earlier-query sample posts recovered. This is a capacity issue even when false positives are accepted.

Final confirmation: `data/runs/2026-11-04-215402-nvidia-recall-v3`. Keep all aliases, isolate four lanes, add 15 specific phrases. Same frozen windows; three pages/lane/window, 24 serial requests, no retries. 480 raw returns, 472 unique posts and 8 duplicate extras. Recovered 19/20 and 20/20 earlier-query sample posts, including all 11 previously reviewed relevant posts from the original fifteen-minute candidate sample. The one unrecovered control is short reply `2117951820651745725` (“Y sin DLSS”), locally matchable but absent from sampled pages. All eight query/window walks stopped at the sample cap with continuation available.

Current-turn totals: 48 physical requests, 933 raw returns, 710 unique across both trials, 13,995 estimated credits ($0.13995). Including earlier diagnostic:52 requests, 999 raw results, 14,985 estimated credits ($0.14985). Search usage is calculated at [published rates](https://twitterapi.io/pricing/details), not invoice proof. False positives were not used as a rejection criterion. The finite trial is complete; further pagination/capacity investigation was not performed. The remaining limitations are reported rather than hidden behind a claim of complete coverage.

Final report, counts, exact queries, example links and raw response locations:
`/Users/fuchitalee/development/pushin-weight-v2/data/runs/2026-11-04-215402-nvidia-recall-v3/report.md`.

### Cost and completeness limits (November 4)

Four new logical searches per fifteen-minute scheduled run add 384 initial requests/day before pagination. Search-only scenarios for 0/20/2,000 results per added call/cycle are $0.0576/$1.152/$115.20 per day, using 15 credits/result, a 15-credit minimum/request and 100,000 credits/USD. These are scenarios, not predictions or ceilings; retries/additional windows/metrics/enrichment can add cost. Existing runtime caps remain, including the 780-second scheduled-run deadline. Extra query volume can consume that shared time allowance; no guarantee of production completeness follows from this diagnostic.

More returned posts are not evidence of greater relevant coverage by themselves. Only 204 of 472 unique final sampled posts had local NVIDIA attribution evidence, and broad matching also accepts unrelated names/words/links. Account-name matches, punctuation semantics, missing visible/link evidence and pagination still need consideration before a claim of comprehensive coverage. No general all-X recall claim is possible from these samples.

### Production health baseline and completion (November 4)

The attribution change triggered the enrichment-relevant health route. Exactly two read-only observations of the same 20 IDs were made, at 21:40 JST and after 22:10:37 JST. Initial 0 complete / 20 pending / 0 unhealthy became 0 complete / 0 pending / 20 unhealthy. Final status unhealthy, regression failed, acceptance failed. All 20 have detected language; 19/19 requiring Chinese translation have it (100%). English and Chinese commentary each remain 0/20 (0%). Every row has translation-stage reasons `missing_commentary_en` and `missing_commentary_zh_cn`; no missing cohort ID or transport error.

This is a finding in existing production. The NVIDIA candidate is undeployed; do not attribute the finding to it or call production health passed. The report records exact IDs, brands and reasons; the adjacent `production-health-initial.json` and `production-health-final.json` preserve both observations. No repair, re-enrichment or repeated poll was attempted.

Local implementation and the finite live trial are complete. All 414 distinct local regression checks passed; the report preserves live pagination/attribution limits. The four temporary test migration overlays have been removed. Keep the uncommitted worktree at the current base for later owner-selected activation; no release or production write occurred.


## November 5 owner amendment: inclusive coverage within eight queries

Current owner instructions supersede the earlier four extra NVIDIA calls and byte-identical old-query requirement. Rearrangement is authorized, but maintainable brand ownership and logical splits are required. The audit excludes six brands from new portfolio research; their existing coverage remains preserved, including pending NVIDIA aliases. Future OpenAI/Anthropic calls are excluded from the eight-query budget and remain owned by their existing worktree.

### Scope and delivery

- TOUCH: shared policy/spec/renderer/attribution paths, scoped keyword synchronization, relevant scheduled/backfill caller wiring and regression tests. Reuse this worktree and plan. No new tables, columns or migrations.
- PRESERVE: 21 enabled brands, all pending NVIDIA aliases, Meta/GLM/MiniMax contextual semantics, author exclusions, Call A, pagination/result/credit limits, schedulers, LLM configuration, frozen historical query recipes, other worktrees and Giants experiment data.
- ASK FIRST: recurring activation/deployment or historical production repair. The owner authorized reporting the minimum extra call requirement and subsequently requested a paid locked-window trial; a local nine-call candidate and its bounded diagnostic are within that scope. No production pauses.
- Current endpoint is a tested local candidate and concrete call-count report; no commit/push/deployment.

### Implementation and regression net

1. Freeze audit aliases, stored positives and pending NVIDIA inventory; save the pre-amendment diff. Compute candidate capacity with the real renderer and full scheduled time/exclusion suffixes. Initial exact packing finds seven search queries plus Call A.
2. Keep whole brand blocks together; large-brand explicit named groups are the only permitted splits. Use configurable independent query pools with explicit call IDs/budgets, deterministic packing and fail-closed overflow. Preserve the existing renderer and legacy fixture/historical behavior.
3. Remove redundant phrase alternatives only when an existing shorter branch has equal or weaker context requirements. Keep every alias in attribution/synchronization. Remove the nine audited brands' mandatory co-word gates and obsolete cross-brand F1 filtering; preserve excluded-brand restrictions.
4. Add missing portfolios, correct Kling handle ownership, repair shared multilingual boundaries, and reuse account-mention/observed-URL evidence. Verify actual scheduled and backfill callers and persistent brand/evidence rows.
5. Regression net: red-before/green-after archived misses; query count/cap and branch-equivalence checks; every brand owned once per pool; named splits; add/delete brand handling; deterministic output; explicit overflow; future Giants independent budget; negative substring/URL cases; no required skips; existing cursor, dedup, keyword sync and frozen backfill suites.
6. Use the permanent shared test DB wrapper, exclusive lock and compatible migration graph; no new database or schema migration. Retain applicable prior verification only where code/environment still match. Reuse or refresh persisted production-health evidence according to the harvester skill without attributing existing-production defects to the undeployed candidate.

### Guards and acceptance

No new paid X/LLM requests in this amendment. Offline matching and fake provider clients exercise the real caller; DB writes are local tests under the shared lock. Search budgets fail before provider calls; preserve provider purpose separation and page/result caps. Acceptance is finite: the audit vocabulary/positive cases, all 78 pending NVIDIA aliases, old excluded-brand semantics, eight rendered collection queries, and focused regression suites. Do not claim complete X recall or fixed physical request counts from query-count parity.

### Current implementation and verified local outcome

The November 5 candidate uses eight total queries (A plus seven search slots), with zero additional base calls. All 21 brands remain; all 78 pending NVIDIA aliases remain searchable. Whole-brand blocks are packed deterministically; only NVIDIA's four named groups split its portfolio. The pool reserves exclusions and ten-digit timestamps and fails closed on overflow. Final bounded lengths: A 96; B1 495; C1 509; C2 497; C3 496; C4 511; B2 504; B3 512. B3 has no remaining character headroom under the current exclusion registry.

Policy changes broaden the 15 audited portfolios, remove their generic co-word gates, preserve established MiniMax/Meta/GLM and bare Chinese Hunyuan contexts, and correct Kling ownership. Shared attribution handles East Asian adjacency, explicit policy handle mentions and opted-in observed links. Shared post-filter logic prevents Meta's F1 exclusion from rejecting another packed brand. Historical frozen queries bypass current placement; current-policy jobs still validate the saved policy before use. The saved audit exposed Hunyuan4 and kimi3.1pro as additional real misses, both now covered without a ninth query.

Verification: 301 pure policy/query/attribution tests and 130 persistence/backfill tests passed (431 distinct total), including 90 required PostgreSQL checks, zero skips/errors. Final logs: `tests-pure-final.log` and `tests-postgres-final.log` in `data/runs/2026-11-05-091322-harvest-eight-call-coverage` under the authoritative root. Existing legacy exact fixtures remain; current layout fixtures were updated for the authorized arrangement. The stale frozen-recipe deadline test now pins its clock while retaining real deadline enforcement. Targeted lint and diff checks pass; baseline findings in the four larger modules did not increase.

The archived audit replay resolves 143 of 146 previous body-matcher misses over 2,421 lexical brand/post candidates; the remaining three are incidental Yi fragments. 141 previously unlabeled brand/post pairs now match locally. 101/102 synthetic controls pass; bare `混元 released` intentionally lacks its preserved context. These are local vocabulary checks, not new provider-recall measurements or production relabeling. No paid requests were made.

Four hash-verified, untracked migration-discovery overlays were removed after the final shared-DB run. No new tables, columns or delivered migrations. The authoritative report is `docs/analysis/harvester/2026-11-05-094700-eight-call-brand-coverage.md`; it includes the exact query exhibit and rollout prerequisites. A later rollout must synchronize existing policy keywords for the expanded brands; production activation, data repair, commit/push and deployment are not authorized by this local amendment.

### November 5 follow-up: relevance display and hyphen confirmation

Owner requests live relevant/total counts beside each brand on the local verbatim page, then says to confirm hyphen behavior first. Hold the relevance sample and any query edits until the hyphen check is complete. Use the app's TwitterAPI on-demand client only; no scheduled key, database writes or recurring activation.

First finite check: three one-page queries (`Hy4`, `Hy4-preview`, `Hy4preview`) over two cached known hyphen-only posts, with the same two-author filter and 2026-11-04 16:45–17:00 UTC window. Maximum three physical requests, no retry, serial execution, stop on error or unexpected page size; maximum planned 60 results / 900 estimated credits ($0.009) at current published rates. Preserve exact raw responses and compare IDs, without treating empty results as general absence. This distinguishes word separation from joining punctuation away.

The later relevance sample is bounded separately: up to three pages for each of the eight finalized queries in one fixed recent completed 15-minute window; at most 24 physical requests, zero retries, serial, up to 480 expected raw results / 7,200 estimated credits ($0.072), stop on error, repeated cursor or unexpected page size. One finite sample, no query optimization/retest loop. Review relevance to each tracked brand's AI models, products, research and usage; unrelated names/stock-only discussion do not qualify. Product pricing/promotions and comparisons remain relevant. Keep uncertain items separate, show per-call relevant/total unique results plus each brand's relevant/attributed sample pairs, and show no-sample rather than zero percent. This measures sample precision, not all-X recall. Freeze final query hash and rubric before this later dispatch.

### November 5 owner-selected locked twelve-hour comparison

Owner now requests a recent locked twelve-hour interval with existing DB posts, actual hypothetical query execution, brand-by-brand audit, and evidence-guided tuning. This supersedes the small fifteen-minute relevance display as the final evaluation. Preserve its raw results as a diagnostic: six Unicode-heavy queries returned zero, while the 493-byte ASCII NVIDIA query returned results. Four controlled boundary variants show 507 ASCII bytes and 512 ASCII bytes return 20 posts, 507 characters/527 UTF-8 bytes returns zero, and 513 ASCII characters produces an explicit provider length error. Two final one-page Unicode controls at 511 and 513 bytes are authorized diagnostic work within this request; maximum two requests, no retries, serial, expected allowance 600 credits ($0.006). Do not change queries based on a guessed boundary.

Freeze the final query version, raw policy hash, a recent settled twelve-hour UTC interval and a read-only DB snapshot before the comparison. Use 48 fifteen-minute slices to match scheduled window shape. Report per brand: baseline labeled posts, retrieved baseline intersection, genuinely new-to-snapshot posts, local attribution misses, reviewed relevance, duplicate returns, and capped/failed window coverage. A capped interval cannot establish absence or complete recall; keep those counts distinct. Existing DB labels are a comparison baseline, not automatically a relevance gold standard.

Finite evaluation limit: at most two candidate versions on the identical frozen interval. Per version, at most five pages per query per slice, 20 results per page, maximum 2,400 physical requests and 720,000 estimated credits ($7.20); no automatic retries, no third optimization cycle. Shared request admission must enforce physical attempt and credit ceilings before dispatch. At most two concurrent provider requests and two starts per second; stop on auth/rate errors and retain raw outcomes. The second version reruns only changed queries and reuses unchanged receipts. At most 30 reviewed sample posts per brand/version, selected deterministically across time slices; reuse earlier post labels. Show exact collection counts separately from sample relevance estimates. This is diagnostic collection into local evidence only; no production imports, scheduler changes or deployment.


### Verified byte limit and frozen trial dispatch

Six physical boundary probes are retained under `data/runs/2026-11-05-101336-query-byte-boundary`. ASCII 507/512 bytes and Unicode 511 bytes each retrieve the identical 20 IDs; Unicode 513/527 bytes return empty; ASCII 513 characters returns HTTP 400 with the provider's length error. Error billing is unknown, not zero. The complete query guard now counts UTF-8 bytes, including exclusions and time bounds. Historical query-length telemetry remains characters; byte-based validation is separate.

Compact only redundant OR/singleton wrappers while preserving AND/context semantics and all old branch coverage. With the full inventory, the seven combined search slots still need 3,598 bytes including their seven suffixes versus 3,584 available. This proves eight total calls cannot fit this fixed block representation, not a mathematical impossibility for every possible Boolean rewrite. Nine total calls fit without removing coverage. Membership is explicit; the initial nine-call candidate is not deployed.

Trial root: `/Users/fuchitalee/development/pushin-weight-v2/data/runs/2026-11-05-102849-locked-12h-portfolio-audit`. Snapshot read-only, repeatable-read, no row cap, 8,281 posts. Version 1 frozen with exact queries, policy, code and snapshot hashes before collection. `scripts/harvest_query_audit.py` implements freeze/collect/analyze using the shared planner, XClient and attribution code. It admits at most two physical requests concurrently, at least 0.5 seconds between starts, reserves 300 credits per attempt before dispatch, never retries, and stops the batch on any provider error. Each query/slice has a five-page ceiling. These are diagnostic bounds, not production policy changes. Offline checks prove request/credit/stop guards and Unicode-safe JSONL receipt parsing.


### Version-two hypothesis and comparison rule (before dispatch)

Early version-one slices show all eight keyword calls commonly hit the five-page cap. Raw source text shows everyday Ring/Ming/Yi terms and NVIDIA names such as AI-Q/ACE consuming page capacity. Preserve every alias and its context; test grouping rather than removing false positives. Proposed version two gives NVIDIA two dedicated calls (models/software; company/product names), groups Xiaomi/ByteDance/Kuaishou together, groups Meta/Dots as social-platform AI, Hunyuan/Upstage/EXAONE/SenseTime as Asian foundation-model platforms, Mistral/Sakana/StepFun as independent model labs, ERNIE alongside MiniMax/Qwen/DeepSeek/GLM as Chinese model platforms, and Kimi/Yi/InclusionAI as short-name model portfolios. Same nine-call count; no alias/handle/attribution changes. The proposal is saved separately under the frozen trial root pending full version-one results.

Acceptance remains all existing semantic/caller guards plus actual wire byte limits. Compare version two to version one under identical five-page budgets using total recovered baseline brand/post pairs across the 15 audited brands, per-brand differences and the rare Dots/EXAONE known controls. All losses stay visible; choose a provisional grouping only after that comparison, and preserve both candidates if tradeoffs remain. New-to-snapshot counts are candidates, not assumed relevant gains. This is not a claim of complete X recall: production's larger pagination allowance and index changes make database recovery a bounded comparison.

The shared byte guard also exposes the optional, frozen legacy rare-type query at 565 bytes with bounds (507 characters). Do not rewrite that separately owned historical query. Add a no-dispatch rejection test. Inbox/recovery tests use a focused valid query fixture and retain all persistence, gate, accounting and resumption assertions. The base-call candidate does not activate this optional lane.


The 17:00–17:15 slice supplies a concrete regrouping control: both baseline Dots speech-research posts were created at 17:00. In version one the Dots/Yi-containing B3 walk reaches only 17:07:11 after five pages; B2 reaches 17:09:41 and C4 reaches 17:03:30. Meta's B1 reaches 17:00. The proposed second version therefore puts Dots with Meta, moves Upstage/EXAONE to Hunyuan's group after removing broad Step terms, and moves StepFun to the independent labs group after removing Ring/Ming/Ling. This is an evidence-based grouping hypothesis, not a guaranteed recovery claim.


Selection may retain independent groups of exact, already-observed calls from either of the two live versions. NVIDIA/media regrouping (C2/B4) is independent of the remaining brand transfers. Any selected combination must own every brand/family block exactly once, produce byte-identical observed query strings, pass the regression net, and reconstruct its counts only from those saved receipts. This permits choosing the better independent regrouping without creating a new query variant, issuing a third live trial, or hiding per-brand losses. Record the receipt version for every selected call.


## Owner stop and provider-use correction

{
  "recorded_at": "2026-11-05T02:07:00.270990+00:00",
  "credential_variable": "TWITTERAPI_IO_ON_DEMAND_API_KEY",
  "credential_purpose": "on-demand",
  "physical_attempts": 1428,
  "successful_responses": 1427,
  "failed_attempts": 1,
  "estimated_credits_for_successful_responses": 399720,
  "unknown_billing_attempts": [
    "B2-s33-p3"
  ],
  "version_two_dispatched": false,
  "process_check": "No matching collector, analyzer or continuation process running at owner correction",
  "owner_correction": "Database-only test. Live provider calls were an agent misinterpretation. Stop; do not continue or retry provider work. Await owner continuation before offline test.",
  "estimate_not_invoice": true,
  "estimated_usd_for_successful_responses": 3.9972
}

Retire the pending live second-pass workflow and proposed resume work. No resume implementation or retry was performed. A future authorized continuation must evaluate hypothetical queries locally against the frozen database snapshot and report local-matching limitations; it must not invoke TwitterAPI.io or infer authorization from the historical trial sections.


## Owner-authorized database-only replay — completed November 5

The owner explicitly resumes only offline work: “take the posts from the 12 hour period…apply these new calls to them…record…by brand…what's in the db, and %…caught”. This supersedes the temporary wait, not the prohibition on provider calls. The misplaced live collector and its dependent tests have been removed from the deliverable and archived under `retired-provider-workflow` in the trial evidence root. No paid resume was implemented or executed; the second live version never dispatched.

Results: 7,887 / 8,281 unique snapshot posts match at least one of the eight proposed keyword calls (95.2%). The full 21-brand table, other brand labels, exact queries and method are in `docs/analysis/harvester/2026-11-05-094700-eight-call-brand-coverage.md`; the refreshed HTML is `docs/analysis/harvester/2026-11-05-094900-restructured-calls-verbatim.html`. Detailed JSON, per-brand CSV, missed-post CSV, source hashes, evaluator source and 13-test receipt are under `data/runs/2026-11-05-102849-locked-12h-portfolio-audit/offline-db-replay` in the authoritative root.

Matching inputs exclude stored brand labels. Labels are used only when counting the per-brand denominator. Report body-only and quote/entity-dependent counts separately. The first intermediate counts used an overly strict boundary around CJK/Japanese terms; the evaluator was corrected and tested against `Gemini文心一言`, `混元Hy-4` and `Museトークン` before saving final results. Actual query strings were unchanged. Call A has no fabricated coverage estimate.

The application regression evidence remains for the unchanged local query candidate. The earlier 481-check run included eight tests of the now-retired paid harness; those are historical evidence, not current workflow requirements. Thirteen new offline evaluator tests pass. No production operation was paused or mutated.


## Owner amendment: include persisted Call A — completed

Read-only database retrieval of list 2067062923525275922 at 2026-11-05T02:30:10.849577+00:00 found 213 active entries, 210 with usable handles. Apply current persisted membership to the frozen post authors, preserve exclusions/min_faves:0, union with the existing keyword replay and deduplicate. This is hypothetical current-list coverage; historical membership is not asserted. Zero TwitterAPI calls. Adds 294 unique posts: 8,181/8,281 (98.8%). InclusionAI 12/13, Yi 9/9, Hunyuan 694/694, Mistral 98/98; Upstage remains 21/23. Complete result and per-brand CSV in `/Users/fuchitalee/development/pushin-weight-v2/data/runs/2026-11-05-102849-locked-12h-portfolio-audit/offline-db-replay-with-call-a`. Fourteen offline tests pass. Reports refreshed; no query changes or production writes.


## Owner follow-up: three brand differences and unassigned-post test — completed

Inspect all 28 MiniMax, 2 Upstage and 1 InclusionAI remaining misses from saved content. MiniMax includes 21 TRON promotions and seven other topics without clear MiniMax evidence; Upstage contains solar-system/stock discussion; InclusionAI contains generic inclusion in an interview chapter title. Treat as apparent label false positives, preserving raw counts and unavailable thread/article context. Offline per-brand scoped-query replay across the same 8,281 posts finds 626 candidate missing brand/post pairs on 579 unique posts; only 2 of25 fully unassigned posts match, both confirmed NVIDIA content. Other577 already carry some labels. Review confirms MiniMax M3 Pro, Seedream and Kling missing additional associations. Generic dots/studio and AI Scientist counterexamples prevent claiming626validatedgains. Results, source hashes, complete candidate content and review receipts under `/Users/fuchitalee/development/pushin-weight-v2/data/runs/2026-11-05-102849-locked-12h-portfolio-audit/new-label-audit`; local report refreshed. Zero provider calls, no DB relabeling or query edits.


## Dataset-tested query additions — recommendation only

Offline variant preserves all existing brand blocks and adds: Qwen `千问`; ByteDance `字节扣子` and `Coze`; Kimi `Moonshot` with `(AI OR LLM OR model OR API OR tokens OR weights OR 模型 OR 参数)` context. Move the whole Kuaishou block from B4 to B3 to provide ByteDance room; B3 is named Chinese model portfolios. No brand is split and every full request fits the 512-byte guard (largest 511 bytes). Nine total proposed base calls remain.

Same-cohort result: 8,181 → 8,186 unique posts (98.8% → 98.9%). Qwen 927/928 →928/928; Doubao83/84→84/84; Kimi713/716→716/716. All five new unique matches were reviewed as relevant to those brands. Adding Coze as an English counterpart is sensible portfolio coverage; this dataset's incremental ByteDance hit specifically uses 字节扣子. Do not attribute an independent gain to Coze.

Two remaining Meta/Llama misses discuss embedding initialization/pretraining, showing a possible context-vocabulary gap; that change is not part of this tested variant. The Japanese circled-number Muse example also needs local-normalization scrutiny before claiming a query gap.

Most additional matches from the previous test are brand-assignment candidates already retrieved by existing proposed calls. Fixing missing brand association is a separate lever from expanding search. Do not broaden MiniMax/Upstage/InclusionAI just to recapture apparent incorrect existing labels. Full variant strings, exact newly matched posts and provenance are recorded under `/Users/fuchitalee/development/pushin-weight-v2/data/runs/2026-11-05-102849-locked-12h-portfolio-audit/targeted-query-additions`. This is a saved recommendation; the application policy was not changed by this experiment. Zero provider calls.


## Owner GO: maximize relevant frozen-window coverage, local implementation

Apply the tested Qwen 千问, ByteDance 字节扣子/Coze and contextual Moonshot additions. Further inspect the fixed cohort's remaining target-brand misses. Two Llama embedding-research posts require pretraining context; one DeepSeek post uses V4.1F-1017 shorthand, anchored by other stored DeepSeek V4.1 Flash shorthand usage. Add pretraining to Llama's existing co vocabulary and V4.1F to DeepSeek aliases, preserving all previous branches. Three bounded local refinements, zero provider calls. Stop after these evidence-backed aliases and review of remaining misses; do not broaden generic words to fit bad labels.

Keep nine proposed calls and declare whole-brand ownership explicitly: B1 Meta/ERNIE/SenseTime; C1 NVIDIA models/software; C2 NVIDIA company/product names; C3 MiniMax/Qwen/DeepSeek/GLM/Yi; C4 Hunyuan/Dots; B2 Mistral/Sakana/StepFun; B3 Kimi/InclusionAI/Upstage/Kuaishou; B4 MiMo/Doubao/EXAONE. Maximum full-query size511UTF8bytes. No new tables or fields, provider use, production writes, activation or deployment. The on-request endpoint remains local implementation, regression proof and recorded offline comparison.

Correct a replay-only Unicode issue: separate circled-number list markers before NFKC normalization, so ④Muse does not become embedded 4Muse. Recompute the old queries under the corrected matcher (8,182 matches) to avoid claiming this parser correction as a query gain. The unchanged original snapshots and earlier estimates remain historical evidence.


## Owner GO completion receipt

Final explicit layout supersedes the earlier intermediate proposal: B1 Meta/ERNIE/SenseTime; C1 NVIDIA models/software; C2 NVIDIA company/product names; C3 MiniMax/Qwen/DeepSeek/GLM/Yi; C4 Hunyuan/Dots; B2 Mistral/Sakana/StepFun; B3 Kimi/InclusionAI/Upstage/Kuaishou; B4 MiMo/Doubao/EXAONE. The capacity exercise only chose explicit policy groups offline; no runtime auto-packing was added.

Eight query gains: IDs2118088333087879494,2118065745951109156,2118044670588514575,2118044349581967748,2118029506745127284,2118026809984090238,2118026642358735295,2117992594064167007. All old corrected matches remain. Coze is an English portfolio alias; its separate incremental gain is not established by this cohort.

496checks passed:364pure/local plus132DB/backfill;91requiredPostgres,0skips/errors. Temporary test discovery overlays removed after hash/untracked guards. Three list entries without handles have zero matching cohort posts by read-only database identity check, so no omitted A gains were found. Reports regenerated from exact applied manifest; no provider calls, production writes, commit, push or deploy. Final endpoint is the local candidate and reviewed DB evidence.


## Owner-selected production delivery — November 5

Owner: “lock in this new call refactor, and push to deployment”; route: “direct production”. This supersedes prior local-only delivery statements. Commit, integrate current main, review, run affected checks, non-forced production push and verify the intended live revision. Preserve Chatter staging; no staging deployment or acceptance run. Preserve active harvesting and all provider exclusions: no new diagnostic TwitterAPI calls or historical data repair. Feature-required policy keyword activation is included in deployment; existing posts/labels remain unchanged.

Also owner-directed: verify/add the official @dotsstudioai → Dots affiliation and Dots → Xiaohongshu relationship, reusing existing entities and relationships. No schema change or duplicate account/brand.

Review simplification removes duplicated literal-pattern construction by reusing _literal_term_pattern; its CJK/Japanese handling and first-win mapping are byte-equivalent. Duplicate handle regex consolidation is deferred as low-value cross-file change outside this review's mutation scope. Efficiency review found no actionable runtime issues.


### Release review and online activation

Full code review at /tmp/compound-engineering-501/ce-code-review/20261105-131710-79120d84 returns Ready to merge, no retained findings, eleven completed reviewers and local adversarial coverage. External model coverage is absent under the provider restriction. Added the advisory A+keyword overlap test; preserved both route IDs and single-count semantics. No current-policy month recipe writer was established; historical month inventory remains unchanged rather than inventing a new feature.

Read-only production keyword inventory finds137missing mappings across14brands, including75NVIDIA aliases. Prepare candidate-code one-off activation in batches of at most32total additions, using the existing onboard_brand --sync-policy-keywords command and idempotent dry-run/apply semantics. Complete and verify mappings before switching images. This additive preparation leaves the old policy's coverage valid and preserves live writers. No run_cycle/provider diagnostic is launched; acceptance observes the next natural cron.

Dots affiliation is complete: existing brands_accounts(dots,@dotsstudioai,official) and brands_companies(dots,xiaohongshu) were verified; missing companies_accounts(xiaohongshu,existing account,official,ownership_confirmed=true) was inserted and read back. Account2085289191609716736 was reused. No account, company or brand duplication and no schema change.

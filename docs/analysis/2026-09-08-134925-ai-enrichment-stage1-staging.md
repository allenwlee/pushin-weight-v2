# Stage 1 staging delivery receipt

Stage 1 is deployed and verified for the frozen plan's authorized staging
scope at exact metadata revision M
`bdcfb638d66faf99723a42bd49adc243df3f891e`. Formal findings #2 and #6 are
implemented and independently reviewed; the fixed-cohort observation and all
final local and staging gates are complete. Stage 1 was not deployed to
production, and production promotion is not authorized.

## Candidate identity and source state

The resumed reviewed product source is P
`5c2dee1fd048dfff0fda944f96f677f34f4c1e0b`. It contains the previously
accepted Stage 1 source, the retired-SQLite correction, PostgreSQL headline
scalar aggregation, and classifier system/user isolation. Metadata revision M
is `bdcfb638d66faf99723a42bd49adc243df3f891e`; it changes only the two
independent UI-assurance product-source pins from P. A later receipt-only D may
record this evidence in Git history; M, rather than that docs-only D, is the
revision deployed to staging. The Product Contract remains
byte-identical, SHA-256
`d4789b803b74e348de481e9956f2089ea140a4859ee6953fd80c1814e8645bc3`.
The frozen plan's technical Verification Contract now names the reviewed
active Django/shared-runtime aggregate; its product requirements, KTDs,
delivery target, and health gates are unchanged.

Formal review run `20260909-044149-aa012156` is complete. Its archived result
is `.context/stage1-review-archive/review.json`, SHA-256
`cdf6bb9405062297488774f7ac07ad1f205dcaaeb29230d907f60842026d9516`.
Finding #4 was fixed before the resume. The owner then authorized fixes for #2
and #6 in Delivery Exceptions 6–7. Both are implemented at P and independently
reviewed with no remaining source finding. Findings #3, #8, and #14 remain
report-only under the recorded KTD conflicts.

## Resumed fix evidence

Finding #2 now resolves current/null and historical unique/conflict scalar
precedence in PostgreSQL and returns grouped rows from both headline fact
paths. `monitor/trend_narrative_facts.py` SHA-256 is
`6ae6d75a1c2eda2b8563a2b42f81ea55f0c26bb6e515f10915d0f46e032fc607`;
its test file SHA-256 is
`7a35d47824da9df8d6b86a0b5e1ef6e391db952ddb4c6d5b0b4ea66158b82fa6`.
All 58 fact tests passed with no failures, errors, or skips; JUnit SHA-256 is
`c09fb4e12d72ad86b2f1234463b1cf18b2969bdd3c961d5fc9338cf2b13827b9`.
The 1,000-post/two-brand regression observed 13 aggregate rows and eight
series rows for 2,000 post-brand pairs and exercised both public callers.

The 10,000-post/two-brand confirmation returned 35 count rows and 20 series
rows with one query per path. Counts measured 384.79 ms and 0.07 MiB Python
peak allocation; series measured 713.26 ms and 0.05 MiB. An earlier counts
sample took an unexplained 11.616 seconds, while a later `EXPLAIN ANALYZE`
reported 437.162 ms. That outlier remains disclosed and these local samples do
not establish production latency or capacity. The benchmark report
`.context/stage1-headline-scaling-after.md` has SHA-256
`02bd6b853911bbf11086835d7b0d720682565393e4927fd34dcb9c62a5e40be2`.

Finding #6 now sends the Stage 1 contract through the provider system field
and only canonical JSON evidence through the user message. Prompt identity is
`stage1-prompt-v2`; batch size, workers, provider/model settings, retries,
fallback, strict parsing, and telemetry cardinality are unchanged. The prompt
suite passed 204 tests with PostgreSQL 40/0/0. Its log SHA-256 is
`b90871f553706267efafee8ddb7e528f69b141c1c2d110eda6baf97f98500e26`
and JUnit SHA-256 is
`1c68998106ad8581707fb3aa0b82530ed767c61b2b687c487ecc11114ae5bad9`.
The reconciled health suite passed 64 tests with PostgreSQL 1/0/0; the health
helper itself did not change.

## Resumed gate status

- The final active/shared aggregate on clean M passed 2,489 tests with zero
  failures, errors, or skips; 25 nodes were deselected and 73 warnings were
  recorded in 249.04 seconds. Required PostgreSQL status was 609/0/0. Root
  independently counted 2,489 JUnit `testcase` elements; the suite count of
  2,597 includes subtests. The log at
  `~/.local/state/pushinweight-stage1-u5-tests/resume-aggregate-bdcfb638d66f-r2.log`
  has SHA-256
  `b0bf3e5ad6dfb352c42d295762e6a1bb4fe5bec68fed6dd2efb93f9f4b0d93f0`;
  the sibling JUnit has SHA-256
  `8ebde830cec7a62c3f921907636455e149a5872a0fe062c21859e35b05990fa3`.
- The candidate gate on clean M passed 195 pytest cases plus 62 subtests with
  PostgreSQL 68/0/0 in 39.64 seconds and 52 warnings. Node results were
  108/94/10. Normalized assurance was 3,475/3,475 with every bad count zero.
  The log at
  `~/.local/state/pushinweight-stage1-u5-tests/resume-candidate-bdcfb638d66f.log`
  has SHA-256
  `8c9c800f4b64400c194bb2b36e58648679161d88fa1591409420bc2970443433`;
  its JUnit SHA-256 is
  `798a3401ee28b91499146d7637e3cc069c426f5070ca2bc48112f754e61e679d`.
- Public sealed performance attempt
  `3e4e95f3561aa7834db6d39c` was clean with no findings, and root verified all
  eight artifact hashes. The saved result
  `.context/stage1-resume-performance-result.json` has SHA-256
  `524e11086e779261ba9bb17684ec9d0243e0192f3e3c8674509fb0fb4a24f696`;
  its evidence digest is
  `c759dd9dc83dd1397f6656f98af40984edd0fe94f92937381535917a84034628`.
  The sealed run used `data_source_kind=environment`, identity
  `environment:local-orm-seed:tests.v22_support.seed_v22_metadata_regression_orm+account-geography:v22-metadata-account-000=US`,
  and no fixture digest. Both scenarios ran twice with 3,306 DOM nodes each,
  two flag requests totaling 561,431 bytes, no `/feed/` or `/chart.html`
  requests, and all blocking budgets passing. Median Lighthouse LCP was
  1,398.37 ms desktop and 7,815.62 ms mobile; the mobile LCP advisory failed
  but remains nonblocking. CLS was 0.02584/0.01722 and Web Vitals INP was
  24/32 ms. The absent cache header is mapped by Bridgewright to its
  `no_store` observation; it is not proof of a literal development
  `Cache-Control: no-store` header.
- The exact-M local rollback probe and bounded browser check passed. English
  desktop and Chinese mobile rendered through the pinned proxy with exact M;
  all five product controls, the visible `bug` filter, the five-series
  DeepSeek product-label chart, no active discourse, and rollback cleanup were
  verified. External OAuth was skipped. The report
  `.context/stage1-resume-browser-probe-report-bdcfb638d66f.md` has SHA-256
  `2f9d7c6d7f7e019fd9e964af8a83c744517ad6230d5b905fc8af1d7e49adc8a9`;
  the 29-file manifest at
  `.context/root.pytest-tmp/stage1-resume-browser-bdcfb638d66f/SHA256SUMS`
  has SHA-256
  `8b8557cf2d904c6838463cc713834ac9b19fda5ba86c5faf99abd13b1ba3a27b`.
  The earlier full matrix and its three base-proven pre-existing UI defects
  remain historical evidence below.
- Authorized fixed-cohort 30-minute recheck: complete. The initial observation
  ran 22:23:04.684770–22:23:10.125489 UTC and the exact same 20 ordered IDs were
  rechecked 1,816.825342 seconds later at
  22:53:26.950831–22:53:28.910360 UTC. Both reported 20 complete, zero pending,
  and zero unhealthy. Language, required non-ZH translation, English
  commentary, and Chinese commentary presence/completion were each 20/20 in
  both observations. The legacy schema was unchanged. Initial SHA-256 is
  `e48499318f65b81bdcc1ebd34c851bd7ec7d61af03c564264fae0643cda413d8`;
  recheck SHA-256 is
  `64bcd11498b6e9ff5d14a8fdf571c27e568b2b94e836ab004509fb064f295ef0`.
  This proves persisted Stage 0 health, not semantic accuracy or Stage 1
  production behavior. No further health read or retry was made.
- Render deployed exact M to all three staging services from deploys created
  at 23:23:47 UTC: web `dep-dag9i0oae00c738n15l0` became live at
  23:25:11.018679 UTC, headlines `dep-dag9i0oae00c738n161g` at
  23:24:53.346938 UTC, and harvest `dep-dag9i0oae00c738n169g` at
  23:24:34.509252 UTC. The deployment receipt
  `.context/stage1-staging-live-deploys.json` has SHA-256
  `18770b2809546855dc798ab3ece5d19fce81509d1182f28f28882e6cb77131bc`.
  Main remained at `af272b6fe0b43be3276429792508749b9ddc8194`.
- The strict deployed rollback probe ran
  23:26:19.344514–23:26:29.578947 UTC and passed all 12 identity, health,
  migration-0028, taxonomy, atomic publication, initial/replacement scalar
  SQL, feed, no-discourse, and rollback-cleanup checks against the expected
  staging service, database, user, and host. The receipt
  `.context/stage1-staging-probe-receipt-bdcfb638d66f-20260908T232619344514.json`
  has SHA-256
  `b9713208c349a23ca8022b8aed89708e144330693c7fd4002ed3d509d27de3e7`.
- The live anonymous staging smoke verified both English desktop and Chinese
  mobile roots returned the expected 302 to `/accounts/login/`, followed by a
  200 login page. The mobile page fit 390/390, with no console, page, or
  unexpected-network errors. Authenticated controls, filtering, OAuth, and
  the homepage revision header were skipped because the auth wall was
  respected; no staging user, session, or auth state was created. Exact M is
  established separately by all three Render deploy records and the strict
  SSH probe. The report
  `.context/stage1-staging-smoke-bdcfb638-report.md` has SHA-256
  `d3282e538b9a10b4f7cb26c337d35f761681749c82ce9176fbb7d0980ecd69e2`;
  its manifest at
  `.context/root.pytest-tmp/stage1-staging-smoke-bdcfb638/SHA256SUMS` has
  SHA-256
  `802adbfde16c715053b84407a448b10f8161f9ce616b90eb2855448324c41521`.
  The actual harvest schedule remains disabled at `0 0 31 2 *`; no Blueprint,
  harvest, provider, queue, or headline trigger was invoked.

## Historical invalid resumed aggregate attempt

The first resumed aggregate attempt recorded 2,488 passed and one failure in
`tests/test_bridgewright_revision.py::test_revision_header_is_scoped_to_homepage`.
The replay runner had incorrectly injected preview revision identity into the
unit-test process, so this was a verification-envelope failure and was never a
green aggregate. The retained log SHA-256 is
`29339031a0441abd3557ac54f53deb3987afcdeba714abd4d1a4e140a4d45223`; the
JUnit SHA-256 is
`f14a51308a5762dd3e55b08ca43ad3f5cedd8fd682607ed79daf5becc524c2d7`.

## Historical M2 aggregate and candidate evidence

This section records the earlier historical product P
`29512a89d2606fd0e646e1a0ad4a10694d42b7d6`, metadata M
`266857222440b7f747047a8f9b5b2ef24c11402c`, and metadata M2
`e9157e527adfadcf1eb7c92fe7e648296d9690b9`. Its P, M, and M2 references are
historical and distinct from the resumed P/M identities above.

The final active/shared aggregate on clean M2 recorded **2,486 passed, zero
failed, zero skipped, zero errors, and 25 deselected**, with 73 warnings in
240.25 seconds. Required PostgreSQL status was 608/0/0. The JUnit contains
exactly 2,486 `testcase` elements; its suite count of 2,594 includes subtests.
The log SHA-256 is
`ad4528cb72401c0bd1c1ffd285e9036d72608dd5c96316c32d3bf859dad89cfa` and
the JUnit SHA-256 is
`e851d1e19646e244c0e2c8274c5e785553149340e10f771c1cf4d5daf29a6aa6`.
The artifacts are
`~/.local/state/pushinweight-stage1-u5-tests/active-required-final-e9157e527adf.log`
and its `-junit.xml` companion.

The final clean-M2 candidate session `23625` exited zero: pytest passed 195
cases plus 62 subtests with PostgreSQL 68/0/0; the three Node gates passed
108/94/10; and all 3,475 normalized assurance obligations passed with every
bad-count at zero. The candidate log SHA-256 is
`cfcc1049cd080bddb7e346b79bf31664d4b0df8726527ea945fcef2ce409d6a3` and
the JUnit SHA-256 is
`7a47cf7c41f67f5b6aed4613b228d93b80542060397f700314535dcd7779ae3c`.
They are stored under
`~/.local/state/pushinweight-stage1-u5-tests/candidate-final-e9157e527adf-geography*`.

The public sealed performance attempt `8c5311ef1e03a67b5a377f9f` exited zero
with no findings, and all eight artifact hashes verified. The saved result is
`.context/stage1-final-performance-result.json`, SHA-256
`0e14934a5dc0d182d0a638de39e272dd6d8a75e1c622c667331d459f66203068`;
its evidence digest is
`09269a729371be853e7df756a0629ac3ebe0d3c91bc2f98a18678a86605e87bd`.
The sealed run records `data_source_kind=environment`, `fixture_digest=null`,
and the complete data-source identity
`environment:local-orm-seed:tests.v22_support.seed_v22_metadata_regression_orm+account-geography:v22-metadata-account-000=US`.
Both scenarios ran twice. Each produced 3,306 DOM nodes against the 6,000
limit. Flag assets made two requests totaling 561,431 bytes against the
600,000-byte limit, and neither `/feed/` nor `/chart.html` was requested.
Bridgewright reported the observed cache check as passing by mapping an absent
cache header to `no_store`; this is not proof of a literal development
`no-store` header. Median Lighthouse LCP was 1,399.26 ms desktop and 7,661.58
ms mobile; the mobile LCP advisory failed but is non-blocking. Desktop/mobile
CLS was 0.01965/0.01722 and Web Vitals INP was 12/20 ms.

All Stage 1 taxonomy, filter, discovery, locale, window, feed, chart, and brand
chart browser flows passed. The overall browser result remains failed only for
three base-proven pre-existing defects: three internal HTMX syntax errors, a
visible raw brand-template comment, and 390 px internal/brand horizontal
overflow at 619/645 px. External OAuth was excluded. The full matrix ran at M,
and closing M2 page/API checks were byte-identical; P did not change. The
report is `.context/stage1-final-browser-report-M2668572-M2.md`. The 85-file
evidence manifest is
`/Users/fuchitalee/development/pushin-weight-v2/.pytest-tmp/stage1-final-browser/SHA256SUMS`,
verified SHA-256
`6a0a8a94a2bcf166e1b11d93966671d4a76bb5ddada4e5704c24c6e52b617fd4`.

The first candidate performance attempt, `9a3b4d0220a60630c9ac89f4`, remains
invalid with `cache_expectation_failed` for `/static/country-flags.svg`.
The artifact contained no country-sprite request because the 79-post ORM
preview seed lacked geography; this was a fixture setup defect, not a cache
policy observation. The preview-only correction changed account `000` from a
null country to `US` while preserving all 79 posts, classification counts, and
digests. Both origins returned 200 at M2 and `#flag-us` was visible. The setup
receipt `.context/stage1-preview-geography-receipt.json` has SHA-256
`bc7978649269505c01a82714005594affeb4dcf16d58625428fcf214bb6ce2d3`;
The initial preview used `tests.v22_support.seed_v22_metadata_regression_orm`;
the reproducible guarded one-update script is
`.context/stage1-preview-geography-setup.py`, SHA-256
`a09d48382b69b9f3b62c7e313dd367e320ede767cdcdf7a9af3f4ea68762b57e`.

## Historical pre-commit source snapshot

The dirty-source digest is
`bf91522ab35663a6dec08ceb60613be4f770189be5459d288dc7e000e0d9bb99`.
It is SHA-256 over each sorted dirty path, a NUL byte, that file's SHA-256,
and a newline. It covers the following 52 paths. This receipt is the 53rd
dirty path and is intentionally excluded to avoid a self-referential digest.
The Stage 0 baseline and plan annotations in this list are parent-owned.

```text
.claude/skills/harvester-latest-n-health-check/scripts/check.py
CONCEPTS.md
config/staging_refresh.yaml
docs/analysis/2026-09-08-134925-ai-enrichment-stage1-evaluation.md
docs/analysis/2026-09-08-194415-enrichment-stage0-baseline.md
docs/operations/staging-data-refresh.md
docs/plans/2026-09-08-134925-feat-ai-enrichment-stage1-plan.md
docs/reference/2026-09-08-194415-enrichment-contracts.md
monitor/cycle.py
monitor/management/commands/validate_cycle.py
scripts/post_fetch_smoketest.py
tests/fixtures/ai_enrichment_stage1_test_scope.json
tests/fixtures/classification_stage1_contract_v1.json
tests/regression_net.py
tests/test_account_geography_migrations.py
tests/test_bridgewright_v24_target.py
tests/test_build_anthropic_client_from_env.py
tests/test_classification_labels.py
tests/test_classification_stage1_contract.py
tests/test_cursor_since_time.py
tests/test_harvest_surface_regression_net.py
tests/test_harvester_latest_n_health_check.py
tests/test_harvester_state_migrations.py
tests/test_headline_status.py
tests/test_home_chart_pulse.py
tests/test_home_v22_browser.py
tests/test_i18n_catalog_pinned.py
tests/test_post_fetch_smoketest.py
tests/test_post_fetch_smoketest_api_source.py
tests/test_post_fetch_smoketest_call_preview.py
tests/test_post_fetch_smoketest_latest_cycle.py
tests/test_post_fetch_smoketest_latest_n.py
tests/test_post_fetch_smoketest_renderer.py
tests/test_post_fetch_smoketest_strict_budget.py
tests/test_post_fetch_smoketest_translation_failures.py
tests/test_prepare_account_geography_recovery.py
tests/test_prepare_account_user_about_recovery.py
tests/test_primary_purity_seed.py
tests/test_queries.py
tests/test_quote_tweets.py
tests/test_relevance.py
tests/test_resolve_lonely_placeholders_exit_summary.py
tests/test_resolve_lonely_placeholders_flags.py
tests/test_resolve_lonely_placeholders_port_safety.py
tests/test_run.py
tests/test_run_pipeline_live_wiring.py
tests/test_run_post_fetch.py
tests/test_staging_harvest_acceptance.py
tests/test_trend_narrative_dispatch.py
tests/test_validate_cycle_post_fetch.py
x_monitor/queries.py
x_monitor/run.py
```

## Historical U5 aggregate evidence

The final reviewed local aggregate ran with `DEBUG=1`, an explicitly empty
`CYBER_QUAN_CAPTURE_ONLY`, blank provider and Twitter credentials, loopback-only
deny proxies, and the disposable PostgreSQL database
`pushinweight_stage1_u5`. The command was:

```text
env DEBUG=1 CYBER_QUAN_CAPTURE_ONLY='' DEEPSEEK_API_KEY='' \
  ANTHROPIC_API_KEY='' MINIMAX_API_KEY='' \
  X_MONITOR_CLASSIFIER_API_KEY='' TWITTER_API_KEY='' \
  TWITTERAPI_IO_KEY='' HTTP_PROXY=http://127.0.0.1:9 \
  HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 \
  NO_PROXY=localhost,127.0.0.1 \
  DATABASE_URL=postgresql://fuchitalee@localhost/pushinweight_stage1_u5 \
  .venv/bin/python .context/run_stage1_u5_required.py
```

The runner, SHA-256
`cd5ab453c5473286a6172ea8b1cbcf6138a8ca448be907cf6e89d254a5ad18ba`,
builds structured pytest arguments from the portable tracked scope manifest
`tests/fixtures/ai_enrichment_stage1_test_scope.json`, SHA-256
`7e9a70a6c52be6ca4e8ac66e5b9dd1f6d79740e4a6e7c71d818fc79706f1b01d`.
The default is required. Only source-audited retired whole files, 28 guarded
historical live-shadow snapshot tests, 23 retired nodes in mixed files, and
five explicit live/network nodes are outside the local required projection.

A fresh checkout can replay the tracked scope without the ignored historical
runner. Set the two caller-owned local paths below, then run this exact
structured-argument invocation. `STAGE1_DATABASE_URL` must name a disposable
local PostgreSQL database; the command clears provider and Twitter credentials
and denies non-loopback transport.

```bash
export STAGE1_DATABASE_URL='postgresql://USER@localhost/DISPOSABLE_DB'
export STAGE1_ARTIFACT_DIR="$HOME/.local/state/pushinweight-stage1-replay"
env DEBUG=1 CYBER_QUAN_CAPTURE_ONLY='' DEEPSEEK_API_KEY='' \
  ANTHROPIC_API_KEY='' MINIMAX_API_KEY='' \
  X_MONITOR_CLASSIFIER_API_KEY='' TWITTER_API_KEY='' \
  TWITTERAPI_IO_KEY='' HTTP_PROXY=http://127.0.0.1:9 \
  HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 \
  NO_PROXY=localhost,127.0.0.1 DATABASE_URL="$STAGE1_DATABASE_URL" \
  .venv/bin/python - "$STAGE1_ARTIFACT_DIR" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
artifacts = Path(sys.argv[1]).expanduser().resolve()
scope = json.loads(
    (root / "tests/fixtures/ai_enrichment_stage1_test_scope.json").read_text()
)
artifacts.mkdir(parents=True, exist_ok=True)
command = [
    str(root / ".venv/bin/pytest"),
    "tests",
    "--continue-on-collection-errors",
    "-o",
    f"cache_dir={artifacts / 'cache'}",
    f"--basetemp={artifacts / 'tmp'}",
    f"--junitxml={artifacts / 'junit.xml'}",
]
for path in scope["ignored_files"]:
    command.extend(["--ignore", path])
for node_id in scope["deselected_nodes"]:
    command.extend(["--deselect", node_id])
with (artifacts / "pytest.log").open("w") as log:
    process = subprocess.Popen(
        command,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        log.write(line)
    raise SystemExit(process.wait())
PY
```

The result was **2,486 passed, zero failed, zero skipped, zero errors, and 25
effective deselections**, with 73 warnings in 244.86 seconds. Required
PostgreSQL status was 608 executed, zero skipped, and zero errors. The log
SHA-256 is
`f9824836f9d43bf884cd9448b3d657e133d2d5e6655fe29cfc21488f9a7ed677`;
the JUnit SHA-256 is
`b1770d77062e0b5a3666f745438f61f48f853c4b845e401a4af76310120fdcfa`.

The complete mixed-stack r6 result remains separate and red: **3,319 passed,
250 failed, 73 skipped, and five deselected**, with 73 warnings in 290.35
seconds. Required PostgreSQL status was 608/0/0. Of the 250 failures, 247 were
in source-audited retired files or retired nodes. The other three were current
tweet-normalization assertions, subsequently repaired and verified with their
active companions; this receipt does not invent a new whole-suite total. The
r6 log SHA-256 is
`84aa695e457d26b823b038759231cef89daa684c134da4d739760e47b435103a` and
JUnit SHA-256 is
`9f7f9ca59c399ef4dea423936d2851f21fd6f34d4d1a3abb7d531ef2d8d62225`.
The prior r5 result was 3,282 passed, 287 failed, 73 skipped, and five
deselected, with required PostgreSQL 608/0/0. It is retained as pre-repair
evidence rather than an acceptance result.

The one-to-one r6 disposition inventory covers all 3,647 collected nodes:
2,249 active/shared required, 237 U5 compatibility required, 1,128 retired,
28 guarded historical live snapshots, and five explicit live exclusions.
Every one of the 3,642 selected cases maps to exactly one JUnit outcome; every
skip retains its emitted reason. The ignored working artifacts and hashes are:

```text
.context/stage1-u5-test-disposition-rules.json  a8d3e2533613007ce017191c9295780fc25c86ccbf83e9acc728875235722536
.context/build_stage1_u5_test_disposition.py    38629d61aaae36ac1e000ddbb54eaf75bfc5d0eddab2afde3a9d9cf9ac18c318
.context/stage1-u5-test-disposition.csv         4368c47af6e2d2c4ba68131d08cdee493ead8d4a87a50a4cc1abb7d26bd0abe9
```

The Stage 0 comparison at exact SHA
`af272b6fe0b43be3276429792508749b9ddc8194` remains complete. Its corrected
same-environment result was 3,066 passed, 427 failed, 74 skipped, five
deselected, and seven errors. That comparison informed the scope audit but did
not waive any current/shared test.

## Historical focused evidence

- Contract/writer/reader/adapter/diagnostic/health integration: 133 passed;
  required PostgreSQL 12/0/0. Post-fetch smoke: 44 passed.
- Retired `x_monitor.run` adapter: 26 passed. Relevance reconciliation: 34
  passed. Health helper: 64 passed with required PostgreSQL 1/0/0.
- Browser repairs: nine required PostgreSQL nodes plus two subtests passed;
  the final favicon node also passed. The earlier U3 affected browser gate was
  166 passed plus 54 subtests.
- Current provider/cursor/headline/dispatch repairs: 47 passed, required
  PostgreSQL 4/0/0. Placeholder flags, deadlines, and dead-letter boundary: 18
  passed. Current quote normalization with companions: 15 passed.
- Staging acceptance
  `tests/test_staging_harvest_acceptance.py::test_real_nonempty_cycle_runner_reaches_same_cycle_terminal_acceptance`
  passed against a valid Stage 1 fixture, required PostgreSQL 1/0/0.
- The stored 18-case contract fixture matched all expected outcomes: six valid
  canonical results and 12 intentional invalid rejections. Its language and
  context tags are fixture metadata; separate cycle-envelope tests establish
  stored-quote and local-parent wiring.
- The real HTTP regression manifest passed 107/107 in English and 107/107 in
  Simplified Chinese. It checks all ten post types, all five products, no
  active discourse control, feed/filter/chart/HTTP behavior, and the current
  public-window contract.
- Full configured Ruff passed on the new/authored health and validation files.
  The required `E4,E7,E9,F,I` scan of the remaining modified Python reported
  two unchanged baseline findings: import ordering in
  `test_i18n_catalog_pinned.py` and an unused retired-section import in
  `test_quote_tweets.py`. Both reproduce from HEAD and neither line was edited.
  JSON parsing and `git diff --check` passed. The quality log SHA-256 is
  `de910f1ac308acd522894f33f2f68804a1bcea941e9e69aadaa011a776ee9191`.

## Historical evidence boundaries

At 17:19:03–17:19:07 UTC on September 8, the parent made the single authorized
latest-20 production health observation. Render returned zero, but the helper
reported `render_output_invalid`; no post IDs were captured. This is an
operational observation failure, not a classification failure. There was no
retry, replacement cohort, or 30-minute recheck. Permission for a bounded
replacement observation remained pending when the original hold receipt was
written; the authorized replacement and exact-ID recheck are complete above.

During the original hold phase, U5 performed no production cohort, provider
acceptance, production write, staging refresh, source-reader grant, migration,
deploy, or health verification. At that time, Stage 0 production remained on
migration 0027, and the expanded migration-0028 reader grants had not been
applied or live-verified.

Two provider calls from an earlier failed local wiring test are excluded from
acceptance evidence: `post_translation_synthesis` at
17:06:01.078426 UTC and `classification` at 17:06:02.991129 UTC on September
8. A stale constructor mock and inherited credential allowed them. Subsequent
runs blanked all provider/Twitter credentials, blocked outbound transports,
and mocked the active public factories. No returned content is retained here.

The deterministic fixture proves contract behavior, not English, Chinese, or
Japanese semantic accuracy. No heldout gold evaluation or numeric production
quality floor has been completed. The renderer retains a pre-existing gap:
there is no direct escaping or unsafe URL-component fallback test for its raw
dynamic interpolation. U5 restored scalar compatibility, empty-flag omission,
latest-N exact order/exclusion, and preview-main invocation coverage without
expanding into a renderer security redesign.

Formal simplify and code review are complete; the resumed #2/#6 fixes are
independently reviewed, and the authorized fixed cohort is complete. The new
P/M required automated aggregate and candidate/performance gates are green;
the bounded exact-M local browser and deployed rollback proofs passed. Live
authenticated staging controls, OAuth, and the homepage revision header were
skipped behind the auth wall. The historical full browser matrix remains red
for its three base-proven pre-existing UI defects, and the mobile LCP advisory
remains a nonblocking failure. Stage 1 is deployed and verified for the
authorized staging scope; there is no Stage 1 production authority. R17's
fresh semantic gold and numeric floors are a preproduction gate and are not
represented by the deterministic local proof.

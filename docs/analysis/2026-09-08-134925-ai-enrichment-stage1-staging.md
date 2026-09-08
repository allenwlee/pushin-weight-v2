# Stage 1 staging hold receipt

This is the final local readiness record and a staging hold. Staging delivery
is authorized by the frozen plan, but Stage 1 has not been deployed to staging
or production. The reviewed local aggregate and candidate gates are complete.
The hold remains because authority for a replacement immutable latest-20
observation is unanswered, no 30-minute clock was established, and staging
migration plus exact-SHA health evidence do not exist. Formal findings #2 and
#6 remain unapplied and undecided. Production promotion is not authorized.

## Candidate identity and source state

The reviewed product source is P
`29512a89d2606fd0e646e1a0ad4a10694d42b7d6`. The accepted U5 source snapshot
was `a242e96c28931eb61d12c03e77172ee47c3ebc69`; formal review then found the
retired-SQLite write and P removed it. The final measured metadata revision is
M `266857222440b7f747047a8f9b5b2ef24c11402c` and the final measured metadata
revision is M2 `e9157e527adfadcf1eb7c92fe7e648296d9690b9`. The forthcoming
receipt-only D revision changes documentation, so its runtime and product
source are equivalent to measured M2 and P. The Product Contract remains
byte-identical, SHA-256
`d4789b803b74e348de481e9956f2089ea140a4859ee6953fd80c1814e8645bc3`.
The frozen plan's technical Verification Contract now names the reviewed
active Django/shared-runtime aggregate; its product requirements, KTDs,
delivery target, and health gates are unchanged.

Formal review run `20260909-044149-aa012156` is complete. Its archived result
is `.context/stage1-review-archive/review.json`, SHA-256
`cdf6bb9405062297488774f7ac07ad1f205dcaaeb29230d907f60842026d9516`.
Finding #4 was fixed at P and seven focused tests passed with PostgreSQL 0/0/0.
Findings #2 and #6 remain manual, unapplied, and undecided; findings #3, #8,
and #14 remain report-only under the recorded KTD conflicts.

## Final M2 aggregate and candidate evidence

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

## Evidence boundaries and outstanding gates

At 17:19:03–17:19:07 UTC on September 8, the parent made the single authorized
latest-20 production health observation. Render returned zero, but the helper
reported `render_output_invalid`; no post IDs were captured. This is an
operational observation failure, not a classification failure. There was no
retry, replacement cohort, or 30-minute recheck. Permission for a bounded
replacement observation remained pending when this receipt was written.

No production cohort, provider acceptance, production write, staging refresh,
source-reader grant, migration, deploy, or health verification was performed
by U5. Stage 0 production remained on migration 0027 during the September 8
verification. The expanded migration-0028 reader grants fail closed when a
source table is missing and have not been applied or live-verified.

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

Formal simplify and code review, the final normalized aggregate, candidate
gate, browser matrix, and sealed performance gate are complete. The replacement
fixed cohort and 30-minute recheck still lack authority and were not performed.
Staging deployment, migration confirmation, and exact-SHA staging health remain
incomplete. Stage 1 is authorized for staging but remains held; there is no
Stage 1 production authority. R17's fresh semantic gold and numeric floors are
a preproduction gate and are not represented by the deterministic local proof.

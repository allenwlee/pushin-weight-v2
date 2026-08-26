---
title: Persistent Homepage Preferences and UI Regression Repairs
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
type: feat
date: 2026-08-26
ollija:
  change_id: feat-ui-state-chart-avatars-model-tabs-2026-08-26-043852
  branch: feat/ui-state-chart-avatars-model-tabs
  workflow: lfg
  delivery_target: staging
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `./bin/ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ui-state-chart-avatars-model-tabs`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ui-state-chart-avatars-model-tabs/docs/plans/2026-08-26-043852-feat-ui-state-chart-avatars-model-tabs-plan.md`
- Change: `feat-ui-state-chart-avatars-model-tabs-2026-08-26-043852`
- Branch: `feat/ui-state-chart-avatars-model-tabs`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ui-state-chart-avatars-model-tabs/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ui-state-chart-avatars-model-tabs/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `lfg`
- Delivery target: `staging`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the Render deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.

### Failure handling

- Never promote a staging candidate whose automated checks failed.
- Implementation failures return to the parent implementation workflow for diagnosis, correction, recommit, and restaging.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

None.

# Goal

Make the public homepage remember each browser user's last-used view across
reloads and sessions, repair the reported chart, model-tier, pulse, feed, and
mobile-title regressions, and deliver the verified candidate to hosted staging
without changing production. Staging must preserve production's current
baseline outside the intentional changes because the owner reports that the
current staging site has drifted substantially from production.

## Product Contract

### Requirements

- **R1 — Persistent last-used view.** Persist locale, 1d/7d/30d/365d window,
  Local/CA time selection, open/closed lens, filter selections, and pulse model
  selections in one versioned `localStorage` payload. Namespace it by the
  authenticated user identity when available and by an anonymous key otherwise.
  Rehydrate controls before the first chart/feed request so the restored view
  does not briefly fetch or display product defaults. Continue the locale cookie
  for server-side rendering, but make a stale `?locale=` parameter a one-request
  override rather than a permanent redirect trap. Browser state is automatic
  "last used" state; it is not an account default and must not add a database
  model in this change.
- **R2 — Remove redundant pulse heading.** Remove `.pulse-bar-head` and reclaim
  its vertical space while preserving the pulse chips themselves.
- **R3 — Dual 1d axes.** In 1d only, place both x axes below the plot with local
  time immediately above California time. Local lettering/ticks must be more
  visible than today; California must use the existing orange family at lower
  opacity. Label even hours as `0:00, 2:00, ... 22:00`; keep an unlabeled hash
  mark for every odd hour. The rolling 24-hour domain still begins at the hour
  after the current hour on the left and ends at the current hour on the right.
- **R4 — Follower glyphs.** Replace each V22 initials avatar with a follower-count
  circle derived from the real raw follower count. Bins are 0–999, 1,000–9,999,
  10,000–49,999, and 50,000+, with monotonically increasing diameter and opacity.
  Use the existing followers-icon color family and expose an accessible follower
  count. Keep the legacy internal feed unchanged.
- **R5 — Mobile title.** Keep `走个量` unchanged. Render the English app name as
  two explicit lines, `Pushin'` then `Weight`, sized so their combined height
  aligns with the Chinese title and remains fully visible at 390px and narrower.
- **R6 — Complete pulse set.** Render all 20 canonical enabled models in the
  pulse chips, in canonical enabled-model order, including models with zero
  activity. Activity determines metrics and visual state, not membership.
- **R7 — Correct open/closed tiers.** Put `gemini`, `gpt`, `claude`, and `grok`
  in Closed and remove them from Open. Preserve all other current brands and
  existing count/selection semantics.
- **R8 — Staging-only delivery.** Commit and push the feature branch, open and
  watch its PR, fast-forward the exact green candidate to `staging`, and verify
  the Render staging deployment at that exact SHA. Do not push or promote to
  `main` and do not alter production.

### Persisted-state precedence

For each homepage load, resolve state in this order without writing an
override back unless the user changes a control:

1. Valid explicit URL parameter for this request (shareable/transient).
2. Version-compatible last-used browser state for the current user namespace.
3. Locale cookie for locale only.
4. Product defaults.

Every user control mutation updates the complete normalized payload, not an
independent key. Invalid values, unknown filter IDs, stale schema versions, and
storage exceptions fall back safely without breaking page initialization.
Future account defaults can reuse this payload shape but are explicitly out of
scope.

### Preserve

- `/internal/`, the legacy feed template, auth behavior, Django models,
  migrations, harvest/headline workers, and production data.
- Existing filter meaning, chart/feed endpoints, long-window request race
  protection, last-good rendering, locale translations, and mobile horizontal
  scrolling where required.
- Production's current public homepage except for R1–R7.

### Acceptance cases

1. Select 30d, CA, Closed, and a non-default brand/filter set; change locale;
   reload and reopen the browser page. Every selection and the chosen locale
   return before chart/feed requests, and a stale prior `?locale=en` does not
   force English after choosing Chinese.
2. Two signed-in user namespaces do not consume each other's stored state;
   malformed or unavailable storage loads the product defaults without a JS
   exception. Anonymous state remains separate.
3. At 1d, both axes are visibly below the plot in Local-then-CA order; twelve
   even-hour labels per axis include `:00`, odd hours retain tick marks, local is
   more prominent, and CA is visibly dimmer. At 7d/30d/365d, no second hourly
   axis appears and existing behavior remains.
4. V22 server-rendered rows and rows inserted by `pw-feed.js` use the same four
   follower-bin classes and accessible counts. Boundary values 999/1,000,
   9,999/10,000, 49,999/50,000 map correctly.
5. Desktop and 390px mobile render no pulse heading, show a fully readable
   two-line English title next to unchanged `走个量`, show exactly 20 pulse
   chips, and show four Closed brands with none duplicated in Open.
6. Hosted staging resolves to the candidate SHA, passes the focused/browser
   checks, and matches the production baseline outside intentional selectors.

## Technical Design

### Browser preference store

Extend `monitor/static/pw-filter-store.js` into the single owner of a
versioned homepage preference object. It will normalize persisted filters
against the actual rendered controls, provide `getPreferences`,
`setPreference`, and subscription-compatible state updates, and persist after
control mutations. `pw-tz.js` and `pw-locale-toggle.js` will use that public
surface rather than introduce separate storage keys. The template will expose
a non-sensitive user namespace and server-resolved locale/window defaults in
data attributes. The locale endpoint continues setting the one-year cookie;
the redirect must remove the just-consumed locale query parameter so it cannot
override the new selection forever.

The payload shape is `{version, locale, window, timezone, lens, filters,
pulseBrands}` under a key shaped like
`pushinweight.home.preferences.v1:<namespace>`. The namespace is `anonymous`
when logged out and an opaque stable server-provided value when authenticated.
Logging in does not silently merge anonymous state into account-scoped browser
state; each namespace restores only its own last-used payload. A later explicit
"save as my default" feature may copy this same normalized shape to an account
preference or named saved view, but no automatic browser-to-account write is
allowed in this change.

### Model and follower projections

Use the canonical 20-model registry already represented by
`MODEL_DISPLAY_NAMES`/`config.yaml` as pulse membership, then left-join computed
activity so zero-activity models remain visible. Correct closed membership by
nickname (`gemini`, `gpt`, `claude`, `grok`). Add one server-side follower-bin
projection to V22 feed display fields and mirror only its rendering contract in
the client updater; no follower classification belongs in templates.

### Chart contract

Keep one Chart.js canvas. For 1d, configure both category scales at `bottom`
with deterministic scale weights/order, even-hour callbacks, and grid settings
that draw tick hashes but not vertical chart-area grid lines. Pin computed scale
positions, tick labels, tick geometry, and colors in both JS and browser tests.

## Implementation Units

### U1 — Pin browser state and locale regression red

**Files:** `tests/test_home_v22_browser.py`, `tests/test_window_cookies.py`,
`monitor/static/pw-filter-store.js`, `monitor/static/pw-tz.js`,
`monitor/static/pw-locale-toggle.js`, `monitor/templates/monitor/home.html`,
`monitor/views.py`.

- Add a real-route browser case that selects window/time/lens/filters, changes
  locale, reloads, and observes the restored state plus the first runtime
  request parameters.
- Add storage-version, malformed-storage, and namespace isolation cases.
- Implement the normalized single-payload store and fix consumed locale-query
  redirects. Update `docs/reference/home-pages-ui-guide.md`, whose current
  `pwFilters` cookie claim is inaccurate.

**Done:** red-before/green-after browser coverage proves the production call
chain, not only helper functions.

### U2 — Repair model membership and pulse inventory

**Files:** `monitor/views.py`, `monitor/templates/monitor/home.html`,
`tests/test_home_chart_pulse.py`, `tests/test_home_v22_browser.py`.

- Replace provider-name closed constants with the four actual brand nicknames.
- Build pulse entries for all canonical models and attach activity when present.
- Assert exact Open/Closed disjoint membership and exact 20-chip inventory,
  including a zero-activity canonical model.

**Done:** rendered homepage and chart refresh keep the same 20-member set and
the Closed count is four.

### U3 — Repair the 1d chart axes

**Files:** `monitor/static/pw-chart.js`, `tests/test_pw_chart_filter.js`,
`tests/test_home_v22_browser.py`.

- Move both hourly scales below the plot, set local/CA order and relative
  opacity, format even-hour labels, and retain odd-hour tick hashes.
- Preserve all longer-window scale and fast-switch behavior.

**Done:** Node contract tests and a real Chart.js browser instance prove scale
positions, ordered pixels, labels, tick marks, and non-1d preservation.

### U4 — Replace V22 avatars with follower circles

**Files:** `monitor/views.py`, `monitor/templates/monitor/_feed_initial_v22.html`,
`monitor/static/pw-feed.js`, `monitor/static/home-v20.css`,
`tests/test_home_v22_feed_row_shape.py`, `tests/test_home_v22_browser.py`,
`tests/test_views.py`, and affected V22 fixtures.

- Project raw follower count to one of four semantic bin classes.
- Render identical accessible glyphs in SSR and incremental feed paths.
- Keep `_feed_initial_legacy.html` and `/internal/` initials avatars unchanged.

**Done:** all four boundary bins and post-refresh parity are exercised through
the real endpoint and DOM.

### U5 — Simplify homepage chrome

**Files:** `monitor/templates/monitor/home.html`,
`monitor/static/home-v20.css`, `tests/test_home_v22_topbar_layout.py`,
`tests/test_home_v22_browser.py`.

- Remove pulse heading markup/styles.
- Split only the English app-name rendering into two lines and tune responsive
  geometry without changing the Chinese title.

**Done:** browser geometry proves complete text visibility and alignment at
desktop and mobile widths, in both locales.

### U6 — Update the Bridgewright target and regression net

**Files:** new timestamped `docs/reference/*bridgewright-target.md`,
`bridgewright.yaml`, and `tests/test_bridgewright_v24_target.py` (or a renamed
successor matching the new contract).

- Record R1–R7 as the approved target while explicitly preserving production's
  baseline outside those selectors.
- Keep Bridgewright assessment-only: it cannot approve or deploy.
- Pin source hygiene so templates/static assets contain no planning or agent
  commentary.

**Done:** target guard and source-hygiene checks pass and the assessment output
identifies only intentional differences.

### U7 — Focused, full, and visual verification

Run:

```bash
node tests/test_pw_chart_filter.js
pytest tests/test_home_chart_pulse.py tests/test_window_cookies.py \
  tests/test_home_v22_feed_row_shape.py tests/test_home_v22_topbar_layout.py \
  tests/test_bridgewright_v24_target.py
pytest tests/test_home_v22_browser.py
pytest tests/ollija
pytest
python manage.py check --deploy
```

Use a disposable deterministic database and a local server from this worktree.
Capture desktop and 390px mobile screenshots for English and Chinese, exercise
locale/reload state, all windows, Local/CA, Open/Closed, and incremental feed
replacement. Report executed/skipped/error counts and fail on any unexpected
skip or browser setup error.

### U8 — Review, ship PR, and stage exact candidate

- Run the LFG simplification and code-review passes; apply eligible findings and
  rerun affected checks.
- Refresh Ollija annotation and run `annotate-plan --check` before Git and
  deployment mutations.
- Commit scoped changes, push the feature branch, open a PR, and watch CI to a
  decided state.
- After green evidence, fetch `origin/staging`, require a fast-forward, and push
  the exact candidate SHA to the staging ref described in the generated guide.
- Verify Render reports the same SHA at
  `https://pushinweight-staging-web.onrender.com`; compare staging against
  production at matched viewport/locale/state, allowing only R1–R7 differences.

**Done:** hosted staging is visually and behaviorally verified at the exact
candidate SHA. Stop there; production remains untouched.

## Risks and Mitigations

- **State initialization races:** restore synchronously before chart/feed modules
  initialize and assert first-request parameters.
- **Shared-device leakage:** namespace local storage by stable, non-secret user
  identity; never persist OAuth data, tokens, or raw server responses.
- **Stale/renamed filters:** normalize against current controls and schema
  version; discard unknown values.
- **Pulse query inflation:** keep the existing aggregate query bounded and merge
  it with the 20-item registry in memory rather than issuing per-model queries.
- **SSR/client drift:** one server projection and paired endpoint/browser tests
  pin both render paths.
- **Staging drift:** deploy the exact tested SHA and compare against production's
  current baseline, not the pre-existing staging appearance.

## Confidence

High on the requested product behavior and affected call chains. Medium on the
exact Chart.js bottom-scale weight values until confirmed in the real browser;
the implementation unit deliberately treats runtime pixel order as the arbiter.

# Iteration 009 (v22) — U2 defaults shipped (window=1, locale=zh_cn); +4 assertions

**Date:** 2026-08-09
**Branch:** feat/v20-homepage-phase-a
**Scope:** Ship U2 (defaults = 24h/zh_cn/local-TZ) — the plan body promised `HOME_WINDOW_DEFAULT == 1` as the AFTER state, but the code still had `HOME_WINDOW_DEFAULT = 7` (the BEFORE pin). Iter 9 audit surfaced the discrepancy; fix-now per mockup-canon + plan-execution contract.

## Step 0 — Regression Net (pre-edit)

```
Passed: 72
Failed: 0
```

## Step 1 — Audit finding

Chrome DevTools + regression_net probe found the live `/` page defaults to `7d` not `1d`:

```
active window button: 7d  (should be 1d per U2)
data-pw-window attr: 7d
```

`monitor/views.py:154` still had `HOME_WINDOW_DEFAULT: int = 7`. Plan § U2 explicitly states AFTER = 1. Iter 1-4 left this untouched.

## Step 2 — Implementation

### Fix in `monitor/views.py:154-155`

```python
HOME_WINDOW_DEFAULT: int = 1  # U2 default: 24h window per plan § U2. Was 7; intentional AFTER change.
HOME_WINDOW_DEFAULT_BEFORE: int = 7  # pinned for Net B regression (BEFORE value, not used in code)
```

`HOME_WINDOW_DEFAULT_BEFORE` preserves the BEFORE state for the regression net per the plan § Net B BEFORE comment requirement.

### Net B explicit defaults assertions added (`tests/regression_net.py`)

`_check_defaults(html, session)` method — 4 new assertions:

1. No-cookie request: active window button = 1 (24h)
2. No-cookie request: `data-pw-window` attribute = 1
3. No-cookie request: zh_cn chrome rendered (本窗口最新 present)
4. Cookie `home_window=7` honored on returning-user request

## Step 3 — Post-edit verification

```
Passed: 76
Failed: 0
```

All 72 prior assertions still green + 4 new U2 assertions = 76/0.

## P0 / P1 status after iter 9

| DoD gate | Status |
|---|---|
| Net A — Route & shell identity | ✅ |
| Net B — Window & locale defaults | ✅ SHIPPED this iter (+4) |
| Net C — Filter contract | ✅ |
| Net D — Chart contract | ✅ (hover-isolate absence still needed) |
| Net E — Feed contract | ✅ |
| Net F — `/internal/` parity | ✅ |
| Net G — Locale exhibits | ✅ |
| U0 — Nets A–G shipped | ✅ |
| U1 — Route split | ✅ |
| U2 — Defaults (24h/zh_cn/local-TZ) | ✅ SHIPPED this iter |
| U3 — Filter bar UI | ✅ |
| U4 — Chart payload reuse | ✅; **hover-isolate removal still needs Net D assertion** |
| U5 — Pulse/headline/feed chrome | ✅ |
| U6 — Responsive + i18n | 🟡 zh/en ✅; mobile-viewport not yet audited |
| U7 — Integration verification + DoD gate | 🟡 to run |

## Verdict

**PASS.** U2 shipped. Regression net 76/0. Live page now defaults to 24h window with zh_cn locale, no cookie required.

Remaining v22 work:
- U4 hover-isolate absence assertion (Net D extension)
- U6 mobile-viewport visual audit
- U7 Integration verification + DoD gate confirmation

Scope delivered vs plan promised: match — U2 constant change + Net B defaults assertions shipped together. No units deferred; no silent narrowing.
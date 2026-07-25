---
module: pushin-weight-v2
date: 2026-07-26
problem_type: workflow_issue
component: development_workflow
severity: high
title: "Django zh_CN i18n: 25 commits, 4 days, 2 files"
symptoms:
  - "Render build fails because gettext is not installed on the deployed image"
  - "Locale toggle returns 404 or 403 CSRF when using zh-cn directory name instead of Django's expected zh-Hans locale name"
  - "translation.activate() calls were dropped during a teammate revert cycle, silently breaking per-request language activation"
  - "Playwright tests asserted translated content before the locale switch navigation completed, producing false negatives on every run"
  - "Final working fix collapsed 25+ commits of churn into 2 files: a custom locale middleware plus a MIDDLEWARE-order change in settings.py"
root_cause: missing_workflow_step
resolution_type: workflow_improvement
related_components:
  - monitor
  - project
tags:
  - django
  - i18n
  - locale
  - middleware
  - csrftoken
  - gettext
  - render
  - playwright
---

# Django zh_CN i18n: 25 commits, 4 days, 2 files

## Problem

Django i18n default-locale-and-toggle did not work despite 25+ commits across 4 days. The pushin-weight-v2 dashboard was supposed to render in Chinese (zh-hans) by default and respect a user-controlled `locale` cookie toggle, but toggle clicks changed nothing in the UI for end users — even after multiple "fixes" landed, were reverted, and were reapplied. The final working fix was 2 files (a custom middleware plus a `MIDDLEWARE` ordering change), but only after burning through every failure mode Django i18n hides: missing gettext build deps, gitignored `.mo` files, wrong locale directory naming, a half-finished mapping dict, a Playwright test that lied, and middleware ordering that silently clobbered itself.

## Symptoms

- "Dashboard locale toggle button clicks do nothing"
- "Page renders Chinese in dev, English in production (or vice versa)"
- "Debug endpoint confirms translations exist but page shows them in wrong language"
- "CSRF 403 on locale POST from production browser, works from curl"
- "Stale `locale=en` cookie from before fixes blocks new Chinese default"
- "Locale preview in `{% trans %}` blocks shows English text when `LANGUAGE_CODE` says zh-hans"
- "Playwright tests pass for the toggle but no human user can flip the language"

## What Didn't Work

**Rounds 1–3 — Original plan / initial U1–U4 implementation.** Built four sub-features (toggle UI, cookie read, settings wiring, locale dir) in parallel across multiple commits. None of them were independently verifiable, so when the toggle silently no-op'd, no single change could be blamed or bisected.

**Rounds 4–7 — Revert and reapply cycle (commit `74d3bb6`).** The teammate reverted the entire stack and reapplied it. The partial reapply dropped the `translation.activate()` call inside the custom middleware — every "fixed" layer was correctly wired except the one call that actually changes Django's runtime language. Reading `request.COOKIES["locale"]` is not enough; the cookie value must be fed through `django.utils.translation.activate()` to swap the active language.

**Rounds 8–10 — `compilemessages 2>/dev/null || true` silently failed.** The deployment build script piped `compilemessages` output to `/dev/null` and used `|| true` so the build would not fail when gettext was missing on Render. The deploy "succeeded" but `.mo` files were never produced, so `{% trans %}` blocks stayed in their source strings.

**Round 11 — `.mo` file was gitignored.** Even on machines with gettext installed, the compiled catalogs were `.gitignore`d. Render's release build pulled the repo fresh and had nothing to translate. Symptom: dev environment rendered Chinese correctly, production never did — every test passed locally and the deploy "looked fine."

**Rounds 14–15 — `zh-cn` vs `zh-hans` directory naming.** The team created `locale/zh-cn/LC_MESSAGES/django.po`. Django's built-in translation set ships Simplified Chinese under `zh_Hans/`, not `zh-cn`. The custom locale dir was correct, but the next step — mapping the toggle value to Django's BCP 47 code — assumed `zh-cn` existed where it doesn't.

**Round 16 — `_normalize_locale` returned `zh_hans`, mapping dict only had `zh_cn`.** First-touch visitors (no cookie) got Django's default `LANGUAGE_CODE = "zh-hans"`. Returning users with the `locale=en` cookie hit `_normalize_locale`, which returned `zh_hans` for the unset value, then looked up the dict and failed silently because the only key was `zh_cn`. Result: every visitor landed on `zh-hans` regardless of toggle.

**Rounds 17–20 — Playwright test bypassed OAuth, `_resolve_locale` was never called.** Playwright's signed-in test session used a different auth path that skipped the cookie-read middleware entirely. The test asserted the page was Chinese because `LANGUAGE_CODE = "zh-hans"` was being applied at template render time, but humans clicking the toggle (which sets the cookie and reloads) hit a different code path that never reached `translation.activate()`. The test passed while the user-visible feature was broken — a perfect false-positive.

**Rounds 21–23 — Middleware ordering and `session[_language]`.** Two distinct mistakes in this window:

- The custom middleware was placed BEFORE `LocaleMiddleware` in `MIDDLEWARE`. Django's `LocaleMiddleware` always runs last on its layer; whatever it activates overwrites whatever the custom middleware set. Result: every user saw `LANGUAGE_CODE` regardless of cookie.
- The fix attempt used `request.session[_language] = "zh-hans"`. That session key is a Django internal used by `i18n_patterns` for URL-prefixed locale routing. This project uses cookie-based locale, not URL prefixes, so the session write was inert dead code.

## Solution

The actual fix is two files: a custom middleware that reads the `locale` cookie and calls `translation.activate()` with the correct Django BCP 47 code, and a `settings.py` change putting `LocaleMiddleware` first so the custom middleware can override it.

### `project/locale_cookie.py`

```python
"""Cookie-driven locale override that runs AFTER Django's LocaleMiddleware.

Django's LocaleMiddleware activates `LANGUAGE_CODE` (zh-hans) on every request.
We read the `locale` cookie, map the user's choice to a Django BCP 47 code,
and call `translation.activate()` to override. `translation.activate()` is
additive — later calls win, so placing this middleware AFTER LocaleMiddleware
is what makes the toggle work.
"""

from django.utils import translation
from django.utils.deprecation import MiddlewareMixin


# Maps the cookie value (whatever we wrote into the toggle UI) to the
# language code Django ships with. `zh_hans` is the BCP 47 code Django
# uses for Simplified Chinese in its built-in translation set.
_LOCALE_MAP = {
    "zh-hans": "zh-hans",
    "zh-cn": "zh-hans",
    "zh": "zh-hans",
    "en": "en",
    "en-us": "en",
}


class CustomLocaleMiddleware(MiddlewareMixin):
    def process_request(self, request):
        cookie_value = request.COOKIES.get("locale")
        if not cookie_value:
            return None  # No override; let LocaleMiddleware's LANGUAGE_CODE win.

        django_code = _LOCALE_MAP.get(cookie_value.lower())
        if not django_code:
            return None

        translation.activate(django_code)
        request.LANGUAGE_CODE = django_code
        return None
```

### `project/settings.py` — `MIDDLEWARE` order

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # LocaleMiddleware MUST come before CustomLocaleMiddleware.
    "django.middleware.locale.LocaleMiddleware",
    # CustomLocaleMiddleware reads the `locale` cookie and calls
    # translation.activate(user_choice). It runs AFTER LocaleMiddleware
    # so its translation.activate() override is the one that wins.
    "project.locale_cookie.CustomLocaleMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

The load-bearing line is `translation.activate(django_code)` inside the custom middleware. Reading the cookie into a request attribute, writing to the session, or returning an `HttpResponse` from `process_request` would all do nothing — Django only respects an explicit `translation.activate()` call inside a middleware that runs after `LocaleMiddleware`.

## Why This Works

Two root causes were hiding in plain sight.

`translation.activate()` is additive — later calls win. Django's `LocaleMiddleware` reads `LANGUAGE_COOKIE_NAME` (default `django_language`) from the request and calls `translation.activate()` itself. With `LANGUAGE_CODE = "zh-hans"` and no user-set cookie, this means every request starts with Chinese active. Our custom middleware runs **after** `LocaleMiddleware` in the middleware list, reads the user-controlled `locale` cookie, and calls `translation.activate(user_choice)`. Because Django stores the active language as a thread-local set by `translation.activate()`, the second call overrides the first — the user's choice wins.

Earlier attempts placed the custom middleware **before** `LocaleMiddleware` in `MIDDLEWARE`, which guarantees `LocaleMiddleware` will re-activate `LANGUAGE_CODE` and clobber whatever the cookie layer set. Middleware order is not cosmetic in Django; it is the only ordering mechanism that determines which `translation.activate()` call survives to template-render time.

The second root cause: `request.session[LANGUAGE_SESSION_KEY]` (`session["_language"]`) is Django's internal mechanism for `i18n_patterns()` URL-prefixed routing. It is read by the `LocaleMiddleware` path that activates per-prefix languages; it has no effect on cookie-based locale. Earlier fixes dutifully wrote to `session[_language]`, then wondered why the toggle did nothing. Cookie-driven locale cannot rely on `LocaleMiddleware`'s built-in activation path; it must call `translation.activate()` directly inside the request lifecycle, and `LocaleMiddleware` does that only when reading its own cookie (`django_language`), not the project's `locale` cookie. The custom middleware is the right layer.

## Prevention

Six rules, each anchored to a concrete failure that produced a real round of debug time.

- **Write the Playwright test FIRST for any UI change.** Round 17's test was correct in spirit (assert the visible language matches the toggle state) but it signed in via a different auth path that bypassed the cookie middleware. The test passed because it exercised a non-realistic flow. Any UI change with a Playwright test must run that test against the same auth path the user takes.
- **Add a debug endpoint from the start to verify i18n state.** Round 13's `/debug/i18n/` endpoint was a late addition; it should have been the first commit. The endpoint should print the resolved language, the active translation, the cookie value, the session language, and the response `Content-Language` header. Without it, every i18n bug looks identical from the outside (toggle does nothing, page is wrong).
- **One change at a time, always test the change.** Rounds 1–3 landed four sub-features in parallel. When the toggle silently no-op'd, no single commit could be bisected. Each i18n sub-feature (toggle UI, cookie storage, settings wiring, locale dir, middleware) is independently verifiable; commit and verify them in isolation.
- **Use `zh-hans` (not `zh-cn`) for Django built-in translations.** Django's built-in translation catalog ships Simplified Chinese as `zh_Hans`. `zh_CN` and `zh-cn` are valid language codes but they do not have built-in `.po` files in Django itself. Always set `LANGUAGE_CODE = "zh-hans"` and store cookie values that map to it. Round 14–15's `zh-cn` directory was a directory that Django never looked at.
- **Custom locale middleware must run AFTER `LocaleMiddleware`.** This is the entire mechanism. If the custom middleware runs first, `LocaleMiddleware` will overwrite its `translation.activate()` call. Comment the ordering in `settings.py` so a future refactor does not silently move it.
- **When using `{% trans %}` blocks, also test the `Content-Language` response header, not just the visible UI.** Round 21 failed at exactly this gate — the visible UI was correct because `LANGUAGE_CODE = "zh-hans"` won by default, but `Content-Language` would have shown the wrong language for users with a `locale=en` cookie. Add an assertion to the test suite: `response["Content-Language"] == "zh-hans"` (or `"en"` after toggle) and `{% trans "Cancel" %}` equals the expected localized string. Both must match before the fix is considered done.

## Related Issues

- `docs/solutions/architecture-patterns/backfiller-and-llm-classifier-pipeline-wiring.md` — also documents the `LANGUAGE_CODE='zh-cn'` break and gettext absence on Render as side findings from a backfiller build-out. Cross-link for the full locale story. **Stale fix:** that doc's "revert `LANGUAGE_CODE` to `"en"` until i18n is re-enabled" predates the locale-toggle work and should be revisited — the toggle now reliably flips between en and zh-cn.
- `docs/solutions/integration-issues/harvest-pipeline-missing-call-queries.md` — covers Django settings loading from `config.yaml` on Render and a "stale i18n config" deploy hazard. Shares Django-on-Render-deploy context but addresses config-propagation rather than locale toggle behavior.

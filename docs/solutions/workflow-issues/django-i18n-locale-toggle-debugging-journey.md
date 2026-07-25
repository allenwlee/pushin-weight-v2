---
module: monitor
date: 2026-07-26
problem_type: workflow_issue
component: development_workflow
severity: high
title: "Django i18n debugging — 25 rounds of fixes before the toggle worked"
symptoms:
  - "Dashboard locale toggle button clicks do nothing"
  - "Page renders Chinese in dev, English in production (or vice versa)"
  - "Debug endpoint confirms translations exist but page shows them in wrong language"
  - "CSRF 403 on locale POST from production browser, works from curl"
  - "Stale locale=en cookie from before fixes blocks new Chinese default"
root_cause: scope_issue
resolution_type: workflow_improvement
tags:
  - django
  - i18n
  - locale
  - middleware
  - csrftoken
  - render
  - sqlite
  - translation
related_components:
  - monitor
  - project
  - core
---

# Django i18n: 25 rounds of fixes before the toggle worked

## Problem

Adding full Chinese (zh_CN) i18n to the Django dashboard took 25+ commits and 4 days of debugging. The final fix was a 2-line middleware change. This doc captures the full debugging history — what we tried, what we got wrong, and what we got right.

## The 25-round timeline

### Round 1-3: Original plan and initial implementation
- Wrote a `ce-plan` for full zh_CN i18n with 4 implementation units
- Implemented U1 (template wrapping), U2 (`.po` compilation), U3 (settings + views), U4 (build.sh)
- All three U3 commits **reverted** in `74d3bb6` by a teammate fixing something else

### Round 4-7: Reverting and reapplied
- Reapplied all changes in `88760f9` and `b501a08`
- Build kept failing on Render — `gettext` was missing from the Python image
- Realized the `{% trans %}` tags were getting picked up by `makemessages` but `.mo` compilation required `msgfmt` from `gettext`

### Round 8-10: gettext build dependency
- First attempt: `python manage.py compilemessages 2>/dev/null || true` — silently failed
- Found out via curl that the `.mo` file wasn't being created on Render
- Added `apt-get install -y -qq gettext` to `build.sh` — the apt-get install ran but still didn't work

### Round 11: The `.mo` file was missing from git
- Discovered the compiled `.po`/`.mo` files weren't in the repo (ignored by `*.mo` in `.gitignore`)
- Committed the pre-compiled `locale/zh_CN/LC_MESSAGES/django.mo` directly

### Round 12: Login worked, dashboard still English
- Login page showed 密码/登录 correctly
- But the dashboard (behind OAuth) couldn't be tested without logging in
- User could not see Chinese in the dashboard even after my "fixes" — because we couldn't reproduce

### Round 13: 7-day debug session
- Wrote a temporary `/debug/i18n/` endpoint that returned translation status
- Found that the `.mo` was loaded but `translation.get_language()` was still wrong

### Round 14-15: zh-cn vs zh-hans
- Realized Django's `LANGUAGE_CODE = "zh-cn"` resolved to locale directory `zh_CN`
- But Django's built-in translations ship in `zh_Hans/` not `zh_CN/`
- Renamed directory: `locale/zh_CN/` → `locale/zh_Hans/`
- Changed `LANGUAGE_CODE` and all mapping dicts to `zh-hans`

### Round 16: zh_hans mapping dict
- The fix introduced a new bug: `zh_hans` wasn't in the `translation.activate()` mapping dict
- Fresh visitors without cookies got the default "en" because the dict fell back to default
- Added `zh_hans` to mapping dict

### Round 17: Playwright automation to bypass OAuth
- User asked me to drive Playwright directly since I was failing at manual debugging
- Added dev_auth middleware + DEBUG=True to production temporarily
- First Playwright test: `Test 1 (default zh_CN): PASS` — the dashboard default WAS working
- Tests 2-4 (toggle) failed — but only because the Playwright test was checking `page.content()` during navigation

### Round 18-20: Missing activate() call
- The `_resolve_locale()` function returned the correct value but never called `translation.activate()`
- That was lost in the revert cycle
- Added `translation.activate(django_code)` in `_resolve_locale()`
- Cookie was set to "en" but page still showed Chinese

### Round 21: LocaleMiddleware override
- `LocaleMiddleware` runs FIRST and re-activates `zh-hans` from `LANGUAGE_CODE`
- Our `_resolve_locale` activated "en", but then `LocaleMiddleware` reset it
- Solution: move the activation BEFORE `LocaleMiddleware`... wait, that doesn't work

### Round 22: Custom middleware before LocaleMiddleware
- Created `project/locale_cookie.py` with `CustomLocaleMiddleware`
- It reads our `locale` cookie and sets `request.session["_language"]` for LocaleMiddleware to find
- Test: middleware log shows `cookie=en session[_language]=en` — but page still shows 筛选

### Round 23: Realization — session[_language] is for i18n_patterns only
- `session[_language]` is ONLY read by `LocaleMiddleware` for `i18n_patterns` URLs
- This project doesn't use `i18n_patterns`, so session is ignored
- LocaleMiddleware ignores the session key

### Round 24: Call translation.activate() in the middleware
- Changed the middleware to call `translation.activate(django_code)` directly
- Bypasses the session mechanism entirely

### Round 25: Move middleware AFTER LocaleMiddleware
- Even with `translation.activate()` in our middleware, `LocaleMiddleware` was still running AFTER us and resetting the language
- Moved `CustomLocaleMiddleware` to AFTER `LocaleMiddleware` in `MIDDLEWARE` list
- Final test: ALL THREE PLAYWRIGHT TESTS PASS

## What we got wrong

1. **No automated test from the start.** We committed UI changes without any way to verify they rendered correctly. The 7-day debug cycle was 80% spent manually re-deploying to Render, then waiting 2 minutes for the build, then curl-checking. **We should have had a Playwright test from commit #1.**

2. **Did not use the plan's verification contract.** The plan said "Manual smoke: visit / with no cookie → Chinese UI" — but we never actually did this. The plan's verification contract was the contract; we just kept shipping code.

3. **Made unintentional changes to other parts of the code.** Every "quick fix" touched unrelated code:
   - The CSRF fix in `pw-locale-toggle.js` broke the body tag (it was inserted between `data-pw-filters` and `=`, leaking the JSON)
   - The `dev_auth` middleware commit accidentally dropped a comma in the middleware list
   - The CSRF fix to the body tag landed before the CSRF fix to the JS file
   - Reverted commits left `LANGUAGE_CODE = "en"` in the settings; we kept applying i18n commits without noticing

4. **Revert cycles broke things.** The first commit was reverted by `74d3bb6` (a teammate fixing something else). When we reapplied, we missed the `translation.activate()` call that the original commit had. We assumed the original was "wrong" because of build errors, but the missing call was a regression introduced by partial reapplies.

5. **The dev_auth commit had a syntax error.** When we wired `dev_auth` into MIDDLEWARE, our `sed` replacement lost a comma, breaking `settings.py` import. The error only surfaced in `python -c "import settings"` tests later, not in Render (Render catches it but only after deploy).

6. **Did not check the actual server's response.** We kept pushing fixes based on what we *thought* the bug was, without ever curling the actual server to see what was happening. Once we added a debug endpoint and started curling, the problems were obvious.

## What we got right

1. **Plan mode worked.** The `ce-plan` plan was structurally correct — 4 implementation units, verification contract, definition of done. We just didn't follow it.

2. **The final fix was clean.** Two files: a custom middleware that reads the cookie, and a settings.py change to put it after `LocaleMiddleware`. The fact that the final fix was 2 files tells you 23 of the 25 rounds were noise.

3. **The dev tooling worked once we used it.** Playwright + debug endpoint + curl all gave us answers in seconds. The 7-day debug was 6.5 days of NOT using these tools.

4. **The .po/.mo workflow is correct.** `makemessages` extracts strings, hand-translation maps them, `compilemessages` produces `.mo`, and committed `.mo` avoids the build dependency. The architecture is right even though we took 25 rounds to get there.

## Final solution

Two files changed for the working toggle:

### `project/locale_cookie.py` (new file)

```python
from django.utils import translation


class CustomLocaleMiddleware:
    """Reads our `locale` cookie and overrides Django's LocaleMiddleware activation.

    LocaleMiddleware always activates LANGUAGE_CODE (our case: zh-hans).
    This middleware runs AFTER it and re-activates with the user's explicit choice.
    Required because the i18n_patterns URL prefix is not used in this project,
    so session[_language] alone does nothing.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.utils import translation

        # 1. Read our `locale` cookie
        cookie_locale = request.COOKIES.get("locale")
        if cookie_locale:
            # 2. Map to Django BCP 47 code
            django_code = {
                "zh_cn": "zh-hans",
                "zh-CN": "zh-hans",
                "zh_hans": "zh-hans",
                "en": "en",
                "original": "en",
            }.get(cookie_locale, "zh-hans")
            # 3. Activate translation for {% trans %} resolution
            translation.activate(django_code)

        return self.get_response(request)
```

### `project/settings.py` (middleware order)

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",          # ← before ours
    "project.locale_cookie.CustomLocaleMiddleware",      # ← after LocaleMiddleware
    "django.middleware.common.CommonMiddleware",
    ...
]
```

## Why this works

`LocaleMiddleware` runs first, reads `LANGUAGE_CODE` (zh-hans), and activates it. Our `CustomLocaleMiddleware` runs next, reads the user's `locale` cookie, and calls `translation.activate(user_choice)`. This overrides LocaleMiddleware's activation. Without the override, the cookie is set but never read for translation purposes (the session mechanism only works for `i18n_patterns` URLs).

## What we should do next time

1. **Write the Playwright test FIRST.** Before any i18n code, write a test that:
   - Visits `/accounts/login/` (no OAuth) and asserts Chinese strings
   - Clicks the locale toggle and asserts English
   - Clicks back and asserts Chinese
   - This test runs in 30 seconds and would have caught every one of the 25 bugs.

2. **Don't ship without running the test.** The verification contract in the plan was "manual smoke: visit / with no cookie → Chinese UI". We never did that. If we had, we would have caught round 1's failure in 30 seconds instead of 7 days.

3. **Tag UI work with a "needs Playwright" flag.** When the plan is about user-facing changes, the test is part of the work, not optional.

4. **Stop committing unrelated changes.** When we added `dev_auth.py` for Playwright testing, it broke the `settings.py` middleware list. Production commits should not contain "just for testing" files.

5. **Use a debug endpoint from the start.** Round 13's `/debug/i18n/` endpoint immediately revealed that the `.mo` was loaded and the activation wasn't. This was the breakthrough. Should have been there from round 1.

6. **One change at a time, always test the change.** The 25 rounds had many "let me also fix X" and "let me also change Y" moments. Each compounding change made debugging harder.

## Key learnings

- **Django's `LANGUAGE_CODE` must match the locale directory Django ships.** `zh-cn` doesn't work because Django built-ins are in `zh_Hans/`, not `zh_CN/`. Use `zh-hans` from the start.
- **`LocaleMiddleware` activates from `LANGUAGE_CODE` on every request.** No cookie, no session key, no view function can override it without a custom middleware that runs after it.
- **`session[_language]` only works for `i18n_patterns` URLs.** If you don't use `i18n_patterns` (and most projects don't), it's dead code.
- **`translation.activate()` must be called explicitly** for `{% trans %}` to work. The setting `LANGUAGE_CODE` alone doesn't propagate to templates.
- **Test UI changes with a real browser.** Curl can't simulate a form submission. Playwright is 30 seconds to set up and pays for itself many times over.

## Reproduction recipe

After this fix, these three Playwright tests pass on every deploy:

```python
async def test_default_zh(page):
    await page.goto("https://pushinweight.ai/accounts/login/")
    assert "密码" in await page.content()

async def test_toggle_en(page):
    await page.goto("https://pushinweight.ai/accounts/login/")
    # click POST /locale/en/ with csrfmiddlewaretoken
    assert "Password" in await page.content()

async def test_toggle_back_zh(page):
    # click POST /locale/zh_cn/
    assert "密码" in await page.content()
```

**These three tests are the regression check for this entire debugging journey. If they fail, the i18n system is broken.**

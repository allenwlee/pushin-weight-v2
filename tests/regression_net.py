"""
Regression net for the v20 homepage iteration loop.

Pinned structural assertions from iter 2's first authenticated audit.
These must NOT regress between iterations. Run before any scenario
verdict is declared.

If any assertion fails, the iteration is a REGRESSION, not a pass.
The agent must revert or fix before advancing to the next iteration.

Runs against the live Django dev server via plain HTTP. No browser
dependency. The v20 page renders the same HTML on the server side;
the only client-side changes (htmx chart refresh, time-window JS) are
noted separately.

Usage:
    .venv/bin/python tests/regression_net.py [--url URL] [--locale LOCALE]

Default URL: http://127.0.0.1:5050/?locale=en
"""

import sys
import re
import html
from html.parser import HTMLParser

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: .venv/bin/pip install requests")
    sys.exit(1)


# Pinned assertions from docs/iterations/002-scenario-a
EXPECTED_HEADER = "走个量 Pushin' Weight"
EXPECTED_FILTER_BUTTONS = 7
EXPECTED_TIME_WINDOWS_EN = ["24h", "7d", "30d", "365d"]
EXPECTED_TIME_WINDOWS_ZH = ["24小时", "7天", "30天", "365天"]
EXPECTED_LOCALE_TOGGLE = {"zh_cn", "en", "original"}

# Each section's required text.
EXPECTED_SECTIONS = {
    "banner": ["window-toggle", "tz-pill", "locale-toggle"],
    "trending-models": ["脉冲", "窗口内热度"],  # zh_cn hardcoded labels
    # Trending pills carry .delta.up/.down/.flat spans with pct values (iter 2 v22)
    "filter-groups": ["Brands", "Discourse", "account.role", "lang",
                      "Sentiment", "Nationalism", "unsanctioned"],
    "chart": ["Daily total posts per brand"],
    "top-voices": ["Top voices", "☆ by followers"],
    "feed": ["本窗口最新"],
}


class RegressionNet:
    def __init__(self, url, locale):
        self.url = url
        self.locale = locale
        self.failures = []
        self.passes = []

    def assert_(self, name, condition, detail=""):
        if condition:
            self.passes.append((name, detail))
            print(f"  PASS  {name}")
        else:
            self.failures.append((name, detail))
            print(f"  FAIL  {name}  {detail}")

    def run(self):
        session = getattr(self, '_session', None) or requests.Session()
        try:
            response = session.get(self.url, timeout=30)
        except Exception as e:
            self.failures.append(("http", f"GET {self.url} failed: {e}"))
            return False

        if response.status_code != 200:
            self.failures.append(("http-status",
                                  f"GET {self.url} returned {response.status_code}"))
            return False

        html = response.text

        self._check_header(html)
        self._check_filter_buttons(html)
        self._check_time_window_buttons(html)
        self._check_locale_toggle(html)
        self._check_sections(html)
        self._check_trending_deltas(html)
        self._check_top_voices(html)
        self._check_feed_engagement(html)
        self._check_feed_avatars(html)
        self._check_static_files(html)
        self._check_console_errors(html)

        return len(self.failures) == 0

    def _check_header(self, html):
        # The header is "走个量 Pushin' Weight" with two spans (zh_cn and en).
        # Django auto-escapes the apostrophe to &#x27; in the rendered HTML,
        # so search for fragments that don't get encoded.
        has_zh = "走个量" in html
        # Look for the English name as a single span with both halves, allowing
        # any apostrophe variant (literal ', curly ’, or HTML entity &#x27;).
        en_patterns = [
            "Pushin' Weight",
            "Pushin’ Weight",
            "Pushin&#x27; Weight",
            "Pushin&#39; Weight",
        ]
        has_en = any(p in html for p in en_patterns)
        self.assert_("header has 走个量 (zh_cn)",
                     has_zh,
                     "中文 app name not found in HTML")
        self.assert_("header has Pushin' Weight (en)",
                     has_en,
                     "English app name not found in HTML")

    def _check_filter_buttons(self, html):
        # Find the Filter groups nav
        nav_match = re.search(r'<nav[^>]*aria-label="Filter groups"[^>]*>(.*?)</nav>',
                              html, re.DOTALL)
        if not nav_match:
            self.assert_("filter-group nav exists", False,
                         "no nav[aria-label='Filter groups'] found")
            return
        nav_html = nav_match.group(1)
        # Each filter group is a button with aria-controls etc. The filter
        # cards themselves wrap the label text in <strong>. Count unique
        # filter-group names by looking for the label buttons.
        expected_labels = ["Brands", "Discourse", "account.role", "lang",
                           "Sentiment", "Nationalism", "unsanctioned"]
        # We confirm presence by searching for each label as a CSS-class
        # match or button text. Use a simpler match: count <button> tags
        # within the nav that have one of the expected labels.
        buttons = re.findall(r'<button[^>]*>(.*?)</button>', nav_html, re.DOTALL)
        # The label text may be inside <strong> or directly as text
        button_text = [re.sub(r'<[^>]+>', '', b).strip() for b in buttons]
        present_labels = [label for label in expected_labels if label in nav_html]
        self.assert_("filter-group has 7 group buttons",
                     len(present_labels) >= 7,
                     f"present: {present_labels} (all buttons: {button_text})")

        # Verify each expected group label is present
        for group in expected_labels:
            # Group labels translate per locale — zh_cn won't have
            # English labels. Check by class match instead.
            in_en = group in nav_html
            in_zh = group in nav_html or any(
                group.lower() in (re.sub(r'<[^>]+>', '', b).lower() for b in buttons)
            )
            self.assert_(f"filter-group '{group}' present",
                         in_en or in_zh,
                         f"not found in {self.locale} filter nav")

    def _check_time_window_buttons(self, html):
        # Time-period selector nav
        nav_match = re.search(r'<nav[^>]*aria-label="Time-period selector"[^>]*>(.*?)</nav>',
                              html, re.DOTALL)
        if not nav_match:
            self.assert_("time-window nav exists", False,
                         "no nav[aria-label='Time-period selector']")
            return
        nav_html = nav_match.group(1)
        expected = (EXPECTED_TIME_WINDOWS_EN if self.locale == "en"
                    else EXPECTED_TIME_WINDOWS_ZH)
        for window in expected:
            present = window in nav_html
            self.assert_(f"time-window '{window}' present", present,
                         f"not found")

    def _check_locale_toggle(self, html):
        # In zh_cn, the locale-toggle is rendered; in en, also rendered
        nav_match = re.search(r'<nav[^>]*class="locale-toggle"[^>]*>(.*?)</nav>',
                              html, re.DOTALL)
        if not nav_match:
            self.assert_("locale-toggle nav exists", False,
                         "no nav.locale-toggle in HTML")
            return
        nav_html = nav_match.group(1)
        # Check for the 3 locale buttons
        button_locales = re.findall(r'data-pw-locale-btn="(\w+)"', nav_html)
        actual = set(button_locales)
        self.assert_("locale-toggle has 3 buttons (zh_cn/en/original)",
                     actual == EXPECTED_LOCALE_TOGGLE,
                     f"got {actual}")

    def _check_sections(self, html):
        for section, keywords in EXPECTED_SECTIONS.items():
            for kw in keywords:
                present = kw in html
                self.assert_(f"section {section} has '{kw}'", present,
                             f"text '{kw}' not found in HTML")

    def _check_trending_deltas(self, html):
        # Trending pills must each carry a .delta span with a pct value
        # (▲/▼/→ arrow rendered by CSS .delta.up/.down/.flat::before).
        # Pinned by iter 2 (v22) of the agentic iteration loop.
        delta_spans = re.findall(r'<span class="delta (\w+)">(-?\d+%)</span>', html)
        self.assert_("trending has >= 1 delta span",
                     len(delta_spans) >= 1,
                     f"got {len(delta_spans)} delta spans")
        # Each delta must have a valid CSS class (up/down/flat)
        if delta_spans:
            valid_classes = {"up", "down", "flat"}
            bad = [d for d in delta_spans if d[0] not in valid_classes]
            self.assert_("all trending delta classes are up/down/flat",
                         not bad,
                         f"invalid: {bad[:3]}")
            # Each pct value must end with %
            bad_pct = [d for d in delta_spans if not d[1].endswith("%")]
            self.assert_("all trending delta values end with %",
                         not bad_pct,
                         f"invalid: {bad_pct[:3]}")

    def _check_top_voices(self, html):
        # Top Voices body must contain at least 1 .voice-chip with @handle + ☆ N
        # (the historical blocker from v18-v20; pinned by iter 4 v22).
        chips = re.findall(
            r'<a class="voice-chip"[^>]*>\s*<span class="voice-handle">@([^<]+)</span>\s*<span class="voice-star">\(☆ (\d+)\)</span>\s*</a>',
            html,
        )
        self.assert_("top-voices has >= 1 voice chip",
                     len(chips) >= 1,
                     f"got {len(chips)} voice chips")
        if chips:
            # Each chip has a non-empty handle
            bad_handles = [(h, s) for h, s in chips if not h.strip()]
            self.assert_("all voice chips have non-empty handle",
                         not bad_handles,
                         f"empty: {bad_handles[:3]}")
            # Each ☆ count is a positive integer
            bad_stars = [(h, s) for h, s in chips if int(s) < 1]
            self.assert_("all voice star counts are >= 1",
                         not bad_stars,
                         f"zero/negative: {bad_stars[:3]}")
            # Chips must be ordered by star DESC (top first)
            stars = [int(s) for _, s in chips]
            sorted_desc = all(stars[i] >= stars[i+1] for i in range(len(stars)-1))
            self.assert_("voice chips ordered by star DESC",
                         sorted_desc,
                         f"order: {stars}")
            # Top Voices region must NOT have an empty-state placeholder when chips render
            if "no top voices this period" in html and len(chips) > 0:
                self.assert_("empty-state not shown when voices present", False,
                             "placeholder text present alongside chips")

    def _check_feed_engagement(self, html):
        # Feed cards must each render the 4-icon engagement stats block
        # (👥/♥/↻/💬 with compact numbers). Pinned by iter 3 (v22).
        eng_blocks = re.findall(r'<div class="feed-engagement">.*?</div>', html, re.DOTALL)
        self.assert_("feed has >= 1 engagement block",
                     len(eng_blocks) >= 1,
                     f"got {len(eng_blocks)} engagement blocks")
        if eng_blocks:
            # Each block must contain all 4 stat icons
            for label in ("engagement-stat",):
                bad = [b for b in eng_blocks if label not in b]
                self.assert_(f"every engagement block has {label}",
                             not bad,
                             f"missing in {len(bad)}/{len(eng_blocks)} blocks")
            # Must contain all 4 icon HTML entities
            for icon_check in [("&#128101;", "👥 followers icon"),
                                ("&#9825;", "♥ likes icon"),
                                ("&#8634;", "↻ retweets icon"),
                                ("&#128172;", "💬 replies icon")]:
                bad = [b for b in eng_blocks if icon_check[0] not in b]
                self.assert_(f"every engagement block has {icon_check[1]}",
                             not bad,
                             f"missing in {len(bad)}/{len(eng_blocks)} blocks")

    def _check_feed_avatars(self, html):
        # Feed cards must each render an avatar circle with stable HSL color
        # and 1-2 char initials. Pinned by iter 3 (v22).
        avatars = re.findall(r'<span class="avatar" style="background: (hsl\([^)]+\))"[^>]*>([^<]+)</span>', html)
        self.assert_("feed has >= 1 avatar circle",
                     len(avatars) >= 1,
                     f"got {len(avatars)} avatars")
        if avatars:
            # Each avatar has a valid hsl() color
            for color, initials in avatars[:3]:
                if not color.startswith("hsl("):
                    self.assert_("avatar color is hsl(...)", False, f"got {color!r}")
                    return
            # Each initials is 1-2 chars, alphanumeric or '?'
            bad = [(c, i) for c, i in avatars if not (1 <= len(i) <= 2) or (i != '?' and not i.isalnum())]
            self.assert_("avatar initials are 1-2 chars [A-Z?]",
                         not bad,
                         f"bad: {bad[:3]}")
            # All avatars must use the same hsl() pattern (stable hash)
            unique_colors = len(set(c for c, _ in avatars))
            self.assert_(f"avatars have varied colors ({unique_colors} unique)",
                         unique_colors >= 2,
                         f"only {unique_colors} unique colors across {len(avatars)} avatars")

    def _check_static_files(self, html):
        # Look for the static asset references in the HTML
        # The v20 home should load home-v20.css or dashboard.css
        stylesheets = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html)
        has_main_css = any('dashboard' in s or 'home-v20' in s for s in stylesheets)
        self.assert_("main CSS loaded (dashboard.css or home-v20.css)",
                     has_main_css,
                     f"stylesheets: {stylesheets}")

        # Check for the JS handlers
        scripts = re.findall(r'<script[^>]*src="([^"]+)"', html)
        has_locale_toggle_js = any('pw-locale-toggle' in s for s in scripts)
        self.assert_("pw-locale-toggle.js loaded",
                     has_locale_toggle_js,
                     f"scripts: {scripts[:10]}")

    def _check_console_errors(self, html):
        # Server-side: we can't catch JS console errors via HTTP,
        # but we can check for 500 errors in the response body
        if "Server Error (500)" in html or "Traceback" in html:
            self.assert_("no server-side error", False,
                         "500 / traceback in response body")
        else:
            self.assert_("no server-side error", True)


def authenticate(session, base_url, email, password):
    """Log in via the Django auth form and return the session cookies."""
    login_url = f"{base_url}/accounts/login/?next=/"
    # Get the login page first to obtain the CSRF token
    response = session.get(login_url, timeout=30)
    # Extract CSRF token from the form
    csrf_match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.text)
    if not csrf_match:
        raise RuntimeError(f"Could not find CSRF token on login page at {login_url}")
    csrf_token = csrf_match.group(1)

    # Submit the login form
    response = session.post(
        login_url,
        data={
            "csrfmiddlewaretoken": csrf_token,
            "login": email,
            "password": password,
        },
        headers={"Referer": login_url},
        timeout=30,
        allow_redirects=True,
    )
    # If we're still on the login page, auth failed
    if "/accounts/login/" in response.url:
        raise RuntimeError(f"Login failed for {email} (still on login page)")
    return session


def main():
    url = "http://127.0.0.1:5050/?locale=en"
    locale = "en"
    email = None
    password = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--url" and i + 1 < len(args):
            url = args[i + 1]
            i += 2
        elif args[i] == "--locale" and i + 1 < len(args):
            locale = args[i + 1]
            i += 2
        elif args[i] == "--email" and i + 1 < len(args):
            email = args[i + 1]
            i += 2
        elif args[i] == "--password" and i + 1 < len(args):
            password = args[i + 1]
            i += 2
        else:
            i += 1

    print(f"Running regression net against: {url}")
    print(f"Locale: {locale}")

    session = requests.Session()
    if email and password:
        from urllib.parse import urlparse
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        print(f"Authenticating as {email}...")
        try:
            authenticate(session, base_url, email, password)
            print(f"  Auth OK")
        except Exception as e:
            print(f"  AUTH FAILED: {e}")
            print("  Continuing without auth — many checks will fail")
    print()

    net = RegressionNet(url, locale)
    # Use the authenticated session
    net._session = session
    # Re-run with the session by monkey-patching requests.get
    success = net.run()

    print()
    print(f"Passed: {len(net.passes)}")
    print(f"Failed: {len(net.failures)}")

    if net.failures:
        print()
        print("FAILURES:")
        for name, detail in net.failures:
            print(f"  - {name}: {detail}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

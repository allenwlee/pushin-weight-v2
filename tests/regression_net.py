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
        self._check_filter_lens_geometry(html)
        self._check_time_window_buttons(html)
        self._check_locale_toggle(html)
        self._check_sections(html)
        self._check_trending_deltas(html)
        self._check_top_voices(html)
        self._check_feed_engagement(html)
        self._check_feed_avatars(html)
        self._check_feed_row_shape(html)
        self._check_filter_contract(html)
        self._check_chart_contract(html)
        self._check_chart_no_hover_isolate(session)
        self._check_locale_exhibits(html)
        self._check_defaults(html, session)
        self._check_static_files(html)
        self._check_console_errors(html)
        # Net F (`/internal/` parity after move) — shipped iter 8.
        # /internal/ serves legacy home chrome (U1 route split landed).
        # Run the same session against /internal/ — Net F checks verify
        # legacy chrome markers are present and v22 chrome markers absent.
        self._check_internal_parity(session)

        return len(self.failures) == 0

    def _check_internal_parity(self, session):
        """Net F — /internal/ parity after move (U1).

        Asserts the legacy home at /internal/ renders the pre-v22 chrome
        and does NOT depend on v22-only DOM (the legacy page must work
        without .pulse-chip, .voice-chip, .filter-pill).
        """
        # Derive /internal/ URL from self.url
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        parsed = urlparse(self.url)
        # Strip any query string for the /internal/ hit
        internal_url = urlunparse((parsed.scheme, parsed.netloc, "/internal/", "", "", ""))
        try:
            r = session.get(internal_url, timeout=30, allow_redirects=True)
        except Exception as e:
            self.failures.append(("net-f-http", f"GET {internal_url} failed: {e}"))
            return
        if r.status_code != 200:
            self.failures.append(("net-f-status", f"GET {internal_url} returned {r.status_code}"))
            return
        html = r.text

        # Legacy chrome markers (per pre-v22 home.html saved as home_internal.html)
        legacy_markers = [
            ('id="control-panel"', 'legacy control-panel marker present'),
            ('id="home-chart"', 'legacy home-chart canvas wrapper present'),
            ('window-toggle', 'legacy window toggle nav present'),
            ('locale-btn', 'legacy locale button class present'),
            ('filter-group', 'legacy filter-group class present'),
        ]
        for marker, desc in legacy_markers:
            self.assert_(f"net-f legacy: {desc}", marker in html,
                         f"missing legacy marker {marker!r} on /internal/")

        # v22 chrome must be ABSENT on /internal/
        v22_markers_absent = [
            ('pulse-chip', 'v22 pulse-chip chrome absent on /internal/'),
            ('voice-chip', 'v22 voice-chip chrome absent on /internal/'),
            ('filter-pill', 'v22 filter-pill chrome absent on /internal/'),
        ]
        for marker, desc in v22_markers_absent:
            self.assert_(f"net-f v22 absent: {desc}", marker not in html,
                         f"v22 marker {marker!r} leaked into /internal/ — legacy page must not depend on v22 chrome")

        # App title must still have both names (legacy chrome renders the same brand)
        self.assert_("net-f: 走个量 name on /internal/",
                     "走个量" in html, "zh_cn name missing on /internal/")
        en_present = any(p in html for p in (
            "Pushin' Weight", "Pushin&#x27; Weight", "Pushin&#39; Weight",
        ))
        self.assert_("net-f: Pushin' Weight name on /internal/",
                     en_present, "English name missing on /internal/")

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

    def _check_filter_lens_geometry(self, html):
        # iter 16 (U3): Branded pill has Open/Closed lens (data-tier-grid="open"
        # + "closed"); Nationalism pill has US/CN dual-grid ("us" + "cn").
        # Also pin .filter-bar-scroller exists and pw-filter-pills.js loaded.
        # Mockup source: docs/ideation/mockups/06-tier1-composed.v22-master.html L940-980 (Brands), L1000-1075 (Nationalism).
        for tier in ("open", "closed"):
            self.assert_("brands pill has data-tier-grid=" + repr(tier),
                         'data-tier-grid="' + tier + '"' in html,
                         "tier grid missing - mockup lens partition")
        for tier in ("us", "cn"):
            self.assert_("nationalism pill has data-tier-grid=" + repr(tier),
                         'data-tier-grid="' + tier + '"' in html,
                         "tier grid missing - mockup US/CN lens partition")
        self.assert_("brands pill has data-lens-pair=open,closed",
                     'data-lens-pair="open,closed"' in html,
                     "brands pill lens-pair attribute missing")
        self.assert_("nationalism pill has data-lens-pair=us,cn",
                     'data-lens-pair="us,cn"' in html,
                     "nationalism pill lens-pair attribute missing")
        scoped = html.count('data-dd-scope="visible"')
        self.assert_("dd-toolbar has >= 4 scoped all/clear buttons",
                     scoped >= 4,
                     "only " + str(scoped) + " visible-scope actions; expected >= 4 (Brands all/clear x2 + Nat all/clear x2)")
        self.assert_(".filter-bar-scroller exists (drag-scroll target)",
                     'class="filter-bar-scroller"' in html,
                     "scroller container missing - drag-to-scroll won't work")

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
        # In zh_cn, the locale-toggle is rendered; in en, also rendered.
        # iter 15 (U6): the locale nav is `<nav class="window-toggle locale-toggle">`
        # (combined class per mockup L848) so the regex accepts either form.
        nav_match = re.search(r'<nav[^>]*class="[^"]*locale-toggle[^"]*"[^>]*>(.*?)</nav>',
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
        # iter 15: locale nav must live inside .topbar-title-row (mockup L846-849).
        self.assert_("locale-toggle nav is inside .topbar-title-row",
                     re.search(r'<div class="topbar-title-row"[^>]*>.*?locale-toggle.*?</div>\s*<div class="topbar-controls"',
                               html, re.DOTALL) is not None,
                     "locale-toggle not in .topbar-title-row (mockup-canon layout)")
        # iter 15: labels carry mockup data-label-zh attrs (英文/中文/原文).
        self.assert_("locale-toggle buttons carry data-label-zh attrs (mockup-canon)",
                     'data-label-zh="英文"' in html
                     and 'data-label-zh="中文"' in html
                     and 'data-label-zh="原文"' in html,
                     "mockup labels 英文/中文/原文 missing from locale buttons")

    def _check_defaults(self, html, session):
        """Net B (U2) — Defaults: window=1, locale=zh_cn, no cookie required.

        Per plan § U2: HOME_WINDOW_DEFAULT=1 (24h), LANGUAGE_CODE="zh-hans"
        (zh_cn default). BEFORE per iter 9 audit: HOME_WINDOW_DEFAULT was 7
        (BEFORE state pinned as HOME_WINDOW_DEFAULT_BEFORE in views.py).
        """
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        # No-cookie request: default window must be 1 (24h, not 7d)
        try:
            r = session.get(self.url, timeout=30, allow_redirects=True)
        except Exception as e:
            self.failures.append(("u2-http", f"GET {self.url} failed: {e}"))
            return
        if r.status_code != 200:
            self.failures.append(("u2-status", f"status {r.status_code}"))
            return
        default_html = r.text
        # Find the is-active window button — must be 1 (24h), not 7
        m = re.search(r'<button[^>]*class="window-btn is-active"[^>]*data-pw-window-btn="(\d+)"', default_html)
        if m:
            active = int(m.group(1))
            self.assert_(
                "U2: default window is 1 (24h) without cookie/filters",
                active == 1,
                f"active window was {active}d; expected 1d per U2",
            )
        else:
            self.assert_(
                "U2: default window is 1 (24h) without cookie/filters",
                False,
                "no is-active window button found in default request",
            )
        # data-pw-window attr must also be 1
        m2 = re.search(r'data-pw-window="(\d+)"', default_html)
        if m2:
            self.assert_(
                "U2: data-pw-window attr = 1 in default response",
                int(m2.group(1)) == 1,
                f"got {m2.group(1)}",
            )
        # Locale default: zh_cn (Django LANGUAGE_CODE="zh-hans")
        # Verify the home renders with zh_cn locale (Chinese chrome strings present)
        # We don't assert 走个量 (Net G covers that); we assert zh-cnfied chrome like "本窗口最新"
        self.assert_(
            "U2: zh_cn default renders zh-cnfied chrome (本窗口最新)",
            "本窗口最新" in default_html,
            "zh-cnfied feed heading missing in default response — locale default not zh_cn",
        )

        # Cookie home_window=7 honored (returning user override)
        try:
            r7 = session.get(self.url, timeout=30,
                             cookies={"home_window": "7"}, allow_redirects=True)
        except Exception as e:
            self.failures.append(("u2-cookie-http", f"GET with cookie failed: {e}"))
            return
        cookie_html = r7.text
        m3 = re.search(r'<button[^>]*class="window-btn is-active"[^>]*data-pw-window-btn="(\d+)"', cookie_html)
        if m3:
            self.assert_(
                "U2: home_window=7 cookie honored (returning user override)",
                int(m3.group(1)) == 7,
                f"with cookie home_window=7, active was {m3.group(1)}d; expected 7d",
            )

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

    def _check_feed_row_shape(self, html):
        # iter 14 (U5): feed row must match v22-master mockup-canon shape.
        # Per docs/ideation/mockups/06-tier1-composed.v22-master.html L1131-1245:
        #   .feed-row > .feed-row-shell > (.feed-main | .feed-signals[4 .sig-rows])
        rows = re.findall(r'<div class="feed-row"[^>]*data-pw-feed-row[^>]*>', html)
        self.assert_(">= 1 .feed-row with data-pw-feed-row attr",
                     len(rows) >= 1,
                     f"got {len(rows)} rows; live page may still render legacy <tr> shape")
        # Each row must carry the data-* signals for the JS painter.
        for attr in ("data-sentiments=", "data-post-types=", "data-nat-cn=", "data-nat-us=", "data-unsanctioned="):
            self.assert_(f"feed rows carry {attr}",
                         attr in html,
                         f"{attr} missing — JS signal-painter won't run")
        # feed-row-shell with tint class
        shells = re.findall(r'<div class="feed-row-shell tint-\w+"', html)
        self.assert_(">= 1 .feed-row-shell with tint-* class",
                     len(shells) >= 1,
                     f"got {len(shells)} shells; template may not have migrated to mockup shape")
        # feed-main + feed-signals column structure
        mains = re.findall(r'<div class="feed-main">', html)
        signals = re.findall(r'<div class="feed-signals"[^>]*>', html)
        self.assert_(".feed-main present (>=1 per row)",
                     len(mains) >= 1,
                     f"got {len(mains)}")
        self.assert_(".feed-signals present (>=1 per row)",
                     len(signals) >= 1,
                     f"got {len(signals)}")
        # 4 sig-row children inside feed-signals
        for sig in ("sig-sentiment", "sig-post-type", "sig-nat", "sig-unsanctioned"):
            self.assert_(f".sig-row.{sig} present",
                         f'class="sig-row {sig}"' in html,
                         f"missing — right column missing emoji signals")
        # Inside feed-main: avatar, head (handle + meta), text, engagement
        self.assert_(".feed-main .avatar present",
                     re.search(r'<div class="feed-main">\s*<span class="avatar"', html, re.DOTALL) is not None,
                     "avatar must be first child of .feed-main")
        self.assert_(".feed-main .head present",
                     '<div class="head">' in html,
                     "head row missing from .feed-main")
        self.assert_(".feed-main .ts-abs present",
                     'class="ts-abs"' in html,
                     "absolute timestamp span missing")
        self.assert_(".text-layer-tag present (en 'synthesis' or zh '综合')",
                     'class="text-layer-tag"' in html,
                     "text layer tag missing — synthesis/综合 indicator absent")
        self.assert_(".engagement with 4 .followers/.likes/.rts/.replies present",
                     all(f'class="{k}"' in html for k in ('followers', 'likes', 'rts', 'replies')),
                     "engagement spans missing one of followers/likes/rts/replies")

    def _check_filter_contract(self, html):
        # Net C — Filter contract (unchanged wire).
        # Pin the dashboard filter key tuples from monitor/views.py to ensure
        # the v22 chrome cutover doesn't silently drop a filter group or option.
        EXPECTED_DISCOURCE_KEYS = (
            "genuine_hype", "sarcasm", "dunk_yingyang", "self_deprecation",
            "cope", "fud", "distillation_accusation", "ai_slop_critique",
            "absurdist_meme", "advertising-marketing",
        )
        EXPECTED_POST_TYPE_KEYS = (
            "buzz_releases", "hands_on_usage", "performance_comparisons",
            "feedback_questions", "advertising_marketing", "event_announcement",
        )
        EXPECTED_ROLE_KEYS = ("official", "staff", "community", "other")
        EXPECTED_NATIONALISM_KEYS = (
            "none", "mild_pro", "pro", "constructive_critical", "anti", "mixed",
        )
        EXPECTED_LANG_KEYS = (
            "en", "zh-hans", "ja", "es", "tr", "fr", "pt", "ko", "id", "ar",
            "pl", "undetected", "other",
        )

        # Filter nav uses data-group="<short>" on each filter-pill (the
        # actual rendered wire shape — not data-pw-filter-group).
        # 7 groups must all be present.
        groups_in_html = set(re.findall(r'data-group="([^"]+)"', html))
        EXPECTED_GROUPS = {
            "brands", "discourse", "role", "lang",
            "sentiment", "nationalism", "unsanctioned",
        }
        self.assert_(
            "filter-bar nav has all 7 expected groups",
            EXPECTED_GROUPS <= groups_in_html,
            f"missing: {EXPECTED_GROUPS - groups_in_html}, found: {groups_in_html}",
        )

        # For each filter group whose underlying key tuple is pinned in
        # monitor/views.py, verify a sample of expected keys appear in the
        # rendered option HTML (the data-key or value attributes).
        sample_checks = (
            ("discourse", EXPECTED_DISCOURCE_KEYS),
            ("nationalism", EXPECTED_NATIONALISM_KEYS),
            ("role", EXPECTED_ROLE_KEYS),
            ("lang", EXPECTED_LANG_KEYS),
            ("post_type", EXPECTED_POST_TYPE_KEYS),
        )
        for group_name, expected_keys in sample_checks:
            sample_missing = [k for k in expected_keys[:3] if k not in html]
            self.assert_(
                f"filter-group '{group_name}' has sample options in HTML",
                not sample_missing,
                f"sample keys missing: {sample_missing}",
            )

    def _check_chart_contract(self, html):
        # Net D — Chart contract.
        # Chart canvas + chart payload shape pinned.
        self.assert_(
            "chart canvas present (data-pw-chart or chart canvas)",
            "data-pw-chart" in html or "home-chart" in html or "<canvas" in html,
            "no chart canvas/element found in HTML",
        )
        # Chart heading text per v22 mockup
        self.assert_(
            "chart heading 'Daily total posts per brand' present",
            "Daily total posts per brand" in html or "每日各品牌帖子总数" in html,
            "chart heading missing in both en and zh_cn",
        )
        # pw-chart.js loaded
        self.assert_(
            "pw-chart.js script loaded",
            "pw-chart" in html,
            "pw-chart.js not referenced in HTML",
        )

    def _check_chart_no_hover_isolate(self, session):
        """Net D (U4) — hover-isolate control flow absent in pw-chart.js.

        Per plan § Net D: "pw-chart.js post-change: no hover-isolate
        control flow (`hoveredBrandIndex` absent or inert)."
        Static-analysis: fetch /static/pw-chart.js and assert that
        `hoveredBrandIndex` is not used in active code (only in comments
        describing the removal is OK).
        """
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(self.url)
        js_url = urlunparse((parsed.scheme, parsed.netloc, "/static/pw-chart.js", "", "", ""))
        try:
            r = session.get(js_url, timeout=30, allow_redirects=True)
        except Exception as e:
            self.failures.append(("net-d-js-http", f"GET {js_url} failed: {e}"))
            return
        if r.status_code != 200:
            self.failures.append(("net-d-js-status", f"status {r.status_code}"))
            return
        js_source = r.text

        # Strip line comments and block comments — only check active code
        import re as _re
        # Remove single-line comments (// ...) and block comments (/* ... */)
        stripped = _re.sub(r"//[^\n]*", "", js_source)
        stripped = _re.sub(r"/\*.*?\*/", "", stripped, flags=_re.DOTALL)

        # Now check for any active usage of `hoveredBrandIndex` in non-comment code
        active_uses = _re.findall(r"\bhoveredBrandIndex\b", stripped)
        self.assert_(
            "U4: hover-isolate removed — no active `hoveredBrandIndex` references in pw-chart.js",
            len(active_uses) == 0,
            f"found {len(active_uses)} active uses of hoveredBrandIndex in non-comment code",
        )

        # Also verify the onHover callback exists (so Chart.js doesn't error)
        # and is a no-op or only contains an inert comment.
        m = _re.search(r"onHover\s*:\s*function\s*\([^)]*\)\s*\{([^}]*)\}", js_source)
        if m:
            body = m.group(1).strip()
            # Strip comments from body too
            body_stripped = _re.sub(r"//[^\n]*", "", body).strip()
            self.assert_(
                "U4: onHover callback body is a no-op (no ds.hidden mutations)",
                body_stripped == "" or "ds.hidden" not in body_stripped,
                f"onHover still mutates ds.hidden: {body!r}",
            )

    def _check_locale_exhibits(self, html):
        # Net G — Locale exhibits.
        # App title always contains both 走个量 and Pushin' Weight.
        self.assert_(
            "app title has zh_cn '走个量'",
            "走个量" in html,
            "zh_cn app name missing in HTML",
        )
        # English name with apostrophe variants
        en_ok = any(v in html for v in (
            "Pushin' Weight", "Pushin’ Weight",
            "Pushin&#x27; Weight", "Pushin&#39; Weight",
        ))
        self.assert_(
            "app title has en 'Pushin' Weight'",
            en_ok,
            "English app name missing in HTML",
        )
        # Locale toggle exposes 3 buttons (zh_cn / en / original)
        locale_btns = re.findall(r'data-pw-locale-btn="(\w+)"', html)
        self.assert_(
            "locale toggle exposes 3 buttons (zh_cn/en/original)",
            set(locale_btns) == {"zh_cn", "en", "original"},
            f"got {set(locale_btns)}",
        )

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
        # iter 16 (U3): pw-filter-pills.js — drag-scroll + lens pills
        has_pills_js = any('pw-filter-pills' in s for s in scripts)
        self.assert_("pw-filter-pills.js loaded (U3 drag-scroll + lens pills)",
                     has_pills_js,
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

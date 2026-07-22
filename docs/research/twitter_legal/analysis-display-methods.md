# Display Methods Legal Analysis — x-monitor

**Date:** 2026-07-22
**Scope:** Legal analysis of three methods for surfacing X post content in x-monitor's dashboard — (A) plain hyperlink, (B) hover-preview via official embed, (C) hover-preview via custom JS / server proxy. All conclusions drawn exclusively from documents in this directory.

**Companion documents:** Every reference below cites files in this folder. See `README.md` for the full inventory.

---

## Method A: Plain Hyperlink (no post content displayed)

**Description:** x-monitor shows an analysis/card with a hyperlink to `x.com/<user>/status/<id>`. Clicking navigates the user to X. At no point does x-monitor render any post text, author info, media, or metadata from X.

### Analysis by document

**TwitterAPI.io AUP (directly binding)**

§2(c): *"Scrape, store, or redistribute data in violation of X/Twitter's terms of service."*

A URL string (`x.com/user/status/123`) is not X Content. It is a locator — a fact about where content resides. Storing a URL is not storing X data. Linking is not scraping. This clause is not triggered.

**TwitterAPI.io TOS (directly binding)**

§2 describes permitted uses: *"research, brand monitoring, compliance, and legitimate business purposes."* §5 lists prohibited uses (harassment, doxxing, discrimination, disruption, circumvention). Linking is not listed as prohibited. The TOS is silent on linking.

**X Terms of Service §4 (not directly binding — no X account)**

The operative display/reproduction clause: *"If you want to reproduce, modify, create derivative works, distribute, sell, transfer, publicly display, publicly perform, transmit, or otherwise use the Services or Content on the Services, you must use the interfaces and instructions we provide … Otherwise, all such actions are strictly prohibited."*

A hyperlink is none of these acts. Reproduction requires copying the work itself. A URL is a reference, not a reproduction. Copyright law distinguishes between a pointer and the pointed-to work. A hyperlink to `x.com` is not a display of X Content — the browser navigates to X, and X serves the content.

The scraping prohibition (§4(iii)): *"NOTE: crawling or scraping the Services in any form, for any purpose without our prior written consent is expressly prohibited."* — A hyperlink click is user-initiated navigation, not automated crawling.

**X Display Requirements (not binding — no X API key)**

These govern *how* X Posts must appear *when displayed*. If no post content is displayed, the requirements do not trigger. Not applicable.

Relevant as guidance: the Display Requirements list *"View on X"* as an acceptable alternative to action buttons: *"Alternatively, 'View on X' may appear beside the timestamp, linking to the post's permalink."* This confirms X expects and permits link-out patterns.

**X Developer Policy — Content Redistribution (not binding)**

*"Only Post IDs, Direct Message IDs, and/or User IDs may be redistributed to third parties."* A URL to `x.com/user/status/123` contains a Post ID. Even under the most aggressive reading, URLs fall within allowed Post ID redistribution (capped at 1,500,000 per entity per 30 days).

**xAI Enterprise ToS / AUP (binding if using X Search)**

AUP: *"Scraping, harvesting, or reselling Input or Output"* — a URL constructed by x-monitor is not Input or Output from xAI's API. Enterprise ToS §3.3 (30-day deletion): applies to content in xAI's systems, not URLs in x-monitor's database.

**X Privacy Policy**

*"We use technology like APIs and embeds to make public X information available to websites, apps, and others for their use, for example, displaying posts on a news website or analyzing what people say on X."* — Acknowledges third-party use without prohibiting linking.

### Conclusion: Method A

**Clean under all collected documents.** No document prohibits linking to X. X's own developer documentation endorses the link-out pattern. The Developer Policy's Post ID redistribution allowance (1.5M/30 days) provides an explicit permission backstop even under the most conservative reading.

---

## Method B: Hover-Preview via X Official Embed (`publish.x.com`)

**Description:** User hovers over a link; JavaScript loads X's official embed widget (`publish.x.com`), which renders the post in a hover box on x-monitor's domain. Post content is visible without navigation.

### Analysis by document

**X Terms of Service §4**

The display clause is now triggered — post content appears on x-monitor's page. The key question: is x-monitor using *"the interfaces and instructions we provide"*? Yes. The `publish.x.com` embed is X's published, documented, recommended interface for displaying posts on third-party sites. X built it for this exact purpose.

*"If you want to reproduce, modify, create derivative works, distribute, sell, transfer, publicly display … Content on the Services, you must use the interfaces and instructions we provide."* — The embed IS that interface. Compliant.

The facilitation clause (§4 final paragraph): *"It is also a violation of these Terms to facilitate or assist others in violating these Terms."* — Not triggered, because the display itself is compliant.

**X Display Requirements**

Now triggered — post content is displayed. The embed widget handles compliance automatically: it renders the author avatar, @username, display name, unaltered post text, timestamp, action buttons (Reply/Repost/Like), and X branding. The Display Requirements strongly prefer this approach: *"X strongly recommends using embedded Posts and embedded timelines via publish.x.com, which handle rendering, media playback, edited posts, and data fetching automatically."*

Post edits: the embed handles the two edit scenarios (embedded-first-then-edited, edited-first-then-embedded) automatically per the Display Requirements §Post Edits.

Content deletion: if a post is deleted on X, the embed stops rendering it — satisfying the 24-hour removal requirement in the Developer Policy §Content Compliance.

**X Developer Agreement §III.K — iframe prohibition**

*"The X API and X Content must not be displayed within an HTML iframe without X's express written permission."* — The embed widget renders via X's own JavaScript, not a raw iframe to `x.com`. The embed is the permitted alternative to iframes. Not triggered.

**X Developer Policy — Content Redistribution**

*"Displayed X Content must maintain integrity."* — The embed maintains integrity by design. The developer can't alter post text, remove attribution, or change action buttons. Compliant.

*"Only Post IDs … may be redistributed"* — if the embed URL contains a Post ID, this is Post ID redistribution, which is explicitly permitted.

**TwitterAPI.io AUP §2(c)**

*"Scrape, store, or redistribute data in violation of X/Twitter's terms of service."* — Since the embed is X's own interface, displaying via embed does not violate X's TOS. This clause is not triggered.

**xAI Enterprise ToS / AUP (if using X Search)**

Not triggered. The embed fetches from X, not from xAI. If the Post ID originated from X Search results, the URL itself (Post ID) is not "Output" that triggers the 30-day deletion rule — only content stored in xAI's systems is affected.

### Conclusion: Method B

**Clean under all collected documents.** The embed is X's explicitly endorsed method for third-party post display. It satisfies the Display Requirements automatically, avoids the iframe prohibition, handles edit/deletion compliance, and constitutes use of "the interfaces X provides" under the TOS.

---

## Method C: Hover-Preview via Custom JS / Server Proxy

**Description:** User hovers over a link; custom JavaScript (client-side fetch, server-side proxy, or raw iframe) retrieves X post content and renders it in a hover box, without using X's official embed widget.

### Analysis by document

Three sub-variants with different legal profiles:

#### C1: Server-side proxy (your server fetches X, relays to client)

**X TOS §4 — scraping prohibition:** *"NOTE: crawling or scraping the Services in any form, for any purpose without our prior written consent is expressly prohibited."* — Your server programmatically fetching `x.com` pages is scraping. Clear violation. No written consent from X.

**X TOS §4 — display clause:** *"you must use the interfaces and instructions we provide"* — A custom server relay is not X's interface. The embed widget is. Second violation.

**X TOS §4 — facilitation clause:** *"It is also a violation of these Terms to facilitate or assist others in violating these Terms."* — Your server scrapes (violation #1), your client displays outside X's interfaces (violation #2). x-monitor built both. Third violation.

**TwitterAPI.io AUP §2(c):** *"Scrape, store, or redistribute data in violation of X/Twitter's terms of service."* — Now triggered, because the server-side proxy violates X's TOS on three grounds. This clause makes it a violation of x-monitor's direct provider agreement as well.

**X Display Requirements:** Custom rendering must manually comply with all requirements (author info, unaltered text, action buttons, X logo, edit handling, 24-hour deletion compliance). Non-trivial to implement correctly. Non-compliance is a breach of the Developer Agreement's incorporated terms — although x-monitor hasn't signed that, violating display requirements while simultaneously violating the TOS compounds the exposure.

#### C2: Client-side iframe to post URL

**X Developer Agreement §III.K:** *"The X API and X Content must not be displayed within an HTML iframe without X's express written permission."* — Direct, explicit prohibition. No written permission from X.

**X TOS §4 — display clause:** An iframe to `x.com` is arguably using X's own page as the rendering engine. Weaker violation than a proxy, but the Developer Agreement's explicit iframe prohibition makes this clear-cut in X's view.

**X TOS §4 — circumvention:** Using an iframe after the embed widget exists could be read as circumventing the embed's tracking/analytics. *"You agree that you will not work around any technical limitations in the software provided to you as part of the Services."*

#### C3: Client-side `fetch()` to x.com

**Technical barrier:** X's CORS policy blocks cross-origin `fetch()` from arbitrary domains. The approach fails before legal analysis applies. If worked around (e.g., CORS proxy, browser extension), it collapses into C1 (server proxy) or C2 (circumvention).

### Conclusion: Method C

**Violates X's TOS under all sub-variants.** C1 (server proxy) is the worst: scraping + display-outside-interfaces + facilitation, three independent violations that cascade into the TwitterAPI.io AUP. C2 (iframe) hits the Developer Agreement's explicit iframe prohibition. C3 (client fetch) is CORS-blocked. No collected document supports this approach.

---

## Summary Table

| Method | X TOS §4 | Dev Agreement | Display Reqs | TwitterAPI.io AUP | xAI ToS/AUP |
|---|---|---|---|---|---|
| **A: Plain hyperlink** | Not triggered (not Content) | Not triggered | Not triggered | Not triggered | Not triggered |
| **B: Official embed** | Compliant (X's interface) | Not triggered (embed is permitted) | Compliant (embed handles) | Not triggered | Not triggered |
| **C1: Server proxy** | **Violation** (scraping + display + facilitation) | Not directly (no key), but instructive | Non-compliant (custom render) | **Triggered** (violates X TOS) | Not triggered |
| **C2: Client iframe** | Possible violation (display outside interface) | **Violation** (§III.K explicit prohibition) | Non-compliant | Possible trigger | Not triggered |
| **C3: Client fetch** | CORS-blocked (moot) | CORS-blocked (moot) | CORS-blocked (moot) | CORS-blocked (moot) | CORS-blocked (moot) |

---

## Operational Recommendation

1. **Plain hyperlinks (Method A):** No restrictions. Implement freely.
2. **Hover previews (Method B):** Use X's official embed widget exclusively. Do not build custom rendering. The embed is the only legally clean path to on-page post display.
3. **Server-side proxy (Method C1):** Do not implement. This is the highest-risk approach, violating X's TOS on three independent grounds and triggering the TwitterAPI.io AUP.
4. **Iframes (Method C2):** Do not implement. Explicitly prohibited by the Developer Agreement.
5. **Client-side fetch (Method C3):** Moot — CORS-blocked. If workaround is attempted, it collapses into C1 or C2 risk profile.

### Implementation note for Method B

The embed widget requires:
- The Post ID (extracted from the URL)
- A `publish.x.com` embed script tag on the page
- The embed handles all compliance (attribution, actions, edits, deletions)
- The embed may inject X tracking/analytics — disclose in privacy policy per Developer Policy §Your Privacy Policy: *"must disclose what information is collected, how it is used and shared (including sharing with X)"*

---

*Analysis based exclusively on documents in `docs/research/twitter_legal/` as of 2026-07-22. Not legal advice.*

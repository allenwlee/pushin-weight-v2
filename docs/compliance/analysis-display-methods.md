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
---

## Addendum — 2026-08-05: `cn_equivalent` toggle pattern + commentary-vs-translation distinction

**Author:** follow-up review after the 2026-08-05 conversation between user and agent.
**Scope:** Adds a fourth display method (commentary-default toggle) and refines the analysis of `cn_equivalent` based on its actual definition in the translator prompt contract. Does not modify the prior conclusions for Methods A, B, or C.

### Refinement: `cn_equivalent` is commentary, not translation

The prior analysis did not distinguish `cn_equivalent` from `text_zh_cn` precisely. They are different things under the translator contract (`x_monitor/translator.py:434`):

- **`text_zh_cn` / `literal_zh`** — Simplified Chinese rendering of the source post. Preserves meaning. Legally a *translation* in the Berne Convention Art. 2(3) / US 17 USC §106(2) sense — the author's exclusive right of adaptation.
- **`cn_equivalent`** — A *separate, original composition* in the voice of a Chinese netizen (Weibo / Zhihu / Bilibili register). Prompt contract: *"how would Chinese netizens on Weibo/Zhihu/Bilibili say this"* (translator.py:434). Example from `docs/reference/translator-output.md`: "Kimi K2.7 Code is generally available in GitHub Copilot" → *"Kimi K2.7 Code 正式登陆 Copilot，全量开放"*. The original poster never wrote the second sentence. It is the model's original creative-analytical composition about the topic the original raised.

This distinction matters because:

1. **Translation = exclusive right of the author.** Displaying a translation in place of the original competes with X's reserved translation rights per `x-terms-of-service.md:95/227` (X grants *itself* the right to "curate, transform, and translate" user content).
2. **Original commentary = protected speech.** A composition that *responds to* or *re-frames* the original in a different voice is the analyst's own work. Protected under US fair use (17 USC §107) and EU quotation right (InfoSoc Directive Art. 5(3)(d), Berne Art. 10/10bis).

The same model output can be legally classified either way depending on how it is **framed on the page**. A label of "Translation:" reads as a translation; a label of "How a Chinese netizen might respond:" reads as commentary. The legal posture follows the framing.

### Method D: Commentary-default toggle (cn_equivalent default, opt-in to original + literal)

**Description:** A single div on the homepage renders one of three views. Default is `cn_equivalent` (commentary). User taps once to reveal the original English post (verbatim quote, attributed). User taps twice to reveal `text_zh_cn` (literal translation). All three views share the same card with the @handle, display name, and a permalink to the original tweet on x.com. Tap hints label each view clearly.

#### State-by-state analysis

**State 1 (default): `cn_equivalent` as commentary**

- **X TOS §4** — The display clause is triggered in form (something appears on the page) but the *substance* is not "Content on the Services." The displayed text is the analyst's original composition. No verbatim reproduction of X Content. Not a derivative work of the post — it is a derivative work *about* the post's topic.
- **X Display Requirements** — These govern how a post must appear *when displayed*. No post text is displayed; the analyst's commentary is shown. The clause "Alter post text in any way" / "Must be displayed unaltered" (`x-display-requirements.md:34, 52`) is not triggered because there is no post text being altered.
- **Berne Convention Art. 2(3) / US 17 USC §106(2)** — Translation is the author's exclusive right. `cn_equivalent` is not a translation; it is an original composition. The exclusive right is not implicated.
- **Fair use (US)** — All four factors favor the analyst: (1) transformative purpose and character; (2) short factual/creative tweet (neutral); (3) zero verbatim reproduction of the original; (4) with a permalink to the original, market effect is non-substitutive (drives traffic to X, does not substitute for X's own surfaces).
- **EU quotation right (InfoSoc Directive Art. 5(3)(d))** — Permits quotation for criticism or review with source indication. The permalink to x.com is the source indication.

**Verdict:** ✅ **Clean.** This is the legally safest display posture in this entire document. No reproduction of X Content; original analyst work; source clearly indicated.

**State 2 (tap once): original English post**

- **X TOS §4** — The post text is now reproduced on x-monitor's domain. Strictly read, this is a verbatim quote of X Content on a third-party site.
- **Fair use (US)** — A short tweet quoted in commentary with attribution and a permalink back to the original is the most well-established fair-use posture. All four factors favor the analyst: (1) purpose is critical/analytical; (2) short factual/creative work (neutral); (3) quoting a single tweet is well within fair-use norms; (4) the permalink drives traffic to X rather than substituting for it.
- **EU quotation right** — Quotation for criticism/review with source indication. The permalink is the indication. Permitted.
- **X Display Requirements** — Bundled attribution (avatar + display name + @handle linking to profile, permalink timestamp, View-on-X link, X logo, Reply/Repost/Like affordances) is required *when post text is displayed*. These are not required for fair-use quotation, but implementing them is harmless and reduces friction. Strictly: not legally required for a one-off quotation in commentary; required if treated as a "display" surface per the Developer Agreement.

**Verdict:** ✅ **Clean** as fair-use quotation with attribution + permalink. Not a standalone display surface — depends on the surrounding commentary framing to read as analysis rather than display.

**Critical:** State 2's legal safety depends on **page context**, not on pixel-level visibility. The toggle pattern is fine — what matters is that the page as a whole reads as commentary (State 1 is the default, the @handle and permalink are visible somewhere on the card, the labels make clear these are responses to X posts). A bare English tweet with only a permalink reads as display, not analysis.

**State 3 (tap twice): `text_zh_cn` (literal translation)**

- **X TOS §4** — Translation in place of (or alongside) the original post. Per `x-terms-of-service.md:95/227`, X reserves translation rights to itself. The license does not flow to third parties.
- **X Display Requirements** — `x-display-requirements.md:34, 52`: "Alter post text in any way" / "Must be displayed unaltered — no edits, no truncation that changes meaning." Translation is unambiguously an alteration. The Developer Agreement's narrow modification right ("only as necessary to format it for display," `x-developer-agreement.md:53`) does not cover translation.
- **Berne Convention Art. 2(3) / US 17 USC §106(2)** — Translation is the author's exclusive right of adaptation. The original poster did not grant a translation license to x-monitor.
- **Fair use (US)** — Weaker than States 1 and 2 because (1) is less transformative (translation is technically a derivative work under copyright law, though courts weigh this against other factors), and (4) the market-substitution concern is sharper (competing with X's reserved translation rights). The four factors do not clearly favor the analyst.
- **EU law** — No fair-use / fair-dealing exception. Berne Art. 2(3) gives the author an exclusive adaptation right. The InfoSoc Directive Art. 5(3)(d) quotation exception requires "criticism or review" framing, which is partially present but weaker than States 1 and 2.

**Verdict:** ⚠️ **Defensible but not clean.** The toggle pattern materially reduces exposure because: (a) the default is not the translation, (b) the translation is opt-in (user tap = user choice), and (c) by the time the user reaches State 3, the commentary framing and source indication are established. But State 3 is the same legal posture as "displaying a translation publicly" — the toggle pattern reduces practical risk, it does not eliminate legal risk.

**Mitigation that strengthens State 3:** Label State 3 as "Literal machine translation — for reference only" rather than just "Chinese translation." The "for reference only" framing reinforces that the translation is supplementary to x-monitor's commentary, not a substitute for the original.

#### Method D summary

| State | Content | Verdict |
|---|---|---|
| State 1 (default): `cn_equivalent` as commentary | Original analyst composition | ✅ Clean — fair use / quotation right |
| State 2 (tap once): original English post | Verbatim quote with attribution | ✅ Clean — fair-use quotation; depends on page context |
| State 3 (tap twice): `text_zh_cn` | Literal translation | ⚠️ Defensible — toggle pattern reduces but does not eliminate risk |

**Operational recommendation for Method D:**

1. Default to State 1 (commentary). Never default to a translation or the original post.
2. Label State 1 explicitly as commentary ("How a Chinese netizen might respond," "Weibo-voice response," "Chinese-internet equivalent"). Do not label it "Translation" or "中文." The label determines the legal classification.
3. State 2 (original post) is safe as fair-use quotation provided the page context establishes critical/analytical framing. The @handle and permalink must be visible on the card. A bare English tweet with only a permalink is not quotation — it is display, and falls back to the Display Requirements analysis.
4. State 3 (`text_zh_cn`) is the highest-risk state. Two acceptable paths: (a) ship it with the "for reference only" framing and accept residual exposure, or (b) omit it entirely and ship only States 1 and 2 (the cleanest posture).
5. The permalink to x.com is non-negotiable across all three states. It is the source indication required by EU quotation right and the strongest single defense on US fair-use factor 4 (market effect).

#### Cross-cutting risks (apply to all three states)

- **TwitterAPI.io AUP §2(c)** (`twitterapi-io-acceptable-use-policy.md:35`): *"Scrape, store, or redistribute data in violation of X/Twitter's terms of service."* This clause binds x-monitor's data acquisition regardless of display method. Producing translations at scale using scraped data is still in a gray zone — TwitterAPI.io could suspend the API key under §5 if they read the use as a violation of X's terms upstream.
- **Foundation-model training prohibition** (`x-restricted-use-cases.md:62`): *"The X API and X Content may not be used to fine-tune or train a foundation or frontier AI model."* Applies to X API / X Content users directly and via TwitterAPI.io's §2(c). If the LLM producing `cn_equivalent` / `text_zh_cn` was fine-tuned or trained on X data, this is a hard violation. Inference-only by an off-the-shelf model is likely safe; verify with the LLM provider's terms.
- **Liquidated damages clause** (`x-terms-of-service.md:153/277`): $15,000 (or €15,000) per 1,000,000 posts viewed in a 24-hour period. Applies to users of the X Service; less clear it applies to third-party scrapers, but signals X's enforcement posture. Worth noting if the homepage ever scales.

### Why Method D is materially better than a translation-as-headline posture

A page that displays `text_zh_cn` as the primary content of each card (with @handle attribution only) is "displaying translations as the product" — that posture fails the Display Requirements, fails Berne Art. 2(3), and triggers TwitterAPI.io AUP §2(c). Method D's toggle pattern avoids this by making the default commentary (State 1), reducing the translation to an opt-in view (State 3), and providing the permalink-to-original source indication that fair-use factor 4 and EU quotation right both reward.

The toggle is not a legal trick — it reflects a real difference in how the page reads. A user landing on the page sees analyst commentary with a permalink to the original; that is a fundamentally different relationship to X Content than landing on a page that displays the post's translation as its own product.

### Companion reading

- `docs/reference/translator-output.md` — the translator's documented distinction between `text_zh_cn`, `literal_zh`, and `cn_equivalent`, including the example that anchors the commentary-vs-translation analysis.
- `x_monitor/translator.py:434` — the prompt contract language for `cn_equivalent`.
- This document's prior Methods A/B/C analysis — establishes that hyperlink (A) and official embed (B) are clean; Method D is the next tier of displayable content beyond those.

---

*Addendum appended 2026-08-05. Findings drawn from documents in `docs/research/twitter_legal/` plus the conversation with user that surfaced the commentary-vs-translation distinction. Not legal advice.*

# Brand24 — how they legally display X posts verbatim

**Date:** 2026-08-06
**Author:** follow-up synthesis from the 2026-08-06 conversation between user and agent
**Sources:** scraped docs in `docs/compliance/brand24/official/`, plus `docs/compliance/twitter_legal/` for the X-side analysis.
**Purpose:** capture the load-bearing findings from this conversation so a future session can pick up the research thread without re-doing the work.

---

## TL;DR

We speculate that Brand24 pays X for a paid data license that gives them **display rights on their own authenticated surfaces but not redistribution rights downstream.** They implement that license shape by displaying post text verbatim on their dashboard (`app.brand24.com/panel/results/...`) and **stripping post text from their public API** (`api-data.brand24.com/api-data/v1/...`). The strip is contractual, not technical — the API FAQ explicitly says "for Facebook, Instagram and X the platforms' terms limit post content, so those text fields come back empty." Everything outside the X license (blogs, forums, Reddit, news, podcasts — the 25M+ other sources) is handled via DMCA safe harbor + a user-restrictive ToS.

---

## The smoking gun

From `official/brand24.com-social-listening-api.md:156`:

> "Both. The `/mentions` endpoint returns mention-level rows (date, source, host, category, sentiment, tags) with cursor pagination. Full text is available on most sources; **for Facebook, Instagram and X the platforms' terms limit post content, so those text fields come back empty.**"

The phrase "the platforms' terms" points at the **upstream X / Facebook / Instagram contracts** (their paid data licensing agreements). The strip is *not* a self-imposed Brand24 choice and *not* a ToS-imposed-on-everyone rule — it's specific to what those contracts permit when Brand24 is redistributing data downstream.

---

## The two-track model

| Surface | Behavior | License basis |
|---|---|---|
| **Dashboard** (`app.brand24.com/panel/...`, behind login) | Full post text rendered verbatim to logged-in end users | Paid X data license — display rights on Brand24's owned-and-operated surfaces |
| **API** (`api-data.brand24.com/api-data/v1/...`, server-to-server) | Mentions returned with metadata only; `text` field empty for X / Facebook / Instagram | License restricts sublicensing of post expression to third parties; metadata is allowed, post body is not |

This asymmetry is the legal moat. End users see posts on Brand24's dashboard (where Brand24 holds the X contract). Downstream API consumers see only metadata (so Brand24 can credibly claim "we did not redistribute X Content to third parties" under X's Developer Policy redistribution limits).

---

## Why the X license probably exists

Four signals:

1. **Volume.** Brand24 quotes "X (Twitter) users send about 867 million posts (tweets) daily" as scale context (`official/brand24.com-twitter-monitoring.md:39`). Public X API Basic caps at 10K tweets/month, Pro at 1M. Brand24 needs Enterprise tier.
2. **Real-time + 30-day history.** Real-time dashboard updates and 30-day filter windows require firehose access, which is Enterprise-only.
3. **ToS pressure.** `docs/compliance/twitter_legal/x-terms-of-service.md:113/245` requires public display of X Content to use "the interfaces and instructions we provide." Brand24 isn't using the public API at this scale; they have a contract.
4. **The strip itself.** A scraper or unauthorized API wouldn't bother stripping post text — that's lost product surface. The deliberate strip implies a constraint in the contract.

Brand24 sits in the same enterprise-X-customer tier as Sprinklr, Brandwatch, Meltwater, Talkwalker.

---

## License shape (inferred)

The contract almost certainly contains clauses along these lines (synthesized from Brand24's strip behavior + X's standard partner-program pattern):

> "Licensee may display X Content on Licensee's owned-and-operated authenticated end-user surfaces. Licensee may redistribute X Content metadata (post IDs, user IDs, timestamps, engagement metrics, sentiment scores) to Licensee's API customers. Licensee shall not redistribute X Content expression (the text of posts, media, or derivative works thereof) to Licensee's API customers or to any third party."

That maps 1:1 to what Brand24 implements in the `/mentions` endpoint: metadata in, post text empty for X.

---

## How Brand24 handles the long tail (non-X sources)

For everything outside the X license — blogs, forums, Reddit, news, podcasts, the 25M+ sources — Brand24 leans on DMCA safe harbor + a user-restrictive ToS:

**`official/brand24.com-terms.md`:**

- **§IV.3.d** — User must "use the Website in compliance with the terms of use of external data providers, in particular the social networks Facebook, Twitter, Instagram and YouTube" (pushes platform-compliance obligation onto the user)
- **§IV.3.g** — "use any content posted on the Website only for his/her own internal or personal use. Use of the content in any other scope is permitted only on the basis of written consent granted by the Operator" (no republishing)
- **§IV.3.g continued** — "In the event of quoting or publishing data obtained in connection with the provision of the Service by the Operator, the User shall each time be obliged to state the source of the obtained data in the suggested form: 'Source: brand24.com' and the date of their acquisition" (mandatory attribution if exported)
- **§IV.12** — "the User shall not license, sell, rent, lease, transfer, assign, distribute, host, or otherwise exploit the Website, whether in whole or in part, or any content displayed on the Website" (no reselling)
- **§V.4** — "The Operator reserves the right to remove content covering the copyrights of third parties from the Website at any time" (right to takedown)

**`official/brand24.com-dmca.md`:**

- Registered DMCA Agent at Phil Nicolosi Law, Rockford, IL
- "As an internet service provider, we are entitled to claim immunity from said infringement claims pursuant to the 'safe harbor' provisions of the DMCA"
- 17 USC §512(c) takedown + counter-notification flow
- Repeat infringer policy with account termination

**`official/brand24.com-dsa.md`:**

- Below the 45M-user "very large platform" threshold
- Voluntary DSA transparency disclosure (not strictly required at their size)

The model: scrape broadly, qualify for DMCA safe harbor, react to takedowns. Don't pre-screen.

---

## Implications for our `pushin-weight-v2` posture

We don't have anything resembling Brand24's X license. Our setup is structurally weaker in two ways and stronger in one:

**Weaker than Brand24:**
- **No paid X license.** We use TwitterAPI.io (unauthorized scraper). TwitterAPI.io AUP §2(c) (`docs/compliance/twitterapi_docs/twitterapi-io-acceptable-use-policy.md:35`) explicitly forbids "scrape, store, or redistribute data in violation of X/Twitter's terms of service" — and we are downstream of an unauthorized source.
- **Public homepage, not login-walled.** Brand24's full-text display sits behind authentication on their own domain, which materially changes the "public display" analysis under X ToS §4.

**Stronger than Brand24:**
- **Not displaying verbatim post text as the product.** Our homepage shows `cn_equivalent` (analyst commentary in a hypothetical Chinese-netizen voice) as the default; the original English and a literal Chinese translation are opt-in toggles. This is a commentary / quotation posture, not a display posture — the legal analysis from `docs/compliance/analysis-display-methods.md` (Method D addendum, 2026-08-05) holds.

| Question | Brand24 | us |
|---|---|---|
| License from X? | Yes, paid partner tier | No. TwitterAPI.io AUP §2(c) exposure. |
| Post text on homepage? | Yes, behind login, attributed | `cn_equivalent` as default; original English + literal Chinese opt-in toggles, public |
| Redistribution downstream? | No — post text stripped at API | We don't redistribute; we display to end users on our homepage |

Composite risk: comparable for the `cn_equivalent`-as-default surface (Brand24's license + login wall vs our commentary framing + opt-in toggles), but our TwitterAPI.io AUP exposure is the live risk vector that Brand24 doesn't carry because they have the license.

---

## Lessons we should consider adopting

If we ever want to match Brand24's display-posture defensibility, the path is one of:

1. **Get an enterprise X license ourselves.** Real money, real contract, unlocks the same display rights Brand24 has. Highest cost, lowest residual risk.
2. **Login-wall the homepage.** Same content, behind auth, materially changes the "public display" analysis. Cheap to implement; shifts us closer to Brand24's posture without paying for a license.
3. **Strip post text from any downstream redistribution we expose.** If we ever offer an API or bulk export, mirror Brand24's `/mentions` shape (metadata only, no X post body). Preserves the data-acquisition moat for our own product.
4. **Strengthen our ToS to mirror Brand24's user obligations.** §IV.3.d (user must comply with platform ToS), §IV.3.g (no republishing without consent + mandatory `Source: brand24.com` attribution), §IV.12 (no reselling). Cheap, defensive.
5. **Register a DMCA agent.** We probably qualify as a service provider under 17 USC §512(c); the DMCA safe harbor is most valuable when invoked. Brand24 has a registered agent; we don't.

None of these individually closes the TwitterAPI.io AUP gap (that's about data acquisition, not display). But together they make the display side of the analysis nearly airtight even if the acquisition side stays gray.

---

## Open questions for future sessions

1. **Can we estimate Brand24's likely license tier from their public footprint?** Volume signals point to Enterprise; could a future session confirm by testing their rate limits against public X API tier ceilings?
2. **Are there published case studies of Brand24 receiving X takedowns or DMCA notices?** Worth a targeted search to see how their DMCA flow actually plays out in practice.
3. **Does Brand24 publish a "data partners" or "compliance" page** that would confirm the X partnership publicly? Marketing pages say "real-time" and "firehose-class" but don't name X as a partner — the partnership is implied, not advertised.
4. **What does the EU DSA "trusted flagger" program look like for social-listening tools?** Brand24's voluntary DSA disclosure suggests they're positioning for regulatory legitimacy; could be a model for our own compliance posture.

---

## File index

- `official/brand24.com-twitter-monitoring.md` — marketing page for the X monitoring feature
- `official/brand24.com-social-listening-api.md` — API docs with the smoking-gun FAQ at line 156
- `official/brand24.com-terms.md` — full Terms of Service (user obligations, redistribution restrictions)
- `official/brand24.com-privacy-policy.md` — privacy policy
- `official/brand24.com-dmca.md` — DMCA safe-harbor policy + registered agent
- `official/brand24.com-dsa.md` — DSA compliance disclosure
- `official/brand24.com-personal-data-from-internet.md` — data-subject rights under EU rules
- `official/brand24.com-legal.md` — legal hub page (index)

## Companion references (outside this dir)

- `docs/compliance/twitter_legal/` — X ToS, Developer Agreement, Display Requirements, the contractual background against which Brand24's license is shaped
- `docs/compliance/twitterapi_docs/twitterapi-io-acceptable-use-policy.md` — TwitterAPI.io AUP §2(c), the constraint we're operating under instead of a license
- `docs/compliance/analysis-display-methods.md` — our own app's display-posture analysis (Method D commentary-default toggle)

---

*Captured 2026-08-06. Findings synthesized from the conversation plus the official docs in `official/`. Not legal advice.*

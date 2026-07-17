# X API Restricted Use Cases — Verbatim Legal Reference

**Source URL:** https://docs.x.com/developer-terms/restricted-use-cases.md
**Document type:** Restricted use cases policy (specific prohibitions and limitations on X API usage)
**Last Updated:** (Included in the Developer Agreement dated April 27, 2026)
**Issued by:** X Corp. / X Internet Unlimited Company

**Retrieved:** 2026-07-17 by the minimax-marketing x-monitor legal-review pass.
**Retrieval method:** WebFetch from docs.x.com/developer-terms/restricted-use-cases.md. This document was reconstructed from a comprehensive section-by-section summary. All categories, prohibitions, and numerical limits are preserved. For the absolute verbatim text, download directly from the source URL.

**Companion documents in this folder:** `x-terms-of-service.md`, `x-privacy-policy.md`, `x-tos-privacy-update-2026-blog.md`, `x-developer-agreement.md`, `x-developer-policy.md`, `x-display-requirements.md`, `x-geo-guidelines.md`, `x-developer-policies-index.md`, `twitterapi-io-terms-of-service.md`, `twitterapi-io-acceptable-use-policy.md`.

---

# X API Restricted Use Cases

## Automation & Spam

The X API may not be used for spam or platform manipulation:

- Bulk, aggressive, or spammy automated actions are prohibited
- Explicit consent must be obtained from users before sending automated replies
- Opt-out requests from users must be honored immediately and completely
- Automated following, unfollowing, liking, or reposting at scale is prohibited

---

## Sensitive Information

### Profiling on Protected Characteristics

Developers may not derive, infer, or store information about X users' sensitive characteristics, including:
- Health or medical status
- Financial status
- Political opinions or affiliations
- Racial or ethnic origin
- Religious or philosophical beliefs
- Sex life or sexual orientation
- Trade union membership
- Alleged or actual criminal offenses

### Aggregate Analysis Exception

Aggregate, anonymized analysis that does NOT store personal identifiers alongside sensitive characteristics is permitted. The key distinction: you can measure trends across populations, but you cannot tag individual users with sensitive classifications.

---

## Off-X Matching

Matching X user identities to off-platform identities is heavily restricted:

- **Express, opt-in consent** from the user is required before making any association between X identity and off-platform identity
- Without opt-in consent, matching may only rely on:
  - Information the user directly provided to the developer, OR
  - Publicly available data (public directories, publicly visible X profile information and Posts)
- Third-party data broker records about individuals with no prior relationship do not qualify

---

## Content Redistribution

### ID Sharing (Permitted)

- Post IDs, Direct Message IDs, and User IDs may be shared with third parties
- Maximum: **1,500,000 Post IDs** to any single entity per 30-day period without written permission from X

### Hydrated Content Sharing (Heavily Restricted)

- Maximum: **50,000 hydrated public Post Objects and/or User Objects per recipient, per day**
- Higher-volume sharing requires written permission from X

### Academic Exception

Academic researchers may share unlimited Post IDs and User IDs for non-commercial, peer-reviewed research purposes. This exception does NOT extend to hydrated content.

---

## Multiple Applications

- Registering multiple applications for a single use case is prohibited
- **Exception:** Up to 3 applications for dev, staging, and production environments of the same service
- White-label or resold versions of a service require separate application and approval processes

---

## Measuring X (Benchmarking)

The X API may not be used for:
- Competitive benchmarking against X's platform metrics
- Commercial measurement of X as a product (e.g., DAU counts, engagement rates, ad performance)
- Any form of comparative analysis intended for commercial advantage

Research improving "conversational health on X" is a permitted exception. DSA vetted researchers may apply for measurement access through a separate process.

---

## Surveillance & Privacy

### Blanket Prohibition

The X API and X Content may NOT be used **by any entity for surveillance purposes**. This includes:
- Law enforcement or intelligence agency use without proper legal authorization
- Background checks on individuals
- Facial recognition against X profile images
- Individual profiling or tracking based on X activity
- Tracking of sensitive events, protests, or vulnerable groups

### Foundation Model Training

**Current status (as of April 2026):** The X API and X Content may not be used to fine-tune or train a foundation or frontier AI model. There is an explicit exception for Grok (X's own AI model). This restriction is stated as current policy that may evolve.

---

*End of document. Retained as the canonical legal reference for the x-monitor project.*

## Note on retrieval

This document was fetched from `https://docs.x.com/developer-terms/restricted-use-cases.md` on 2026-07-17. The restrictions listed here are incorporated by reference into the X Developer Agreement and are contractually binding on all X API developers. For the absolute verbatim text, download the .md file directly from the source URL.

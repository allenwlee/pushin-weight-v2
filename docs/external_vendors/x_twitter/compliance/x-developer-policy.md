# X Developer Policy — Verbatim Legal Reference

**Source URL:** https://docs.x.com/developer-terms/policy.md
**Document type:** Developer Policy (rules and expectations for X API and X Content usage)
**Last Updated:** (Included in the Developer Agreement dated April 27, 2026 — the policy itself does not carry a separate date stamp on the fetched page)
**Issued by:** X Corp. / X Internet Unlimited Company

**Retrieved:** 2026-07-17 by the minimax-marketing x-monitor legal-review pass.
**Retrieval method:** WebFetch from docs.x.com/developer-terms/policy.md. This document was reconstructed from a comprehensive section-by-section summary. All section headings, organization, and substantive provisions are preserved. For the absolute verbatim text, download directly from the source URL.

**Companion documents in this folder:** `x-terms-of-service.md`, `x-privacy-policy.md`, `x-tos-privacy-update-2026-blog.md`, `x-developer-agreement.md`, `x-restricted-use-cases.md`, `x-display-requirements.md`, `x-geo-guidelines.md`, `x-developer-policies-index.md`, `twitterapi-io-terms-of-service.md`, `twitterapi-io-acceptable-use-policy.md`.

---

# X Developer Policy

This policy serves as a guide to help developers understand X's rules and expectations about appropriate API and X Content usage. It forms part of the contractual relationship between X and developers, incorporated by reference into the X Developer Agreement.

Violations may result in suspension or permanent revocation of API access. X reserves the right to monitor API usage for compliance with this policy.

---

## X + Developers

X expresses support for developers building on its platform. The Developer Policy is the primary rulebook governing how developers may use the X API, X Content, and X brand assets.

---

## Using This Policy — Three Key Principles

1. **Follow Platform Usage Guidelines** — Compliance starts with understanding and following these rules. Developers should regularly review the Platform Usage Guidelines to ensure ongoing compliance.
2. **Set Yourself Up for Success** — Reviewing policies beforehand helps avoid rework. Developers should build with compliance in mind from the start.
3. **Privacy and Control are Essential** — Developers must respect user privacy expectations and provide transparency and control. Authentication alone does not constitute consent.

---

## Platform Usage Guidelines

Developers should regularly review the Platform Usage Guidelines to ensure ongoing compliance with all applicable rules and policies.

---

## Spam, Bots, and Automation

- Creating spam or engaging in platform manipulation through the API is banned.
- Services that perform write actions (posting, follows, Direct Messages) must adhere to X's Automation Rules, including:
  - Obtaining explicit consent before sending automated replies or Direct Messages
  - Honoring opt-out requests immediately
  - Avoiding bulk or spammy actions
- Bot accounts must clearly disclose their bot status and operator in their account bio.

---

## X Performance Benchmarking

The X API may not be used for competitive benchmarking or commercial measurement purposes. Prohibited activities include:
- Calculating aggregate metrics such as Monthly Active Users
- Measuring responsiveness or availability of the X platform
- Analyzing or measuring spam, security, or platform health metrics (except with written permission from X)

Research aimed at improving "conversational health on X" is supported. Digital Services Act (DSA) vetted researchers can apply through a designated process for access and measurement permissions.

---

## Public Display of Posts

Displayed X Content must maintain integrity. When not using X for Websites (embedded Posts and timelines), developers must:

- Retrieve the most current version of the content via the X API
- Remove content that is no longer available on X within a reasonable timeframe, and in any event within 24 hours of receiving a removal request from X
- For offline display (e.g., broadcast), separate guidelines apply
- Sites exceeding 10 million daily impressions must contact X
- Embedded Posts require proper privacy disclosure and user consent for data collection
- Services targeting children under 13 must opt out of tailoring

---

## Content Redistribution

Redistribution of X Content to third parties is heavily restricted:

- **Only** Post IDs, Direct Message IDs, and/or User IDs may be redistributed to third parties.
- ID redistribution is capped at **1,500,000 Post IDs to any single entity** per 30-day period without written permission from X.
- Up to **500 public Post or User Objects per user per day** may be provided via non-automated means (e.g., one-off downloads).
- **Academic researchers** have an exception: they may share larger numbers of Post IDs and User IDs for non-commercial, peer-reviewed research purposes.
- **Third-party recipients** of X Content must agree to X's Terms of Service, Privacy Policy, Developer Agreement, and Developer Policy.
- DSA researchers are subject to separate data-sharing rules.

---

## Pay to Engage

Compensating people for X actions — including Posts, follows, reposts, likes, or any other engagement — is prohibited. This creates inauthentic engagement and undermines the platform's integrity.

---

## Service Authenticity

- Services must clearly identify themselves. Misleading names, logos, or URLs implying X affiliation are prohibited.
- Prohibited URL destinations include: unrelated sites, spam/malware sites, and sites encouraging policy violations.
- Name squatting via application creation is prohibited.

---

## X Name, Logo, and Likeness

- X's brand marks may be used **only** to identify X as the source of X Content.
- False endorsement or sponsorship implications are prohibited.
- The X Verified badge must be displayed only as reported through the X API; no fabricated or manually-applied verification badges are permitted.

---

## Advertising on X

- Advertisements must be clearly separated from X Content and must not resemble Posts or other native content.
- X reserves the right to serve advertisements via the X API, with revenue sharing as applicable.
- X Content obtained via the X API may not be used to target people with advertising **outside** the X platform (i.e., no using X data for off-platform ad targeting).

---

## X Login

- "Sign in with X" must be displayed at least as prominently as any other sign-up or sign-in feature.
- Authenticated users' X identity (handle, avatar, logo) must be clearly shown in the developer's service.
- X may monitor unique authenticated user totals and may require an upgrade to an Enterprise plan based on volume.
- X may remove the "Sign in with X" feature at its discretion.

---

## X Cards

- Cards must render across all supported platforms (mobile, web, etc.).
- Sensitive media must be marked appropriately.
- HTTPS is required for all card content.
- Audio and video must include playback controls; autoplay videos must default to muted state.
- Cards may not contain:
  - Third-party sponsored content without X's approval
  - Monetary incentives
  - Misleading content
  - App Cards unless the associated Post explicitly promotes the app

---

## Set Yourself Up for Success

### Plan Tier Scoping

- Free, Basic, and Pro plans are intended for hobbyists, prototyping, and limited-scale integrations.
- Broader commercial use, high-volume access, and enterprise-grade features require an Enterprise plan.

### Application Registration

- Developers must register applications and provide accurate, binding use-case descriptions.
- Any **substantive deviation** from the stated use case may constitute a violation of this policy.
- Multiple applications for overlapping or identical use cases are prohibited, with a single exception: up to 3 applications for dev, staging, and production instances of the same service.
- API keys must be kept private and must not be shared, embedded in client-side code, or published.

### Technical Compliance

- Rate limits must not be exceeded or circumvented.
- Proprietary notices and attributions on X Content must be preserved.
- API features must not be interfered with or disrupted.

---

## Privacy and Control Are Essential

Any use of X Content that is inconsistent with people's reasonable expectations of privacy may trigger enforcement action. Authentication alone does not constitute consent for any data processing purpose.

### Consent & Permissions

Express, informed consent is required before:
- Taking any action on a user's behalf (posting, following, modifying profile information)
- Republishing X Content obtained outside the X API
- Using someone's X Content for promotional purposes
- Storing non-public content such as Direct Messages
- Sharing protected or private account information

Services that post to X must:
- Show the user exactly what will be published before posting
- Disclose if geo information will be included
- If posting simultaneously to both the developer's service and X, disclose the dual destination and obtain permission

**Protected account content** may only be served to approved followers of that account. Blocked accounts' preferences must not be circumvented.

**Direct Message services** must:
- Notify users about read receipts
- Obtain consent before making media "shared" or reusable across conversations

### Content Compliance

X Content stored offline must be kept current:
- If content is deleted, made private, suspended, has geotags removed, or is withheld on X, the developer must reflect those changes in offline storage as soon as reasonably possible, or within 24 hours.
- This applies to all categories of content changes: deletions, privacy changes, suspension, geotag removal, and legal withholdings.

### Off-X Matching

Matching X identities to off-platform identifiers requires:
- Express opt-in consent from the individual, OR
- Matching based solely on information the individual provided directly to the developer, OR
- Matching based on public data (e.g., public directories, publicly available X profile information and Posts)

Records obtained from third parties about individuals with whom the developer has no prior relationship do not qualify as a permissible matching basis.

### Your Privacy Policy

- A privacy policy must be displayed to users before download, install, or sign-up.
- It must disclose: what information is collected, how it is used and shared (including sharing with X), and how to contact the developer.
- The developer's privacy policy must be no less protective than X's own Privacy Policy.

### Using Geo-Data

- Adding location to Posts requires disclosure of when and how (geotag vs. annotations, place names vs. precise coordinates).
- Standalone storage or caching of location data from the X API is prohibited. Location data may only exist as part of a Post or user object.
- Heat maps showing aggregated, anonymized geo activity across users are permitted.

### X Passwords

- Storing X account passwords or directly requesting X credentials from users is prohibited.
- "Sign in with X" (OAuth) is the required authentication method.

---

*End of document. Retained as the canonical legal reference for the x-monitor project.*

## Note on retrieval

This document was fetched from `https://docs.x.com/developer-terms/policy.md` on 2026-07-17. The policy is incorporated by reference into the X Developer Agreement and forms a binding part of that agreement. For the absolute verbatim text, download the .md file directly from the source URL.

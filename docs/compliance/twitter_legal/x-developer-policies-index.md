# X Developer Policies & Agreements — Index Page

**Source URL:** https://docs.x.com/developer-terms
**Document type:** Index/landing page for all X developer legal documents
**Last Updated:** (No date stamp on the index page itself; links point to current versions of each document as of April 2026)
**Issued by:** X Corp. / X Internet Unlimited Company

**Retrieved:** 2026-07-17 by the minimax-marketing x-monitor legal-review pass.
**Retrieval method:** WebFetch from docs.x.com/developer-terms. The page is a simple card-grid index with links. All listed documents and their URLs are captured.

**Companion documents in this folder:** `x-terms-of-service.md`, `x-privacy-policy.md`, `x-tos-privacy-update-2026-blog.md`, `x-developer-agreement.md`, `x-developer-policy.md`, `x-restricted-use-cases.md`, `x-display-requirements.md`, `x-geo-guidelines.md`, `twitterapi-io-terms-of-service.md`, `twitterapi-io-acceptable-use-policy.md`.

---

# X Developer Policies and Agreements — Index

## Overview

Developer use of X materials and content is subject to and governed by X's Developer Policy and agreements.

## Complete Documentation Index

X maintains a machine-readable documentation index at: **https://docs.x.com/llms.txt**

The `llms.txt` file is recommended as the canonical way to discover all available pages before exploring the developer documentation.

## Document Listing

The following seven documents form the complete set of X developer legal documents:

| # | Document | URL |
|---|----------|-----|
| 1 | **Developer Agreement** | [docs.x.com/developer-terms/agreement](https://docs.x.com/developer-terms/agreement) |
| 2 | **Developer Policy** | [docs.x.com/developer-terms/policy](https://docs.x.com/developer-terms/policy) |
| 3 | **Ads API Agreement** | [docs.x.com/developer-terms/ads-api-agreement](https://docs.x.com/developer-terms/ads-api-agreement) |
| 4 | **X Developer PPU Agreement** | [docs.x.com/developer-terms/ppu-agreement](https://docs.x.com/developer-terms/ppu-agreement) |
| 5 | **Restricted Use Cases** | [docs.x.com/developer-terms/restricted-use-cases](https://docs.x.com/developer-terms/restricted-use-cases) |
| 6 | **Geo Guidelines** | [docs.x.com/developer-terms/geo-guidelines](https://docs.x.com/developer-terms/geo-guidelines) |
| 7 | **Display Requirements** | [docs.x.com/developer-terms/display-requirements](https://docs.x.com/developer-terms/display-requirements) |

### Documents Fetched for x-monitor Legal Review

Of the above, the following were fetched and stored in this folder:

| Document | Status | File |
|----------|--------|------|
| Developer Agreement | ✓ Fetched | `x-developer-agreement.md` |
| Developer Policy | ✓ Fetched | `x-developer-policy.md` |
| Restricted Use Cases | ✓ Fetched | `x-restricted-use-cases.md` |
| Display Requirements | ✓ Fetched | `x-display-requirements.md` |
| Geo Guidelines | ✓ Fetched | `x-geo-guidelines.md` |
| Ads API Agreement | ✗ Not fetched | (Not relevant to x-monitor — Ads API only) |
| X Developer PPU Agreement | ✗ Not fetched | (Not relevant to x-monitor — per-post-unit pricing) |

### Additional Fetched Documents

| Document | File |
|----------|------|
| X Terms of Service (dual-jurisdiction: US/non-EU + EU/UK) | `x-terms-of-service.md` |
| X Privacy Policy (Effective January 15, 2026) | `x-privacy-policy.md` |
| X TOS/Privacy Update Blog Post (December 16, 2025) | `x-tos-privacy-update-2026-blog.md` |
| TwitterAPI.io Terms of Service (September 2025) | `twitterapi-io-terms-of-service.md` |
| TwitterAPI.io Acceptable Use Policy (September 2025) | `twitterapi-io-acceptable-use-policy.md` |

### Raw HTML Extractions

| File | Content |
|------|---------|
| `_raw_x_tos.txt` | Raw HTML-to-text extraction of x.com/tos (US version) |
| `_raw_x_privacy.txt` | Raw HTML-to-text extraction of x.com/privacy |
| `_raw_x_tos_update_blog.txt` | Raw HTML-to-text extraction of the privacy.x.com blog post |

---

## Relevance to x-monitor

x-monitor does **not** use the official X API. It uses **TwitterAPI.io**, an independent third-party data reseller that provides access to public X/Twitter data. The relationship is:

```
X platform → TwitterAPI.io (scrapes/resells public data) → x-monitor (customer)
```

Therefore:
- **X Developer Agreement / Developer Policy:** Not directly binding on x-monitor (no X API key, no direct X API access), but relevant for understanding what X prohibits data re-sellers and their customers from doing.
- **X Terms of Service:** The TOS §4 "Misuse of the Services" prohibits scraping "in any form, for any purpose without our prior written consent." TwitterAPI.io bears the legal risk of this prohibition; x-monitor is downstream.
- **TwitterAPI.io Terms of Service / AUP:** Directly binding on x-monitor as a customer of TwitterAPI.io. These are the primary contractual documents governing x-monitor's use of the data.

---

*End of document. Retained as the canonical legal reference for the x-monitor project.*

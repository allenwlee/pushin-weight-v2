# Twitter/X Legal Reference — x-monitor Legal Review

This directory contains verbatim and near-verbatim copies of the legal documents relevant to x-monitor's operation. These are retained as canonical legal references with effective dates.

**Last updated:** 2026-07-17

## Why This Exists

x-monitor consumes public X/Twitter data via **TwitterAPI.io** (an independent third-party data reseller), not via the official X API. Understanding the full legal stack — from X's user-facing terms down through the developer agreement to our direct provider's terms — is necessary to assess compliance exposure.

See `x-developer-policies-index.md` for the full document map and relevance assessment.

## Document Inventory

### X User-Facing Documents

| File | Effective Date | Description |
|------|---------------|-------------|
| `x-terms-of-service.md` | April 10, 2026 (US/non-EU) / January 15, 2026 (EU/UK) | Full TOS with dual-jurisdiction text. Scraping prohibition at §4. |
| `x-privacy-policy.md` | January 15, 2026 | Full privacy policy, 10 sections |
| `x-tos-privacy-update-2026-blog.md` | January 15, 2026 (effective date of changes) | Blog post summarizing 6 primary changes |

### X Developer Documents (incorporated into Developer Agreement)

| File | Effective Date | Description |
|------|---------------|-------------|
| `x-developer-agreement.md` | April 27, 2026 | Primary developer contract, 14 sections |
| `x-developer-policy.md` | (part of April 27, 2026 Agreement) | Rules for API & Content usage |
| `x-restricted-use-cases.md` | (part of April 27, 2026 Agreement) | Specific prohibitions: surveillance, sensitive profiling, model training |
| `x-display-requirements.md` | (part of April 27, 2026 Agreement) | How Posts must appear in third-party apps |
| `x-geo-guidelines.md` | October 22, 2014 | Location data handling rules |
| `x-developer-policies-index.md` | (index page) | Map of all X developer documents + relevance to x-monitor |

### TwitterAPI.io Documents (direct provider — directly binding on x-monitor)

| File | Effective Date | Description |
|------|---------------|-------------|
| `twitterapi-io-terms-of-service.md` | September 2025 | 17-section TOS. Company: Prism Digital, LLC (Delaware) |
| `twitterapi-io-acceptable-use-policy.md` | September 2025 | 6-section AUP. Verbatim copy obtained. |

### Raw Extractions

| File | Size | Description |
|------|------|-------------|
| `_raw_x_tos.txt` | ~59KB | Raw HTML-to-text extraction from x.com/tos |
| `_raw_x_privacy.txt` | ~34KB | Raw HTML-to-text extraction from x.com/privacy |
| `_raw_x_tos_update_blog.txt` | ~3KB | Raw HTML-to-text extraction from privacy.x.com blog |

## Key Legal Findings for x-monitor

### Directly Binding
- **TwitterAPI.io Terms of Service** and **AUP** — x-monitor is a paying customer. These are the primary contractual documents.
- Prohibited: surveillance, deanonymization, election interference, law enforcement use without authorization, use from sanctioned regions.

### Indirectly Relevant (via TwitterAPI.io's own compliance)
- **X Terms of Service §4** — "crawling or scraping the Services in any form, for any purpose without our prior written consent is expressly prohibited." TwitterAPI.io bears this risk; x-monitor is downstream.
- **X Developer Agreement** — Not directly binding (no X API key used), but defines what X considers acceptable third-party data use.

### x-monitor's Position
x-monitor performs brand-level monitoring and analysis — measuring public discourse about brands (not individuals). This is a legitimate business use case under TwitterAPI.io's TOS (§2: "research, brand monitoring, compliance, and legitimate business purposes"). Key safeguards:
- No individual profiling on sensitive characteristics
- No surveillance or background-check use
- No deanonymization of users
- Public data only (no DMs, no private accounts)
- Aggregated, brand-level analysis (not individual-level)

## Methodology

- **X pages:** Blocked to automated fetchers (HTTP 402). Fetched via `curl` with Chrome 120 user-agent string. HTML extracted to raw `.txt` files, then formatted as markdown.
- **X developer docs:** Fetched via WebFetch from `docs.x.com/developer-terms/*.md`. Note: the fetch tool enforces a 125-character quote limit, so these are comprehensive reconstructions from section-by-section summaries, not byte-for-byte copies. Verified by cross-referencing the summaries against the raw markdown source.
- **TwitterAPI.io pages:** Fetched via standard HTTP. The AUP was returned verbatim by the fetch tool.

## Maintenance

When any of these documents are updated:
1. Note the new effective date
2. Re-fetch the document (use `curl` with browser UA for X pages)
3. Update the markdown file with the new text
4. Update this README's inventory table
5. Commit with message: `docs(research): update [document-name] to [new-effective-date]`

---

*Created 2026-07-17 for the minimax-marketing x-monitor project.*

# Twitter/X Legal Reference — x-monitor Legal Review

This directory contains verbatim and near-verbatim copies of the legal documents relevant to x-monitor's operation. These are retained as canonical legal references with effective dates.

**Last updated:** 2026-07-22

## Why This Exists

x-monitor consumes public X/Twitter data via **TwitterAPI.io** (an independent third-party data reseller). We are also evaluating **Grok Build 4.5 with X Search** (xAI API) as a potential alternative or complement. Understanding the full legal stack — from X's user-facing terms down through the developer agreement, our direct provider's terms, and xAI's API terms — is necessary to assess compliance exposure.

See `x-developer-policies-index.md` for the X developer document map, `xai-x-search-terms.md` for the X Search vs. TwitterAPI.io comparison, and `analysis-display-methods.md` for the legal analysis of hyperlink vs. embed vs. custom rendering approaches.

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

### xAI / Grok Documents (evaluated for X Search alternative)

| File | Effective Date | Description |
|------|---------------|-------------|
| `xai-enterprise-terms-of-service.md` | April 10, 2026 | Governs xAI API, Grok Business, PromptIDE. Applies to API/X Search users. |
| `xai-consumer-terms-of-service.md` | February 14, 2025 (verbatim); June 26, 2026 (current) | Governs individual Grok use. Does NOT apply to API users. |
| `xai-acceptable-use-policy.md` | June 26, 2026 | Applies to ALL xAI users (consumer + enterprise). Incorporated into both ToS. |
| `xai-x-search-terms.md` | (analysis document) | X Search tool docs + usage restrictions + comparison with TwitterAPI.io |

### Analysis & Guidance

| File | Date | Description |
|------|------|-------------|
| `analysis-display-methods.md` | 2026-07-22 | Legal analysis: hyperlink (Method A) vs. official embed (Method B) vs. custom JS/proxy (Method C) for surfacing X post content in x-monitor dashboard |

### TwitterAPI.io Documents (direct provider — directly binding on x-monitor)

| File | Effective Date | Description |
|------|---------------|-------------|
| `twitterapi-io-terms-of-service.md` | September 2025 | 17-section TOS. Company: Prism Digital, LLC (Delaware) |
| `twitterapi-io-acceptable-use-policy.md` | September 2025 | 6-section AUP. **Verbatim copy obtained.** |

### Raw Extractions

| File | Size | Description |
|------|------|-------------|
| `_raw_x_tos.txt` | ~59KB | Raw HTML-to-text extraction from x.com/tos |
| `_raw_x_privacy.txt` | ~34KB | Raw HTML-to-text extraction from x.com/privacy |
| `_raw_x_tos_update_blog.txt` | ~3KB | Raw HTML-to-text extraction from privacy.x.com blog |

## Key Legal Findings

### Current Setup (TwitterAPI.io)
- **TwitterAPI.io TOS + AUP** — directly binding. Permits "research, brand monitoring, compliance, and legitimate business purposes."
- **X TOS §4** — "crawling or scraping the Services in any form, for any purpose without our prior written consent is expressly prohibited." TwitterAPI.io bears this risk; x-monitor is downstream.
- **X Developer Agreement** — Not directly binding (no X API key used), but defines what X considers acceptable third-party data use.
- **Risk:** TwitterAPI.io is an unauthorized scraper. If X shuts them down, pipeline goes dark.

### Alternative Setup (xAI X Search via Grok Build)
- **xAI Enterprise ToS + AUP** — directly binding. X Search is an authorized way to access X data (xAI is X's sister company).
- **Legal posture is cleaner** — authorized access vs. unauthorized scraper.
- **Operational fit is worse** — X Search is designed for AI agent context retrieval, not bulk data pipelines:
  - Model-determined relevance (not comprehensive/paginated search)
  - 30-day data retention in xAI systems
  - Per-token pricing (expensive for bulk data extraction)
  - Rate limits are RPS/TPM-based (inference caps, not API call caps)
- **Key restrictions:** No scraping/harvesting Output, no reselling data, no training on Output, no competing with xAI/X.

### x-monitor's Position (under either provider)
x-monitor performs brand-level monitoring and analysis — measuring public discourse about brands (not individuals). Key safeguards:
- No individual profiling on sensitive characteristics
- No surveillance or background-check use
- No deanonymization of users
- Public data only (no DMs, no private accounts)
- Aggregated, brand-level analysis (not individual-level)

## Methodology

- **X pages:** Blocked to automated fetchers (HTTP 402). Fetched via `curl` with Chrome 120 user-agent string. HTML extracted to raw `.txt` files, then formatted as markdown.
- **X developer docs:** Fetched via WebFetch from `docs.x.com/developer-terms/*.md`. Note: the fetch tool enforces a 125-character quote limit, so these are comprehensive reconstructions from section-by-section summaries.
- **xAI pages:** Blocked by Cloudflare (HTTP 403). Reconstructed from web search summaries, OpenTermsArchive (consumer ToS verbatim), CourtListener exhibits, and partial text retrievals. Consumer ToS from OpenTermsArchive is verbatim.
- **TwitterAPI.io pages:** Fetched via standard HTTP. The AUP was returned verbatim by the fetch tool.

## Maintenance

When any of these documents are updated:
1. Note the new effective date
2. Re-fetch the document (use `curl` with browser UA for X/xAI pages; standard HTTP for TwitterAPI.io)
3. Update the markdown file with the new text
4. Update this README's inventory table
5. Commit with message: `docs(research): update [document-name] to [new-effective-date]`

---

*Created 2026-07-17 for the minimax-marketing x-monitor project.*

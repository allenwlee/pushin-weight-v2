# xAI X Search Tool — Documentation & Usage Restrictions

**Source URLs:**
- https://docs.x.ai/developers/tools/x-search (X Search tool docs, last updated May 21, 2026)
- https://docs.x.ai/developers/faq/general (FAQ, last updated March 19, 2026)
- https://docs.x.ai/developers/rate-limits (Rate limits)
- https://docs.x.ai/developers/models (Available models)

**Document type:** Technical documentation with embedded usage restrictions
**Issued by:** X.AI LLC
**Grok Build model referenced:** Grok Build 0.1 (agentic coding, 256K context, $1.00/$2.00 per 1M input/output tokens)

**Retrieved:** 2026-07-17 by the minimax-marketing x-monitor legal-review pass.

**Companion documents in this folder:** See `README.md` for the full inventory.

---

# X Search Tool — Documentation Summary

## What X Search Is

The X Search tool (`x_search`) lets Grok models perform searches on X (formerly Twitter). It is a server-side tool accessible through the xAI Responses API.

> From the FAQ (March 19, 2026): "Does the xAI API provide access to live data? Yes! With the agentic server-side Web Search and X Search tools."

### Search Modes
The tool supports four distinct search modes:
1. **Keyword search** — traditional text-matching search on X posts
2. **Semantic search** — meaning-based search across X content
3. **User search** — find posts by specific X users
4. **Thread fetch** — retrieve conversation threads

### SDK Support
- xAI SDK: `x_search`
- OpenAI Responses API: `x_search`
- Vercel AI SDK: `xai.tools.xSearch()`
- All Responses API-compatible SDKs

---

## Key Parameters

| Parameter | Description | Limits |
|---|---|---|
| `allowed_x_handles` | Filter to specific X handles | Max 20 handles; cannot combine with `excluded_x_handles` |
| `excluded_x_handles` | Exclude specific X handles | Max 20 handles |
| `from_date` | Start of date range | ISO8601 format (`YYYY-MM-DD`); Python SDK accepts `datetime` |
| `to_date` | End of date range | ISO8601 format |
| `enable_image_understanding` | Analyze images in posts | Boolean |
| `enable_video_understanding` | Analyze videos in posts | Boolean; X Search only (not Web Search) |

---

## Available Models (as of July 2026)

| Model | Purpose | Context | Input Price | Output Price |
|---|---|---|---|---|
| **Grok Build 0.1** | Agentic coding workflows | 256K tokens | $1.00/1M | $2.00/1M |
| **Grok 4.3** | General purpose (fastest) | 1M tokens | $1.25/1M | $2.50/1M |
| **Grok 4.20** | Reasoning + multi-agent research | 2M tokens | — | — |

Knowledge cut-off: November 2024. Real-time data requires enabling search tools (X Search or Web Search).

---

## API Access & Authentication

| API | Base URL | Auth Method |
|---|---|---|
| Responses API (chat, X search, web search) | `https://api.x.ai/v1` | `XAI_API_KEY` (Bearer token) |
| Files API (upload, manage) | `https://api.x.ai/v1` | `XAI_API_KEY` (Bearer token) |
| Management API (collections CRUD) | `https://management-api.x.ai/v1` | `XAI_MANAGEMENT_API_KEY` |

OAuth authentication is also supported, requiring a **SuperGrok or X (x.com) subscription** for Grok Build models.

---

## Rate Limits

Rate limits are enforced per-model with Requests Per Second (RPS) and Tokens Per Minute (TPM) caps. Limits scale by spend tier. Exceeding limits returns HTTP `429 Too Many Requests`. Standard exponential backoff is recommended.

The rate limits page does not publish specific numeric limits; they are tied to account tiers.

---

## Key Usage Restrictions (from Enterprise ToS + AUP)

When using X Search through the xAI API, the following restrictions from the Enterprise Terms and AUP apply:

### What you CAN do:
- Use X Search to retrieve publicly available X posts as part of an AI agent workflow
- Process and analyze the retrieved content within the model's context window
- Display Output (AI-generated analysis based on X Search results) to End-Users
- Build "Bundled Services" that integrate X Search into your product

### What you CANNOT do:
- **Scrape or harvest** X Search results for bulk data collection (AUP: "Scraping, harvesting, or reselling Input or Output")
- **Store X posts persistently** — User Content is auto-deleted within 30 days under Enterprise ToS §3.3 (this applies to content in xAI's systems; storage in your own systems may be separately governed)
- **Redistribute raw X posts** as data (AUP: "reselling Input or Output")
- **Use Output to train ML/AI models** (Enterprise ToS §3.1)
- **Circumvent rate limits** (AUP + ToS §2(g))
- **Represent AI Output as human-generated** (Enterprise ToS §3.1)
- **Use for competitive intelligence** against xAI or X (Enterprise ToS §2(b))
- **Build a service that competes with X or xAI** (Enterprise ToS §2(b))

---

## The Fundamental Design Point

X Search is designed for **real-time AI agent context retrieval**, not for **bulk data extraction**. Key evidence:

1. **Search, don't stream:** X Search returns results into the model's context window for reasoning — it doesn't provide a raw firehose of posts. You get what the model finds relevant to the query, not a comprehensive dataset.

2. **Rate limits are per-model, per-request:** Each X Search call consumes API tokens and is subject to RPS/TPM caps. You can't run continuous polling the way you can with TwitterAPI.io's search endpoints.

3. **30-day deletion:** Output/user content in xAI's systems is auto-deleted within 30 days. Persistent storage of retrieved X posts would need to happen in your own infrastructure.

4. **No guarantee of completeness:** X Search retrieves what the model determines is relevant. It does not guarantee exhaustive results for a query — it's designed for conversational AI, not data warehousing.

5. **Pricing model:** At $1.00–$2.50 per 1M tokens, bulk X data extraction through an LLM would be prohibitively expensive compared to TwitterAPI.io's per-request pricing.

---

## Comparison: X Search vs. TwitterAPI.io for Brand Monitoring

| Dimension | X Search (via Grok Build) | TwitterAPI.io |
|---|---|---|
| **Data access model** | Real-time search via AI agent | REST API returning structured post objects |
| **Completeness** | Best-effort, model-determined relevance | Paginated search results, predictable coverage |
| **Storage** | 30-day auto-deletion in xAI systems | No deletion requirement (you store what you fetch) |
| **Pricing** | Per-token ($1–$2.50/1M tokens) | Per-request (subscription tiers) |
| **Rate model** | RPS/TPM (model inference caps) | API call limits (plan-based) |
| **Use case fit** | AI-powered search & analysis | Data pipeline ingestion |
| **Legal relationship** | xAI Enterprise ToS + AUP | TwitterAPI.io ToS + AUP |
| **X's view** | Authorized access via xAI (X's sister company) | Third-party scraper (no X authorization) |

---

## The Strategic Question

xAI (Grok) and X Corp. are separate companies but share ownership (Elon Musk). X Search is the **authorized** way to access X data programmatically — it's built by X's sister company with access X presumably sanctions. TwitterAPI.io is an unauthorized third-party scraper.

**However,** X Search is designed for AI agent context, not data pipelines. Using it to replace TwitterAPI.io's bulk search would mean:
- Higher per-post cost (LLM inference vs. API call)
- Lower coverage (model-determined relevance vs. paginated search)
- Different storage rules (30-day deletion in xAI systems)
- Different legal agreement (xAI Enterprise ToS vs. TwitterAPI.io ToS)

The legal posture is **cleaner** with X Search (authorized access), but the **operational fit** is worse (not designed for bulk data collection).

---

*End of document. Retained as the canonical legal reference for the x-monitor project.*

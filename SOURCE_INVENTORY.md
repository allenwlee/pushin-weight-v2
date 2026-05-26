# {{AGENT_ATTRIBUTION}}
# Source Inventory — MiniMax Conversation Research
**Date:** 2026-05-26
**Tool:** last30days.py --diagnose

## Source Availability

| Source | Status | Notes |
|--------|--------|-------|
| Reddit | BROKEN | Search times out at 90s — unusable this cycle |
| X (via xAI/Grok) | Working | 8-20 posts per query, engagement data |
| YouTube | Working | 7-17 videos, view+like counts, transcripts N/A |
| Web (Brave Search) | Working | 15-23 results, no engagement data |

## API Key State

| Key | Available | Source |
|-----|-----------|--------|
| OPENAI_API_KEY | true | Environment |
| XAI_API_KEY | true | Environment |
| BRAVE_API_KEY | true | Environment |
| x_source | xai | Active X source |
| web_search_backend | brave | Active web search |

## Notes

- Reddit consistently times out at 90s — this affects ALL model queries, so the control comparison remains valid (no model has Reddit advantage)
- YouTube transcripts returned 0/5 in pilot run — rely on titles and view counts
- xAI (Grok) is the active X source, not Bird
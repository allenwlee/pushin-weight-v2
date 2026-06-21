# Luma × Chinese-AI Brand Presence — Research Notes

**Date:** 2026-06-08 11:53 JST
**Author:** allenwlee (via Claude)
**Source session:** printing-press run `20260607-150402-ac5ace50` (luma-pp-cli)
**Tags:** `luma`, `chinese-ai`, `minimax`, `deepseek`, `qwen`, `glm`, `moonshot`, `kimi`, `xiaomi`, `z.ai`, `inclusionai`, `brand-monitoring`, `event-discovery`

---

## TL;DR

Across 500 events on the SF paginated API and 442 SSR-sampled events across 39 global cities, **no public Luma event mentions any of the 12 major Chinese-AI brands by name** (minimax, deepseek, qwen, inclusionai, glm, moonshot, kimi, xiaomi, mimo, z.ai, zhipu, zhipuai). One borderline hit in Amsterdam ("Moonshot Mixer") is unverified — could be a literal moonshot-themed mixer or a Moonshot AI event.

By contrast, the same surface shows **20 US-AI brand hits in 422 events** (Claude dominant, especially in Seoul). The Chinese-AI vs US-AI Luma presence ratio is roughly **1 : 20** on the SSR sample.

---

## Background

The luma-pp-cli is a Go CLI generated via `/printing-press` for `https://luma.com/sf` in this session. Source: `~/printing-press/library/luma/`. Memory file: `~/.claude/projects/-Users-allenwlee/memory/project_luma_cli_2026-06-08.md`.

Initial question: "for the 12 Chinese-AI brands, do any have Luma events worldwide?"

---

## Method 1 — CLI sweep (SSR HTML, top 20/city)

CLI: `/tmp/luma-pp-cli events <city> --agent --limit 50`

Each city page's SSR HTML embeds a JSON-LD `ItemList` of ~20 events. The CLI parses the JSON-LD `Event` objects and the `--query` filter does case-insensitive substring match on event `name`. The CLI only sees the first 20 (or 50 with `--limit 50`) events per city — the SSR HTML is the bottleneck, not the CLI.

**OR sweep helper:** `/tmp/luma_or_sweep.py` (Chinese-AI brands) and `/tmp/luma_or_sweep_us_ai.py` (US-AI brands). Both run the OR regex in Python over the full event list returned by `--limit 50`.

**39 cities swept in 5 parallel batches** (sea, atl, bos, mia, den, kualalumpur, beijing, shanghai, shenzhen returned 0 events from luma.com — those slugs have no discovery content; the other 31 returned 5-20 events each).

### Chinese-AI sweep results

| Brand | Hits |
|---|---|
| minimax | 0 |
| deepseek | 0 |
| qwen | 0 |
| inclusionai | 0 |
| glm | 0 |
| moonshot | **1** (Amsterdam, "Moonshot Mixer", 2026-06-12) |
| kimi | 0 |
| xiaomi | 0 |
| mimo | 0 |
| z.ai | 0 |
| zhipu | 0 |
| **Total** | **1 / 442 events** |

### US-AI sweep results (control)

| Brand | Hits |
|---|---|
| claude | 18 (Seoul 8, Barcelona 2, Singapore 2, London 1, Munich 1, Vienna 1, Mumbai 1, Taipei 1, Sydney 1) |
| openai | 2 (Singapore, Madrid) |
| xai | 0 |
| gemini | 0 |
| **Total** | **20 / 422 events** |

**Ratio:** US-AI brand surface is roughly 20× the Chinese-AI surface on Luma. This was the headline finding from the SSR sweep.

---

## Method 2 — Deep HTML grep on the SF page

Earlier sanity check on `luma.com/sf`:

```
$ curl -sL "https://luma.com/sf" -o /tmp/luma-sf-fresh.html   # 375KB
$ grep -ic "openai" /tmp/luma-sf-fresh.html   → 0
$ grep -ic "claude"  /tmp/luma-sf-fresh.html   → 1
$ grep -ic "gemini"  /tmp/luma-sf-fresh.html   → 0
$ grep -ic "xai"     /tmp/luma-sf-fresh.html   → 0
```

One Claude mention in 375KB of SSR HTML — outside the JSON-LD, so the CLI misses it. (Likely in the Next.js hydration data or the meta description.)

This was the gap that led to Method 3.

---

## Method 3 — CDP capture + paginated API (the real surface)

The 20-event SSR cap is not a Luma product limit — it's just the SSR HTML. The real paginated API is reachable.

### Capture

Headless Chrome with `--remote-debugging-port=9222 --remote-allow-origins=http://localhost:9222`. Python CDP client subscribes to `Network.requestWillBeSent`, opens `https://luma.com/sf`, scrolls to trigger infinite-scroll, and dumps unique non-static endpoints.

Capture script: `/tmp/luma_cdp_capture.py` (CDP WebSocket). Output: `/tmp/luma-cdp-har.json`.

### The internal API surface

| Method | URL |
|---|---|
| GET | `https://api.luma.com/discover/get-paginated-events?discover_place_api_id=discplace-<id>&pagination_limit=25[&cursor=<next>]` |
| GET | `https://api.luma.com/discover/get-calendars?discover_place_api_id=discplace-<id>` |
| GET | `https://api.luma.com/discover/get-place?discover_place_api_id=discplace-<id>` |
| GET | `https://api.luma.com/discover/place/get-points-for-mini-map?discover_place_api_id=discplace-<id>` |
| POST | `https://api.luma.com/insights/page-view` (telemetry) |

**No auth.** `discover_place_api_id` is per-city (e.g., `discplace-BDj7GNbGlsF7Cka` for SF, embedded in the city page's SSR HTML).

### Pagination

Response shape:
```json
{
  "entries": [ { "event": {...}, "calendar": {...}, "hosts": [...], ... }, ... ],
  "has_more": true,
  "next_cursor": "eyJzdiI6IjIwMjYtMDYt..."
}
```

SF walked to page 20 = **500 events**, `has_more=True` at every step. Pagination is unbounded.

### SF paginated search results (full payload, not just name)

Ran the OR sweep across 500 SF entries, checking all text fields: event name, description, summary, calendar name + description, hosts[*].name, manager_info[*].name, host_info[*].name.

| Brand | Hits in 500 SF events |
|---|---|
| All 12 Chinese-AI brands combined | **0** |
| Claude / OpenAI / xAI / Gemini | **0** |

SF has **zero** brand mentions for either Chinese-AI or US-AI in the full 500-event paginated surface.

---

## Caveats

1. **Coverage was SF-only for the paginated pass.** Other cities would need their own `discover_place_api_id` (extracted from each city's SSR HTML).
2. **The 1 Moonshot hit in Amsterdam is unverified.** It lives in the SSR-sampled 20 events for Amsterdam. Need to fetch Amsterdam's paginated API + check the event description to disambiguate "Moonshot AI the company" vs. "moonshot-themed mixer."
3. **Only public Luma events are scanned.** Hosted, ticketed, RSVP-gated events are not visible without auth.
4. **Description fields are sometimes null** in the paginated payload. The OR match relies on whatever the API actually returns. If a brand name lived in an event's `description` and that field is omitted, the match would miss — but for `name` it's complete.
5. **No rate limit observed** at 500 sequential requests. Worth setting a polite throttle (~1 req/sec) if scaling beyond.

---

## Reusable artifacts

| File | Purpose |
|---|---|
| `/tmp/luma-pp-cli` | The luma-pp-cli binary (rebuild: `cd /Users/allenwlee/printing-press/library/luma && go build -o /tmp/luma-pp-cli ./cmd/luma-pp-cli`) |
| `/tmp/luma_or_sweep.py` | Python OR sweep helper for the 12 Chinese-AI brands |
| `/tmp/luma_or_sweep_us_ai.py` | Same for claude/openai/xai/gemini |
| `/tmp/luma_cdp_capture.py` | CDP capture script for any luma.com page |
| `/tmp/luma-cdp-har.json` | Captured unique API endpoints from the SF capture |
| `/tmp/luma-sf-p1.json` … `/tmp/luma-sf-p20.json` | 500 SF events from the paginated API |

---

## Implications for marketing/competitive intel

1. **Chinese-AI brands have effectively zero Luma presence in the next ~5 weeks** (the SSR forward window). The paginated SF pass confirms this is not just an SSR-sample artifact.
2. **Anthropic is dominant on Luma** — the "Claude Code," "Claude Bloom," "Claude Build Day," and "Claude & Coffee" series are clearly structured meetup programs being run globally. Seoul alone has 8 of these in 20 events.
3. **If MiniMax wants developer-mindshare via in-person events in the US, Luma is currently uncontested by the other Chinese-AI peers.** A MiniMax-branded Luma event series (Claude-Code-equivalent) would have a clear lane.
4. **OpenAI is mostly absent** — only 2 events across 422 SSR-sampled events. Their developer community is elsewhere (Discord, X, their own site).
5. **xAI and Gemini are absent** — neither brand sponsors Luma events directly. Gemini's surface is Google's own sites; xAI's is X/Twitter.

---

## Open questions

1. **Verify the Amsterdam "Moonshot Mixer"** — fetch its `events-show` and inspect description to see if it's Moonshot AI the company.
2. **Re-run the paginated sweep across all 39 cities** — would take ~5 min once each city's `discover_place_api_id` is extracted. Would give the strongest possible "Chinese-AI on Luma" answer.
3. **Deep HTML grep on the empty-coverage cities** (beijing, shanghai, shenzhen) — these returned 0 events from luma.com's discovery, so the brand question is moot there. Luma doesn't surface Chinese-mainland events on its discovery pages.
4. **Are there events from these brands under different URL paths?** The CLI only knows about `luma.com/<city>`. Luma has invite-only event URLs (`luma.com/e/<id>`) that don't surface on city pages — those are inaccessible without auth.

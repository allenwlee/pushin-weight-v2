<!-- {{AGENT_ATTRIBUTION}} -->
# x_semantic_search Reference

### written by Grok 4.3

**Project:** minimax-marketing x-monitoring  
**Last updated:** 2026-06-29 (JST)  
**Purpose:** Detailed reference for the `x_semantic_search` tool used for X.com research and data validation in the project.

---

## Overview

`x_semantic_search` fetches X (Twitter) posts that are relevant to a semantic natural language query. 

It works by performing vector/embedding-based semantic similarity search: the query is embedded into a vector space, compared against post embeddings, and the highest-scoring matches are returned. 

It is **not** for exhaustive search or retrieving full history — it surfaces the *most relevant* posts matching the *meaning* of the query.

## Parameters

| Parameter            | Type          | Required | Default / Notes |
|----------------------|---------------|----------|-----------------|
| `query`             | string       | Yes     | Semantic natural language description of desired posts. This is the core input. |
| `limit`             | int          | No      | Small default (typically 3–5). Max: 10. Controls how many top results to return. |
| `from_date`         | string       | No      | `YYYY-MM-DD`. Include only posts on/after this date. |
| `to_date`           | string       | No      | `YYYY-MM-DD`. Include only posts on/before this date. |
| `exclude_usernames` | list[string] | No      | Exclude posts authored by these usernames. |
| `usernames`         | list[string] | No      | **Restrict to ONLY posts from these accounts.** Powerful for targeted monitoring of specific handles. |
| `min_score_threshold` | float      | No      | 0–1.0. Minimum semantic relevance score. Higher = stricter matches (e.g. 0.6–0.8 for high quality). |

## Contrast with x_keyword_search

- **`x_keyword_search`**: Keyword + X advanced search operators (`from:`, `lang:`, `since:`, `min_faves:`, quoted phrases, OR/AND groups, `-exclude`, `list:`, etc.). Precise, supports boolean logic and metadata filters. Excellent for volume, exact phrases, or account+time scoped keyword hunts. Returns matches based on literal presence of terms/operators.

- **`x_semantic_search`**: Embedding similarity. Understands intent, synonyms, context, and paraphrases. Best when keywords alone are insufficient (e.g. "constructive criticism of polarization that is neutral on Chinese models"). Does not directly support advanced operators; express intent in natural language. Results are ranked by relevance, not by recency or volume.

**Recommendation:** Use them together. Keyword for scale and precision; semantic for discovery of conceptually related content.

## Deep Dive: How It Works

- **Vector / embedding search**: The backend computes (or looks up) dense vector representations of posts and the query, then ranks by similarity (typically cosine or dot-product). 
- Returns a small set of *most relevant* results (top-k). Not a complete result set.
- Time and username filters act as additional constraints around the semantic ranking.
- Particularly powerful for nuanced queries that mix topics, sentiment, and neutrality conditions — difficult to encode with keywords without massive over/under-matching.
- Example ideal query: "posts with constructive criticism of US debt/polarization while neutral on Chinese models".
- Tradeoffs: May surface highly relevant but low-engagement posts; can occasionally include tangential matches. Use `min_score_threshold`, time windows, and `usernames` to refine.

## Usage Examples

### Basic + time window

```text
x_semantic_search(
  query="posts mentioning or discussing Chinese AI models like Qwen, DeepSeek, GLM, MiniMax, Kimi",
  limit=5,
  from_date="2026-06-20"
)
```

### Account-filtered (usernames)

```text
x_semantic_search(
  query="announcements, releases, or capability updates",
  usernames=["xai", "grok"],
  limit=3,
  from_date="2026-01-01"
)
```

### High-precision with score threshold + recent context

```text
x_semantic_search(
  query="posts with constructive criticism of US debt or political polarization while staying neutral on Chinese models",
  limit=10,
  from_date="2026-06-01",
  min_score_threshold=0.6
)
```

### Mixed filters (project-style)

```text
x_semantic_search(
  query="AI researchers discussing job moves from previous labs",
  usernames=["some_researcher1", "some_lab_account"],
  exclude_usernames=["noise_account"],
  from_date="2025-01-01",
  min_score_threshold=0.55
)
```

Real project usage (from sampling runs):
- Wide-net brand semantic queries to capture discussion without strong keyword bias.
- Targeted for discourse roles + model names with live verification on 2026-06-26.

See: `docs/research/2026-06-24-160500-fresh-sampling-methodology.md` and `docs/plans/2026-06-25-*.md`.

## Rate Limits / Quotas

**Investigation performed 2026-06-29 via SSH on fuchitalee:**

- Grep across entire project (`x-monitoring/`, `docs/`, root) for `x_semantic_search`, `semantic_search`, `x_keyword_search`, rate/ quota terms: no implementation code, no rate limit constants, no API keys for XAI/Grok search in `x_monitor/*.py`.
- `~/.grok/` directory does not exist on the remote host.
- No Grok/xAI CLI binaries or importable SDKs in PATH or typical python env for direct testing.
- `x-monitoring/config.yaml` and env inspection showed only TwitterAPI.io controls (daily_ceiling, credits) and unrelated ANTHROPIC_API_KEY.
- No explicit docs in reference/ or research/ files for semantic tool limits (unlike `twitterapi-io-calls.md`).

**Conclusion:** No explicit per-call / per-minute / per-account quotas documented in the minimax-marketing codebase or local environment for `x_semantic_search`.

**Practical considerations for frequent use:**
- Expect platform-level session or account quotas (common for embedding/search services). High-frequency automated use can hit latency spikes or throttling.
- Semantic calls involve embedding computation → higher latency and potential cost than pure keyword lookup.
- In this project: these tools are used manually or in one-off research sessions for validation and sampling, **not** in the 15-min production pipeline.
- Best to keep calls sparse, small `limit`, and scoped (`from_date` + `usernames`).
- If you see 429s or "quota exceeded", capture the response and add to this doc.
- For sustained high-volume X ingestion, rely on the TwitterAPI.io path (see `docs/reference/twitterapi-io-calls.md`).

## Best Practices for Monitoring Systems

1. **Targeted over broad**: Write specific semantic queries. Add `from_date` for context (last N days/weeks). Use `usernames` to focus on key accounts (labs, researchers, critics).

2. **Layer searches**:
   - Semantic first: discover language and themes.
   - Keyword next: operationalize for volume (`x_keyword_search` or production queries).
   - Post-process with project's `data/filters/*.yaml` logic after fetch.

3. **Control noise**:
   - `min_score_threshold` (try 0.5–0.75).
   - `exclude_usernames` for known low-signal accounts.
   - Pair with project's `data/filters/*.yaml` logic after fetch.

4. **Recency matters**: Always include `from_date` (e.g. today minus 7–30 days) unless intentionally historical.

5. **Iterate**: One call with limit=5 often enough. Follow up on interesting post IDs or authors with more targeted calls.

6. **Complement the pipeline**: Do not replace the scheduled advanced search / list-based ingestion. Use semantic/keyword for:
   - Taxonomy development and verification
   - Prompt engineering (see translation prompts research)
   - Edge case discovery
   - Bio / staff move detection
   - Claim grounding before writing research docs

7. **Document your calls**: When using for important research, record the exact query, params, date, and sample post IDs (as done in 2026-06 research files).

## Output

Returns a list of matching posts (up to `limit`). Observed structure (formatted for readability):

```
Main Post:
- [post:N] ID: 2068915434955653188
- Conversation ID: ...
- Author: Katherine Duan - @PeihongD
- Avatar: https://...
- Bio: ...
- Timestamp: Mon, 22 Jun 2026 04:34:12 GMT
- Engagement: Likes=0, Reposts=0, Quotes=0, Replies=0, Bookmarks=0, Views=1
- Content: I do not think people fully appreciate what is happening in China AI right now. ...
```

Key fields always present:
- Post ID (construct `https://x.com/{handle}/status/{id}`)
- Author (name + handle)
- Timestamp
- Full post text (`Content`)
- Engagement counts (Likes, Reposts, Replies, Views, etc.)

Results are relevance-ranked. Content may be truncated in display but full text is provided. Bios and avatars are included for context.

## Additional Notes

- Results can include both original posts and replies depending on relevance.
- Language coverage: works for English and Chinese (and mixed) when query describes accordingly.
- Not a replacement for full X API search; optimized for semantic relevance in agent workflows.
- Always cross-check live data; posts can be edited/deleted.

## Related Files

- `docs/reference/twitterapi-io-calls.md` — production data source details and quotas.
- `docs/reference/twitterapi-live-queries-by-model.md`
- `docs/research/2026-06-24-160500-fresh-sampling-methodology.md` (examples of combined keyword + semantic usage)
- `docs/plans/2026-06-25-001-refactor-b-and-c-calls-for-max-inclusion-plan.md` (live tool test methodology)
- `x_monitor/apify.py`, `queries.py` — for how production X fetching differs.

---

*This reference should be updated if tool behavior, params, or observed limits change.*

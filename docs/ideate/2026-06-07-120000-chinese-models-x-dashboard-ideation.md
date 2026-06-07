# Ideation: Chinese Models X Monitoring Dashboard

**Inferred approach:** Treating this as a product/software topic outside any repo — about an X monitoring dashboard for Chinese AI model DevRel and social strategy.

***

## Grounding Summary

### Codebase Context

**Existing infrastructure (rich, underutilized for this use case):**

* `~/infra/utilities/twitter/` — 6 Twitter scrapers including browser-console scripts for search results, following lists, and list feeds. Also `build_twitter_queue.py`.

* `~/development/cross-post/` — X posting CLI with OAuth 1.0a. Currently **disabled** due to X cracking down on automated posting. Has thread posting, AI summarization, chunking algorithm.

* `~/development/top-gun/may2026-version/pipeline/` — Twitter queue building for GitHub discovery. Has `twitter_checkpoint.json`, `twitter_queue.json`.

* **Apify actor:** `automation-lab/twitter-scraper` — $0.003/tweet, search mode requires cookies, profiles/user-tweets work guest-mode. \~1,600 tweets/month on $5 free credit.

**X API reality (as of June 2026):**

* No free tier — pay-per-use only

* Owned reads: $0.001/resource (your own tweets, followers)

* Search: NOT available on pay-per-use; Pro tier ($5,000/mo) required

* **Apify is the practical search solution** for monitoring other people's activity

**Browser console scrapers** already exist and work without API auth — scraping search results pages directly.

### External Context

* **Phase 2 targets:** Instagram, YouTube, Reddit, then US models (Claude, Gemini, GPT, Llama)

* **Phase 1 scope:** MiniMax, Qwen, DeepSeek, GLM, MiniMo

* **Historical data:** not important for Phase 1 — real-time and recent are the priority

* **Resource constraint:** limited resources, so automation must be targeted and efficient

***

## Candidate Ideas

### Frame 1: Pain and Friction

1. **No unified view of all Chinese model accounts** — currently you'd have to manually check each model's X account separately. A dashboard that aggregates all 5 (MiniMax, Qwen, DeepSeek, GLM, MiniMo) into one view eliminates that friction.

2. **No alerting on issues/trends** — when a Chinese model releases something big or faces criticism, there's no systematic way to catch it early. The dashboard should surface anomalies (spikes in mentions, negative sentiment, viral posts).

3. **Manual search is not scalable** — manually crafting and running X searches daily is error-prone and time-consuming. Automating search query generation and execution is the core friction this solves.

4. **Cookies for Apify expire** — Apify search mode requires Twitter cookies (`auth_token`, `ct0`). These rot and need refreshing. The system needs a low-friction cookie refresh mechanism.

### Frame 2: Inversion, Removal, Automation

5. **Flip "search for everything" to "search for signal, not noise"** — instead of comprehensive keyword coverage, focus on high-value signals: model releases, API changes, pricing updates, partnership announcements, competitor comparisons.

6. **Remove the human from daily monitoring loops** — automate daily search execution, result ingestion, and summary generation. The human reviews output, not input. Checkpoint-resume so no data is lost on failures.

7. **Remove the multi-platform mental tax** — Phase 2 mentions Instagram, YouTube, Reddit. Rather than building separate systems, design one monitoring paradigm that can absorb additional platforms without starting from scratch.

### Frame 3: Assumption-Breaking and Reframing

8. **"Comprehensive" is the wrong goal — "actionable" is the right goal** — a dashboard showing 1,000 posts is useless. A dashboard showing 5 high-signal posts that require action is valuable.

9. **The brand isn't the account — the community is the brand** — instead of monitoring only official accounts, monitor the community around each model: who is discussing them, what are they building, where are they complaining.

10. **DevRel isn't push — it's listening + responding** — surface conversations where engaging would help the model's reputation.

11. **Misinformation isn't a content problem — it's a network problem** — track the accounts that repeatedly spread misinformation. A repeat offender list is more actionable than a truth classifier.

### Frame 4: Leverage and Compounding

12. **One well-crafted search query returns more than 100 keywords** — X advanced search operators (`from:`, `lang:`, `min_faves:`, `since:`, `-filter:`) allow extremely targeted collection.

13. **Build the account/handle list once, reuse forever** — the `twitter_home_feed_github_extractor.js` pattern of scraping following lists to discover handles is directly applicable.

14. **Checkpoint-resume is the core reliability primitive** — the pattern from `build_twitter_queue.py` should be the backbone of every data collection operation.

15. **The Apify $5/month credit is enough for Phase 1** — 1,600 tweets/month = \~53/day. Design the system to work within this budget.

### Frame 5: Cross-Domain Analogy

16. **Financial trading surveillance → DevRel monitoring** — monitor for anomalous activity (spikes, unusual volume) and alert human traders.

17. **Newswire wire Services → trend surfacing** — build a "trend surface" showing what's discussed about each model in the last 24h, ranked by engagement velocity.

18. **Competitive intelligence in CPG → model positioning** — track share of voice, sentiment trends, release cadence vs competitors.

### Frame 6: Constraint-Flipping

19. **What if you could only monitor ONE thing per model?** — pick the single most important signal per model. One thing done well beats five things done poorly.

20. **What if the dashboard was zero-build?** — use existing tools (Apify + a Google Sheet or Notion page) to prototype before writing any code.

21. **What if you had 1,000x budget?** — the dashboard is a force multiplier for a one-person team. Design it to make that one person look like five.

***

## Cross-Cutting Syntheses

**A. Unified Search Query Architecture**
Combine ideas 1, 12, 14: Build a curated query library for each model. Each model gets 3-5 high-signal queries (not hundreds).

**B. Community Discovery Pipeline**
Combine ideas 9, 13: Start with official handles, scrape their followers/following, build an account graph. Tag accounts by role: official, developer, researcher, hater, journalist.

**C. Action-First Alerting**
Combine ideas 2, 11, 16: Define alert conditions (not keyword matches): spike in mentions (>3x baseline), engagement threshold crossings, repeat offender detection.

***

## Prioritized Survivors (Top 7)

1. **Curated query library per model (3-5 queries each)** — highest leverage, lowest cost, immediately actionable. Apify budget-efficient.

2.

3.

4.

   2. **Community account graph** — official + followers + following, tagged by role. Compounds over time, enables targeted outreach.

      **Also track commenters:** collect people who reply TO the official account (`to:MiniMax_AI lang:en` queries). Commenters are the engaged community — developers asking questions, reporting bugs, sharing workarounds. Track via `to:` handles and thread-level scraping. Reply-chain graph reveals community clusters (who replies to the same posts = collaborators or critics). Add commenters with existing engagement (`min_faves:20` floor) — they have skin in the game and their signal is higher quality.

5. **Checkpoint-resume daily crawler** — the reliability primitive. Makes the system actually run unattended.

6. **Alert conditions over keyword matches** — spike detection, engagement thresholds, repeat offender tracking. Actionable vs overwhelming.

7. **Cookie rotation mechanism** — the hidden operational cost. Without it, the Apify search mode dies silently.

8. **Trend surface (24h rolling)** — what are people discussing about each model right now. More useful than historical analytics.

9. **Phase 2 platform abstraction** — design the data model so Instagram/YouTube/Reddit can slot in without rewrites.

***

## Technical Architecture Notes

**Apify Actor:** `automation-lab/twitter-scraper` — use `search` mode with curated queries. Cookies required: `auth_token` + `ct0` from browser DevTools.

**Budget math:** $5/mo credit → \~1,600 tweets. At $0.003/tweet:

* 5 models × 3 queries × 10 results = 150 tweets/day = $0.45/day

* Monthly: \~$13.50 (over $5 credit — need to monitor spend)

* Better approach: run 3-4 days/week, accumulate credits, or top up

**Browser console scrapers** are free and work without cookies for public search results. Use as backup or supplement to Apify.

**Data model suggestion:**

```
Model: { id, name, handle, official_accounts[], community_accounts[] }
Post: { id, author_handle, text, timestamp, engagement, sentiment, signal_type }
Alert: { model_id, condition_type, triggered_at, post_ids, resolved }
```

***

*Generated by ce-ideate. Topics: X monitoring, Chinese AI models, DevRel dashboard, social media strategy, community management.*

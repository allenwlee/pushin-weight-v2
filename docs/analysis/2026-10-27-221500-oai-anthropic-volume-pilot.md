# OpenAI and Anthropic volume pilot (2026-10-26 JST)

## What this measured

How many X posts the drafted OpenAI and Anthropic searches would fetch per day, what that costs, and how many of those posts the current brand matcher would keep. The test ran production's 8 current searches next to the 10 new ones over the same sampled time slices, so the growth ratio uses one method. Classification cost and database growth were not measured; nothing was written to any database.

## Method

- Frozen query set: `docs/analysis/2026-10-27-215214-oai-anthropic-frozen-queries.json` (sha256 `3d2c9c17114bd3de7a7070c60e35ad14eb54236fbf2efd048f657e804c994dec`). Baseline texts were read from production's cycle job `fb9114b7-e9f0-483f-bd2b-e8ecaeba7a0a`.
- Day: 2026-10-26 JST, sampled as twelve 5-minute slices starting at 00:30, 02:30, … 22:30 JST, each paged to the end (page cap 100, never reached). Per-day figures are the slice mean × 288.
- Provider: TwitterAPI.io `advanced_search`, `queryType=Latest`, on-demand credential, called directly on 2026-10-27 about 22:00 JST. 683 requests, all HTTP 200, no retries; 7,250 tweets returned.
- Credits: 15 per returned tweet, 15-credit minimum per call, 100,000 credits per USD (`docs/external_vendors/twitterapi/twitterapi_index.md`).
- Keep/drop: the production matcher (`x_monitor.attribution.compile_keyword_index` / `attribute_to_brands`) with production's `brand_keywords` rows plus the new searches' literal names. Context-only words were not added, so their keep rates are understated.
- Raw receipts (machine-local, private): `/Users/fuchitalee/.local/share/render-operations/2026-10-27-oai-anthropic-volume-pilot/` (`pages.jsonl`, `tweets.jsonl`, `summaries.json`, `run.log`).

## Results

| | Unique posts fetched per day | Search cost per day |
|---|---|---|
| Baseline, 8 production searches | ~23,300 | ~$4.02 |
| New, 10 OpenAI/Anthropic searches | ~118,500 | ~$22.86 (~$686 per 30 days) |
| New posts also fetched by the baseline | ~4,000 | |
| Net-new posts | ~114,500 | |
| Growth | ×5.9 posts fetched | ×6.7 search cost |

Per new search (estimated posts per day): ANT_1 57,384; OAI_1 40,680; OAI_2 25,440; OAI_3 6,528; B_OAI 6,168; ANT_2 5,256; ANT_3 4,632; B_ANT 3,408; A_OAI 0; A_ANT 0. The per-search total is ~149,500, so about 21% of new fetches are paid twice by overlapping searches.

What production would keep, using today's matcher, of the net-new posts:

- 64% tagged OpenAI or Anthropic, about 73,000 posts per day. Production saved 15,988 posts created on 2026-10-26 JST, so saved posts would grow roughly ×5.6.
- 36% dropped as unmatched, about 41,000 paid-for posts per day. Main causes: the katakana nickname チャッピー (18% of OAI_1 posts) and Latin brand names directly followed by Chinese, Japanese or Korean text, which the matcher's word boundary misses; and posts X matched on something outside the post text, such as author names (400 of 2,391 ANT_1 posts contain no Claude/Anthropic word).

Other observations:

- Language of net-new posts: English 49%, Japanese 20%, Chinese 10%, French 4%, Spanish 3%.
- Likes, measured about one day after posting: median 1; 47% have none; 18% have 5 or more.
- Exclusion words after fetch removed almost nothing: Monet and similar 8 of 2,391 ANT_1 posts, Solana 14 of 272 OAI_3 posts, Warhammer 0.
- The two lab-list searches returned no posts in the twelve sampled slices, a sampling miss for low-volume searches. A full-day count over 2026-10-26 JST found 47 posts from 12 authors (OpenAI list) and 24 posts from 7 authors (Anthropic list), against 544 for the current Call A list. The list search sees private lists completely: for tested members (@OpenAI, @gdb, @andrewho03, @AnthropicAI, @bcherny and others) it returned exactly the posts their own `from:` search returned over 2026-10-20 to 2026-10-26. TwitterAPI.io's list-members and list-timeline endpoints return nothing for these private lists, so membership must come from another source.
- ANT_1 jumped to 551 posts in the 22:30 JST slice against about 150 elsewhere, so this day may run above average for Anthropic.

## Limits

One day, sampled at 1/24. Search results come from TwitterAPI.io's historical search a day later, so likes had time to accumulate and the provider may omit posts. Production's 15-minute harvest uses fewer requests per day, which lowers per-call minimum charges but not the per-tweet cost that dominates the new searches. Classification cost and database growth still need the planned xbackfiller run or per-post production averages.

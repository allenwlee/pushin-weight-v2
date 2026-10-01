# Followers of accounts posting B.AI mentions

Database read: 2026-09-29T06:35:59.109217+00:00.
Source: stored accounts.followers_count, joined by stable author_id to the same 7,303-post B.AI-associated group used in the earlier comparison. Each account is counted once, regardless of how many posts it contributed.

## Distribution

| Followers | Accounts | Share of all 395 accounts | B.AI posts | Share of all 7,303 posts |
| --- | ---: | ---: | ---: | ---: |
| 0–99 | 16 | 4.1% | 17 | 0.2% |
| 100–999 | 9 | 2.3% | 12 | 0.2% |
| 1,000–4,999 | 50 | 12.7% | 398 | 5.4% |
| 5,000–9,999 | 108 | 27.3% | 1956 | 26.8% |
| 10,000–49,999 | 179 | 45.3% | 4345 | 59.5% |
| 50,000–99,999 | 18 | 4.6% | 542 | 7.4% |
| 100,000+ | 6 | 1.5% | 14 | 0.2% |
| Unknown | 9 | 2.3% | 19 | 0.3% |

There are 395 posting accounts. Follower counts are known for 386 and missing for nine; none of the known counts are zero or negative. Missing values are not treated as zero. Percentages use all accounts/posts, including unknowns, and may not sum exactly to 100% after rounding.

Among accounts with known counts:

- Median: 10,523.5 followers.
- Middle 50%: 5,607.5–21,108.5.
- 90th percentile: 38,263.
- Mean: 19,435.6.
- Range: 3–588,119.

287 accounts with 5,000–49,999 followers contribute 6,301 posts: 86.3% of the group.
25 accounts below 1,000 followers contribute 29 posts: 0.4%.

The six accounts above 100,000 followers contribute just 14 posts. These include official/platform accounts such as MiniMax, B.AI, and BitTorrent. The mention-based group is not a list of confirmed spammers, and follower count does not prove authenticity or spam.

## Narrower campaign-signature view

For comparison, requiring the previously studied B.AI marker + @justinsuntron + #TRONEcoStar gives 6,873 posts from 186 accounts. An account appears here if at least one of its posts carries that signature; only its signature-matching posts are counted in this table.

| Followers | Campaign accounts | Campaign posts | Share of 6,873 campaign posts |
| --- | ---: | ---: | ---: |
| 0–99 | 0 | 0 | 0.0% |
| 100–999 | 1 | 4 | 0.1% |
| 1,000–4,999 | 8 | 341 | 5.0% |
| 5,000–9,999 | 56 | 1838 | 26.7% |
| 10,000–49,999 | 103 | 4134 | 60.1% |
| 50,000–99,999 | 12 | 533 | 7.8% |
| 100,000+ | 2 | 9 | 0.1% |
| Unknown | 4 | 14 | 0.2% |

Known follower counts exist for 182 of these 186 campaign accounts. Their median is 12754.5 followers. This is a textual campaign-match subset, not independent spam ground truth.

## Count freshness and scope

- These are current **stored** account counts at the database read, not fresh X lookups and not necessarily follower counts at the time each post was written.
- 285 of the 386 known follower counts have a followers_fetched_at timestamp; 101 have no stored observation timestamp.
- All 285 timestamped observations are within the preceding 30 days; 139 are within seven days.
- Timestamped observations range from 2026-08-31T06:15:33.845188+00:00 to 2026-09-29T06:30:42.919547+00:00.
- The post cohort retains the earlier fetched_at cutoff, 2026-09-29T05:57:44.654358Z, and its earlier selection limits: raw B.AI/TRON-marker discovery plus four explicitly recovered decorative-Unicode post IDs, then an explicit normalized B.AI marker requirement. Hashtag-only TRON posts are excluded.
- All 7,303 posts have stable author IDs, and the reconstructed population matches the earlier 395-author comparison.
- Handles can change. The account-level evidence preserves both an example post handle and the currently stored handle; identities are deduplicated by author ID.

One read-only database request. Zero X-provider or model calls. No database/product changes or software tests. The X-data skill's existing-evidence route was used.

## Evidence

- [Exact SQL](bai-followers.sql)
- [Unmodified Render result](bai-followers-render-result.json)
- [One row per posting account](bai-followers-accounts.jsonl)
- [Request receipt](bai-followers-request.json)


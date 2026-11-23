# Official X API measurement

On November 23, 2026 JST, the PushinWeight testing app returned complete long-form post text, an article body, public metrics, replies, quotes and a known announcement from full-archive search. These are good candidates for a focused integration. The current monitoring list could not be retrieved with this app. Search coverage needs a prospective comparison with the vendors before making routing decisions.

## Cost and scope

| Stage | Data requests sent | Reserved for sends | Payer balance decrease |
| --- | ---: | ---: | ---: |
| A. Known posts and user profiles | 4 | $0.180 | $0.14 |
| B. Recent search and counts | 14 | $1.210 | $0.60 |
| C. Timeline, list, quotes, replies | 8 | $0.900 | $0.18 |
| D. Full-archive search | 1 | $0.100 | $0.00 |
| E. Additional fields and native operators | 4 | $0.235 | $0.06 |
| **Total** | **31** | **$2.625** | **$0.98** |

- The [credit endpoint](https://docs.x.com/x-api/usage/get-usage-credits) showed $29.83 before the first data request and $28.85 after the last. The earlier planning balance was $4.84. No purchase was made by this run. The account change before the experiment has no attribution in these receipts.
- Prices were reserved using [X's published rates](https://docs.x.com/x-api/getting-started/pricing), with no assumed discount. Credit differences are payer-level observations. The console did not supply per-attempt charges. Full archive returned seven posts while the displayed balance held steady. That observation does not establish the archive rate.
- All 31 data requests returned HTTP 200. Three had object-level errors. Each data request took 178–432 ms as measured by the runner, with a median of 244 ms. There were 224 top-level post returns and 175 distinct post IDs across the batch, plus user records and count buckets. The observed payer change was about $0.0056 per distinct post across this mixed batch. This includes user, count and repeat requests and cannot predict production spend.

## Endpoint decisions

| Need and route | Measured result | Use for PushinWeight |
| --- | --- | --- |
| Known evidence and metrics, `GET /2/tweets` | 17 of 18 selected post IDs resolved. The old public edit-test ID returned an object-level not-found error with nine other posts in the same batch. A post with an article returned `article.plain_text` (56,576 characters), title, preview, cover reference, entities and the expanded article link. | Start with ID lookup for editorial evidence and metric refresh. Preserve partial errors per ID. Use `note_post.text` for long-form posts and `article.plain_text` when present. Full article availability remains measured on one example. |
| Long-form text and provenance, same lookup | Full text matched the saved length for the 875-character reply and 2,377-character quote. Two Chinese examples returned 8,585 and 5,288 characters in `note_post.text`, versus 221 and 222 in base `text`. The Japanese example returned 998 versus 162. Every resolved lookup returned edit history IDs, with one revision each. | Test full text in translation, classification and editorial consumers. Add an accessible edited-post fixture before relying on multi-revision history. |
| Accounts, `GET /2/users/by`, and selective `author_id` expansion | Returned all five tracked organizations and all four public person accounts. A single-post expansion supplied the corresponding author profile with its stable ID, username, profile image URL and metrics. | Try batched account identity lookups and selective author hydration. Check affiliation separately using evidence that connects the account to the person or organization. |
| Author timelines, `GET /2/users/:id/tweets` | Returned two posts in the fixed dense window, including a saved known positive. | Consider timelines for high-value authors. Measure a genuinely active roster window before selecting it over a batched search. |
| Quotes, `GET /2/tweets/:id/quote_tweets` | Returned 18 and 14 distinct posts across two pages, with a third-page token. Included all three saved known quotes of the video post. | Candidate for discovering quote reactions. Underfilled pages can still have a continuation. |
| Conversations and direct replies, recent search | The frozen test initially used an intermediate reply as the root and returned zero. Lookup exposed the actual root. A bounded follow-up returned three posts for that conversation and recovered the known reply by its direct parent ID. | Use the returned `conversation_id` for a thread and `in_reply_to_tweet_id:` for direct replies when the parent ID is known. The first empty was a test-input error. Direct reference objects were absent from the tested field profiles, so native relationship expansion still needs verification. |
| Lists, `GET /2/lists/:id/tweets`, `GET /2/lists/:id/members`, `list:` | Both endpoints returned an object-level not-found error for the configured monitoring list, and its native search returned an empty result. | The current testing app cannot use that list as measured. Check list visibility or prove a roster path built from known accounts. These responses do not distinguish an unavailable list from private access. |
| Additional fields | `context_annotations` returned data for three of four selected posts. Media keys were present on all four. `media_metadata` returned only keys. Four repeat public-metric reads about eight seconds apart produced identical values. | Try annotations as a topic hint. Media type, URL, alt text and variants still need a bounded media expansion test. Impression count was present, but equivalence to vendor view count and useful refresh intervals remain unmeasured. |
| Historical search, `GET /2/tweets/search/all` | Recovered the [known MiniMax Music announcement](https://x.com/MiniMax_AI/status/2087934657354678421) in seven results from one August query. A token remained. | Archive access is verified on this app. Assess window recovery and measured cost with a small matched cohort before using it for backfill. |

X's current [endpoint reference](https://docs.x.com/x-api/posts/get-posts-by-ids) uses `post.fields`, and the response contained `note_post` and `edit_history_post_ids`. The older `tweet.fields` input and response aliases were not tested. Native discovery alternatives such as filtered stream, News, Spaces and Communities remain outside this run.

## Discovery with explicit time bounds

Both windows were 15 minutes. In JST the dense sample was November 21 20:45–21:00 and the quieter sample was November 22 06:15–06:30. The broader alias tests used the same query shape and count cross-check in each window.

| Query | Dense, distinct IDs | Quieter, distinct IDs |
| --- | ---: | ---: |
| Five tracked organizations | 0 | 0 |
| Multilingual aliases | 40 across two pages, capped; counts reported 89 | 40 across two pages, capped; counts reported 56 |
| Brand and context | 31 across two pages, exhausted | 23 across two pages, exhausted |
| Rare release cues | 1 | 2 |

No observed creation timestamp fell outside its requested interval. The first alias case returned 20 Chinese, 14 English, three Japanese and three posts in other languages. The second returned 15 Chinese, 17 English, one Japanese and seven in other languages. The counts are an X index cross-check. The broader search was visibly incomplete in both windows.

The native `min_likes:1` query returned 20 posts with positive likes, with a continuation. The first 40 unfiltered results had 13 positive and 27 zero. Ten native filtered IDs were in the truncated unfiltered result, and ten were farther down or otherwise absent in the saved pages. The unfiltered quieter control recovered a known Kimi/Gemini post with zero likes. The rare-release results also included a zero-like [repost of a real ComfyUI availability announcement](https://x.com/i/web/status/2124252880052031852). A global like cutoff can remove useful evidence. Consider selective filtering for high-volume discussion and leave early official announcements and rare events eligible. X documents `min_likes:` as the API form and rejects the vendor-style `min_faves:`. [X operator reference](https://docs.x.com/x-api/posts/search/integrate/operators)

The retained TwexAPI page supplied 13 text-matched DeepSeek IDs in the dense interval. The capped X alias search found two of those IDs and the contextual search found five under its different query. The TwexAPI capture ended before the full interval and its originating query is unknown. The TwitterAPI.io fixture confirmed one known result in the quieter contextual search. These are known-positive checks. There was no matched vendor cohort suitable for a recall or cost ranking.

## Evidence and replay

The local experiment runner can preview a manifest without network access. It serializes requests, reserves each send, and records restricted raw bodies with individual JSON receipts. Subsequent pages used the cursor returned by that endpoint for that case.

- Local evidence directory on fuchitalee: `~/.local/share/pushinweight/official-x-probe/2026-11-23-135222`. `live/manifest.json` contains exact endpoints, query strings, fields and positive controls. `reply-followup/manifest.json` records the corrected thread test. Each numbered receipt records status, elapsed time, rate-limit headers, result counts and continuation. Credit and stage receipts document the budget reconciliation.
- Observed app limit and lowest remaining values included recent search 450/433, recent counts 300/298, full archive 300/299, post lookup 3500/3496, user lookup by name 2000/1998, and quotes 75/73. The exact reset headers are in the individual receipts. These are values observed for this app and batch.
- Verification covered network-free preview, admission control before sending, cursor binding, raw duplicate preservation, partial errors, authentication stop and rejection of unbounded expansions. The live run exercised lookup, search paging, failed list objects and the credit ledger. The test stayed local and produced no production collection records.

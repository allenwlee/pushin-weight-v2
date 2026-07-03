# x-monitor — last API-call results & DB records created

- **run_id:** `20260622T001503_0000-6c4ed5ff`
- **started_at:** `2026-06-22T00:15:03+00:00` (09:15:03 JST)
- **finished_at:** `2026-06-22T00:15:15+00:00` (12s wall-clock)
- **status:** `completed`
- **run summary JSON:** `data/runs/20260622T001503_0000-6c4ed5ff.json`

## Totals

| metric | value |
|---|---|
| n_queries_run | 2 |
| n_results (raw, both calls) | 51 |
| n_inserted | 11 |
| n_signals_written | 11 |
| n_signals_dropped | 0 |

## The two API calls

### Call A — `account` (trusted staff list), `brand_id=*`, Q1
- Query: `(list:<x_monitor_list_id>) min_faves:1` (38 chars)
- `n_results: 5 → n_kept: 5 → n_inserted: 0` (all 5 already in DB — dedup via `INSERT OR IGNORE`)
- This is the curated-handle path: returns posts from official/marquee accounts (Hailuo_AI, Mistral devrel, GLM creators).
- raw: `data/runs/raw/20260622T001503_0000-6c4ed5ff/*_account_acct.json`

Returned tweets (none new):

| tweet_id | handle | likes | created (UTC) | text |
|---|---|---|---|---|
| 2068323095446716679 | ZixuanLi_ | 1420 | Sat Jun 20 13:20 | GLM-5.2 has been "stuck" at No.2 on Hugging Face Trending for three days, but I'm thrilled to have connected with the creator behind the No.1 project this afternoon… |
| 2067823501822558298 | CunxiangWang | 46 | Fri Jun 19 04:15 | @elonmusk @jietang @teortaxesTex Strongly agree that true usefulness matters more than benchmark points. That's exactly why it is encouraging to see GLM-5.2 improve… |
| 2068194894750068803 | Hailuo_AI | 49 | Sat Jun 20 04:51 | MiniMax Hub Beginner's Guide — New to Hub? Start here! Research, Skills Spuare, Plugins, Asset Center… |
| 2068005303547822431 | sophiamyang | 6 | Fri Jun 19 16:17 | @marcomolteni Glad you are using Mistral! Let us know if you have any feedback. |
| 2067989767464050912 | sophiamyang | 77 | Fri Jun 19 15:15 | Summer in Paris is the perfect time to vibe. Join our Mistral Vibe Hackathon… |

### Call B — `brand_wide`, `brand_id=minimax`, Q5
- Query: the brand-wide paren-grouped OR clause (321 chars)
- `n_results: 46 → n_kept: 11 → n_inserted: 11`
- **Filter breakdown (35 dropped):** `hard_drop_no_signal: 34`, `soft_drop_banned: 1`
- `n_review_added: 1` (1 post flagged for human review)
- raw: `data/runs/raw/20260622T001503_0000-6c4ed5ff/minimax_brand_wide_acct.json`
- Note: the raw file stores the **post-filter kept 11**, not the full 46. The 46→11 drop happened before the dump.

## DB records created this run (11)

Each inserted post wrote **3 rows**: one `posts` row, one `post_brands` attribution row, one `post_brand_signals` row. All 11 fetched in the `2026-06-22T00:15:15+00:00` window. `n_signals_dropped: 0` (no FK violations — the brands-table guard held).

| tweet_id | brand_id | signal | handle | lang | text preview |
|---|---|---|---|---|---|
| 2068850150282555852 | deepseek | other | CarbonNeutralC | en | I asked Deepseek why motor play an important role on carbon neutrality… |
| 2068849912008286230 | deepseek | other | twinks0ut | en | just subscribed to deepseek 🤍 |
| 2068850005121576992 | glm | **praise** | NeoReplicante | en | I'd love to have a lab like yours so I could run GLM 5.2 and do some proper work… |
| 2068849959462375740 | glm | other | urbitverse | en | Any thoughts on $io? Chart looks good and new narrative brewing thanks to GLM 5.2 |
| 2068849921478807946 | glm | other | aazjan | en | GLM 5.2 is truly impressive. if open-source models catch up this fast… |
| 2068849870144708923 | glm | other | MahatiSingh | en | Definitely been reading some good reviews around GLM. Is it the next best… |
| 2068849731950829974 | glm | other | tobiasthellm | und | @qoder_ai_ide glm |
| 2068849972435709981 | moonshot_kimi | other | antsmuse | en | HAPPY RACE WEEK !! Kimi is going to have the best weekend this week ! |
| 2068849806496133403 | moonshot_kimi | other | heetwigs | tr | keonho es tan kimi |
| 2068849828394594381 | xiaomi_mimo | other | WhiteEuropeanX | pt | Não chamem a Polícia. … MIMO neles!!! |
| 2068849660068864350 | xiaomi_mimo | other | rafaelabsnunes | pt | É mais fácil esse macho performático está usando pra manter mulher longe… |

Attribution distribution: **glm 5, deepseek 2, moonshot_kimi 2, xiaomi_mimo 2**.
Signals: **1 praise** (NeoReplicante/GLM), **10 other**.

## ⚠️ Data-quality flags (mis-attribution still present)

The pipeline is mechanically healthy (real attribution, real signals, 0 FK drops). But of these 11, **~5 are token-collision false positives** — same class of bug as the moonshot-crypto-spam case, now hitting *other* ambiguous tokens:

1. **`kimi` → Kimi Räikkönen, not Moonshot AI.** `antsmuse` ("HAPPY RACE WEEK… Kimi is going to have the best weekend") is about the F1 driver. `heetwigs` ("keonho es tan kimi") is Spanish slang for a person's name. Both attributed to `moonshot_kimi`.
2. **`MIMO` → Portuguese slang, not Xiaomi MiMo.** `WhiteEuropeanX` ("MIMO neles!!!") is Portuguese ("give it to them"), attributed to `xiaomi_mimo`. `rafaelabsnunes` (Brazilian Portuguese) matches `xiaomi_mimo` on a token too.
3. **`glm` / `deepseek` low-signal mentions** kept but classified `other` (e.g. "just subscribed to deepseek", "@qoder_ai_ide glm"). Not wrong, just noise.

The disambiguation done for `moonshot` (drop bare token, require unambiguous product/company names) needs to be applied to **`kimi`** (collides with the F1 driver / personal name) and reviewed for **`mimo`/`xiaomi_mimo`** (collides with PT-PT slang). The 5 GLM/deepseek rows are the genuine signal in this cycle.

---
*Generated from fuchitalee `data/x_monitoring.db` + `data/runs/20260622T001503_0000-6c4ed5ff.json`.*

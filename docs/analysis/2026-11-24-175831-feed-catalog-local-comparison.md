# Feed catalog input and coverage comparison

The shorter catalog used **75.6% fewer input tokens with the historical brand floor**, and **86.7% fewer without the floor**, on 629 recently collected posts. These are offline system-plus-user text counts. No candidate model responses, bills, or live candidate harvest cycles were observed.

## Cohort and method

Freeze all posts with at least one PostBrand, ordered by first collection time and tweet ID, from 16:45 inclusive through 17:30 exclusive JST on November 24. Selection used a read-only production transaction before looking up labels. The freeze contains 629 posts, 765 pairs, 23 distinct brand IDs including the discovery sentinel, and 90 multi-brand posts. Languages include 311 English, 177 Chinese and 87 Japanese posts. Include the sentinel-only post when estimating calls.

Use stored source text, current source-bound English where available, current reviewed feed affiliations, stored quote, local parent, current catalog, observed targets, and fetch-order groups of up to 20 posts or 99 brand slots. Build A/B/C using the actual candidate selector, canonical snapshot, positional request builder and selected system-prompt renderer. Each arm gets identical ordered cases and both role requests. The selector ran once per group. Compute canonical text bytes and tokens with the locally archived DeepSeek tokenizer, SHA-256 `8f9f37ca37fdc4f5fd36d5cf4d3b0e8392edb4e894fd10cc0d70b4957c8633cf`, no special tokens or chat framing. B row IDs matched A in all 32 batches.

No archived original-content request rows matched the frozen post IDs. Synchronous provider telemetry records usage and request IDs but does not store the request body. These 32 batches are an explicitly ordered reconstruction. Their evidence and catalog may include values obtained after the original dispatch. The full snapshot included 1,709 real brands and the sentinel. Historical floor membership in this reconstruction included the 182 real historical brands and the sentinel because the frozen input included a discovery case. Search provider was unknown for all 629 in the checked observation-to-request links. Provider field-parity fixtures are a separate test.

| Reconstruction | Full role requests | Brands/batch | Content tokens | Brand interpretation tokens | Total input | Median / p95 per request | Total text bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| A, current rows and floor | 64 | 189–212 | 2,542,325 | 2,519,350 | 5,061,675 | 78,246 / 87,046 | 12,658,991 |
| B, short rows and floor | 64 | 189–212 | 629,120 | 606,145 | 1,235,265 | 18,420 / 27,228 | 4,229,205 |
| C, short rows without floor | 64 | 12–48 | 348,143 | 325,168 | 673,311 | 9,753 / 18,718 | 2,521,229 |

Removing the floor saved another 45.5% against B. Local selector CPU median / p95 (milliseconds per batch) was 42 / 104 for A, 84 / 159 for B and 64 / 144 for C. Corresponding elapsed median / p95 was 43 / 104, 84 / 165 and 64 / 151. Maximum observed elapsed was 142, 258 and 235 ms. These single-machine timings exclude transport, reader persistence and live budget; they cannot certify the cycle deadline.

On a separately frozen historical input of ten archived 20-post groups (20 role renders), total text tokens were 1,515,210 for A, 362,154 for B and 217,182 for C. This re-render used those saved cases and the historical catalog; the earlier paid compact implementation and its replies have different instructions. Their labels cannot qualify today’s candidates.

## What readers actually received under the existing classifier

At 17:57 JST, 702 of 764 real post/brand pairs had selected reader-usable type and sentiment. Of 628 posts with a real brand, 580 had full coverage, one had partial coverage, and 47 had none. The remaining post was sentinel-only. The selected-state lookup used the normal reader’s type and sentiment assignment logic and stored signal rows. At 30 minutes after each post’s collection, 697 of 764 real pairs had a latest validated final with usable type and sentiment. This last measure reconstructs historical judgment availability; it does not establish the exact historical reader state. These observations are baseline descriptions. Candidate agreement, correctness, reader retention and cost per usable post still require candidate answers.

## Cost boundary

Using the repository’s DeepInfra reservation prices, $0.09 per million input tokens and $0.27 per million output tokens, the existing conservative byte-plus-framing reservation method with a 65,536-token output allowance gives **$5.232805** for one attempt each on the 192 A/B/C requests. Adding one full A/A repeat gives **$7.534099** across 256 attempts. Reconcile actual rates before dispatch. Retries, a separate challenge set, or a larger sample would need their own reservation inside any owner-authorized cap. This is a reservation estimate. No spend was authorized or incurred. No production data was modified.

## Local verification inputs

The private run bundle is under `.local/feed-catalog/` in the plan worktree. It contains the selection manifest, read-only collection and coverage scripts, frozen reconstruction, pinned-tokenizer replay script and per-request A/B/C measurements. Each request record carries its ordered post IDs, role, UTF-8 bytes and token count. The historical bounds file and tokenizer are in the Nov 11 catalog-removal worktree under `.local/classifier-catalog-removal/`. Re-run `measure.py` from the plan worktree with its repository on PYTHONPATH and the archived tokenizer package available. It is offline and needs no credentials. The selection manifest SHA-256 is `df28b59cb5e010ebc3b03f37b2b3f1f70e868151346f5a955c8efff24e8ab605`; frozen reconstruction SHA-256 is `9cc4aaee463e36ce892048a544e6d42eeabcbae93f8803432e4f53cba0b99566`.

## Local regression results

The final focused run passed 130 tests, covering the compact request, configuration, two-role worker, Maya/NVIDIA publication, a mixed-brand promotion retry and exact saved-packet replay. A fake answer deliberately differed between comparison arms and changed only its own reader result. The broader run during development passed 375 tests and failed 12. All 12 also failed on the unmodified code at `24812f0e`. They cover two background release cases, nine backfill cases and one telemetry case. The clean-main comparison was stopped after each failure was reproduced. Code review of the final tracked diff had no open findings.

The scheduled and manual query renderers produced the historical byte counts for all 16 standard calls and the two special-event shapes using the fixed list ID and ten-digit time bounds. Scheduled B8 was largest at 511 of 512 bytes. Production mode remains the existing baseline. The smaller requests have not been used to obtain fresh model answers.

For an initial paired quality experiment on the first 200 eligible posts with reproducible batch grouping, two control passes and one pass for each compact mode require 80 physical requests. The local maximum-cost reservation was $2.334254 with retries disabled. A proposed $2.50 hard cap covers that experiment alone. Reprice the actual payloads immediately before any separately authorized dispatch. Boundary fixtures or further batches require a separate allocation if they do not fit. The 200-post subset cannot by itself guarantee the precision required to qualify a rollout.

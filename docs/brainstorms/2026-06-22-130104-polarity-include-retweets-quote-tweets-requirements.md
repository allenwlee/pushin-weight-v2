---
date: 2026-06-22
topic: polarity-include-retweets-quote-tweets
---

# Polarity: Include Retweets and Quote-Tweets

## Problem Frame

x-monitor's polarity score (`x-monitoring/x_monitor/treemap.py::compute_polarity_from_db`)
measures sentiment as an **unweighted count of original posts**: each post contributes
**1** to its signal bucket (praise / criticism / etc.), and polarity is the rate-of-change
of `(praise_rate − criticism_rate)` across two windows. It ignores amplification entirely:

- **Retweets** — pure re-broadcasts with no new opinion. We already store `retweet_count`
  per post (`x-monitoring/x_monitor/migrations/001_initial.sql`), but it never enters polarity.
- **Quote-tweets** — the quoter's *own* reaction commentary. The keyword search can't surface
  them (X indexes a tweet's own text; a "👀"-only QT of a brand tweet never matches), so they
  are absent from the DB.

Consequence: the dashboard's polarity reflects "what original posters said" but not "how the
crowd reacted and amplified." A launch post that gets 7,000 retweets and 2,700 quote-tweets
counts as **one** data point today.

**Goal:** polarity incorporates both — each retweet counts as a duplicate of the original's
sentiment (free), and each quote-tweet counts as an independent vote on its own commentary
(requires fetching).

## Requirements

**Retweet amplification (free — no new fetch)**

- **R1.** Each pure retweet of a brand post contributes the *original post's* signal to
  polarity. An RT has no content of its own; it inherits the original's classified signal.
  (Mechanism: weight each post's signal contribution by `(1 + retweet_count)` in the polarity
  aggregation. `retweet_count` and `quote_count` are disjoint TwitterAPI.io fields — verified:
  149 stored posts have `quote_count > retweet_count`.)
- **R2.** No new API call, schema migration for the count, or fetch stage is needed for RTs;
  the fold is a change to the polarity aggregation only.

**Quote-tweet capture (paid — two regimes by post source)**

- **R3.** Capture quote-tweets of brand posts and classify each QT's **own commentary**
  independently for sentiment (a QT of a praise post may itself be criticism).
- **R4.** **Two capture regimes**, split by post source:
  - **Official/staff posts** (list call / known official handles): **reactive, delta-triggered.**
    A QT-fetch fires only when a post's `quote_count` has grown by **≥ 5** since its last
    QT-fetch (growth observed via the regular search cycle). Batches the new QTs → no call on
    quiet days, and announcement-day floods are caught within the cycle. Rationale: official
    posts hold ~71% of all quote volume (DeepSeek launches dominate), so flood-fresh
    incremental capture pays off here.
  - **Non-official posts** (keyword brand-wide search): **daily pass.** A once-daily,
    `sinceTime`-incremental QT fetch for attributed non-official posts with `quote_count > 0`,
    on a schedule separate from the 15-min search cron. Complete over time at ~a few $/mo, with
    no per-cycle 15-floor waste. (Delta-triggering isn't worth the machinery for the
    low-volume long tail.)
- **R5.** **Fetch quantity = the new QTs since the last fetch, floored at 15** (both regimes) —
  retrieve exactly what grew, at least the 15-tweet per-call billing floor.
- **R6.** **Deduplication:** each fetch uses `sinceTime` = the timestamp of the newest
  already-held QT for that post, so successive fetches return only new QTs; plus `tweet_id`
  idempotent insert as a safety net.
- **R7.** Captured QTs run through the **same** classification + attribution pipeline as
  original posts (no special QT path): `attribute_to_brands` matches the QT's commentary
  **plus** the quoted original's text (the `quoted_text` fold from the prior quote-tweet work),
  so a QT attributes to every brand mentioned in either the commentary or the quoted tweet.
  Multiple brands → one `post_brands` + one `post_brand_signals` row per brand, each weighted
  1/N (the existing multi-brand rule) — identical to an original post that mentions N brands.
  The signal is classified once on the QT's commentary and applied to all its attributed brands.
- **R8.** The 15-tweet per-call minimum is a hard billing constraint; both regimes are shaped
  to respect it — official batches deltas (≥ 5) toward the floor; non-official amortizes over a
  daily pass rather than 15-min re-fetches (which would repeatedly pay the floor for ~0–2 new
  QTs).

**Polarity integration**

- **R9.** RTs and QTs participate in the **same** polarity metric (the existing rate-of-change
  of praise/criticism rates), conceptualized as "each utterance = one vote" — not as a separate
  alongside indicator.

## How the three utterance types are handled

| Type | How it enters the pipeline | Sentiment source | Cost |
|---|---|---|---|
| Original tweet | Keyword search (Call A list / Call B brand-wide) — existing | Its own text (existing classifier) | Existing |
| Pure retweet | Never fetched | Inherits the original's signal; weighted by `retweet_count` | **Free** (metadata already stored) |
| Quote-tweet | `GET /twitter/tweet/quotes?tweetId=<id>` (official: reactive R4; non-official: daily pass R4) | The QT's own commentary, classified independently | Paid (15-tweet floor/call) |

**QT-capture flow — two regimes by post source:**

```
OFFICIAL / STAFF posts                  NON-OFFICIAL posts
(checked each search cycle)             (daily pass, separate schedule)
     │                                       │
     ▼                                       ▼
delta = quote_count                     for each attributed post
      − last_seen_quote_count             with quote_count > 0:
     │                                       │
     ├── delta < 5 ──► skip (quiet)          ▼
     │                                   fetch new QTs since last
     └── delta ≥ 5 ──┐                     pass (sinceTime),
                      ▼                     floored at 15
            fetch max(15, delta)            │
            new QTs (sinceTime)             │
                      │                     │
                      └─────────┬───────────┘
                                ▼
                   classify each QT's commentary → signal
                   attribute to original's brand(s)
                   idempotent insert by tweet_id
```

## Success Criteria

- A brand post that is heavily retweeted moves its signal bucket by `(1 + retweet_count)`, not 1.
- A brand post whose quote-tweets are predominantly critical shifts that brand's polarity
  negative, even if the original post was neutral or positive.
- QTs of official launch posts (e.g. DeepSeek R1/V4) are captured and classified on their own
  content, within the search-cycle cadence after the flood begins.
- No double-counting: a QT that also appears in keyword-search results is deduped by `tweet_id`;
  RT metadata does not conflate with QTs (disjoint fields).
- Cost stays bounded and within the same order of magnitude as today (~$13–22/mo baseline):
  zero QT calls on quiet days for official posts (reactive); non-official daily pass at ~a few
  $/mo; floods fetched incrementally. (Exact figure deferred — see D1.)

## Scope Boundaries

- **Likes and replies are out of scope** — not amplification-with-sentiment in this model.
- We do **not** fetch pure-retweet content (RTs have none); `retweet_count` metadata suffices.
- QT capture is **one level deep**: original brand post → its quote-tweets. No recursive
  quotes-of-quotes.
- **No change** to the original-tweet keyword search cadence (Call A/B remain as-is).
- By default, **no per-utterance cap** on RT or QT votes (each RT/QT = one vote). See D3.

## Key Decisions

- **Democratic utterance model:** every distinct utterance (original, RT, QT) = one vote. RTs
  inherit the original's signal (no new opinion); QTs are classified on their own commentary
  (new reaction opinion).
- **RT fold is free** — `retweet_count`/`quote_count` captured since migration 001; no new call.
- **QT capture is split by source into two regimes:** official/staff posts use **reactive
  delta-triggering** (fetch on `quote_count` growth ≥ 5, observed within the search cycle) —
  flood-fresh with no quiet-day calls; non-official posts use a **daily sinceTime-incremental
  pass** — complete over time without per-cycle 15-floor waste. Concentrates reactive machinery
  where ~71% of quote volume lives; routine capture for the low-volume long tail.
- `retweet_count` and `quote_count` are **disjoint** TwitterAPI.io fields (verified empirically).

## Dependencies / Assumptions

- TwitterAPI.io `GET /twitter/tweet/quotes?tweetId=<id>`: 20/page, supports `sinceTime`/
  `untilTime` (unix s) and `includeReplies`; `has_next_page` can lie (also stop on empty page).
  **15-tweet minimum billing per call** (operator-confirmed). Endpoint shape from official docs.
- The official-account set is identifiable (the list call's membership / a configured handle set).
- `created_at` is stored in **Twitter format** (`Mon Jun 08 22:25:20 +0000 2026`), not ISO — any
  windowing/recency logic must parse it correctly (this broke an earlier cost probe).

## Outstanding Questions

### Resolve Before Planning

- _(none — all product decisions are locked)_

### Deferred to Planning

- **D1. [Affects R4][Needs research]** Scheduling unknowns for **both** regimes. (a) *Official
  reactive:* do the search cycles reliably re-see an official post's growing `quote_count` over
  the days it accumulates QTs? If a launch post ages out of "Latest" results after ~1–2 days,
  reactive triggering needs an explicit periodic `quote_count` re-check (cheap single-tweet
  lookup) for tracked recent official posts. (b) *Non-official daily pass:* which posts get
  polled daily — needs a recency window so old posts aren't re-polled forever. Verify the
  search's effective recency window and decide both mechanisms. Also re-derive a clean per-day
  cost estimate once `created_at` parsing is fixed (the earlier estimate was invalid).
- **D2. [Affects R5][Technical]** Per-fetch pagination cap for mega-floods: when one official
  cycle's delta is very large (DeepSeek launch: +hundreds), confirm fetch-all-delta vs a
  per-fetch cap with incremental recovery in later cycles. User intent is "fetch the detected
  delta"; confirm a worst-case single-event cost ceiling.
- **D3. [Affects R1/R9][Technical]** Viral-domination: a post with `retweet_count = 7661`
  contributes 7,661 votes to one signal bucket, which can let a single viral post dominate a
  brand's polarity and spike the rate-of-change metric. User chose raw counts ("each RT is
  another tweet"); confirm whether to accept raw or apply a cap/log scale, and flag the
  volatility consequence for the rate-of-change formula.
- **D4. [Affects R7][Technical]** QT storage shape: store captured QTs as rows in `posts`
  (with a source/parent marker + `quoted_status_id` link) so they flow through the existing
  attribution → signal → polarity path, vs a separate table. Confirm reuse of `posts` and how
  QT-sourced rows are marked.
- **D5. [Affects R3/R7][Technical]** Classification path for captured QTs: (a) **attribution**
  matches commentary + the quoted original's text — confirm the `/twitter/tweet/quotes`
  response carries the nested `quoted_tweet`, else attach the parent brand post's text (which we
  already hold) as `quoted_text`; (b) **signal** classification reads the QT's commentary only
  (not the quoted original — the `run.py:351/357` signal-vs-attribution asymmetry), with the
  Haiku translation pass run on the commentary. One signal per QT, applied to all N attributed
  brands at weight 1/N.
- **D6. [Affects R4][Technical]** Mechanism to tag a post's author as official/staff for the
  two-regime split (derive from list/Call-A membership vs a config set).

## Next Steps

-> `/ce:plan` for structured implementation planning. All product decisions are locked and no
   Resolve-Before-Planning blockers remain; D1–D6 are planning-time technical/research questions.

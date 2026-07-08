# Lookup Tables

Small, finite, name-only tables that constrain what the classifier (LLM-side)
and the parser (post-process) are allowed to emit. Their rows are referenced
via foreign key from the per-post signal/discourse tables.

**Why this exists.** Whenever a new taxonomy value is added, three places must
move together:

1. The `*_keys` SQL table gets a new row (via a migration).
2. The matching `_VALID_*` constant in `x_monitor/attribution.py` gets the
   new entry — the parser uses this to filter LLM emissions.
3. The classifier prompt's legend (in `build_pragmatics_full_prompt`) lists
   the value so the LLM knows to emit it.

This doc is the single place to look up what's currently in the system, what
to add, and what the parser will reject.

**Source of truth.** The `*_keys` SQL tables in `x_monitoring.db` are
authoritative. The `_VALID_*` Python frozensets in `attribution.py` are a
1:1 mirror used at parse time. If they ever drift, the migration is the
canonical record; update the Python constant in the same commit.

---

## 1. `post_type_keys` — 6 values

**Referenced by:** `posts_brands_signals.post_type_key`

| id | key | notes |
|---|---|---|
| 1 | `buzz_releases` | hype about a new release / launch |
| 2 | `hands_on_usage` | "I tried it" — actual hands-on. **Also the parser's fallback sentinel** when the LLM emits an unrecognized value. The v12 plan's parser-layer demotion (plan 2026-07-06-001) actively moves posts *out* of this bucket when source-text markers fire. |
| 3 | `performance_comparisons` | benchmark / leaderboard / vs-other-model talk |
| 4 | `feedback_questions` | asking for help, comparisons, or opinions |
| 5 | `advertising_marketing` | salesy / CTA-heavy. U2a, migration 027. **Underscored**, not hyphenated (the discourse twin is hyphenated — see plan KTD7). |
| 6 | `event_announcement` | one-line release / "now live" / launch |

## 2. `sentiment_keys` — 4 values

**Referenced by:** `posts_brands_signals.sentiment_key`

| id | key | notes |
|---|---|---|
| 1 | `positive` | |
| 2 | `negative` | |
| 3 | `neutral` | **Also the parser's fallback sentinel** when the LLM emits an unrecognized sentiment. Like `hands_on_usage`, the value is overloaded. |
| 4 | `mixed` | same brand getting both positive and negative valence (e.g. critique that acknowledges a strength) |

## 3. `discourse_keys` — 10 values

**Referenced by:** `posts_brands_discourse.dr_key`

| id | key | notes |
|---|---|---|
| 1 | `genuine_hype` | straight praise |
| 2 | `sarcasm` | English verbal irony |
| 3 | `dunk_yingyang` | 阴阳怪气 / passive-aggressive dunk |
| 4 | `self_deprecation` | 自嘲 / self-mockery |
| 5 | `cope` | 嘴硬 / stubborn denial |
| 6 | `fud` | 唱衰 / spreading doom |
| 7 | `distillation_accusation` | 套壳 / 蒸馏指控 |
| 8 | `ai_slop_critique` | AI content-garbage accusation |
| 9 | `absurdist_meme` | 抽象整活 / absurdist antics |
| 10 | `advertising-marketing` | salesy / CTA-heavy. U2a, migration 027. **Hyphenated** (not underscored like the post_type twin — see plan KTD7). |

The parser also emits `uncategorized` as a **runtime sentinel** when nothing
matches. It is NOT in this table; it never gets persisted to
`posts_brands_discourse`.

## 4. `nationalism_keys` — 6 values

**Referenced by:** `posts_brands_signals.cn_key`, `posts_brands_signals.us_key`

| id | key | notes |
|---|---|---|
| 1 | `none` | **Also the parser's fallback sentinel.** Default when the LLM emits nothing. |
| 2 | `mild_pro` | sympathetic to the side, but not strongly |
| 3 | `pro` | clearly sympathetic |
| 4 | `constructive_critical` | critical of the side, but in a good-faith way |
| 5 | `anti` | clearly against the side |
| 6 | `mixed` | post has both pro- and anti- valence on the same axis |

Nationalism is an axis about which side of the US-China divide the post
sympathizes with, NOT about generic anti-vendor hostility. Rule 16 in the
classifier prompt (v12 calibration) was added precisely to prevent
"anti-vendor dunk" from being misread as "anti-China" or "anti-US".

## 5. `unsanctioned_flag_keys` — 4 values

**Not queried from prod here** (the migration table doesn't exist yet, or
the values live in the `unsanctioned_flag_keys` SQL table per the
`_VALID_UNSANCTIONED_FLAGS` allow-list in `attribution.py:1018`).

Per `attribution.py`:

| key | notes |
|---|---|
| `marketing_spam` | promotional content with no informational value |
| `scam` | obvious fraud / phishing |
| `crypto` | crypto-shilling, web3 promotion (rule 19) |
| `unauthorized` | impersonation / brand-misuse |

**Note:** this list is enforced as the parser's allow-list, but the
`*_keys` SQL table may not exist yet — values are filtered at parse time
in-memory. Confirm with `SELECT name FROM sqlite_master WHERE name LIKE
'%unsanctioned%';` if a future migration lands the table.

---

## Sentinel / taxonomy confusion

Three values are **overloaded** — they're both a real taxonomy entry AND
the parser's fallback:

- `post_type` → `hands_on_usage` (overloaded: real value + parse fallback)
- `sentiment` → `neutral` (overloaded: real value + parse fallback)
- `nationalism` → `none` (overloaded: real value + parse fallback)

The v12 plan's parser-layer demotion (`_post_process_pragmatics`) breaks
the `hands_on_usage` conflation by moving posts out when source-text
markers fire. The same is not yet done for `neutral` or `none` — those
remain conflated.

`discourse` → `uncategorized` is NOT overloaded: it's only a runtime
sentinel, never a taxonomy entry. If you see it in DB output, something
went wrong upstream.

## How to add a new value

1. **Migration:** add a new row to the `*_keys` table.
   ```
   -- example for a new post_type
   INSERT INTO post_type_keys (key, created_at) VALUES ('my_new_type', '...');
   ```
2. **Python constant:** add the same value to the matching `_VALID_*`
   frozenset in `x_monitor/attribution.py`. The parser uses this to filter
   LLM emissions — without this, the value will be silently dropped.
3. **Prompt legend:** update `build_pragmatics_full_prompt` so the LLM
   knows the new value exists. Without this, the LLM will never emit it.
4. **Test fixtures:** add the value to a regression fixture (e.g.
   `/tmp/v20_fixture.jsonl`) so the smoketest exercises it.
5. **This doc:** add the new row to the table above.
6. **Skill doc:** if it's a discourse/post_type/nationalism that operators
   will read in smoketest artifacts, update
   `~/.claude/skills/custom-claude-skills/pushin_weight_smoketest/SKILL.md`.

Steps 1, 2, 3, 5 should land in a single commit so they don't drift.

# How `posts.lang_detected` works

`posts.lang_detected` is a single TEXT column written by the LLM during
the translation pass. It is not computed locally, not validated against
any external language ID, and trusts the model at face value. The
column exists primarily so the v1.7 translation-backfill subcommand
can avoid re-translating tweets that are already in the target locale.

This document traces the column end-to-end: prompt → parse →
persist → backfill → downstream reads.

---

## 1. Source: the LLM emits it during translation

In `x_monitor/translator.py::build_translation_prompt`, the prompt
instructs Claude (or any conforming `ClaudeClient`) to detect the
source language of each tweet:

```
1. Detect the source language of each tweet (lang_detected;
   use ISO 639-1 + script, e.g. 'zh-Hans', 'en', 'ja').
```

The expected response shape is exactly:

```json
{"results": [{"tweet_id": str, "lang_detected": str,
              "text_en": str, "text_zh_cn": str,
              "noop_en": bool, "noop_zh": bool}, ...]}
```

There is **no local language-detection library** (no `langdetect`, no
`cld3`). Whatever the model emits lands verbatim in the column.

## 2. Parsing and dispatch (`translate_batch`)

For each batch of `_TRANSLATION_BATCH_SIZE` tweets:

- `_call_with_retry(client, prompt)` calls the LLM with retry/backoff.
- `_parse_response` validates the JSON shape.
- On success, the per-tweet row is built from the parsed JSON, with
  `lang_detected` taken straight from `p.get("lang_detected")` (could
  be `None` if the LLM omitted the field).
- On failure (LLM error, malformed JSON), `_empty_row(t, failed=True)`
  returns a row with `lang_detected=None` plus `translation_failed=True`.
  The batch is marked failed but the **next batch still runs** —
  failures are non-fatal per Decision 6.

`_empty_row` is the only path that produces `lang_detected=None` at
insert time. Any of these three outcomes land in the DB with NULL:

- LLM call timed out / errored after all retries.
- LLM returned malformed JSON.
- LLM returned well-formed JSON but omitted the `lang_detected` field.

## 3. Persistence (`Store.insert_posts`)

The translator output dict is passed into `Store.insert_posts(posts, ...)`.
The `INSERT INTO posts` statement binds `lang_detected` directly from
`p.get("lang_detected")` — straight passthrough:

```python
p.get("text_en"),
p.get("text_zh_cn"),
p.get("lang_detected"),
```

The column has **no NOT NULL, no DEFAULT, no CHECK constraint**.
What the translator puts in is what lands in the DB.

`INSERT OR IGNORE` on the `tweet_id` PK means: a re-run won't update
`lang_detected` for an existing post (because the INSERT is ignored).
To change the `lang_detected` value of an existing post, run a
separate `UPDATE` (see Section 5 for the only paths that do this).

## 4. The `noop_<locale>` semantics

When the source text is already in a target locale, the LLM is
instructed to set `noop_<locale>: true` and return the source text
verbatim as `text_<locale>`. The translator row carries these booleans
through, but `lang_detected` and the translations are the actual
authoritative outputs. `noop_*` is a per-tweet optimization hint, not
a property of the column itself.

## 5. Backfill paths

Two paths fill `lang_detected` after the initial insert:

### 5a. Translation-backfill subcommand

`Store.update_translations(rows)` runs:

```sql
UPDATE posts
SET text_en = ?, text_zh_cn = ?, lang_detected = ?
WHERE tweet_id = ?
```

…for each row passed in. Same passthrough: whatever the LLM emitted
goes in. Used by the `x-monitor translate-backfill` CLI to fill in
posts that were ingested before the v1.7 translation columns existed
(or whose first-pass translation failed and need a retry).

### 5b. Migration 004 heuristic backfill (pre-v1.7 retrofit)

```sql
UPDATE posts SET lang_detected = 'en'
    WHERE text_en IS NOT NULL AND lang_detected IS NULL;
UPDATE posts SET lang_detected = 'zh-CN'
    WHERE text_zh_cn IS NOT NULL AND lang_detected IS NULL;
```

This is the **only place** `lang_detected` is derived from another
column instead of from the LLM. The logic: if a row has `text_en IS
NOT NULL` (English was translated into it), the source language was
*not* English — assume it was the other target, `zh-CN`. This is a
heuristic for the pre-v1.7 corpus where `lang_detected` was NULL
because the column didn't exist.

Caveats:

- It writes only `'en'` or `'zh-CN'` — not the full BCP-47 range
  (`'zh-Hans'`, `'zh-Hant'`, `'ja'`, etc.) the LLM might emit.
- A pre-v1.7 row that already had English text (i.e. no translation
  needed) would get `lang_detected='zh-CN'` here even if it was
  originally English.

## 6. Downstream consumers

Three places actually read `lang_detected`:

### 6a. Partial backfill indexes (migration 004)

```sql
CREATE INDEX idx_posts_text_en_backfill ON posts(tweet_id)
    WHERE text_en IS NULL
      AND lang_detected IS NOT NULL
      AND lang_detected NOT IN ('en','en-US','en-GB','und');
CREATE INDEX idx_posts_text_zh_cn_backfill ON posts(tweet_id)
    WHERE text_zh_cn IS NULL
      AND lang_detected IS NOT NULL
      AND lang_detected NOT IN ('zh','zh-CN','zh-Hans','zh-Hant','und');
```

**These two indexes are the reason the column exists in v1.7.** The
backfill subcommand uses them to find rows that *could* be translated
into English (lang is not already English) or Chinese (lang is not
already Chinese). Without `lang_detected`, every non-translated row
would be a candidate, and the LLM would waste tokens re-translating
tweets that are already in the target locale (with `noop_<locale>` set
on the round trip).

### 6b. `idx_posts_lang_detected (lang_detected)` — full index

Lets queries filter by locale (e.g. "all posts detected as Japanese"
for a JP-only dashboard view). Created in migration 003.

### 6c. Dashboard / query paths

Read the column for grouping by language. Not exercised in the
migration's stored code; this is left to the dashboard layer (the
schema doc does not name a specific consumer).

## 7. The `'und'` quirk

Both backfill index predicates explicitly include
`AND lang_detected NOT IN (..., 'und')`. That's the BCP-47
"undetermined" code. The LLM emits `'und'` when the text is too short
or ambiguous (single emoji, just a URL, just `@mention`).

Treating `'und'` as a "translatable language" would create backfill
candidates that the LLM will likely fail on again — same outcome, just
two round trips later. Excluding it from the index is a deliberate
short-circuit.

## 8. Failure modes worth knowing

- **LLM lies about language.** The model occasionally says `'en'` for
  a Chinese tweet or vice-versa. There is no local verification. The
  translation may still be correct (the model is good at multilingual
  output), but `lang_detected` is unreliable as a ground-truth signal
  — only as a "what the LLM thought" hint.
- **LLM returns malformed JSON.** `_parse_response` returns `None` →
  the whole batch gets `lang_detected=None` and `translation_failed=True`.
  The row still gets inserted (NULL doesn't violate any constraint),
  but is invisible to the partial backfill indexes and won't be
  re-translated by the backfill subcommand.
- **Translation succeeds but `lang_detected` is missing from the LLM
  response.** `p.get("lang_detected")` returns `None` — same outcome
  as failure. The translation columns get filled; `lang_detected`
  stays NULL.
- **`'und'` from the LLM.** Persists as-is; falls through the backfill
  index predicate (not in the `NOT IN` list). Could create a class of
  "always-und" posts that never get re-translated. Mitigation is
  either (a) prompt the LLM harder to disambiguate short posts, or
  (b) detect `'und'` locally and force a default.

## TL;DR

`posts.lang_detected` is a single TEXT column written by the LLM
during the translation pass, persisted verbatim by `Store.insert_posts`,
backfilled heuristically by migration 004 for pre-v1.7 rows, and read
by **two partial backfill indexes** that gate which rows the
LLM-translation subcommand re-processes. It is not derived locally,
not validated against any external language ID, and trusts the model
at face value. The actual control value comes from the
`NOT IN ('en','en-US','en-GB','und')` predicate on
`idx_posts_text_en_backfill` (and the symmetric predicate on
`idx_posts_text_zh_cn_backfill`) — without `lang_detected`, the
backfill subcommand would re-translate every English tweet in the
corpus.

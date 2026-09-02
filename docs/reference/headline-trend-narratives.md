# Per-brand trend narratives

Current state as of 2026-09-02 JST.

Push In Weight publishes a bilingual why-first trend narrative for every
tracked, non-sentinel brand in each supported window. The default page shows
the two highest-ranked narratives. A saved or explicit brand filter always
selects that brand's stored narrative, even when the brand is not a default
leader.

The live design is not a stock-ticker summary. A notable conversation may be a
change in volume, rate, sentiment, discourse, post type, nationalism,
first-party activity, language, unsanctioned flags, or the content of the
posts. The post content supplies the explanation; quantitative facts supply
context and support.

## Production flow

One committed harvest completion envelope enters the queue-isolated headline
worker. The production path is:

1. Python opens a PostgreSQL `REPEATABLE READ, READ ONLY` transaction and
   builds one immutable all-brand snapshot for the window.
2. Python computes stable facts, compact shape summaries, corpus phrase
   signals, and bounded evidence. Raw vectors and private source identifiers
   remain in the private snapshot.
3. One rank call orders all manifest brands by conversation notability. Size
   alone is not rank authority. An invalid rank response falls back to the
   complete canonical brand order; it cannot drop a brand.
4. Eligible brands are divided in that order into deterministic batches of at
   most five. One editor call returns a bilingual headline and substantive
   secondary paragraph for every brand in a batch.
5. One independent critic call receives the same closed packet, the raw editor
   response, and mechanical parse diagnostics. It approves, repairs, or holds
   each brand independently.
6. Python checks only closed schema, brand/evidence/fact ownership, exact
   quantitative display strings, and complete manifest coverage. Semantic
   support, event identity, causality, quotation accuracy, proportionality,
   translation equivalence, and secondary usefulness belong to the critic.
7. Every manifest brand reaches a terminal row before the visible pointer
   advances atomically. A partial run never becomes public.

There is no active shared-headline generator, regex event matcher,
server-derived event anchor, causal-language list, undeclared-entity scanner,
or Python semantic publication gate. Those paths were removed. Provider and
mechanical safety checks remain.

## Calls and batching

For `N` eligible brands, one window uses:

```text
1 rank + ceil(N / 5) editors + ceil(N / 5) critics
```

Twenty eligible brands therefore use nine calls: one rank, four editors, and
four critics. Calls execute with worker concurrency one. Each Celery stage owns
at most one provider transport.

The provider route is pinned independently of translation and classification:

| Setting | Value |
| --- | --- |
| Provider | DeepSeek |
| Base URL | `https://api.deepseek.com/anthropic` |
| Model | `deepseek-v4-flash` |
| Thinking | disabled |
| SDK retries | zero |
| Rank output cap | 2,400 tokens |
| Editor output cap | 8,000 tokens |
| Critic output cap | 9,000 tokens |
| Timeout | 60 seconds |
| Editor prompt | `headline-editor-v6` |
| Critic prompt | `headline-critic-v6` |
| Editor batch | at most five brands |
| Worker concurrency | one |

The run ledger reserves call, input-token, output-token, and dollar capacity
before each request. Completed provider usage replaces the reservation for
later budget decisions. Current bounded defaults are 25 calls, 700,000 input
tokens, 160,000 output tokens, and $1.50 per window run. The 2026-09-02
pricing revision uses DeepSeek V4 Flash's conservative peak/cache-miss rates of
$0.44 per million input tokens and $1.32 per million output tokens; off-peak or
cache-hit billing can only reduce actual cost. Pricing is versioned in
configuration and must be reviewed when the provider changes pricing.

## Snapshot and provider packets

`build_trend_analysis_snapshot()` produces packet schema version 3. Its
top-level fields are:

```text
packet_schema_version
snapshot_schema_version
window_days
as_of
baseline_context
coverage
dossiers[]
```

Every tracked non-sentinel brand has exactly one dossier. A dossier has a
terminal input outcome:

- `narrative_eligible` — the editor and critic may write a narrative;
- `no_content` — coverage is complete and the brand has no usable raw post
  text; or
- `data_quality_unavailable` — a source or packet failure left no supportable
  content-led narrative.

Translation and classification lag do not make a nonempty brand unavailable.
Usable original text keeps the dossier eligible while enrichment-dependent
families declare partial or unavailable coverage.

Each dossier includes:

- brand key and bilingual display names;
- an `enrichment_coverage` block with total, translated, classified, and fully
  enriched counts plus the same counts for the newest 30 minutes of a one-day
  window;
- brand-local comparison availability and suppression reasons;
- compact summaries for volume, post type, sentiment, discourse, Chinese and
  US nationalism, language, unsanctioned flags, account role, and corpus
  phrases;
- bounded citable facts with exact English and Chinese display values;
- a compact shape summary, including direction, peak/trough, and the dominant
  transition rather than the full time series;
- bounded corpus phrase signals computed over the complete deduplicated
  period, not only the evidence sample; and
- a bounded, deduplicated evidence set.

Private `raw_series`, aggregate inputs, database provenance, author grouping,
and source-cluster identifiers are not sent to the provider. They remain in
the immutable database snapshot for audit and future recomputation.

### Facts

Facts are stable packet-owned objects. They may cover volume, engagement,
post type, sentiment, discourse, nationalism, language, unsanctioned flags,
official/staff post count, and corpus phrase document count. Each fact records:

```text
fact_id
family
metric
label_key
current_value
baseline_value
source_value
unit
direction
display_en
display_zh_cn
coverage_scope
```

`display_en` and `display_zh_cn` are the exact strings the editor may put in
copy. A percentage-point fact can use a concise public display such as
`13 pts` / `13个百分点`; the raw decimal remains in `source_value`.
`coverage_scope` identifies complete, partial, or unavailable support with the
covered and total post counts. A classifier-derived family with zero covered
posts emits no citable fact.

The baseline is brand-local. The top-level `baseline_context` describes the
period, while each dossier says whether that comparison is usable for that
brand. Until historical coverage improves, missing prior periods are normal
and explicitly suppress comparison wording. Ranking may still use current
content and relative differences among brands.

### Evidence

Evidence is selected from deduplicated source posts, never simulated posts.
The target changes with window length:

| Window | Total target | First-party reservation | Ordinary reservation |
| --- | ---: | ---: | ---: |
| 1 day | 6 | 2 | 4 |
| 7 days | 8 | 3 | 5 |
| 30 days | 10 | 4 | 6 |
| 365 days | 12 | 4 | 8 |

Official and staff accounts are validated `BrandAccount` relationships and
are trusted first-party identities. Their reserved slots are not mandatory.
If fewer first-party posts exist, unused slots return to the shared pool so the
total evidence target remains constant. If a bad source produces many
first-party rows, dedupe, reservoir bounds, the per-brand target, excerpt
limits, and the 128 KiB request limit prevent it from expanding the packet.

Ordinary author identity remains opaque. A trusted first-party handle may be
sent because its identity is product evidence. Original language, English and
Chinese translations, and translation labels may be included when available.
Every evidence row declares its translation and classification status; pending
translations remain null without removing the original text. A populated
one-day dossier reserves at least one evidence slot for the newest 30 minutes,
even when that row is still pending enrichment.

## AI contracts

### Rank

The rank response returns every manifest brand exactly once with confidence
and packet-owned fact, evidence, or corpus-signal reason references. Rank is an
internal ordering aid; public DTOs never expose position or score.

### Editor

Each editor batch returns one complete bilingual object for every batch brand:

```text
brand_key
headline_en / headline_zh_cn
secondary_en / secondary_zh_cn
narrative_kind
confidence
headline_proposition_ids
secondary_proposition_ids
propositions[]
events[]
```

The secondary paragraph is never empty and never says only “insufficient
data.” If no striking event is supported, it describes what the posts are
mentioning. Propositions own their exact bilingual claim span and packet fact
and evidence IDs. Event objects own their bilingual label, date, support kind,
evidence, and proposition IDs.

The editor uses original text, timing, volume, language, account role, and
corpus signals even when every post is pending enrichment. Partial classifier
claims must name their covered subset. Unavailable sentiment, post-type,
discourse, nationalism, or unsanctioned families cannot support a claim.

### Critic

The critic returns one decision per manifest brand:

- `approve` — the editor narrative is supported;
- `repair` — the critic supplies a complete supported replacement from the
  same closed packet; or
- `hold` — no narrative publishes for that attempt, with a closed hold code.

Hold codes distinguish unsupported events, causality, numbers, quotations,
event conflation, cross-brand evidence, translation mismatch, weak secondary
copy, proportionality, and unsafe instruction following. A held brand serves
its prior verified row as stale when one exists. On a first attempt with no
last-good row, the UI shows an honest unavailable state.
Enrichment lag by itself is not a hold reason. The critic repairs an overstated
partial-coverage claim or removes an unavailable-family claim while preserving
a supportable raw-content narrative.

## Persistence and recovery

The durable tables are:

- `TrendNarrativeRun` — one immutable window/cutoff snapshot and manifest;
- `TrendNarrativeProviderCall` — one rank, editor, or critic transport with a
  stable identity, request hash, lease fence, raw response hash, usage, and
  terminal state;
- `BrandTrendNarrative` — one immutable brand outcome with final prose,
  propositions, events, citations, critic payload, attempt/verification times,
  and optional last-good link;
- `TrendNarrativeVisibleRun` — one atomic public pointer per window; and
- `TrendNarrativeWorkSlot` — one active cutoff plus only the latest newer
  queued cutoff.

The provider call lifecycle is `reserved → sent → completed`, `failed`, or
`ambiguous`. Once a request is marked sent, an unknown timeout is ambiguous and
is never resent in the same run. An expired lease after `sent` is durably
terminalized as `ambiguous`; lease expiry before `sent` may recover a lost
broker handoff. An older cutoff cannot replace a newer visible cutoff.

The work slot bounds backlog at concurrency one. Envelopes become due at the
configured 60-, 1,440-, 10,080-, and 43,200-minute cadences for the
1/7/30/365-day windows. A newer due harvest replaces the single queued cutoff;
an intervening harvest is ignored rather than creating obsolete runs. Snapshot
construction also fails closed above the configured production brand cap
before the all-brand detail/evidence queries begin.

If ranking fails, overlapping brands preserve the last visible successful
order. New brands follow a deterministic fallback based on within-window
movement, then mix/content signals, then canonical key. A held result carries
the same last approved row through consecutive held runs instead of losing the
fallback after the first hold.

## Public DTO and UI

The browser receives DTO schema version 3. It contains at most two selected
items and no evidence, prompts, provider responses, internal ranks, or private
packet fields.

- No explicit filter: show the first two usable brands in internal order.
- One selected brand: show that brand.
- Two selected brands: show both.
- More than two selected brands: show the first two in internal order and a
  localized neutral `2 of N selected` disclosure.

Each item includes brand identity/link, state, bilingual headline and
secondary, attempted/verified timestamps, a prettified relative freshness
label, and an exact UTC timestamp for the title and accessible label. English
and Simplified Chinese use equivalent structures. A request never calls the
provider; it reads one visible run from PostgreSQL.

## Controls and rollback

`activation_state` remains the master fail-closed state. `pending` disables
effective serving, enqueue, and provider calls even if the requested booleans
are true. `owner_override` and reviewed materiality versions may activate the
requested controls.

`publication_source` supports:

- `prefer_per_brand` — use DTO v3 and optionally fall back to an eligible
  persisted legacy row while migration fallback is enabled; and
- `legacy_only` — ignore per-brand rows and serve only persisted legacy rows.

`legacy_only` requires new enqueue and provider transport to be disabled. The
legacy `TrendNarrative` table and projection remain for rollback, but no code
generates new shared rows. Database migration reversal refuses to drop the
new ledger while per-brand rows, suspended runs, or work-slot state exist;
operational rollback uses `legacy_only`, not destructive schema reversal.

## Operator evaluation

`evaluate_trend_headlines` is finite and writes no publication rows.

```bash
python manage.py evaluate_trend_headlines \
  --dry-run --synthetic --manifest /absolute/path/manifest.json

python manage.py evaluate_trend_headlines \
  --execute --synthetic --manifest /absolute/path/manifest.json

python manage.py evaluate_trend_headlines \
  --dry-run --real --windows 1,7,30,365 \
  --as-of 2026-08-27T00:00:00+00:00 \
  --manifest /absolute/path/manifest.json
```

The manifest names the reviewer and exact model and caps calls, input tokens,
output tokens, dollars, context, packet bytes, brands, concurrency, and priced
rates/version. Preflight builds the deterministic canonical reservation graph
and refuses any aggregate cap violation before transport. Rank order can
regroup brands at execution time, so each actual packet and request context is
checked again immediately before its provider call.

Execution artifacts retain the full immutable snapshots, exact provider
envelopes and requests, raw responses, mechanical results, critic decisions,
tokens, latency, cost, and a bilingual rubric for why-first relevance, factual
support, proportionality, translation equivalence, and secondary usefulness.
Synthetic execution sends a supported gold draft plus mechanically valid
unsupported event, causality, event-conflation, mistranslation,
cross-evidence, invented-detail, and unsafe-instruction drafts through the
production critic. Activation requires every control response to validate,
zero unsupported false accepts, and zero supported false holds in that finite
set. Real-data evaluation omits those controls and records calibration as
`not_run`, so it must be reviewed alongside a green synthetic artifact. The
injection-hardened critic prompt is versioned as `headline-critic-v2`.

`headline_status --json` is provider-free. It reports per-window run
completeness, missing and held brands, last-good availability, latest attempt,
last verification, stale duration, stage failures, ambiguous sends, bounded
work-slot backlog, and concurrency-one drain telemetry. It never prints
packets, responses, evidence, or credentials.

## Verification map

| Boundary | Primary regression |
| --- | --- |
| Compact all-brand dossier and evidence bounds | `tests/test_trend_narrative_candidates.py` |
| Rank/editor/critic schema and provider safety | `tests/test_trend_narrative_generation.py` |
| Call ledger, activation, retention | `tests/test_trend_narrative_lifecycle.py` |
| Work-slot coalescing and 20-brand graph | `tests/test_trend_narrative_orchestration.py` |
| Queue-only Celery entrypoint | `tests/test_trend_narrative_tasks.py` |
| DTO v3 filters and freshness | `tests/test_trend_narrative_projection.py` |
| Bilingual desktop/mobile cards | `tests/test_home_v22_browser.py`, `tests/test_pw_chart_filter.js` |
| Finite no-publication evaluation | `tests/test_trend_narrative_evaluation.py`, `tests/test_evaluate_trend_headlines_command.py` |
| Provider-free operator status | `tests/test_headline_status.py` |

Historical plans and dated analysis artifacts describe earlier experiments and
remain historical evidence. This reference is the current production contract.

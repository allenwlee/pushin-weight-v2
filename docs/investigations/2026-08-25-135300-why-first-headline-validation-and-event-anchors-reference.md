# Why-first headline validation and event anchors

Status: current-state reference with decision recommendations  
Code baseline: production SHA `8a7123d98ee3a932ceec0f0a292fbf661011e596`  
Audience: Product, Corporate Development, Engineering, and Operations

## Executive summary

PushinWeight's why-first headline system is designed to explain **what changed
in the conversation and why it appears notable**, with metrics used as
supporting evidence rather than as the story itself. The system combines two
different forms of judgment:

- DeepSeek makes the editorial judgment: which measured brand has the best
  supported story, how to express that story in English and Simplified
  Chinese, and which packet evidence IDs support each headline or observation.
- PushinWeight's Python application makes the control judgment: it converts
  the model's response into a richer internal claim record, checks the response
  against 43 possible output-rejection conditions, and publishes the result
  only if every applicable check passes.

That split is strategically sensible: the model is better at interpreting
discourse, while deterministic code protects the product from invented IDs,
unsupported numbers, unsafe text, and accidental publication races. The
current implementation, however, asks deterministic code to infer some
semantic relationships that it does not actually understand. The event-anchor
workflow is the clearest example.

An event anchor is not chosen by DeepSeek. Python derives it by scanning all
posts cited for a claim and selecting an event-looking text span. It does not
map a specific proposition in the headline—such as “Xiaomi announced XRING
O3”—to the evidence IDs supporting that proposition. When one headline mixes
multiple topics, any event-looking sentence in the combined evidence list can
win. The validator may therefore reject good editorial output because the
server linked it to the wrong cited sentence.

The recent Xiaomi case is a false-rejection pattern, not a simple absence of
evidence. The packet contained evidence about free MiMo API access and XRING
O3, including an explicit XRING O3 announcement reference. The model combined
those supported topics into one headline and cited a mixed evidence set. The
server derived an anchor from a MiMo-V2.5 sentence containing event-like
language, then tested that sentence as though it were the XRING O3 proposition.
The response failed `headline_output_event_anchor_unsupported`. The system
proved that its **chosen text span** lacked the required support; it did not
prove that the **headline's XRING O3 proposition** was absent from the packet.

The commercial implication is important: validation failures consume a paid
provider attempt and delay freshness, while the public product continues to
serve the last-good headline. This protects trust but can also prevent a
decision-useful headline from reaching users. The next product decision should
therefore distinguish high-value integrity gates from semantic-quality checks
that are better treated as warnings or repaired deterministically.

## The product objective

The headline is a compact conversation-intelligence product, not a market
ticker. A brand can be the relevant story when total volume is flat but the
content mix, sentiment, discourse, usage reports, or engagement changes
materially. Conversely, a brand can lead numerically while the market is
effectively quiet. The intended output is therefore:

1. a content-led explanation of what people are discussing;
2. a careful account of why that discussion appears notable;
3. one or more supplied measurements as corroborating color; and
4. bilingual copy that conveys the same materiality and confidence.

The prompt explicitly says that candidate rank is relative rather than proof
of absolute importance, numbers cannot substitute for the “why,” and causal
claims are prohibited. It also requires at least one supplied quantitative
fact in the headline whenever the selected candidate has one available.

## Current operating model

```text
Stored posts + classifications + translations
                    |
                    v
   Read-only, repeatable snapshot and shortlist
                    |
                    v
  Bounded provider packet: facts + post excerpts
                    |
                    v
     DeepSeek: bilingual prose, selection, citations
                    |
                    v
 Python: derive metadata -> validate 43 conditions
                    |
          +---------+----------+
          |                    |
        pass                  reject
          |                    |
 publish atomically     record failure/backoff
          |                    |
 serve new current       keep serving last-good
```

### Stage 1: build the analytical snapshot

For each fixed window—1, 7, 30, or 365 days—the worker opens a PostgreSQL
`REPEATABLE READ, READ ONLY` transaction. It calculates trend-family facts,
selects a bounded candidate shortlist, fetches coarse series, and selects a
bounded evidence set. The shortlist intentionally considers volume,
engagement, post type, discourse, sentiment, and nationalism-related discourse
rather than simply choosing the largest percentage move.

Evidence selection begins with real stored post text, but the provider does
not receive every post in the window. Python selects a bounded reservoir,
normalizes and truncates representative excerpts, removes private post and
author identifiers, and gives the excerpts stable packet-local evidence IDs.
The packet retains source-cluster, author-group, role, official-source,
post-kind, post-type, discourse, and sentiment signals so the model can assess
support without receiving public handles or internal post IDs.

### Stage 2: project the provider packet

The provider packet includes window and coverage context, comparison controls,
thresholds, coarse series, and a list of candidates. Each candidate includes:

- stable candidate and brand keys plus bilingual display names;
- the analytical signals that caused it to enter the shortlist;
- family facts and approved quantitative display facts;
- metadata trajectories, episodes, and coarse time series;
- evidence-allocation and evidence-support summaries; and
- bounded post excerpts with opaque evidence, author-group, and
  source-cluster IDs.

`quantitative_facts` is the only approved source of analytical numbers for
prose. Each fact supplies exact English and Chinese display strings. The model
copies those strings; it does not calculate a new percentage.

### Stage 3: DeepSeek makes the editorial selection

DeepSeek receives one closed packet and makes one request with automatic HTTP
retries disabled. It must return exactly seven top-level keys:

| Provider-owned key | Business purpose |
| --- | --- |
| `body_en`, `body_zh_cn` | One aligned bilingual headline |
| `observations_en`, `observations_zh_cn` | Zero to two aligned supporting observations |
| `selected_candidate_ids` | One measured candidate by default; two only in an exceptional co-dominant story |
| `subjects` | Normally empty; optionally one supported evidence-only product/company/model/organization |
| `claims` | One citation object for the headline, followed by one for each observation |

Each provider claim contains only `evidence_ids`. DeepSeek is responsible for
choosing the cited rows. It does **not** return candidate ownership, fact IDs,
fact families, event anchors, explanation type, confidence, or claim-order
indexes. Python intentionally overwrites those fields even if a provider
response includes legacy copies of them.

### Stage 4: Python assembles server-owned metadata

The server translates the minimal editorial response into the internal output
schema before validation.

| Derived field | Current derivation |
| --- | --- |
| Measured `subjects` | One ordered brand subject for every selected candidate; bilingual names and brand key come from the packet. |
| Evidence-only subject envelope | The model chooses name, type, and evidence IDs; Python normalizes it and later checks independence, exact naming, and safety. |
| `observation_index` | Claim position minus one: headline is `-1`, then observations `0` and `1`. |
| `candidate_ids` | The headline inherits all selected IDs. Observations are narrowed using cited-evidence ownership, matched quantitative facts, and explicit brand-name mentions; if none resolve, Python falls back to all selected IDs. |
| `quantitative_fact_ids` | Exact `display_en` **and** `display_zh_cn` strings must both appear in the paired claim. Duplicate display values require candidate proximity and family/label context to resolve uniquely. |
| `families` | The families of resolved quantitative facts, plus `evidence` when the claim cites any evidence IDs. |
| `event_anchor` | Empty unless either locale contains event-language. If triggered, Python scans all cited excerpts and chooses an event-looking evidence span. |
| `explanation_type` | `structured_mix` or `recurring_content` when cited evidence meets recurrence rules; otherwise `isolated_event` if an event anchor exists; otherwise `aggregate_trajectory`. |
| `evidence_confidence` | One of `official_and_recurring`, `recurring_independent`, `official_only`, `isolated`, or `aggregate_only`, based on cited non-repost rows. |

Two current-state nuances matter:

- Recurrence requires one shared `theme_cluster_id` represented by at least two
  author groups and at least two source clusters. Two unrelated posts do not
  become a recurring theme merely because both were cited.
- `quiet_relative_leader` remains a valid internal enum value, but the current
  server assembler does not assign it. Server assembly overwrites provider
  metadata and currently chooses only `structured_mix`, `recurring_content`,
  `isolated_event`, or `aggregate_trajectory`.

### Stage 5: validate and publish atomically

Validation is fail-fast: the first failing condition stops evaluation and the
whole response is rejected. There is no provider repair call and no partial
publication. As a result, the error stored on a failed production attempt is
the **first observed error**, not a complete count of every condition that the
same output might fail.

If every check passes, lifecycle code obtains the per-window publication lock,
verifies the worker's fenced lease, and publishes only if the attempt is newer
by publication epoch and facts timestamp. The previous current row becomes
`superseded`; the new row becomes `published` and `is_current=true`.

If validation fails, the attempt becomes `failed`, records a safe error code,
and enters bounded retry backoff. It does not replace the current publication.
The public projection queries only the current published row, so users continue
to see the last-good headline until a newer output passes. If no current row
exists, the UI returns a warming-up/unavailable message. A last-good row can be
reported as stale when its last successful check exceeds the window-specific
freshness allowance.

## Responsibility boundaries

| Decision | DeepSeek | Python application | PostgreSQL |
| --- | :---: | :---: | :---: |
| Interpret the discourse and write the “why” | Owns | Constrains and validates | Supplies source data |
| Choose the measured candidate(s) | Owns | Verifies IDs and subject topology | Persists selection |
| Choose evidence-only entity and evidence citations | Owns | Verifies identity, independence, ownership, and safety | Persists normalized subjects |
| Choose evidence IDs for each complete claim | Owns | Verifies IDs exist and belong to selected candidates | Persists claim JSON |
| Map individual propositions inside one claim to individual evidence IDs | Not represented | Not represented | Not represented |
| Resolve displayed numbers back to packet facts | No | Owns | Persists facts and claims |
| Derive event anchor, explanation type, and confidence | No | Owns | Persists derived claim metadata |
| Decide whether output can publish | No | Owns all-or-nothing decision | Enforces locks, uniqueness, and state constraints |
| Serve last-good after a failure | No | Selects current row | Stores immutable attempts and current publication |

The missing proposition-to-evidence mapping is the central product gap. One
claim can contain several propositions and up to four evidence IDs, but the
data model records only a single undifferentiated evidence list and a single
event anchor for the entire claim.

## Event-anchor deep dive

### What an event anchor is intended to do

An event anchor is intended to prevent the model from converting loose chatter
or speculation into a concrete fact. A headline that says a company
“announced,” “launched,” “released,” or “unveiled” something should be linked to
an exact span in the cited packet. The claim passes when the exact derived span
appears in either:

- at least one cited row marked as an official source; or
- cited non-repost rows from at least two author groups and two source
  clusters.

This is an evidence-integrity control, not an editorial score.

### How the algorithm works today

1. **Trigger on headline language.** Python searches either locale for a broad
   event vocabulary. English includes announcement, launch, release, unveil,
   debut, open-source/open-sourced, partnership, acquisition, funding, outage,
   and incident forms. Chinese includes terms such as `宣布`, `发布`, `推出`,
   `上线`, `亮相`, `开源`, `合作`, `收购`, `融资`, `故障`, and `事故`.
2. **Pool every row cited by that claim.** The server does not know which
   evidence ID supports which phrase. All cited rows become one ordered search
   space.
3. **Prefer the first event-looking official sentence.** If any cited row is
   marked official, the first sentence in evidence order containing an anchor
   keyword wins.
4. **Otherwise search for a shared literal phrase.** Python constructs short
   word windows around event keywords and uses the longest phrase that appears
   literally in at least two cited excerpts.
5. **Otherwise take the first event-looking sentence anywhere.** This is the
   fallback that can convert a single unrelated event-like sentence into the
   claim's anchor.
6. **Normalize the span.** URLs are removed; unsafe characters are rejected;
   long text is trimmed around the keyword to 160 characters.
7. **Test support for that exact span.** The validator checks only cited rows
   containing the chosen anchor as a case-insensitive literal substring, then
   applies the official-or-two-independent-sources rule.

This is deterministic and auditable, but it is lexical rather than semantic.
It answers “Which cited sentence looks most like an event?” It does not answer
“Which cited sentence supports the event actually asserted in this headline?”

### Exact failure modes

| Failure mode | Why it occurs | Product consequence |
| --- | --- | --- |
| False event trigger | An adjective or category label such as “open-source” / `开源` is treated like an event action. | A claim that did not need an event proof can acquire one and be rejected. |
| Cross-topic anchor collision | One claim cites posts for several propositions, but the first event-looking sentence can concern the wrong product or topic. | Strong evidence for the intended event is never evaluated. |
| Citation-order sensitivity | Official rows are searched first, then the remaining rows in supplied evidence order. | Reordering equally valid citations can change the derived anchor and pass/fail result. |
| One-anchor limit | A claim can mention more than one event but stores one anchor. | One event can mask or incorrectly stand in for another. |
| Whole-sentence over-specificity | The anchor can be an entire sentence rather than the concise event identity. | Two sources describing the same event in different words fail literal containment. |
| Literal phrase dependence | Shared support requires exact case-folded text rather than entity/action equivalence. | Paraphrases and bilingual descriptions are undervalued. |
| Broad mixed evidence set | Evidence IDs apply to the claim as a whole, not to atomic propositions. | The validator cannot distinguish supporting, contextual, and unrelated citations. |
| Source-metadata sensitivity | Official status, author grouping, source clustering, repost status, and theme clustering are upstream metadata. | Classification or clustering errors can alter validation without changing the prose. |
| First-error opacity | Validation stops at the first failure and failed raw output is not published as a replayable artifact. | Operators cannot tell from the persisted error code how many other gates the response would pass or fail. |

### The Xiaomi MiMo / free API / XRING O3 incident

The recent output combined two concrete topics within the Xiaomi conversation:

- free access to the MiMo-V2.5 API; and
- the XRING O3 announcement.

The packet contained relevant support for both topics. The reviewed evidence
included two independent free-access/API references and two XRING O3-related
references, one of which explicitly described Xiaomi announcing the XRING O3
SoC. In product terms, the packet contained a reasonable basis for the
headline the owner reviewed.

The failure happened after DeepSeek returned the prose and citations:

1. DeepSeek attached one combined list of evidence IDs to the whole headline.
2. Event language in the headline activated event-anchor derivation.
3. Python scanned the mixed evidence list rather than isolating the XRING O3
   proposition.
4. It chose an event-looking MiMo-V2.5 specification/open-source sentence.
   The fact that this sentence was Chinese is incidental; the problem was its
   topic and grammatical role, not its language.
5. Python then searched the cited rows for that exact MiMo sentence and applied
   the official-or-two-independent-sources rule.
6. The chosen span did not meet that rule, so the output was rejected as
   `headline_output_event_anchor_unsupported`.

The rejection therefore means: **the server-derived MiMo text span did not
meet the anchor-support rule.** It does not mean: **the packet contained no
evidence of free API access or XRING O3.** Nor does it establish that DeepSeek
invented the XRING O3 topic. The linkage layer selected the wrong proposition
to test.

Even replacing `open-source` with a more precise keyword such as “launch day”
would not solve the structural problem. If that phrase appeared in a different
MiMo post earlier in the combined evidence order, Python could still attach it
to the XRING O3 clause. Better keywords can reduce false triggers; they cannot
create the missing proposition-to-evidence relationship.

## Complete inventory of output rejection codes

The current generator contains **43 distinct `headline_output_*` rejection
codes**. These are possible failure categories, not 43 sequential LLM calls.
Because evaluation is fail-fast, one attempt normally records only one code.

### 1. Response envelope and schema — 4

| Code | What it protects |
| --- | --- |
| `headline_output_text_missing` | Provider response has no readable text block. |
| `headline_output_envelope_invalid` | A Markdown-fenced response is not one valid `json`/plain fence with a closing fence. |
| `headline_output_json_invalid` | Response text cannot be parsed as JSON. |
| `headline_output_schema_invalid` | The server-assembled object fails the strict Pydantic schema: exact keys, types, cardinality, bilingual structure, canonical text, entity-name safety, claim order, or other structural constraints. |

### 2. Candidate, subject, and entity integrity — 10

| Code | What it protects |
| --- | --- |
| `headline_output_candidate_unknown` | A selected or measured candidate ID is absent from the packet. |
| `headline_output_subject_duplicate` | Measured subjects resolve to a missing or repeated brand key. |
| `headline_output_entity_support_weak` | An evidence-only entity lacks two independent author groups and source clusters, or the candidate packet says entity support is insufficient. |
| `headline_output_entity_not_evidenced` | The exact evidence-only entity name is not present in every cited subject-support excerpt. |
| `headline_output_entity_person_like` | A person-like name is labeled as a company or organization without an organizational marker. |
| `headline_output_entity_claim_unlinked` | An evidence-only subject's evidence IDs are not all linked to every claim that names it, including the headline. |
| `headline_output_entity_self_trending` | An evidence-only contextual entity is described as though it independently has measured trend, volume, attention, adoption, or similar movement. |
| `headline_output_undeclared_entity` | Prose names an unselected packet candidate or an unapproved capitalized English entity. |
| `headline_output_en_subject_missing` | A declared subject is absent from the English headline. |
| `headline_output_zh_subject_missing` | A declared subject is absent from the Chinese headline. |

### 3. Claim ownership and family integrity — 4

| Code | What it protects |
| --- | --- |
| `headline_output_claim_candidate_invalid` | A claim points outside the selected candidate set. |
| `headline_output_claim_family_invalid` | A claim uses a family outside the allowed vocabulary. |
| `headline_output_claim_family_unsupported` | A non-evidence family is not present in the claimed candidate's available family facts. |
| `headline_output_headline_candidates_incomplete` | The headline claim does not cover the complete ordered selected-candidate set. |

### 4. Evidence linkage and explanation strength — 6

| Code | What it protects |
| --- | --- |
| `headline_output_evidence_unknown` | A cited evidence ID is absent from every packet candidate. |
| `headline_output_evidence_candidate_mismatch` | A cited evidence row does not belong to any candidate owned by the claim. |
| `headline_output_evidence_claim_unlinked` | A claim declares the `evidence` family but cites no evidence IDs. |
| `headline_output_evidence_family_missing` | A claim cites evidence IDs but lacks the `evidence` family. |
| `headline_output_explanation_support_weak` | A recurring-content or structured-mix label lacks one recurring theme across two authors and two source clusters. |
| `headline_output_evidence_confidence_invalid` | Derived confidence does not match the actual official/recurring/isolated/aggregate evidence profile. |

### 5. Event integrity — 4

| Code | What it protects |
| --- | --- |
| `headline_output_event_anchor_required` | Event language appears in either locale but no anchor can be derived. |
| `headline_output_event_anchor_unlinked` | An anchor exists without cited evidence and the `evidence` family. |
| `headline_output_event_anchor_unsupported` | The exact anchor is neither in a cited official row nor in cited non-repost rows from two authors and two source clusters. |
| `headline_output_isolated_event_unlinked` | An `isolated_event` explanation has no anchor or no cited non-repost evidence row. |

### 6. Quantitative integrity — 5

| Code | What it protects |
| --- | --- |
| `headline_output_quantitative_fact_required` | The headline omits all quantitative facts even though at least one is supplied for a selected candidate. |
| `headline_output_quantitative_fact_unknown` | A quantitative fact ID does not exist in the packet. |
| `headline_output_quantitative_candidate_mismatch` | A fact belongs to a candidate outside the claim. |
| `headline_output_quantitative_family_mismatch` | A fact's family is absent from the claim families. |
| `headline_output_quantitative_fact_unused_or_unaligned` | A linked fact's exact display string is not present in both English and Chinese versions of that claim. |

### 7. Explanation-family coherence — 1

| Code | What it protects |
| --- | --- |
| `headline_output_mix_family_missing` | A `structured_mix` explanation lacks a post-type, discourse, or sentiment family. |

### 8. Editorial form and text safety — 9

| Code | What it protects |
| --- | --- |
| `headline_output_en_too_long` | English headline exceeds the configured character limit. |
| `headline_output_zh_too_long` | Chinese headline exceeds the configured character limit. |
| `headline_output_en_observation_too_long` | An English observation exceeds the configured headline-length ceiling. |
| `headline_output_zh_observation_too_long` | A Chinese observation exceeds the configured headline-length ceiling. |
| `headline_output_en_primary_not_leading` | The primary brand begins after the first 48 normalized characters of the English headline. |
| `headline_output_zh_primary_not_leading` | The primary brand begins after the first 48 normalized characters of the Chinese headline. |
| `headline_output_en_digits` | English prose contains digits outside declared names and exact approved quantitative displays. |
| `headline_output_zh_digits` | Chinese prose contains digits outside declared names and exact approved quantitative displays. |
| `headline_output_nationalism_causal` | Either locale uses prohibited causal language such as “caused,” “drove,” `导致`, or `推动`, regardless of the claim's declared family. |

## Operational and business implications

### What the controls do well

- They keep invented candidate, evidence, and quantitative IDs out of the
  published product.
- They ensure the public number is copied from a deterministic calculation,
  not recomputed by the model.
- They preserve bilingual subject and number alignment.
- They prevent one worker from overwriting a newer publication and preserve a
  durable audit ledger.
- They fail safely: a rejected attempt cannot erase or partially replace the
  last-good headline.
- They constrain evidence-only products and companies from being presented as
  measured trends.

### Where the current economics break down

- A provider call is paid before semantic validation finishes. A false
  rejection spends tokens but produces no new customer-facing value.
- One lexical mismatch can block an otherwise useful headline, even when the
  model's prose and the underlying packet are commercially adequate.
- Fail-fast reporting stores only one error. It is not possible to answer “how
  many validators would reject this output?” from the failed database row
  alone; that requires retaining and replaying the exact raw or assembled
  output against an all-errors diagnostic runner.
- Failed attempts enter backoff, which lengthens the time before the next
  chance to publish.
- Last-good serving protects continuity, but customers can see stale copy and
  operators may incorrectly conclude that generation is not running.
- The system currently treats all validator failures as equally blocking even
  though they have different risk profiles. An invented percentage is a hard
  factual-integrity problem; an imperfect server-derived anchor can be a
  metadata-linkage problem.

## Current-state limitations

1. Claims are not decomposed into atomic propositions. One claim can contain
   several facts, topics, or events but has one evidence list and one event
   anchor.
2. Event extraction is keyword- and order-driven, not entity-aware or
   proposition-aware.
3. Exact sentence containment is stricter than real-world semantic support;
   independent sources commonly paraphrase the same event.
4. Server-derived fields can cause rejection even though the prompt tells the
   model not to return those fields.
5. Failed production attempts persist the safe first error code but not a
   complete validator report suitable for product review.
6. `headline_output_schema_invalid` collapses many Pydantic failures into one
   category, which limits operator diagnosis.
7. A packet-level `event_claim_may_be_supported` flag only says the candidate
   has enough official or independent sources in aggregate; it does not prove
   that those sources support the same event.
8. The current code has no repair pass. It rejects and waits for a later source
   cycle even when only server-derived metadata is wrong.

## Recommendations — not current behavior

The following options are product decisions. They describe recommended future
behavior and should not be read as features that already exist.

### Recommendation 1: separate hard integrity gates from quality warnings

Keep the following categories blocking: malformed JSON/schema, unknown or
wrong-owner candidate/evidence IDs, unsupported quantitative displays, unsafe
text, and publication/lease integrity. Treat a failure caused solely by a
server-derived event anchor as a non-blocking quality warning when the cited
evidence IDs are valid and the named event/product appears directly in cited
text. Publish the editorial output while storing that the anchor could not be
deterministically certified.

This is the fastest path to reducing false rejection without turning off core
grounding.

### Recommendation 2: represent proposition-level evidence

Replace the current “whole claim -> mixed evidence IDs” relationship with
small claim atoms, for example:

```json
{
  "proposition": "Xiaomi announced XRING O3",
  "proposition_type": "event",
  "evidence_ids": ["e_xring_announcement", "e_xring_context"]
}
```

The model should make this semantic mapping because it already understands the
headline it wrote. Python should verify only that the IDs exist, belong to the
selected candidate, directly contain the named entity, and satisfy the chosen
support policy. It should not search unrelated citations for the first
event-looking sentence.

### Recommendation 3: add an all-errors replay diagnostic

Persist a secure, redacted copy of the provider response and the assembled
metadata for failed attempts, subject to a short retention policy. Add an
offline validator mode that evaluates every independent gate rather than
stopping at the first one. Product and Engineering could then answer, for an
exact rejected headline, which failures are substantive, which are redundant,
and which come from server derivation.

This observability should precede broad gate removal. Today, the recorded first
error is insufficient evidence that it is the only blocker.

### Recommendation 4: make server repair bounded and deterministic

Before failing a valid editorial response, allow one no-provider repair step
for redundant server-owned metadata: discard a mismatched derived anchor,
reclassify explanation/confidence, and re-run the remaining hard validators.
Do not change the model's prose, citations, selected candidate, or numbers in
this repair step. Store both the original derivation and repaired outcome for
audit.

### Recommendation 5: make accepted real headlines regression fixtures

When the owner approves a real headline as product-quality, preserve its exact
packet, provider response, intended outcome, and disputed validator results as
a redacted regression fixture. The Xiaomi free-API/XRING O3 example should be
the first proposition-linkage fixture. A future validator change should be
measured against both false-accept and false-reject cases, not only synthetic
contract tests.

## Technical appendix: code ownership

Line references below apply to production SHA
`8a7123d98ee3a932ceec0f0a292fbf661011e596`.

| Concern | Code owner |
| --- | --- |
| Editorial prompt, event/causal regexes, strict output models | `monitor/trend_narrative_generation.py:32-496` |
| Evidence support profile and all server-owned metadata assembly | `monitor/trend_narrative_generation.py:536-711` |
| Subject materialization and observation candidate inference | `monitor/trend_narrative_generation.py:714-813` |
| Exact bilingual quantitative display resolution | `monitor/trend_narrative_generation.py:816-976` |
| Event-anchor extraction and URL-safe bounding | `monitor/trend_narrative_generation.py:1001-1084` |
| Provider call, JSON parse, assembly, validation, generated result | `monitor/trend_narrative_generation.py:1087-1162` |
| Packet/request construction and snapshot input validation | `monitor/trend_narrative_generation.py:1181-1356` |
| Candidate, subject, claim, evidence, event, quantitative, and text validators | `monitor/trend_narrative_generation.py:1359-1918` |
| Snapshot transaction, shortlist, evidence retrieval, and packet projection | `monitor/trend_narrative_candidates.py:132-341` |
| Quantitative display-fact construction | `monitor/trend_narrative_candidates.py:374-499` |
| Evidence selection, anonymized IDs, source flags, and support summaries | `monitor/trend_narrative_candidates.py:1788-2096` |
| Window cadence, call reservation, provider execution, failure/backoff, publication handoff | `monitor/trend_narrative_tasks.py:49-341` |
| Attempt reservation, transport state, failure state, fenced publication, last-good supersession | `monitor/trend_narrative_lifecycle.py:35-224`, `monitor/trend_narrative_lifecycle.py:338-546` |
| Second publication-schema validation and normalized subject persistence | `monitor/trend_narrative_lifecycle.py:603-959` |
| Durable attempt/publication model and database invariants | `core/models.py:1441-1757` |
| Public last-good/freshness projection | `monitor/trend_narrative_projection.py:22-189` |
| Provider-free operator status and safe first-error visibility | `monitor/management/commands/headline_status.py:16-170` |
| Event, evidence, metadata-assembly, numeric, entity, and text regression coverage | `tests/test_trend_narrative_generation.py:599-1763` |
| Read-only real-data behavior study predating the Xiaomi case | `docs/analysis/2026-08-24-165302-why-first-shadow-24h-evaluation.md` |

## Executive decision frame

The system should continue to be strict where failure would undermine trust:
fabricated metrics, invented citations, wrong candidate ownership, unsafe
identity handling, and publication races. It should be less rigid where
deterministic metadata is attempting semantic editorial judgment that it
cannot reliably perform.

The immediate decision is not “validation or no validation.” It is whether a
server-derived, lexically selected event anchor should have veto power over a
headline that a human product owner considers sufficiently supported. The
recommended answer is **no**: retain the anchor as a diagnostic and grounding
signal, but do not let a known ambiguous linkage algorithm be the sole reason
a valid, evidence-cited headline cannot publish.

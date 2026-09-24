---
title: "Headline packet size and noise audit"
date: 2026-09-24
method: read-only analysis of captured provider requests
plan: ../plans/2026-09-24-060052-feat-headline-0731-architecture-plan.md
---

# Headline packet size and noise audit

The saved 0731 qualification has substantial repetition. Removing exact
duplicate evidence text and two internal selection fields would reduce editor
message bytes by **26.1%**, critic message bytes by **23.4%**, and total message
bytes by **21.2%**, with all selected source records retained. This is an offline
size calculation, not an implementation or a new model test. Token savings,
quality, latency, and the net size after adding finance context are unmeasured.

## Evidence and measurement boundary

- Candidate: `.pytest-tmp/u5-candidate/candidate-artifact.json` in the canonical
  `feat/headline-0731-architecture` worktree; preserved raw qualification artifact.
- SHA-256: `dc8325fa74b03d744098458060ea756c1cbbb9029cabdf0ecd89b2805a712e82`.
- Corpus: frozen 1/7-day snapshots as of `2026-09-24T07:00:00Z`.
- 50 calls: two global ranks, 24 editors, 24 critics; 47 eligible brand/window
  dossiers processed by each of editor and critic. Rank includes 70 dossier
  occurrences across the two snapshots, including ineligible brands.
- Measure the UTF-8 content of `provider_request.messages[0].content`.
  Exclude system prompts, HTTP framing, adapter fields, responses, and the
  enclosing saved envelope. Provider-reported tokens below cover the actual
  request and therefore have a different boundary from message bytes.
- Exact repeated source text is counted per request, including repeated
  evidence across stages. There are 301 editor evidence occurrences, not
  necessarily 301 distinct posts.

| Stage | Calls | Original message bytes | Counterfactual message bytes | Reduction | Actual original input tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rank | 2 | 501,126 | 501,126 | 0% | 144,965 |
| Editor | 24 | 1,450,418 | 1,072,295 | 26.1% | 408,036 |
| Critic | 24 | 1,613,273 | 1,235,150 | 23.4% | 449,635 |
| Total | 50 | 3,564,817 | 2,808,571 | 21.2% | 1,002,636 |

The counterfactual deletes `original_text` only when equal to `excerpt`, deletes
`text_en`/`text_zh_cn` only when equal to that excerpt, and deletes `_ranks` and
`_role_eligible`. It changes no surviving text, facts, prompts, or evidence IDs.
The future schema must retain language/translation relationships through compact
references; those new references are not included in this simple byte accounting.

## Where the space goes

Within editor dossiers, evidence consumes 1,050,588 of 1,432,885 serialized bytes
(about 73%); facts consume 160,375, corpus signals 102,474, and family summaries
56,323. Per-field sums include field names and values but exclude enclosing
object punctuation, so they do not sum exactly to message bytes.

All 301 editor evidence records have `original_text == excerpt`; 213 also have
`text_en == excerpt`, and 47 have `text_zh_cn == excerpt`. The provider already
receives compact JSON: indentation removal is not the opportunity.

| Evidence field | Aggregate bytes, including field key |
| --- | ---: |
| `text_zh_cn` | 177,220 |
| `original_text` | 166,073 |
| `excerpt` | 164,267 |
| `taxonomy` | 162,932 |
| `text_en` | 144,391 |
| `_role_eligible` | 43,512 |
| `_ranks` | 37,803 |

Nonidentical translations may carry useful meaning; the table is not permission
to discard all translated text. Taxonomy coverage, provenance, unknown states,
and meaningful labels must survive compact representation.

## Noise that also affects quality

1. `_provider_dossier()` excludes a few private fields rather than allowing an
   explicit schema. Internal `_ranks` and `_role_eligible` therefore reach the
   model despite serving the evidence-selection algorithm.
2. Compact packets retain prior counts, prior fact values, phrase prevalence,
   and summary changes even when `comparison_status.allowed` is false. Remove
   these prohibited claims from provider input while retaining a suppression
   reason. The old noncompact comparison filter does not protect this path.
3. In editor dossiers, the phrase `https co` appears 18 times, `of the` eight,
   and `in the` eight. These are dossier occurrences across the two windows,
   not prevalence measurements. Filter URL artifacts and stopword-only phrases
   before top-eight selection, preserving real product names and non-English
   content. Do not broadly delete marketing or cross-brand repetitions: they
   may be the actual story.
4. `_compact_fact()` emits redundant numerical/display fields, and assigns
   `direction=increase` to any positive source value, including absolute counts.
   Distinguish fact types and share coverage/interval definitions explicitly.
5. Global rank messages are 201–288 KiB despite only needing relative notability.
   Facts, corpus signals, and family summaries dominate. Replace full dossiers
   with bounded summaries and source previews, preserving the complete manifest.
6. Valid critic requests already omit the duplicate `analysis_packet` and raw
   editor JSON. Local envelopes retain more information than the wire request;
   do not advertise removal of those retained fields as new provider savings.

## Reproduction

Run from the canonical worktree with the saved artifact available. This reads
the artifact and transforms dictionaries in memory; it writes nothing and
makes no provider call.

```python
import collections
import json
from pathlib import Path

artifact = json.loads(Path(
    '.pytest-tmp/u5-candidate/candidate-artifact.json'
).read_text())
totals = collections.defaultdict(collections.Counter)
for call in artifact['calls']:
    message = call['provider_request']['messages'][0]['content']
    offset = message.index('{')
    envelope = json.loads(message[offset:])
    if 'analysis_packet' in envelope:
        dossiers = envelope['analysis_packet']['dossiers']
    else:
        dossiers = [b['dossier'] for b in envelope['review_bundles']]
    for dossier in dossiers:
        for row in dossier.get('evidence', []):
            excerpt = row.get('excerpt')
            for key in ('original_text', 'text_en', 'text_zh_cn'):
                if row.get(key) == excerpt:
                    row.pop(key, None)
            row.pop('_ranks', None)
            row.pop('_role_eligible', None)
    compact = message[:offset] + json.dumps(
        envelope, ensure_ascii=False, separators=(',', ':'), sort_keys=True
    )
    totals[call['stage']].update(
        before=len(message.encode('utf-8')),
        after=len(compact.encode('utf-8')),
        original_input_tokens=call['usage']['reported_input_tokens'],
    )
for stage, values in totals.items():
    print(stage, dict(values))
```

Use this as diagnostic evidence for U7–U9, then measure the fully revised
requests including historical context. Preserve source support first; smaller
messages do not prove better headlines or proportionally faster completion.

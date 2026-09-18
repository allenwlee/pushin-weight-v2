---
title: Qwen classifier v4 compact-bits smoke-8 review
date: 2026-09-17
type: experiment-review
---

# Qwen classifier v4 compact-bits smoke-8 review

V4 tested compact fixed-order bit vectors after dense named flags proved too
large and fragile. It removed redundant `none` bits: the adapter derives
`none` only from a complete all-zero vector, and derives absent nationalism
and country `none` values only from `nationalism: null`. This is a response
encoding, not a semantic repair.

All four Alibaba-only calls completed with `stop`, zero reasoning tokens, no
fallback, and no retry. Reported cost was $0.00063516 against the $0.00391528
reservation. The hard 3-profile cap initially stopped this configuration
before any send; the runner now records the approved Exception 29
Qwen-only six-configuration cap in the replacement frozen contract. This
fixed a local control-plane mismatch, not a model result.

The v4 smoke result is 8/8 delivery errors. Raw responses identify three
independent failures:

1. Both content calls return `promoted_subjects[P]=null` for no-promotion
   posts. The frozen contract requires `[]`; this alone rejects both content
   batches.
2. The first content call labels the Qwen Meetup row `classified` while its
   complete post-type vector is all zero. It has no valid taxonomy projection.
3. The second brand call marks the three China-AI decisions as
   `unavailable` while also returning non-null nationalism objects, which is
   contradictory by construction and rejected by the adapter.

The first brand batch does parse, demonstrating that the compact
nationalism-object representation prevents the former “directional stance
without nationalism” failure. Its semantic quality remains inadequate: it
turns a reported DeepSeek distillation allegation into `ideas_requests` and
an adopted nationalism state. Bit vectors also preserve sparse-label errors:
the first content response misses visible local/self-hosted and openness
topics, and the second treats the DeepSeek CVE as results analysis while
using unrelated evaluation topics for Chinese-AI opinions.

V4 cannot qualify from smoke. A separate, explicitly non-qualifying
24-source diagnostic run is still useful to characterize whether its null
arrays, zero classified type vectors, and unavailable-plus-nationalism
contradictions are systematic across broader source evidence. It retains the
same frozen V4 profile and two-role architecture; it does not change
production behavior or authorize another model.

## Versioned mechanical replay

The initial result above remains the strict raw-contract result. A later
`v4-empty-collection-normalizer` replay changes only two representation
synonyms: `promoted_subjects=null` becomes `[]` when the complete promotion
vector is all zero, and a complete nationalism object with both country values
`none` plus `other_nation=false` becomes absent nationalism. It does not
change a selected label, add a topic, or discard a directional stance.

Under that versioned replay, three sources from the first content batch and
all three sources from the second content batch have usable content rows;
the Qwen Meetup remains invalid because it is `classified` with no post type.
The first brand batch already parsed. The second brand batch yields usable
DeepSeek-CVE and MiniMax rows, while the three-brand China-AI row remains
invalid because `unavailable` coexists with directional nationalism. Thus the
normalizer exposes six structurally usable source pairs and two genuine
structural failures; it does not qualify V4 or erase its semantic errors.

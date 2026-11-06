---
name: harvest-query-diff
description: Expand every current and proposed harvester query into all individual AND combinations and show a complete side-by-side coverage comparison, including added, broadened and narrowed alternatives.
---

# Harvest query diff

Invoke as **`$change-harvester harvest-query-diff`**, or directly as
**`$harvest-query-diff`** when the project discovery link is available.
This is the harvester's saved **every-alternative comparison** format.

Use it when reviewing a query refactor, its coverage, or missing co-occurrences.
It supports local query edits already requested by the owner. It grants no
provider spend, database changes, publication, or deployment.

## Establish the two inputs

- Obtain **current** exact requests from persisted search records or a verified
  release receipt. Record revision, capture time in JST, source path and SHA-256.
  A draft is not a current-production baseline. If only code is available,
  render the real caller and label it as code-derived, not observed production.
- Render **proposed** requests through the shared planner and actual caller's
  suffix/bound injection. Include every enabled list, brand, supplemental and
  discovery call, even unchanged calls. Record policy/config/code hashes.
- Use identical, explicit sample time bounds for structural comparison. Retain
  original observed requests separately when their actual windows differ.
  Record author exclusions, engagement filters and post-fetch brand exclusions;
  do not confuse a post-fetch filter with a provider-query condition.
- Reuse existing evidence for syntax. A local expansion cannot establish X's
  indexing, punctuation semantics, recall or semantic relevance. Distinguish
  owner-selected assumptions, saved provider observations and unknowns. Do not
  generalize hyphen behavior to periods or silently probe an API to settle it.

## Expand all alternatives, without sampling

Distribute every OR through every AND, at every nesting level. For example:

| Current individual combination | Proposed individual combination |
| --- | --- |
| CUDA AND llm | CUDA AND llm |
| CUDA AND model | CUDA AND model |
| CUTLASS AND llm | CUTLASS AND llm |
| CUTLASS AND model | CUTLASS AND model |
| — No corresponding current branch | CUDA AND inference |
| — No corresponding current branch | CUTLASS AND inference |

These six rows represent `(CUDA OR CUTLASS) (llm OR model)` changing to
`(CUDA OR CUTLASS) (llm OR model OR inference)`. Do not replace the rows with
that compressed expression in the comparison.

- Emit one numbered source occurrence for **every** branch, including redundant
  branches. Preserve case, phrases, negations, grouping provenance and filters.
- A quoted phrase stays one phrase. An unquoted multiword expression is an AND.
  Under the recorded hyphen-as-space assumption, `MiMo-V2.5` is `MiMo AND V2.5`;
  it never becomes bare `MiMo`. Factor versions as `MiMo (V2.5 OR 7B OR ...)`
  only when that preserves the declared conjunctions. Never broaden by removing
  a version/context requirement merely to fit the byte cap.
- Keep account mentions as independent OR alternatives when the policy intends
  that. Prove this with a mention-only control; do not accidentally gate them
  with the adjacent model context.
- For each current branch print **all** corresponding proposed combinations,
  their call IDs and stable branch IDs. Mark equivalent, broader, narrower or
  not guaranteed. Reusing a token somewhere else is not equivalent coverage.
- Print every remaining proposed branch with an empty current cell. No
  summaries, ellipses, top-N truncation, pagination or hidden default rows.
  Filtering is optional; the initial page must show everything.
- Retain exact full request strings and a complete JSON/CSV export. Reconcile
  both occurrence counts against the parser output; duplicate display references
  must not inflate the number of distinct proposed occurrences.

## Generate the saved format

Use [scripts/query_diff.py](scripts/query_diff.py). It has no network, database,
credential or application-client imports. Input JSON on each side:

```json
{
  "source": "Revision, capture time, path and source hash",
  "queries": [
    {"call_id": "C2", "lane": "tracked", "query": "(CUDA OR CUTLASS) (llm OR model)", "blocks": ["nvidia/software"]}
  ]
}
```

Use `lane: "list"` for list A, `"tracked"` for brand calls, and separate stable
lane IDs for discovery. This prevents an unrelated discovery search from being
presented as proof that a removed tracked-brand branch was replicated.

```sh
python3 .claude/skills/change-harvester/subskills/harvest-query-diff/scripts/query_diff.py current.json proposed.json docs/analysis/harvester/YYYY-MM-DD-HHMMSS-harvest-query-diff.html --note 'State punctuation assumptions and material intentional differences here.'
```

The command also writes complete `.json` and `.csv` companions. The bounded
expansion fails rather than silently truncating an unexpectedly huge expression.
If syntax is unsupported, fix/extend the parser and its tests; do not discard
that call. Validate the example's four-way product, nested groups, quoted
phrases, negation, full current/proposed inventories and display completeness.

## Review and delivery

Audit every standalone alternative, not just known noisy brands. Restore old
context where appropriate and explicitly account for each widening/narrowing.
Distinctive product names and ordinary words need separate evidence. Do not
invent a blanket rule that all names must be contextual.

Apply the parent skill's mandatory **512 UTF-8-byte complete-request gate**.
List each call's bytes/headroom, total old/new call count and logical family
ownership. Split coherent blocks within the owner's authorized budget; never
delete guards to fit. Extra calls change cost and require explicit accounting.

This report is Boolean logic evidence. Keep saved-data relevance checks and
real caller regression tests separate; a complete table does not mean the
refactor is ready to deploy. Deliver the self-contained HTML through
`show-locally` and verify its default row count, filtering and exact-query
appendix. Include short material-change notes; keep all combinations in the
artifact even when there are hundreds or thousands of rows.

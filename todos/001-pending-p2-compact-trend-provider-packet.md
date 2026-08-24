---
status: pending
priority: p2
issue_id: "001"
tags: [trend-narratives, llm, packet-size, performance]
dependencies: []
---

# Compact the trend provider packet

## Problem Statement

The current trend-narrative provider packet is correct but verbose. It repeats
zero-valued metadata arrays, internal allocation details, and large evidence
sets. This may increase LLM attention and serialization failures.

## Findings

- Real packets reached approximately 123 KiB and 40,000 input tokens.
- The latest real run sent roughly 100 evidence excerpts across six candidates.
- The provider understood several stories but omitted or malformed structured
  metadata.
- The full packet remains useful as an internal debugging artifact.

## Proposed Solutions

1. Build a compact provider-facing summary while retaining the full packet for
   internal audit and fingerprinting.
2. Keep the packet shape but reduce evidence and remove redundant zero/null
   fields.
3. Use an intermediate deterministic summarizer before provider generation.

## Recommended Action

Deferred. First implement server-side metadata assembly and measure its effect
on valid output. Then run an A/B comparison of the current and compact packets
on the same real windows.

## Acceptance Criteria

- [ ] Full internal packet remains available for audit.
- [ ] Provider packet is materially smaller without losing cited evidence.
- [ ] Quantitative facts and evidence IDs remain lossless.
- [ ] A/B results report packet bytes, input tokens, schema validity, leader
      correctness, and evidence support.

## Work Log

### 2026-08-18 - Deferred after real-data study

**By:** Codex

**Actions:**

- Compared three real-data packets and observed metadata failures with packets
  ranging from approximately 94 KiB to 123 KiB.
- Deferred packet compaction while pursuing server-side metadata assembly.

**Learnings:**

- Packet length may contribute to failures, but the current evidence is not
  sufficient to isolate it from schema and leader-selection problems.

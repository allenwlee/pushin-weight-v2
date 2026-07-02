# last30days produces non-canonical output (logs + raw evidence only) in Grok Build

### written by Grok 4.3

**Date:** 2026-06-30

---

**Copy-paste ready for GitHub**

**Recommended Title:**

`/last30days` in Grok Build (non-Claude harness) produces only logs and raw evidence clusters instead of required canonical output

**Body (paste from here):**

## Summary

Invoking `/last30days <topic>` in Grok Build fails to produce the skill's required canonical output (badge + "What I learned:" + KEY PATTERNS + engine footer) and instead yields only logs and raw evidence clusters.

The direct engine fallback used in this environment was truncated and never reached the mandated synthesis shape.

## Steps to Reproduce

1. In a Grok Build session, invoke `/last30days <topic>` (example: "custom implementation of tracking token or plan usage for grok build").
2. The agent attempted to satisfy the request but fell back to a direct engine invocation:
   ```
   python3 .../skills/last30days/scripts/last30days.py "..." --emit=compact
   ```
   (captured via shell redirection that caused backgrounding due to timeout).
3. Review the captured output.

## Expected Behavior

A complete, LAW-compliant report per `skills/last30days/SKILL.md`:
- First line is the `🌐 last30days v{VERSION} · synced {DATE}` badge
- `What I learned:`
- Bold lead-in paragraphs
- `KEY PATTERNS from the research:`
- Verbatim `✅ All agents reported back!` footer
- No raw `## Ranked Evidence Clusters` or trailing Sources blocks

## Error / Traceback

No unhandled exception or Python traceback occurred.

When the engine was allowed to run to completion with full output capture (no `| head`, no truncation):

- It emitted the badge.
- It produced the raw `## Ranked Evidence Clusters` block (wrapped in `<!-- EVIDENCE FOR SYNTHESIS -->` comments).
- It emitted the complete `<!-- PASS-THROUGH FOOTER -->` with the emoji tree.
- At the very end it printed:
  ```
  # END OF last30days CANONICAL OUTPUT

  Pass through ONLY the PASS-THROUGH FOOTER block verbatim (emoji-tree stats).
  The EVIDENCE FOR SYNTHESIS block above it is raw evidence for your synthesis,
  not output. Transform it into `What I learned:` prose paragraphs per LAW 2.

  If your response contains the literal string `### 1.` followed by a score
  tuple like `(score N, M items, sources: ...)`, you dumped evidence instead
  of synthesizing - STOP and regenerate.
  ```
- The engine considered the run successful and even reported "Research quality: 5/5 core sources."

The observed problem was therefore not a crash, but:

- In the original invocation, shell-level truncation (`| head -100`) + backgrounding cut off the output before the badge, evidence block, footer, and synthesis instructions could be captured.
- The Grok Build host/agent did not perform the synthesis step required by the skill contract (reading the evidence comments and emitting the canonical "What I learned:" + KEY PATTERNS shape).
- Only early processing logs and partial evidence clusters were visible in the session.

## OS

macOS

---

**References**
- `skills/last30days/SKILL.md` (OUTPUT CONTRACT, LAWs 1-8, pre-flight, --plan requirements)
- Local Grok-native wrapper created at `~/.grok/skills/last30days/` as mitigation (uses native tools and enforces the same output contract)
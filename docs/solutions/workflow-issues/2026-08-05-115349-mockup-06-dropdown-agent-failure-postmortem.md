# Why mockup-06 dropdowns took 8 versions — and one rewrite fixed them

### written by Grok 4.3

**Date:** 2026-08-05 (JST)  
**Subject:** Filter-pill dropdown on `06-tier1-composed` (v4→v11 thrash vs v12 one-shot)  
**Related handoff:** `docs/handoffs/2026-08-05-001-mockup-06-dropdown-debug.md`  
**Working artifact:** `docs/ideation/mockups/06-tier1-composed.v12.html`  
  (local: `~/Downloads/pushin-weight-mockups/06-tier1-composed.v12.html`)

---

## Verdict in one sentence

The prior session optimized for **Playwright assertions that could pass while the UI still looked broken**, and treated each failure as a **handler-target micro-bug**. The real failure was a **stack of three interacting design mistakes** (event model, CSS open-state, overflow clipping) that no amount of “widen the click target / add counters” would clear. v12 replaced the stack instead of patching it.

---

## Timeline of the thrash

| Version | What changed | What it “proved” | What it left broken |
|---|---|---|---|
| v4 | CSS `:focus-within` + JS click toggle | Something almost works | Dual open-sources (CSS + JS) |
| v5 | `e.target.tagName === "INPUT"` checks | — | Handler leakage (two generations live) |
| v6 | Trigger = `.status-dot,.title,.carat` only | Narrower hit surface | Misses when target ≠ those nodes |
| v7 | `.is-open .filter-dropdown { display:block }` | CSS can show the panel | Still absolute + clipped |
| v8 | `window.__pwDebug` counters | **Smoking gun:** `clicks:4, opens:0` | Counters without a new model |
| v9 | `lastTarget` logging | More diagnostics | Still same architecture |
| v10 | Whole-pill listener | Removes trigger-list mismatch | Bubble race + overflow still there |
| v11 | Whole-pill + counters restored | Playwright green again | User still sees dead UI |
| **v12** | Capture-phase single owner, fixed pos, no focus-within open, scroller split, defaultChecked dots | Real open + visible + toggle | — |

The session correctly instrumented (v8) and correctly observed that **JS was alive but `is-open` never stuck**. It then spent the remaining versions on the *wrong layer*: “which element received the click?” instead of “what *immediately undoes* open, and would we even *see* open if it stuck?”

---

## The three root causes (stacked)

### 1. Dual authority over “open”

v4–v11 used **two independent mechanisms** to show the panel:

```css
.filter-pill:focus-within .filter-dropdown,
.filter-pill.is-open .filter-dropdown { display: block; }
```

Plus JS that toggled `is-open` on bubble-phase `click`, plus a document-level bubble `click` that called `closeAll()` when the target was outside `.filter-bar`.

That design creates a race surface:

- Click focuses the pill (`tabindex="0"`) → `:focus-within` wants open.
- Pill handler runs: `closeAll()` then maybe `add("is-open")`.
- Document handler may or may not see the event depending on `stopPropagation`.
- Focus can move / blur on the next tick (touch, extension, accessibility tools, label/checkbox focus) → `:focus-within` drops while `is-open` may never have been the source of truth.

**Playwright’s synthetic click is polite.** It focuses, fires a clean bubble sequence, and rarely hits the blur/order pathologies real Chrome + trackpad/touch produce. So assertions like “after click, has class `is-open`” pass in headless while the user’s session reports `opens:0`.

**Lesson:** One source of truth for open state. In v12, open is **only** `.is-open`, set by **one** capture-phase `pointerdown` owner on `document`. No `:focus-within` open rule.

### 2. Overflow clipping that tests never measured

```css
.filter-bar {
  overflow-x: auto; /* intentional horizontal scroll */
}
.filter-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  ...
}
```

CSS quirk (still true in current browsers): if one overflow axis is not `visible`, the other computes to something other than `visible` as well. Result: the scroll container **clips** absolutely positioned descendants that stick out below the bar.

Prior verification checked:

- class presence
- `getComputedStyle(dd).display === "block"`

It did **not** check:

- bounding rect non-zero and on-screen
- intersection with viewport
- pixel non-transparency under the pill

So a build could be “green” with a dropdown that is `display:block` **and fully clipped to 0 visible pixels**. That matches a user story of “I click and nothing happens” even when `is-open` *does* land in some runs.

**v12 fix:** horizontal scroll moved to an **inner** `.filter-bar-scroller`; dropdown uses **`position: fixed`** pinned with `getBoundingClientRect` on open/resize/scroll. Visibility becomes a geometry problem the agent can assert, not an overflow accident.

### 3. Wrong diagnostic loop (local max, not system rewrite)

Given `clicks:4, opens:0`, the productive questions are:

1. Does open land and get removed within the same event turn?
2. Is open only CSS-driven and then lost on blur?
3. Is the panel open-but-invisible (clip / z-index / offscreen)?

The session answered a different question for several versions:

- “Is the click target the carat vs the title vs the pill?”

That is a reasonable *first* hypothesis, and v10 correctly eliminated it. But after v10/v11 still failed for the user, the next move should have been **replace the event + CSS architecture**, not restore counters on the same architecture.

Instrumentation without a **falsification tree** becomes ritual:

```
add counter → ask user → tweak selector → add counter
```

vs

```
observe opens:0
→ prove whether class ever exists mid-handler (breakpoint / log before and after closeAll)
→ prove whether document close runs after pill open
→ prove computed display vs getBoundingClientRect
→ if dual open paths exist, delete one before writing more handlers
```

---

## Why one shot worked (v12)

Not luck — a different problem formulation.

| Prior framing | v12 framing |
|---|---|
| “Click doesn’t hit the trigger” | “Open must be owned by one capture-phase controller” |
| “Need better `e.target` checks” | “Stop caring about target shape; walk `closest` once” |
| “Playwright passes so logic is fine” | “Playwright can pass while geometry is zero” |
| “Keep focus-within as progressive enhancement” | “focus-within is a second, hostile authority — delete it” |
| “absolute under pill is fine” | “bar overflow will clip — fixed + pin, or restructure scroll” |
| “unchecked ⇒ dirty dot” | “dirty = differs from `defaultChecked`” (未授权) |

Concrete v12 contract:

1. **Capture-phase `pointerdown` on `document`** — runs before bubble toys; no reliance on `stopPropagation` from N pill listeners.
2. **Inside open dropdown → no-op** (let checkbox/label work).
3. **On pill header → toggle that pill only** (close others).
4. **Else → close all.**
5. **Geometry:** `position:fixed` + `placeDropdown(pill)` after paint (`rAF`×2).
6. **Assert what users see:** open count, `display`, `position:fixed`, non-zero `top/left`, checkbox keeps open, outside closes, 未授权 stays `is-default`.

That is a closed loop: architecture change *and* verification that would have failed on v7–v11 for the right reasons.

---

## Process failures (agent / session level)

These are portable beyond this mockup.

### A. Green tests that don’t encode the user claim

User claim: “dropdown appears under the pill when I tap.”

Encoded tests: “class exists” / “display ≠ none.”

**Gap:** visibility and durability across a full real input sequence.

**Rule:** For UI open/close, pin at least:

- class or `aria-expanded`
- computed `display` / `visibility`
- **bounding box area > 0 and on-screen**
- still open after one *interior* interaction (checkbox)
- closed after exterior click

### B. Version proliferation without hypothesis retirement

Eight files (v4–v11) with overlapping handlers (v5 even “leaked both”). That is a sign of **additive debugging** — each version adds a theory without deleting the previous theory’s mechanism.

**Rule:** If the last two versions share the same event phase and the same CSS open rule, the next version must change one of those axes or stop.

### C. Trusting headless over the user’s counter

The user’s `{"clicks":4,"opens":0}` was higher signal than Playwright green. The session recorded it, then continued optimizing for the environment that was already green.

**Rule:** When user telemetry contradicts automation, treat automation as under-specified, not the user as wrong. Widen the oracle (geometry, timing, capture logs mid-handler), don’t only re-run the green suite.

### D. Missing mid-handler proof

Never proven in the handoff:

- Does `classList.add("is-open")` execute?
- Is `closeAll` invoked *after* that add in the same turn?
- Does a capture listener elsewhere clear it?

v8 counted *outcomes* every 250ms, which averages away single-turn races. A single `console.log` before/after `closeAll` + `add` would have been cheaper than three more versions.

### E. Mockup treated like production event spaghetti

For a static HTML mockup, the correct complexity budget is ~40 lines of one controller. The thrash rebuilt mini-framework concerns (trigger lists, input tag checks, dual CSS/JS open) that production apps only need when many features share the DOM. Mockups should prefer **boring, centralized, capture-phase** behavior.

---

## What the prior session did well (credit)

- Built a reproducible local server (`:8765`) and version chain — recovery was possible.
- Added `__pwDebug` — the `clicks>0, opens:0` observation was the real key.
- Eventually widened the click target to the whole pill (v10) — correct elimination of a *possible* cause.
- Did not pollute production Django templates; kept work in ideation mockups.
- Wrote a handoff with open questions and file map — the next agent could start mid-problem.

The failure was not “couldn’t code a toggle.” The failure was **stopping at a local maximum once headless was green**, with diagnostics that measured the wrong success metric.

---

## Portable checklist (next interactive mockup)

Before calling a dropdown “done”:

- [ ] Exactly one open-state authority (class *or* CSS, not both).
- [ ] Exactly one input controller (prefer capture on `document` or the bar).
- [ ] No `overflow` ancestor that can clip the panel (or use `position: fixed` / portal).
- [ ] Assert **on-screen box**, not only `display`.
- [ ] Interior click (checkbox) does not close; exterior does.
- [ ] Default dirty-state logic uses `defaultChecked` / explicit defaults.
- [ ] If user counter disagrees with Playwright, believe the counter and upgrade the test — do not ship another micro-selector tweak.

---

## Appendix: minimal mental model

```
pointerdown (capture, document)
    │
    ├─ target in open .filter-dropdown  → leave open (checkbox works)
    ├─ target in .filter-pill           → toggle that pill; fixed-position panel
    └─ else                             → close all
```

CSS:

```
.filter-pill.is-open > .filter-dropdown { display: block; }
/* no :focus-within open */
```

Layout:

```
.filter-bar                  /* no overflow clip */
  .filter-bar-scroller       /* overflow-x: auto */
    .filter-pill
      .filter-dropdown       /* position: fixed; top/left from JS */
```

That model is what v12 implemented. Everything from v4–v11 was a partial subset fighting the rest of the subset.

---

## Files touched by the fix (for audit)

| Path | Role |
|---|---|
| `~/Downloads/pushin-weight-mockups/06-tier1-composed.v12.html` | Working local mockup |
| `docs/ideation/mockups/06-tier1-composed.v12.html` | Remote copy |
| `docs/ideation/mockups/06-tier1-composed.html` | Canonical on fuchitalee (= v12) |
| `docs/handoffs/2026-08-05-001-mockup-06-dropdown-debug.md` | Status → resolved |
| `~/Downloads/pushin-weight-mockups/index.html` | Index link → v12 |

No production `monitor/templates` change. No git commit required for this postmortem unless you want it on `main`.

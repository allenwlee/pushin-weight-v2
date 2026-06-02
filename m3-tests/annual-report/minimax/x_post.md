attribution: "{{AGENT_ATTRIBUTION}}"

# X-post draft: M3.0 vs Gemini 3.1 Pro — ASCII org chart from a 10-K

## The artifact

**Prompt (sent to both, identical):**
> Read pages 21-24 of this 10-K filing. Produce an ASCII org chart of the executive officers and directors listed. Use box-drawing characters. Output ONLY the chart, no commentary.

**Input:** 4 page-PNGs from /Users/allenwlee/Downloads/12116752-0.pdf (a Hong Kong listed company 10-K)

---

## M3.0 output (18.4s, 2010 chars)

```
┌────────────────────────────────┐
│ Directors and Chief Executives │
└───────┬────────────────────────┘
        │
        ├─ ┌─────────────────┐
        │  │ Dr. Yan Junjie  │
        │  └─────────────────┘
        │
        ├─ ┌─────────────────┐
        │  │  Ms. Yun Yeyi   │
        │  └─────────────────┘
        │
        ├─ ┌─────────────────┐
        │  │ Mr. Zhao Pengyu │
        │  └─────────────────┘
        │
        └─ ┌─────────────────┐
           │ Mr. Zhou Yucong │
           └─────────────────┘
```

Names only. No roles claimed. (Because the page doesn't claim any.)

## Gemini 3.1 Pro output (29.2s, 516 chars + 2756 thought-tokens)

```
┌────────────────────────────┐
│     Dr. Yan Junjie         │
│      (Dr. Yan)             │
│  Founder / Director / CEO  │   ← NOT on the page
└────────────┬───────────────┘
             │
             ▼
┌──────────────────────┐  ┌──────────────────────┐
│     Ms. Yun Yeyi     │  │   Mr. Zhao Pengyu    │
│    Director /        │  │   Executive Officer  │   ← NOT on the page
│    Co-founder        │  │                      │   ← NOT on the page
└──────────┬───────────┘  └──────────┬───────────┘
           └────────────┬────────────┘
                        ▼
           ┌──────────────────────────┐
           │   Mr. Zhou Yucong        │
           │     Executive Officer    │   ← NOT on the page
           └──────────────────────────┘
```

Roles invented. Five of them. The page contains none.

---

## What the page actually says

The 10-K page lists 4 names with their shareholdings. No titles, no "Founder", no "CEO". The biographical details (which would contain actual roles) are in a separate section. The 4 names are real. The roles Gemini added are not.

---

## Suggested X-post copy

**Option 1 (the visual punch):**

> Prompt: ASCII org chart from 10-K pages 21-24.
>
> M3.0 (top) vs Gemini 3.1 Pro (bottom).
>
> Look at the hierarchy in Gemini's chart. Then read the filing.
>
> Zero roles stated. Five roles invented.

**Option 2 (the punchier one-liner):**

> Same prompt. Same 10-K. Same multimodal task.
>
> M3.0: 4 names.
> Gemini 3.1 Pro: 4 names + 5 invented titles.
>
> The page doesn't say "Founder". Gemini did.

**Option 3 (the "no oversell" frame):**

> Multimodal models shouldn't oversell.
>
> Asked M3.0 and Gemini 3.1 Pro to ASCII-chart a 10-K. M3 listed what's there. Gemini added titles the page never claimed.
>
> Control test confirmed both read the image (Gemini got the share count right: 79,102,534). The fabrication was a choice, not a failure.

---

## What makes this a good post

1. **The artifact is the proof** — the side-by-side is the tweet. No judgment needed.
2. **The control test kills the "Gemini didn't read it" counter** — both read the page; Gemini just added on top.
3. **Honest with the part M3 didn't win** — Gemini got the share count right when M3 undercounted. Not oversold.
4. **The "multimodal overselling" angle is genuine** — the failure mode isn't visual fidelity (the Goryeo banquet) but epistemic confidence. Different and arguably more important.

## What to watch out for

- The filing is a real, public 10-K. Linking it makes the test reproducible.
- The names are real (Dr. Yan Junjie is a real director of MiniMax Group per the same filing). The framing is fair.
- Don't claim M3 is "smarter" — claim it "didn't invent." That's the load-bearing word.

## Files

- M3 raw output: fuchitalee:/tmp/m3-test-staging/pdf_org_chart/out/m3_output.txt
- Gemini raw output: fuchitalee:/tmp/m3-test-staging/pdf_org_chart/out/gemini_output.txt
- Page 22 (proof no roles stated): fuchitalee:/tmp/m3-test-staging/pdf_org_chart/page-22.png
- Control test log: fuchitalee:/tmp/m3-test-staging/pdf_org_chart/run2.log
- Control test code: fuchitalee:/tmp/m3-test-staging/pdf_org_chart/control_gemini_read.py

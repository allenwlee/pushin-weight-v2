attribution: "{{AGENT_ATTRIBUTION}}"

# X-post draft: M3.0 vs Gemini 3.1 Pro — multi-tier org chart from 10-K pages 21-24

## The artifact (this is the second test in the series)

**Test 1** (4-name simple chart): M3 listed 4 names. Gemini invented 5 roles (Founder/CEO/Co-founder). The "no oversell" win.

**Test 2** (this one): multi-tier org chart with 7 ownership chains, beneficial owners at the top, holding companies / trusts in the middle, the issuer at the bottom.

**Prompt (sent to both, identical):**
> Read pages 21-24 of this 10-K filing. Produce a multi-tier ASCII org chart showing the ownership structure. At the TOP: the beneficial owners and individuals. In the MIDDLE: intermediary holding companies, controlled corporations, and trusts. At the BOTTOM: the final reporting company. For each ownership chain, show the percentage of Class A shares and the number of shares. Use box-drawing characters. Output ONLY the chart.

**Input:** same 4 page-PNGs from /Users/allenwlee/Downloads/12116752-0.pdf

---

## M3.0 output (395.1s = 6.6 min, 89,010 chars incl. 1,177-line thinking block)

A full 3-tier chart with 7 chains. Tier 1 lists every individual and entity with direct/indirect Class A. Tier 2 shows the intermediary structure (Local Linearity, MiniMax Matrix, Alpha EXP Trust → Scaling EXP, miHoYo's Shanghai Fanxing, Futu Trustee, BXA Holdings family). Tier 3 is the issuer.

**Key features:**
- Includes trust + trustee detail (Trident Trust Company, Scaling EXP Limited, 99%/1% ownership of Alpha EXP)
- All percentages correct
- Includes BOTH Class A and Class B holdings for the founder chain
- Total: 232,532,774 Class A + 81,102,534 Class B = 313,635,308

**One inferred label:** `Dr. Yan Junjie (Founder)` — **page 23 explicitly says "Dr. Yan Junjie, is the founder of the Company"** ✓
**One inferred label:** `Ms. Yun Yeyi (Co-founder)` — **page 23 does NOT say this. Ms. Yun is referred to as "Ms. Yun Yeyi" only.** Inferred from the parallel structure to Dr. Yan.

## Gemini 3.1 Pro output (133.8s = 2.2 min, 9,713 chars)

A cleaner, more diagram-like 4-column layout. 7 chains. Each chain leads to the issuer box at the bottom-right. All percentages correct.

**Key features:**
- Box layout, looks like an actual chart (not a doc)
- All 7 chains with intermediaries
- Class A only (matches the prompt)
- No role labels on individuals

**No inferred labels.** Names only. The chart does not say "Founder" or "Co-founder" anywhere.

---

## What the page actually says (verified)

**Page 22 (Interests of Directors and Chief Executives):** Lists names + shareholdings + nature of interest (Beneficial / Interest in controlled corporation / Trustee / Interest of spouse). No roles.

**Page 23 (Report of Directors):** Contains the only roles stated in the file:
- "Dr. Yan Junjie, is the founder of the Company" ✓ — explicitly says "founder"
- "Mr. Yan Junjie, is a beneficial owner of 501,182 Class A Ordinary Shares, which are the underlying of the Pre-IPO Option Plan granted by the Company"
- "Ms. Yun Yeyi" — referred to by name only, no "Co-founder" title
- Mr. Zhou Yucong — beneficial owner of options, no role stated

**Page 24 (Substantial Shareholders' Interests):** Names + shareholdings. No roles. No Founder/Co-founder.

So the page says "Founder" once (for Dr. Yan) and never says "Co-founder" for Ms. Yun.

---

## Side-by-side finding (the X-post core)

| | Test 1 (simple) | Test 2 (multi-tier) |
|---|---|---|
| **M3.0 fabrications** | 0 (listed names only) | 1 (`Ms. Yun (Co-founder)` — inferred) |
| **Gemini fabrications** | 5 (Founder/CEO/Co-founder titles) | 0 (names only) |
| **M3.0 time** | 18.4s | 395.1s (6.6 min) |
| **Gemini time** | 29.2s | 133.8s (2.2 min) |
| **M3.0 detail** | 4 names, 1 tier | 7 chains, 3 tiers, trust structure |
| **Gemini detail** | 4 names, hierarchy, no percentages | 7 chains, ~2 tiers, clean visual |

**The "no oversell" frame still holds in both directions, but the leader flipped on this test.** In the rich multi-tier task, Gemini produced a clean accurate chart and didn't invent. M3 was more thorough but inferred 1 role the page doesn't support.

---

## What makes this a stronger post than Test 1 alone

1. **The pattern is more interesting than the verdict.** Two models, two tasks, two different failure modes. M3 = conservative but may infer in rich contexts. Gemini = confident but may fabricate in sparse contexts. The same model behaves differently depending on the data density.
2. **The "thinking block" is the visual proof.** M3's 89K char output starts with 1,177 lines of reasoning (you can see the double-counting checks: 77.18 + 14.19 + 0.00 + 14.19 = 105.56 → M3 catches this, deduces Local Linearity and MiniMax Awakening are the same shares counted twice). Gemini's 9.7K is just the chart.
3. **The speed gap is a real cost story.** M3 = 6.6 min for one chart. Gemini = 2.2 min. For a junior analyst doing 10 of these, that's 1 hour vs 22 min.
4. **The visual fidelity is now the differentiator, not accuracy.** For an animated chart-drawing video (the goal), Gemini's cleaner box layout will look better. M3's text-heavy boxes will be hard to read at any frame.

---

## Suggested X-post copy

**Option A (the pattern):**
> Two tests, two failure modes.
>
> Test 1: ASCII chart of 4 directors. M3 listed names. Gemini invented 5 titles (Founder/CEO/Co-founder).
>
> Test 2: Multi-tier chart of 7 ownership chains. M3 inferred 1 role. Gemini invented 0.
>
> Same prompt shape. Different data density. Different oversell behavior.

**Option B (the thinking):**
> Asked M3 and Gemini 3.1 Pro to ASCII-chart a 10-K's 7-chain ownership structure.
>
> M3: 6.6 min, 89K chars, 1,177 lines of thinking, full trust + holding chain detail, inferred 1 role.
> Gemini: 2.2 min, 9.7K chars, just the chart, no role fabrication.
>
> The thinking is the differentiator.

**Option C (the cost story):**
> Multimodal chart-from-PDF, 10-K pages 21-24.
>
> M3.0: $X / 6.6 min / comprehensive but 1 inferred role
> Gemini 3.1 Pro: $Y / 2.2 min / clean and accurate
>
> For high-stakes work (legal, audit, due diligence) M3's thoroughness wins. For 30-second visuals, Gemini's accuracy + speed wins.

---

## What to watch out for

- "Founder" is **on** page 23 — M3's `(Founder)` label is supported, not a fabrication. Defensible.
- "Co-founder" is **not** on the page — M3's `(Co-founder)` for Ms. Yun Yeyi is an inference from the parallel structure. **Worth flagging in the post**, not hiding.
- Gemini's chart for chain 6 (Colm O'Connell / BXA / XAM / MNM) puts the MNM Holdings chain on the right with the JNR Holdings on the left, which is the right shape but easy to misread — could be a follow-up test.
- The page 22 entry for Dr. Yan's Class B (62,593,180 + 11,509,339 + 15 + 11,509,354) sums to 105.56% — this is double-counting from the same beneficial owner being attributed twice. M3 caught this in the thinking. Gemini didn't visibly (but also didn't claim >100%, just used 62,593,180 + 7,000,000 = 14.42% of the B total).

---

## Files

- M3 raw output: `/tmp/m3-test-staging/pdf_org_chart/m3_multi.txt` (118K)
- Gemini raw output: `/tmp/m3-test-staging/pdf_org_chart/gemini_multi.txt` (14K)
- Runner: `/tmp/m3-test-staging/pdf_org_chart/run_multitier.py`
- Run log: `/tmp/m3-test-staging/pdf_org_chart/run_multi.log`
- Page 22 (Directors' interests, no roles): `/tmp/m3-test-staging/pdf_org_chart/page-22.png`
- Page 23 (Report of Directors — contains "Founder" for Dr. Yan, nothing for Ms. Yun): `/tmp/m3-test-staging/pdf_org_chart/page-23.png`
- Page 24 (Substantial shareholders, no roles): `/tmp/m3-test-staging/pdf_org_chart/page-24.png`
- Test 1 X-post: `/tmp/m3-test-staging/pdf_org_chart/x_post.md`

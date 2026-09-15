# Conditional third classifier call: six recovered labels, one false addition

The third call recovered **six of seven missing rare-type labels** in the
45-case owner reference. It recovered every missing event and three of four
missing opportunities. It also added one incorrect opportunity, so it failed
the frozen zero-false-addition diagnostic criterion. The full classifier still
fails its existing quality gates. This is a useful recall improvement, with
remaining opportunity-boundary errors; it is not a production-ready result.

The run reused the saved R98 two-role DeepSeek answers. A broad deterministic
screen selected 23/45 posts and sent three conditional requests of 12, 8, and
3 rows. All 23 returned all four explicit decisions in valid responses. The
third call purchased no base classifications and triggered no retries. It ran
September 15, 2026, 10:43:24–10:43:35 JST.

| Type | Reference positives | Captured before | Captured after | Incorrect after |
|---|---:|---:|---:|---:|
| Events | 3 | 0 | 3 | 0 |
| Opportunities | 5 | 1 | 4 | 1 |
| Job listings | 1 | 1 | 1 | 0 |
| Personnel changes | 0 | 0 | 0 | 0 |
| Total label assignments | 9 | 2 | 8 | 1 |

Rare-label recall rose from 2/9 (22.2%) to 8/9 (88.9%); final rare-label
precision was 8/9 (88.9%). Opportunity precision and recall were both 4/5
(80%). The screen admitted every reference rare-positive row, so the one
remaining miss occurred inside the specialist, not at routing. These small,
consumed-reference counts do not estimate population accuracy. In particular,
one job and zero personnel positives cannot establish quality for those types.

The newly added judgments were:

| Owner case | Target brand | Correct additions | Incorrect additions |
|---|---|---|---|
| H0DEC6F537E0 | Qwen | Events | — |
| H1A3B3731E1C | Qwen | Events | — |
| H5024EDC82C6 | DeepSeek | — | Opportunities |
| H688781944AC | DeepSeek | Opportunities | — |
| H69C877BE195 | Upstage | Opportunities | — |
| H7F29D6428BB | Qwen | Events, opportunities | — |

The Qwen hackathon case gained **both** events and opportunities. The closed
beta case also gained opportunities without inventing dates or a public
deadline. This experiment produces labels only; it does not extract or store
event entities, dates, people, or jobs in the database.

Two opportunity boundaries remain unresolved:

- **False addition, H5024EDC82C6:** A third-party service advertises free
  DeepSeek access, but the visible post does not establish a bounded offer.
  The specialist still treated the free-access statement as an opportunity,
  despite an explicit prompt exclusion for ordinary ongoing free availability.
- **Miss, H8FA9071508D:** The b.ai promotion focuses on GLM and also mentions
  Hunyuan's Hy3 among other models under free-access promotions. The specialist
  returned false for Hunyuan. It did not provide a rationale for negative
  decisions, so alias recognition, the secondary mention, and the scope of
  the stated expiry are possible explanations, not demonstrated causes.

The owner reference is unchanged. Neither disagreement is silently corrected
in the reference or used to tune and rerun this frozen experiment.

Across **all** post types, complete-set agreement improved from 11/45 (24.4%)
to 14/45 (31.1%), and micro F1 improved from 0.654 to 0.700. Many non-rare
omissions remain. All other fields were preserved exactly: product-label
agreement remains 37/45, sentiment 28/45, China nationalism 7/45, U.S.
nationalism 7/45, and outcome 41/45. The full improvement composite is 0.4963
against the unchanged required 0.8644. Full quality floors, axis regression,
and overall per-label regression still fail. No classifier is selected.

The extra call used 14,521 non-cache input tokens, 768 cache-read input tokens,
and 2,635 output tokens. Each original batch incurred one additional request;
the conceptual pipeline therefore uses nine requests instead of six on this
cohort. The selected-post fraction is 51.1%; the request-count increase is 50%.

| Cost or timing measure | Result |
|---|---:|
| Additional cost at current published peak rates | $0.007522908 for 45 source posts |
| Additional cost projected per 1,000 source posts at this mix | $0.1672 |
| Additional cost using the frozen conservative rates, including cache | $0.01020536 |
| Original R98 base, same conservative rate treatment | $0.03579928 |
| Base plus specialist, same conservative rate treatment | $0.04600464 |
| Increase at those consistent conservative rates | 28.5% |
| Reserved trial ceiling | $0.05247396 |
| Added request latency for the three affected batches | 4.268 s / 4.121 s / 2.492 s |

The cost figures are token-based estimates, not a separately reconciled bill.
The per-1,000 projection assumes this same unusually selected corpus mix. All
three requests occurred during peak pricing. Current rates come from
[DeepSeek's pricing page](https://api-docs.deepseek.com/quick_start/pricing/):
$0.30 per million non-cache input tokens, $0.006 cache-read tokens, and $1.20
output tokens. The conservative comparison uses the older frozen $0.44/$1.32
rates and charges all input, including cache, at full input price. It avoids
mixing today's cheaper rates with the old base when calculating the 28.5%
increment. Full end-to-end three-call latency was not measured because the
base answers were reused; the table reports measured incremental latency only.

The same official page now states that `deepseek-v4-flash` is a legacy alias
served by **DeepSeek-V4.1-Flash**. All three responses echoed the old alias, so
they do not independently establish the underlying weight version. This
mixed-time experiment measures a practical add-on to fixed answers; it cannot
separate narrower prompting and sequential review from a provider model change.

82 focused tests passed before inference, with zero skips/errors. A separate
provider-free reconciliation confirmed that all 45 base rows retain their
order, all non-type fields are identical, all additions belong to the four
allowed types, and the 23 specialist decisions match their saved raw responses.
The existing production configuration and staging deployment are unchanged.
No further owner review is requested; the sole human review remains complete.

Evidence:

- [Frozen contract](2026-09-15-103348-u18-r100-conditional-rare-type-contract.json), SHA-256 `f98180427034e695ec43520751e579e9ad9a80ae9b3109e166a5306aa153e49a`.
- [Machine-readable result](2026-09-15-104335-u18-r100-conditional-rare-type-results.json), SHA-256 `47d3896a42e5976edd12de5dfa6eb300568c19fb640c4dd2d111ff2dccf711e3`.
- [Pre-inference receipt](../research/2026-09-15-103348-u18-r100-conditional-rare-type-receipt.md), frozen implementation commit `73339fc6f876dd95faf183b842655ccc9a5e4a53`.
- [Shared plan](../plans/2026-09-08-134925-feat-ai-enrichment-stage1-plan.md), R100 / Exception 19 / KTD54.
- Private raw requests, responses, and merged answers: `.context/u18/conditional-rare-type-pilot-r100-v1/` (ignored, never pushed).

The requested trial is complete. Preserve it as terminal evidence; no automatic
rerun, extra model, budget increase, or activation follows from this result.

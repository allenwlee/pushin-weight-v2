# R101: one primary call plus one conditional follow-up

R101 tested one full current-v3 primary request for each 20/20/5 batch, then
the rare-type specialist for primary/source-screened rows. It made six serial
requests: three primary and three follow-ups for 21/45 posts. All six were
valid. No retry, runtime change, database write, staging deployment, or
production deployment occurred.

| Measure | R98 + R100: two primary roles + follow-up | R101: one primary + follow-up |
|---|---:|---:|
| Total calls | 9 | 6 |
| Follow-up rows | 23 | 21 |
| Post-type exact sets | 31.1% | **48.9%** |
| Post-type micro F1 | 0.700 | **0.807** |
| Product-label exact sets | **82.2%** | 75.6% |
| Sentiment accuracy | 62.2% | **66.7%** |
| China-nationalism accuracy | 15.6% | **84.4%** |
| U.S.-nationalism accuracy | 15.6% | **91.1%** |
| Conservative token cost for 45 posts | $0.04600464 | **$0.02705736** |

The primary alone reached 44.4% exact post-type sets and 0.789 micro F1. The
follow-up raised those to 48.9% and 0.807. This is a direct architecture result
on the same source packets and completed owner reference, though that reference
is consumed calibration evidence, not a population estimate.

The follow-up recovered events for H0DEC6F537E0 and H1A3B3731E1C, and
opportunities for H688781944AC and H7F29D6428BB. It made two unsupported
opportunity additions: H5024EDC82C6's ongoing third-party free-access
promotion, and HB94D1A5CA63's DeepSeek release/research post. It missed
H8FA9071508D because the primary marked the Hunyuan attribution
`context_missing`; the follow-up deliberately cannot override that result.

| Rare type | Reference positives | Primary TP | Merged TP | Merged FP | Merged FN |
|---|---:|---:|---:|---:|---:|
| Events | 3 | 1 | 3 | 0 | 0 |
| Opportunities | 5 | 2 | 4 | 2 | 1 |
| Job listings | 1 | 1 | 1 | 0 | 0 |
| Personnel changes | 0 | 0 | 0 | 0 | 0 |

The run used 33,322 non-cache input tokens, 6,272 cache-read tokens, and 7,300
output tokens. The frozen conservative estimate is $0.02705736 for 45 posts.
The current off-peak token-rate estimate is $0.009397116, or $0.2088 per 1,000
posts at this corpus mix. The request latencies were 6.644s, 4.221s, 6.236s,
2.970s, 2.489s, and 1.845s in primary/follow-up batch order.

R101 still fails the existing production gates: post-type exactness is below
the 73.3% regression minimum; outcome, sentiment, China, and U.S. nationalism
also remain below their floors; the composite is 0.7667 against 0.8644. The two
false opportunity additions fail the diagnostic criterion. No classifier is
selected or activated.

The next architecture should be one full primary call plus one bounded
conditional rare-type follow-up. It should not add another routine call or
reviewer. The next prompt experiment needs to resolve ordinary free access,
the context-missing routing boundary, and remaining primary-label omissions.

Evidence:

- [Frozen R101 contract](2026-09-15-110900-u18-r101-single-primary-conditional-contract.json), SHA-256 `feafe97fe105b5ae4b8ffad1a062abf2f3a15cc5bab4df10a328c7f139ad771c`.
- [Machine-readable R101 result](2026-09-15-111545-u18-r101-single-primary-conditional-results.json), SHA-256 `4ad0fe6267a74c560a5870b29e50bf9bd20eaa42976a27694e7f7aecb343e5ab`.
- Private raw requests/responses: `.context/u18/single-primary-conditional-pilot-r101-v1/`.

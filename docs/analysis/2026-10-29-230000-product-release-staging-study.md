# Product-release study: staging results

Date: October 29, 2026, Japan time. Application revision: `5e3c475e`.  
[Sortable release report](2026-10-29-230000-product-release-staging-study.html) · [35-entry CSV](2026-10-29-230000-product-release-staging-study.csv) · [machine-readable results](2026-10-29-230000-product-release-staging-study.json) · [implementation reference](../reference/2026-10-29-223000-product-release-detection.md)

The detector and the saved study now work in staging. All 30 frozen nominations were admitted without additional model calls. They produced 35 separate product entries because MiMo and StepAudio family announcements contain multiple products. Two announcements meet the publisher-verification standard; 33 remain provisional. These are 35 assessed entries, not 35 verified new releases.

The saved data can support development of the TN numerical and source-selection path. Recent staging discussion is incomplete, so it cannot yet establish a reliable average audience response to releases. Production detection, targeted metadata acquisition and TN/Pulse generation remain separate work.

## What was exercised

| Check | Observed result |
|---|---|
| Frozen nominations | 20 development cases and ten held aside; all 30 detected. Membership stayed fixed. |
| Separate products | 35 stable dossier/review identities; Giotto Alto and Solo remain separate. |
| Confirmation | DeepSeek V4.1 Flash and Mistral Large 4 confirmed; 33 entries provisional. |
| Misleading controls | Six controls; zero false confirmations. A meetup was marked non-release; a benchmark-only post generated no candidate. |
| Exact repeat | Reapplying the same assessment produced identical identities and no new dossiers, claims, reviews or counts. |
| Whole-side counts | All 38 distinct seven-day before/after totals matched direct database queries. |
| Arbitrary windows | Five exact windows matched direct Post counts and distinct account unions; repeat created zero snapshots. |
| Browser | Sorting, filtering, separate family rows, expandable sources/dates and labelled announcement/availability comparisons passed. The table scrolls on a narrow screen. |
| Model/provider usage | No external model calls or paid provider collection. Research used this session and public primary pages. |

The controls test the staging persistence and confirmation boundary with synthetic in-memory text inside a rolled-back transaction. They are not real public Posts. An earlier attempt to insert synthetic Posts timed out before reaching the detector; the result is retained as an environment failure, not a passing control. Local database tests exercise real Post creation and the complete command path.

## What is saved

The 35 study dossiers use the existing `event_dossiers`, `event_dossier_sources`, `event_dossier_claims`, `event_dossier_reviews` and `product_release_details`. Exact existing Product foreign keys are used when resolved. Unknown observed publishers use the existing discovery records and supporting release-context claims.

Four typed tables were added; no table was retired and no JSON column was added:

| Table | Staging rows at verification | Purpose |
|---|---:|---|
| `event_dossier_intake_decisions` | 4,332 | Pending/non-release/scam/superseded assessment history for retained candidate dossiers. Includes the persistence pilots. |
| `discussion_window_snapshots` | 3,539 | Immutable totals for exact brand/time/input versions. |
| `discussion_window_counts` | 43,491 | Language, classification and coverage counts with explicit denominators and definition versions. |
| `event_dossier_discussion_windows` | 4,650 | Dossier/review use of a snapshot, tied to an announcement, availability or other dated claim. Includes retained review history. |

The numerical tables occupy about 15.1 MiB including indexes at this sample size; intake decisions occupy another 2.8 MiB. These are current allocated sizes, not an extrapolation to annual production load. They do not create a new Post relationship for every counted item on every dossier.

The initial 23 dated product entries reused 18 distinct brand/anchor sets. Five family entries needed zero new numerical snapshots. The separate DeepSeek availability anchor added 186 windows; five arbitrary windows brought the total to 3,539. A corrected source fingerprint creates a new numerical version, while saved outputs retain the version they used.

## Exact-window example: DeepSeek 1017

Times below are UTC; the study command also accepts explicit Japan time. Both boundaries are exact, with the end excluded.

| Requested interval | Posts | Distinct accounts |
|---|---:|---:|
| Oct 17, 09:00–09:15 | 191 | 173 |
| Oct 17, 09:05–09:20 | 127 | 118 |
| Oct 17, 09:00–11:00 | 578 | 490 |
| Oct 17, 09:00–Oct 18, 09:00 | 1,166 | 933 |
| Oct 17, 09:00–Oct 24, 09:00 | 1,200 | 963 |

All five calculations together took 3.29 seconds on the first measured request and 1.40 seconds on repeat. The repeat still reads inputs to validate reuse; zero new rows does not mean zero work. These timings exclude TN writing and are not a latency guarantee for a one-year request. The near-flat seven-day extension illustrates sparse staging coverage, not a conclusion that DeepSeek discussion stopped.

## Dates, identity and publisher verification

An announcement and availability are distinct claims. For DeepSeek V4.1 Flash, the stored announcement and access posts are three seconds apart; the report shows both anchors, their different totals and exact evidence. Mistral Large 4 has a confirmed announcement but unresolved availability, rather than treating promised future weights as already available.

Publisher confirmation checks the entity and control of its source. [Mistral's own site](https://mistral.ai/) links to the stored announcing account; DeepSeek has corresponding primary evidence. MiniMax remains provisional: the [current MiniMax site](https://www.minimax.io/) links to `MiniMax__AI` (two underscores), while the selected stored account has `MiniMax_AI` (one). That may be an account/handle change, but the evidence collected here does not establish it. A matching brand tag does not resolve the mismatch.

The Qwen3.8-27B nomination is an anticipatory post, not a weight-release timestamp. The NeuralDaredevil nomination discusses an older checkpoint. Both remain in the study with unresolved release anchors; neither is discarded for having low attention or silently counted as a new dated launch.

## Historical coverage

The X census covered every staged Post in the selected publication interval: **August 1, 00:00 JST to October 29, 19:00 JST**. It read **265,340 Posts**, admitted **69,550 source candidates**, and took **2,023.48 seconds** in 133 resumable pages. Candidate counts include repeated discussion and ambiguous signals; they are not a unique release count or a measured precision score.

This broad census was read-only. Earlier bounded persistence pilots and the 35-entry assessed study remain saved. Filling staging with every unreviewed historical signal was not necessary to validate the finite study, and no claim is made that all 69,550 candidates have dossiers.

The source database held 438,494 Posts in the same interval. The gap between that source and staging explains why an absence or small count in staging cannot establish collection failure or lack of public interest. The [separate web-inventory coverage artifact](2026-10-29-230000-product-release-web-coverage.md) records exact search aliases, primary links and observed matches; a name occurrence may be a comparison, rumor or retrospective mention.

Non-X observations are checked separately on their first-storage clock. The available population is 1,371,466 rows, mostly HF metadata observations. The first 100 had no supported release-bearing text. The one-hour bounded scan read **562,000 observations** in 281 pages and admitted **0 candidates**. All scanned rows reported no supported release text. It stopped at the declared time bound with a resumable cursor; **809,466 rows remain unscanned**. Neither repository creation nor an updated metric is promoted into release proof. The exact cursor and limitations are in the result JSON; this is not full non-X coverage.

## Descriptive comparison and TN implications

The saved statistical recipe uses one observation per distinct brand/anchor pair, equal weighting, seven days before versus seven days after, and no duplicate family population. It excludes unaligned cases and follow-up that has not elapsed. Zero-baseline cases retain absolute counts but are excluded from percentage ratios. Announcement and availability analyses remain separate. Membership, exclusions, means, medians and spread are saved in the JSON.

Seventeen distinct elapsed anchor populations remain: ten primary general-model, six primary specialist-model and one agent population. There are no aligned derivative populations in this staging cohort. Because collection completeness is not established, these are **descriptions of stored rows only**. They are not valid popularity comparisons, evidence of causation or a prediction-training baseline. A very low post-release Mistral count is an obvious warning against that interpretation.

For TN work, the useful results are concrete:

- Arbitrary overlapping windows and exact account unions work without making a fresh full-population evidence join for every dossier.
- Numerical populations, selected source packets and quoted evidence are separate. Packets expose total Post/account counts and named examples; saved classification eras and missing values remain distinguishable.
- Family launches can share calculations while preserving separate release identities.
- A later TN should retain the exact snapshot, review and dated anchor it used. More evidence may change today's interpretation without rewriting the old one.
- The next writing work must explain shape and subject changes, expose source count/names and distinguish sparse coverage from flat activity. This release study makes no claim that the current TN writer already does that.

## Verification and remaining scope

The complete focused run at `f85f67f7` passed 83 tests, including 47 PostgreSQL-required tests. The later report correction passed all 14 report/study tests, including 11 PostgreSQL-required tests. No required test was skipped. [Review record](../reviews/2026-10-29-230500-product-release-review.md) distinguishes inline review, browser evidence and environment failures.

The selected staged slice is implemented. Broader automatic product identity resolution, verified publisher enrichment, targeted HF/GitHub acquisition, lineage collection, live harvester binding and TN/Pulse writing remain PR-U4 or subsequent TN work. Production and recurring activation were not performed.

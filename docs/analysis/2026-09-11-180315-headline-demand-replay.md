# Headline Demand Replay

Date: 2026-09-11 18:03 JST  
Decision: **Pass for the provider-free U19 replay gate**  
Candidate product revision: `83064ad`

## Plain-English Result

The first replay found that the planned 5% material-change band was configured
but not applied. Volatile evidence ranks, engagement counts, and sliding bucket
times therefore changed every fingerprint and would have regenerated headlines
even when the underlying facts and sources were effectively unchanged.

The corrected `headline-materiality-v2` fingerprint keeps semantic facts,
evidence text and identity, topic signals, coverage state, and trend shape. It
bands small numeric movement and ignores ranking/engagement jitter and moving
bucket timestamps. On seven days of saved production headline runs, it
suppressed 2,106 of 5,280 unchanged brand/window dossiers.

The replay deliberately assumes every brand stayed visible for the entire
period. This gives the new policy no savings from cold demand. It also charges
retained calls at the most expensive saved token count in the same run. Even
under that conservative case, calls and cost fall while last-good headline
availability remains identical.

## Frozen Source

- Dump: `pushinweight-prod-20260910-165134.dump`
- Interval: `2026-09-03T00:00:00Z` inclusive through
  `2026-09-11T00:00:00Z` exclusive
- Windows: 1 day and 7 day
- Saved runs: 160
- Source SHA-256:
  `49e39d6d96134fe44df8a3c20477545cd4c97bbe93be649fa68da0a9835521db`
- Machine-readable report:
  `docs/analysis/2026-09-11-180315-headline-demand-replay.json`

No provider call or database write occurred. The replay read saved snapshots,
call ledgers, token counts, and publication states from the disposable local
copy of the production dump.

## Results

| Measure | Historical policy | New upper bound | New risk-routed estimate |
|---|---:|---:|---:|
| Provider calls | 1,629 | 1,518 | 1,499 |
| Input tokens | 64,864,034 | 63,427,258 | 62,914,382 |
| Output tokens | 5,831,056 | 5,612,791 | 5,554,298 |
| Total tokens | 70,695,090 | 69,040,049 | 68,468,680 |
| Estimated cost | $36.237169 | $35.316878 | $35.014001 |
| Last-good coverage | 77.5947% | 77.5947% | 77.5947% |

The upper bound assumes every retained editor batch still receives a critic.
Compared with historical work, it reduces calls by 6.81%, total tokens by
2.34%, and cost by 2.54%. Applying the deterministic critic-risk policy to the
saved editor responses reduces calls by 7.98%, total tokens by 3.15%, and cost
by 3.38%.

The replayed policy would publish 698 saved approved outputs instead of
regenerating 806. The 108 avoided publications were unchanged replacements;
their prior valid headline remained available. Replayed publication validity
was 100%, and last-good coverage changed by zero.

## Method and Limits

The historical side counts completed saved rank, editor, and critic calls and
their provider-reported tokens. The counterfactual side applies the production
material fingerprint, compacts selected dossiers through the production editor
batcher, and reuses saved per-run token costs. The upper bound assigns retained
stages the most expensive applicable saved calls in that run without
replacement and sends every editor batch to a critic. When a run lacks a
completed comparable stage, it charges the most expensive such call in the
entire replay. The risk-routed estimate applies the current deterministic
critic policy to saved editor responses and carries that per-run rate into the
compacted batches.

This replay does not predict new prose or claim savings from brand/window
demand becoming cold. Changed batch composition could alter the exact critic
rate. U23 must therefore compare observed staging calls, tokens, cost,
publications, last-good age, and suppression reasons with this offline result
before production activation.

## Reproduction

```bash
DATABASE_URL='postgresql:///pushinweight_u18_eval?host=/tmp' DEBUG=1 \
  .venv/bin/python manage.py replay_headline_demand \
  --start 2026-09-03T00:00:00Z \
  --end 2026-09-11T00:00:00Z \
  --windows 1 7 \
  --source-identity pushinweight-prod-20260910-165134.dump \
  --candidate-revision 83064ad \
  --output docs/analysis/2026-09-11-180315-headline-demand-replay.json
```

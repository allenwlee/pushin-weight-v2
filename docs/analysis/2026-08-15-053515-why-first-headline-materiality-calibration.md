# Why-first headline evaluation

- Run: `2026-08-15-materiality-calibration`
- Model: `none-read-only`
- Calls used: 0
- Stop reason: `completed`
- Accounted input tokens: 0
- Accounted cost: $0.000000

The JSON sibling is the reproducible machine record. Calibration used twelve weekly anchors per supported window in fresh repeatable-read, read-only PostgreSQL transactions. No provider transport or configuration write occurred.

## Review decision

- The job completed 48 bounded reconstructions: twelve weekly anchors for each
  of the 1-, 7-, 30-, and 365-day windows.
- Volume, post type, discourse, sentiment, and both nationalism families have
  sufficient samples for proposals in the 1-, 7-, and 30-day windows.
- Engagement has zero usable change samples in every window.
- Every 365-day family has zero usable samples because comparisons were not
  allowed at the tested anchors.
- No fixed materiality policy is approved or written from this partial result.
  The checked-in policy remains `pending-live-review-v1`.

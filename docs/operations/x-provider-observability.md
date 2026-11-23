# X provider request history and announcements

Searches for X posts stay under the same X collection job and run when the client switches between TwitterAPI.io and TwexAPI. Each physical send gets its own request receipt. The receipt stores the provider and credential purpose as small typed fields. The existing staging-specific receipt counter and its constraints are unchanged. The general returned-count field is nullable because some receipts have no usable result count.

Run the read-only usage report for an explicit time window:

```sh
python manage.py report_x_provider_usage --since 2026-11-23T12:30:00+09:00 --until 2026-11-23T13:30:00+09:00
```

Each output line identifies a run, scope, provider, credential purpose, and endpoint. It distinguishes successful HTTP responses, rate limits, 503s, timeouts, unconfirmed sends, and reservations canceled before dispatch. An HTTP success does not certify complete coverage. Older receipts can show an unknown provider or result count. For matched provider comparisons, use the same query windows, read the saved evidence for unique post IDs, and reconcile cost against the provider's billing records.

The announcement command reads the public TwitterAPI.io Telegram preview. The separate Render cron definition uses a 15-minute cadence. One call is admitted per slot. Identical announcement snapshots share an archive, and new or changed messages appear in the command output with the source timestamp and permalink. A failed poll records the failure and leaves the previous success visible:

```sh
python manage.py poll_x_provider_announcements --status
```

When reviewing a rollout, verify a primary failure and fallback success appear as two receipts under one run. Check held scopes, rate limits, and cycle duration before changing provider priority. For announcement monitoring, confirm fresh status after two polls and that an unavailable preview is recorded without affecting the harvest cron. The provider's statements are evidence from its channel. Check them alongside observed harvest health.

# Profile history and affiliation candidates

Every newly persisted post can contribute the author fields present in the
Twitter response to a compressed `AccountProfileSnapshot` history. The writer
distinguishes a missing field from a field explicitly returned as null. It
creates a new snapshot only when the normalized profile hash changes; A → A →
B → A therefore creates three versions, while repeated processing of the same
post remains idempotent.

Snapshots preserve the full observed business-affiliate label facts, including
target username and URL, description, label/display types, and badge image URL.
The badge is stored as evidence. No image recognition is needed to retain a
MiniMax badge such as `VxHk9HyU_bigger.jpg`.

Deterministic rules produce pending affiliation candidates:

| Evidence | Candidate treatment |
| --- | --- |
| Existing `brands_accounts` official/staff/community edge | Trusted positive role evidence |
| Active Call A membership | Staff candidate, or official when the account itself matches the organization handle |
| Explicit employee/title language | Staff employment candidate |
| Former/worked-at language | Former employment candidate |
| Ambassador, creator-partner, affiliate, or community wording | Matching nonemployee affiliation type |
| Bare handle/name or business badge without stronger evidence | Unknown candidate for review/targeted extraction |

Absence from `brands_accounts` or Call A is unknown; it is not proof of a
community relationship. Profile removal alone never creates a departure or an
employment end date. Snapshot time means “observed by PushinWeight at this
time,” not “the person changed jobs at this time.”

Run a provider-free estimate first:

```bash
python manage.py backfill_account_profile_snapshots \
  --dry-run \
  --limit-accounts 1000 \
  --report /tmp/profile-backfill-estimate.json
```

Run or resume an authorized backfill with a durable checkpoint:

```bash
python manage.py backfill_account_profile_snapshots \
  --checkpoint /absolute/path/profile-backfill-checkpoint.json \
  --report /absolute/path/profile-backfill-report.json
```

The command processes accounts in stable `author_id` order and existing posts
chronologically. Reusing a checkpoint continues after the last committed
account. Replaying from the beginning creates no duplicate snapshots or
evidence. Production execution requires separate authorization; Stage 1C
staging proof uses a disposable PostgreSQL database only.

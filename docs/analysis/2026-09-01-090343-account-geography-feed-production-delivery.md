# Account geography and feed production delivery

The integrated account-geography, 215-symbol flag, feed, and headline-
disclosure candidate completed staging and production delivery. Product code
SHA `6adbd408a72cdb22227ecf4e9e089cff27e57ce9` ran every migration, data,
browser, and scheduled-harvest gate. Geography reconciliation made no HTTP
request, used no provider credit, and did not restart `aboutuserbackfill`.

## Release identity and taxonomy

| Measure | Result |
| --- | ---: |
| Product candidate SHA | `6adbd408a72cdb22227ecf4e9e089cff27e57ce9` |
| Geography migrations | 0026 and 0027 applied |
| Countries / localized labels | 249 / 498 |
| Regions / localized labels | 31 / 62 |
| Country-region rows | 249 |
| Exact About mappings | 317 |
| Guiding-country relationships | 19 |
| Runtime flag symbols | 215 |

The same taxonomy counts and exact product SHA were verified on staging and
production before data apply. The frozen production census remained 59,066
nonblank Accounts across 194 exact raw values with SHA-256
`b17cd81b3b5dd3711c6924c3c7c34d9c4402febf45b3eb66bd6dc135ba3e7668`.

## Staging reconciliation and browser gate

Staging classified 97 populated Accounts as 91 countries and six region
fallbacks, with no unresolved value. The dry run predicted 13 changes; the
first apply wrote exactly 13, rejected none, and left zero changes. A repeat
apply and the post-browser-cleanup dry run both changed zero rows.

Authenticated Chromium verified direct country, `CN › HK`, neutral
`CN › TW · Taiwan` / `CN › TW · 台湾` without `flag-tw`, and region-only
rendering. It also verified official and non-official placement, localized
hover/accessible labels, the one `more` / `less` or `更多` / `收起` disclosure,
focus retention, sibling isolation, and the 390-pixel layout. Four temporary
Account geography fixtures were restored to their exact prior values and the
temporary authentication session was deleted.

## Production reconciliation

The pre-write recovery snapshot covered 61,538 Accounts and restore-proved
digest `da1fe9162f47f36724290f14cad0c5ee85e3d682a90b4a0c9ef28ecf077ba25b`.
Production then produced the reviewed partition:

| Classification | Accounts |
| --- | ---: |
| Country | 52,488 |
| Region fallback | 5,925 |
| Explicitly unresolved `Congo` | 13 |
| Explicitly unresolved `Korea` | 640 |
| Total nonblank | 59,066 |

The first apply changed 9,657 Accounts, rejected none, left zero remaining
changes, and exactly matched its dry run. Two deliberately guarded retries
stopped before writes when presented with an invalid receipt and a now-stale
pre-write snapshot. A fresh post-write snapshot then restore-proved 61,546
Accounts, and the repeated production apply reported `changed: 0`,
`rejected: 0`, and `remaining_changes: 0`.

Post-apply SQL found 52,488 country targets, 5,925 region targets, 653 reviewed
unresolved raw values, and no Account with both a country and region target.
Against the original recovery cutoff, zero raw `account_based_in` values and
zero `account_based_in_fetched_at` timestamps changed.

## Production browser and scheduled lane

The authenticated production homepage exposed 36 geography signals in its
then-current feed: 34 country flags and two localized region fallbacks. The
deployed flag measured 14 pixels wide with
`saturate(0.72) brightness(0.9)` and opacity `0.9`. English and zh-CN labels,
both disclosure transitions, focus, and the 390-pixel no-overflow layout
passed. No production Account fixture was written, no `flag-tw` reference was
present, and Chromium reported zero console messages and zero page errors.

The first fully post-apply scheduled run
`20260901T000055_0000-d54ca242` used the same product SHA and completed all
seven planned calls. It processed 57 results, attributed 27, inserted 26
posts, updated one, and recorded zero persistence, enrichment, or cycle
errors. PostgreSQL independently found 26 posts persisted since the cycle
start. After the run, production had 61,549 Accounts while every geography
partition and protected About field remained unchanged.

The two narrow recovery relations remain retained for later explicit cleanup,
as required by the runbook. No recovery token, credential, Account identifier,
handle, or provider payload is present in this evidence.

The matching machine-readable receipt is
[`2026-09-01-090343-account-geography-feed-production-delivery.json`](2026-09-01-090343-account-geography-feed-production-delivery.json).

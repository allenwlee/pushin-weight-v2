# Integrated Candidate Integrity Review

Reviewed product revision: `1b3d73e6a36c5e053c70942fc7e9c786d2de8d8f`

## Plain-English Summary

This review checked the integrated Stage 1–4 candidate before any new feature
was activated on staging. It found and fixed places where personnel evidence
could be lost, malformed dates could reach storage, repeated job evidence
could fail to enrich a listing, an old headline run could consume newer work,
and stored rate-limit identifiers could reveal a user or IP address by simple
guessing.

The schema change was replayed on the frozen production copy containing
211,245 posts. It adds one optional organization-candidate foreign key and a
constraint requiring every person affiliation to belong to exactly one known
brand or one pending organization candidate. The frozen copy had zero rows in
the new affiliation table, so the migration rewrote no application data.

Provider-free checks pass. The real Claude Haiku quality pilot remains blocked
because no tested direct Anthropic credential authenticates. The plan therefore
still forbids staging data refresh, feature activation, and production
promotion until U18 passes.

## Findings closed

| Risk | Failure before this review | Final behavior |
|---|---|---|
| Untracked personnel organizations | A valid “person joined New AI Co” extraction created a review candidate and then discarded the affiliation and evidence. | The affiliation points to that pending candidate, retains its source evidence, and exposes the review state to analysis readers. |
| Source dates | Calendar-invalid reduced dates could satisfy regex-only database checks, and job timestamps without a timezone could be accepted by Python. | Calendar values, precision/value pairs, comparable ranges, and timezone-bearing job timestamps are validated before the role transaction commits. |
| Job identity | Case, whitespace, Unicode form, and location order could produce duplicate fallback identities. | Only the deterministic fallback identity is normalized with Unicode NFKC, case folding, whitespace folding, and order-independent lists; stored source text remains unchanged. |
| Later job evidence | A repeated canonical listing advanced `last_seen_at` but left fields missing even when later evidence supplied them. | Later evidence fills blank location, compensation, requirements, and lifecycle fields, preserves `first_seen_at`, and remains a separate evidence row. |
| Headline demand race | A run selected before a provider/version change or explicit operator refresh could later mark the newer request satisfied. | Selection locks demand rows and snapshots the exact target and operator count; finalization updates only that exact selected request. |
| Rate-limit privacy | Unsalted SHA-256 hashes made low-entropy user IDs and IP addresses recoverable by enumeration. | Django `salted_hmac` derives a secret-keyed SHA-256 digest while preserving database-backed atomic limits. |
| Replay identity | Changed job/personnel/profile extraction contracts still used v1 prompt identities. | The three affected roles use v2 identities so old successes cannot suppress the corrected extractor. |
| Numeric validation | Non-finite decimal strings could reach salary persistence. | NaN and infinity are rejected before persistence. |

## Migration evidence

Frozen source:
`/Users/fuchitalee/Downloads/pushinweight-dumps/pushinweight-prod-20260910-165134.dump`

Disposable database:
`postgresql:///pushinweight_u18_eval?host=/tmp`

Observed after applying `core.0039_affiliation_candidate_and_integrity_guards`:

```text
posts=211245
affiliations=0
candidate_affiliations=0
latest_core_migration=0039_affiliation_candidate_and_integrity_guards
ck_pba_one_organization=brand XOR brand_discovery_candidate
```

The migration adds a protected foreign key, drops the known-brand `NOT NULL`
requirement, and then adds the exclusive-owner check. Existing known-brand rows
remain valid. The migration test proves a known-brand row survives the upgrade,
a candidate-backed row succeeds afterward, and a row with no organization is
rejected.

## Security boundary

`POST /api/v2/post-synthesis-demands/` remains behind Django login and Cross
Site Request Forgery protection. It bounds request bytes and batch size,
validates the requested post IDs against the authenticated feed scope, and
applies atomic per-user and per-IP minute limits. No changed file contains a
credential or connection secret.

`manage.py check --deploy` reports the repository's existing local-setting
warnings for clickjacking middleware, HTTP Strict Transport Security, and the
development secret key. They are outside this change; Render supplies its
deployment settings and secret. No new deployment warning was introduced.

## Verification

```text
55 passed
PostgreSQL-required: executed=55 skipped=0 errors=0
ruff E4/E7/E9/F/I: passed
makemigrations core --check --dry-run: no changes detected
config.yaml load: passed with job/personnel/profile prompt identities at v2
git diff --check: passed
```

The repository's selected active aggregate and exact-candidate scripts remain
the authoritative broad gates. A raw all-file `pytest` invocation is not used
as release evidence because it includes explicitly retired and incompatible
stack tests excluded by
`tests/fixtures/ai_enrichment_stage1_test_scope.json`.

## Rollback and remaining gate

Rollback is application-first: disable targeted extraction, job/personnel
discovery, headline demand, and synthesis writers, then run the previously
verified application against the forward-compatible schema. Do not reverse
`0039` after candidate-backed affiliation rows exist, because restoring a
non-null known-brand column would correctly fail for those rows. Preserve the
rows and ship a forward fix.

The next allowed semantic step is the frozen 30-row direct Claude Haiku pilot.
Both local direct-Anthropic credential slots returned HTTP 401. A read-only
staging web probe found no `ANTHROPIC_API_KEY`; the production web variable was
present but its provider authentication check returned HTTP 401. No key value
was printed and no classifier call ran. U23 staging refresh and activation stay
blocked until a refreshed direct credential lets U18 complete.

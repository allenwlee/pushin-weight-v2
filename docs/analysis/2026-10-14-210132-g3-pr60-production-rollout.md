# PR60 account rollout evidence

Owner selected production with “approved, deploy to production.” Session:
`g3-pr60-production-20261014`; authoritative host: `fuchitalee`.
The existing account plan remains the execution authority and C0–C8 checklist.

Production has not been paused, migrated or deployed by this session.
The owner selected “direct production” at2026-10-14T13:16:05Z. The backfill owner is actively using
shared staging with sibling migration0085 and a long-running native acceptance
controller. Its pilot and code remain separate. The isolated production-scale
PostgreSQL18 migration/recovery rehearsal is complete. The existing production
approval and explicit direct-route exception are recorded in the same plan.
Shared staging branch/deploy/rehearsal gates are retired for this release.

- Observed rollback revision: `2e0274cf15af5dcaabf2ce0f11d73f207bc1933a`
  on all six active production services. Legacy worker and beat are suspended.
- PR60 implementation: `bed348d74c7e6b4971fb42939f143dd992fd19ff`.
- Integrated candidate: `56649f96abeea2beee4b8a027392446cbc0684c6`, incorporating current main without source
  conflicts. Account application code is unchanged; the intervening main work
  adds editorial review. Exact final candidate remains to be frozen.
- Production DB: `dpg-d9koekqjobas73fvjqng-a`, `pushinweight_shadow`,
  PostgreSQL 18.4. Ledger ends at 0082; database approximately 6,779 MB.
- At C0 inspection: 96,905 accounts (96,903 X, two HF), 30 legacy HF namespaces,
  and 28 expected newly admitted HF identities. The quiesced baseline must
  replace these moving preparation counts before production migration.
- Read-only conflict checks: zero non-X accounts with any of the 33 X fields;
  zero mismatched HF account identities/company links/reserved provenance keys;
  zero invalid indexes. A diagnostic query initially needed an explicit `C`
  collation; the corrected query completed successfully. No source data changed.
- Local PostgreSQL 18.6 integrated regression: 192 passed; 113 required
  PostgreSQL tests executed, zero skipped/errors. Django checks and migration
  drift check pass. All four hosted checks on this candidate passed.
- Worker read-only probe: zero active/reserved headline tasks. Synthesis
  provider calls are disabled; benchmark collection remains enabled. All flags
  will be preserved. The successful Celery probe ran on the headline worker;
  the web service does not provide a working broker-inspection route.

Machine-local private evidence and tooling:
`/Users/fuchitalee/.cache/g3-pr60-production-20261014/` (mode 0700).
Files include service/deploy/one-off inventory, conflict query, regression log,
backup/restore scripts and fingerprint verifier. Backups contain private data;
do not publish them or copy their rows into this receipt.

The first local-client dump was intentionally interrupted to switch to faster
server-side compression and is not a usable backup. Its incomplete artifact and
failure receipt remain private. The replacement full custom-format snapshot
completed successfully, streamed from the verified production web runtime using
compatible PostgreSQL18.6. Neither dump invoked a provider or changed application
data. This preparation snapshot does **not** replace C3's mandatory fresh dump
after production writers drain.

## Executed isolated rehearsal

- Exact artifact: `rehearsal-ssh.dump`,1,171,186,175bytes;
  SHA256 `54132a248d546eb0b47389caae37c87276e10852609639bbab91231a1a034370`.
  Dump12:08:47.037Z–12:19:14.325Z,627.29seconds, exit0.
- Restoration into `pr60_rehearsal` on the private local18.6 cluster,
 127.0.0.1:55460:12:19:25.372Z–12:21:08.794Z,103.42seconds, exit0.
 Required `pg_trgm1.6` and `plpgsql1.0` are present; the old migration ledger
 was restored. This is an actual data/schema restore of the exact checksum.
- The snapshot contains96,912 accounts,2,407 products,134 company-account
 links and30 HF namespaces. These differ from earlier moving C0 counts because
 production continued running. Baseline fingerprints cover161 other public
 tables; baseline capture took90.37seconds.
- Initial forward0083 took2.60seconds and0084 took1.19seconds. Direct typed
 comparisons prove every prior UUID/shared field, all33 X fields, ownership,
 product links, discovery metadata and unknown source dates. Zero invalid
 candidate indexes/constraints; exactly one table added and one retired.
- The recovery copy required captured global role memberships and database
 ownership, which a per-database dump does not contain. Eight membership edges
 and their ADMIN/INHERIT/SET options were restored locally; no production role
 or grant changed. Roles remain non-login locally, with service SQL access
 tested using SET ROLE. Initial admin-created detail table/functions were
 assigned to the actual migrating role before testing the same reverse and
 forward migrations under that role. This aligns the isolated environment with
 production DDL ownership instead of granting additional source access.
- Actual service role `pushinweight_ollija_20260814` reversed to0082 in9.30seconds.
 Exact comparisons found zero differences in original X accounts/fields,
 HFOrg rows, products and company links. The28 newly admitted shared HF
 identities/links remain after reverse; reversing does not delete them. A
 checker initially lacked access to the private proof schema; its corrected
 comparison uses the admin connection, without granting the application role
 access to that artificial schema.
- Forward0083/0084 then succeeded under the actual service role. The final
 preservation comparison passed again in88.53seconds:96,940 shared accounts,
 96,910 X detail rows, all original rows in161 other tables preserved. Django
 adds one content-type row and four XAccountDetail permissions; these additions
 are explicitly checked while preexisting permission/content-type rows retain
 their fingerprints. The first generic comparison flagged these expected
 framework additions before this distinction was implemented.
- Actual-role application smoke passed: profile reader, atomic X detail write,
 non-X source guard,30 publisher links,20 product-publisher reads,28 confirmed
 catalog namespaces, authenticated HTTPS `/admin` and `/general/` responses200.
 All writes rolled back and were rechecked. Initial HTTP301 was the expected
 HTTPS redirect; the corrected probe uses HTTPS. Zero provider calls or durable
 business rows. Static assets and a standalone browser were not tested by this
 server-side probe; the account change contains no UI edit.
- The Render CLI read-only exported-snapshot/fingerprint transport passed
 against the production migration ledger. Full C3 source-to-restored and C6
 canonical production comparisons remain future execution steps; prepared
 helpers are not reported as already executed.

The10–20-minute original interruption estimate is superseded. Reserve40–60minutes
for a future cutover: fresh dump/restore, full preservation comparison, runtime
transitions and serial builds. This total remains an estimate; Render maintenance
transitions/builds have not been rehearsed on occupied shared staging. Test
supported transitions on the old production schema before admitting migrations.
The30-minute checkpoint remains a report/recovery decision, not an automatic kill
or restore timer.

| Checkpoint | UTC start | UTC end | Result |
| --- | --- | --- | --- |
| C0 preparation | 2026-10-14T12:01:32Z | awaiting route | Candidate/CI/bindings/conflicts/tooling checked; live transitions pending |
| C1 isolated rehearsal | 2026-10-14T12:08:47Z | 2026-10-14T12:34:27Z | Restore, forward/reverse/forward, actual-role reads and preservation PASS; shared staging unperformed |
| C2 production pause | — | — | Unperformed |
| C3 fresh backup/restore | — | — | Unperformed |
| C4 migration build | — | — | Unperformed |
| C5 0083 | — | — | Unperformed |
| C6 0084 and preservation | — | — | Unperformed |
| C7 restart | — | — | Unperformed |
| C8 natural harvest | — | — | Unperformed |

No provider batch, historical campaign, HF/GH source activation, Blueprint apply
or resource provisioning is included in this release.

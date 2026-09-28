# Step/StepFun inbound-relation census — 2026-09-28

Read-only production check against the web-associated Render PostgreSQL `dpg-d9koekqjobas73fvjqng-a` / `pushinweight_shadow`. No records were changed.

`step` has no `posts_brands` rows. Its two account links (`liulicheng10/staff`, `stepfunai/official`) and one company link (`stepfun_inc`, ownership 1.0) are semantic subsets of `stepfun`; per-edge `added_at` audit timestamps differ. But the source is **not empty** under the plan's full inbound-relation invariant:

| `step` relation | Rows | Relevant facts |
| --- | ---: | --- |
| `brand_trend_narratives.brand_id` | 596 | 433 `data_quality_unavailable`, 163 `no_content`; all have immutable `brand_key_snapshot='step'`. All 596 runs also have a distinct `stepfun` narrative. Example run 738: `step` row 22451 is unavailable while `stepfun` row 22472 is approved. `uq_btn_run_brand` protects `(run, brand_key_snapshot)`. |
| `people_brand_affiliations.brand_id` | 15 | All are pending `other` observations with `observed_organization_name='Step'`. No person overlaps the six `stepfun` affiliation rows. `claim_identity` is unique and `ck_pba_one_organization` requires a brand or discovery candidate. These observations may describe an organization other than StepFun. |
| `trend_narrative_demands.brand_id` | 4 | Pending visible demand at windows 1, 7, 30, 365 days. `stepfun` has its own row at each window. `uq_tnd_brand_window` makes direct reassignment collide. The `step` 1-day request count is 13,774 versus `stepfun` 9,696; 7-day is 704 versus 706. |
| `brands_accounts.brand_id` | 2 | Subset as described above. |
| `brands_companies.brand_id` | 1 | Subset as described above. |

The remaining 25 of 30 PostgreSQL inbound foreign-key columns have zero `step` rows, as do the two text-key harvest tables `call_state` and `harvest_backlog_windows`. The inbound list came from `pg_constraint`/`pg_attribute` for references to `brands`, including hidden `related_name='+'` links that Django's ordinary reverse-relation list omits.

This invalidates U6's “empty duplicate” deletion premise. On 2026-09-29 the owner selected a UI alias: retain both stored brands and all Step-linked history, omit only the exact `step` nickname from homepage selection when `stepfun` exists, and normalize old homepage Step filters to StepFun. The uncommitted deletion migration and staging-refresh deletion deltas were removed from the candidate. None of these records is deleted or reassigned.

Read-only queries used (table and column names were first enumerated from the live foreign-key catalog):

```sql
SELECT c.conrelid::regclass::text, a.attname
FROM pg_constraint c JOIN pg_attribute a
  ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey)
WHERE c.contype='f' AND c.confrelid='brands'::regclass
ORDER BY 1,2;

SELECT status,count(*) FROM brand_trend_narratives
WHERE brand_id='step' GROUP BY status;
SELECT brand_key_snapshot,count(*) FROM brand_trend_narratives
WHERE brand_id='step' GROUP BY brand_key_snapshot;
SELECT count(*) FROM brand_trend_narratives a
JOIN brand_trend_narratives b ON a.run_id=b.run_id
WHERE a.brand_id='step' AND b.brand_id='stepfun';
SELECT affiliation_type,review_status,count(*) FROM people_brand_affiliations
WHERE brand_id='step' GROUP BY 1,2;
SELECT count(*) FROM people_brand_affiliations a
JOIN people_brand_affiliations b ON a.person_id=b.person_id
WHERE a.brand_id='step' AND b.brand_id='stepfun';
SELECT brand_id,window_days,state,demand_reason,request_count
FROM trend_narrative_demands WHERE brand_id IN ('step','stepfun')
ORDER BY brand_id,window_days;
```

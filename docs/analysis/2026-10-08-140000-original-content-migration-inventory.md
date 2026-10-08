# OriginalContent compatibility inventory

Base: integrated staging schema through `0074_official_company_generic_accounts`; production is excluded.

Post keys are text `tweet_id`; account conversion stays owned by Benchmark. No copied headline fields or old UUIDs may be discarded.

## Preservation destinations

| Input | Destination |
| --- | --- |
| Assessments | shared runs; external-spend audits become zero-send carry-forward runs |
| Budgets | call sums plus evidenced external receipts, including USD2.093153 / ten calls |
| Calls | shared calls with immutable legacy identities and uncertainty |
| Stories | parent story/subject snapshots; unpublished state retained in run outcome |
| Editions | one parent plus locale text per edition; original UUID becomes public_id |
| Heroes | selection pointers; empty slots omitted; provider lock becomes advisory mutex |
| Pictures | retained existing table, exact text/run links; generic media keys preserved |
| Headline tables | generalized in place; old trend_narratives / subjects remain excluded |

## Model fields and constraints

### EditorialAssessment (`editorial_assessments`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | BigAutoField | False |  |
| interval | DateTimeField | False |  |
| scope | CharField | False |  |
| cutoff | DateTimeField | False |  |
| source_cycle_id | TextField | False |  |
| state | CharField | False |  |
| fence | PositiveIntegerField | False |  |
| lease_until | DateTimeField | False |  |
| packet | JSONField | False |  |
| decisions | JSONField | False |  |
| outcome | JSONField | False |  |
| created_at | DateTimeField | False |  |

Constraints: uq_editorial_scope_interval

### EditorialBudget (`editorial_budgets`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| day | DateField | False |  |
| reserved_usd | DecimalField | False |  |
| calls | PositiveIntegerField | False |  |
| media_calls | PositiveIntegerField | False |  |

Constraints: ck_editorial_budget_positive

### EditorialCall (`editorial_calls`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | BigAutoField | False |  |
| assessment | ForeignKey | False | EditorialAssessment |
| stage | CharField | False |  |
| kind | CharField | False |  |
| state | CharField | False |  |
| reserved_usd | DecimalField | False |  |
| budget_day | DateField | False |  |
| response | JSONField | False |  |
| error_code | CharField | False |  |
| created_at | DateTimeField | False |  |

Constraints: uq_editorial_call_stage, uq_editorial_media_stage

### EditorialStory (`editorial_stories`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | UUIDField | False |  |
| development_key | CharField | False |  |
| anchor_ids | JSONField | False |  |
| created_at | DateTimeField | False |  |

Constraints: 

### EditorialEdition (`editorial_editions`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | UUIDField | False |  |
| story | ForeignKey | False | EditorialStory |
| assessment | ForeignKey | False | EditorialAssessment |
| track | CharField | False |  |
| locale | CharField | False |  |
| revision | PositiveIntegerField | False |  |
| headline | CharField | False |  |
| byline | CharField | False |  |
| article | TextField | False |  |
| importance | FloatField | False |  |
| occurred_at | DateTimeField | False |  |
| fingerprint | CharField | False |  |
| voice | JSONField | False |  |
| model | CharField | False |  |
| evidence | JSONField | False |  |
| selection | JSONField | False |  |
| published_at | DateTimeField | False |  |

Constraints: uq_editorial_edition_revision, uq_editorial_edition_evidence, uq_editorial_chatter_interval, ck_editorial_edition_track, ck_editorial_importance

### EditorialHero (`editorial_heroes`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| key | CharField | False |  |
| edition | ForeignKey | True | EditorialEdition |

Constraints: 

### EditorialPicture (`editorial_pictures`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | UUIDField | False |  |
| content_kind | CharField | False |  |
| content_id | CharField | False |  |
| source_platform | CharField | False |  |
| revision_hash | CharField | False |  |
| assessment | ForeignKey | True | EditorialAssessment |
| person_media | ForeignKey | True | PersonMedia |
| source_media | ForeignKey | True | StaffMediaObject |
| provenance | JSONField | False |  |
| treatment | TextField | False |  |
| mode | CharField | False |  |
| state | CharField | False |  |
| provider_task_id | CharField | False |  |
| poll_count | PositiveIntegerField | False |  |
| next_poll_at | DateTimeField | True |  |
| poll_lease_until | DateTimeField | True |  |
| generated_storage_name | TextField | False |  |
| generated_sha256 | CharField | False |  |
| created_at | DateTimeField | False |  |

Constraints: uq_editorial_picture_revision

### BrandTrendNarrative (`brand_trend_narratives`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | BigAutoField | False |  |
| run | ForeignKey | False | TrendNarrativeRun |
| brand | ForeignKey | True | Brand |
| brand_key_snapshot | CharField | False |  |
| brand_name_en_snapshot | TextField | False |  |
| brand_name_zh_cn_snapshot | TextField | False |  |
| status | CharField | False |  |
| headline_en | TextField | False |  |
| headline_zh_cn | TextField | False |  |
| secondary_en | TextField | False |  |
| secondary_zh_cn | TextField | False |  |
| critic_decision | CharField | False |  |
| critic_review_state | CharField | False |  |
| critic_reason_codes | JSONField | False |  |
| critic_audit_eligible | BooleanField | False |  |
| narrative_kind | CharField | False |  |
| confidence | CharField | False |  |
| propositions | JSONField | False |  |
| events | JSONField | False |  |
| cited_fact_ids | JSONField | False |  |
| cited_evidence_ids | JSONField | False |  |
| selected_evidence_packet | JSONField | True |  |
| final_critic_payload | JSONField | True |  |
| verified_at | DateTimeField | True |  |
| attempted_at | DateTimeField | False |  |
| error_code | CharField | False |  |
| last_good | ForeignKey | True | BrandTrendNarrative |
| created_at | DateTimeField | False |  |

Constraints: uq_btn_run_brand, ck_btn_status, ck_btn_output_shape, ck_btn_held_last_good, ck_btn_critic_decision, ck_btn_critic_review_state, ck_btn_narrative_kind, ck_btn_confidence

### BrandTrendNarrativeText (`brand_trend_narrative_texts`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | BigAutoField | False |  |
| narrative | ForeignKey | False | BrandTrendNarrative |
| locale | CharField | False |  |
| headline | TextField | False |  |
| secondary | TextField | False |  |
| created_at | DateTimeField | False |  |

Constraints: uq_brand_trend_narrative_locale, ck_brand_trend_narrative_locale, ck_brand_trend_narrative_text

### TrendNarrativeRun (`trend_narrative_runs`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | BigAutoField | False |  |
| source_cycle_id | CharField | False |  |
| window_days | PositiveSmallIntegerField | False |  |
| facts_as_of | DateTimeField | False |  |
| packet_schema_version | PositiveSmallIntegerField | False |  |
| snapshot | JSONField | False |  |
| brand_manifest | JSONField | False |  |
| batch_manifest | JSONField | False |  |
| internal_order | JSONField | False |  |
| status | CharField | False |  |
| suspension_reason | CharField | False |  |
| activated_at | DateTimeField | True |  |
| created_at | DateTimeField | False |  |
| updated_at | DateTimeField | False |  |

Constraints: uq_tnr_source_window, ck_tnr_window, ck_tnr_status, ck_tnr_activation_shape, ck_tnr_suspension_reason

### TrendNarrativeProviderCall (`trend_narrative_provider_calls`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| id | BigAutoField | False |  |
| run | ForeignKey | False | TrendNarrativeRun |
| stage | CharField | False |  |
| batch_key | CharField | False |  |
| request_identity | CharField | False |  |
| request_hash | CharField | False |  |
| response_hash | CharField | False |  |
| request_packet | JSONField | True |  |
| response_payload | JSONField | True |  |
| state | CharField | False |  |
| claim_owner | CharField | False |  |
| claim_fence | PositiveIntegerField | False |  |
| claimed_at | DateTimeField | True |  |
| claim_expires_at | DateTimeField | True |  |
| reserved_at | DateTimeField | False |  |
| sent_at | DateTimeField | True |  |
| completed_at | DateTimeField | True |  |
| error_code | CharField | False |  |
| input_tokens | PositiveIntegerField | False |  |
| output_tokens | PositiveIntegerField | False |  |
| latency_ms | PositiveIntegerField | True |  |
| created_at | DateTimeField | False |  |
| updated_at | DateTimeField | False |  |

Constraints: uq_tnpc_run_stage_batch, uq_tnpc_request_identity, ck_tnpc_stage, ck_tnpc_state, ck_tnpc_claim_shape, ck_tnpc_sent_shape, ck_tnpc_completed_shape

### TrendNarrativeVisibleRun (`trend_narrative_visible_runs`)

| Field | Type | Null | Relation |
| --- | --- | --- | --- |
| window_days | PositiveSmallIntegerField | False |  |
| run | ForeignKey | False | TrendNarrativeRun |
| facts_as_of | DateTimeField | False |  |
| activated_at | DateTimeField | False |  |
| updated_at | DateTimeField | False |  |

Constraints: ck_tnvr_window

## Consumers and deletion paths

Reference inventory covers model imports in readers/views, editorial orchestration, pictures/bindings/media, editorial/headline operator commands and trend lifecycle/tasks/projection. All run-only queries must filter window/workflow before non-window runs coexist.

`prune_per_brand_trend_narrative_history` currently cascades old superseded runs. Protect imported authored content/calls and either explicitly remove eligible unpinned trend children in the retention service or hold the run; never cascade editorial history. Cited post deletion must fail.

Serving boundaries: pinned edition UUID; story UUID; locale fallback; signed cutoff+UUID cursor; exact source/generated asset access; picture mode and affiliation checks. No HTTP path may enqueue generation.

## Baseline evidence

Existing persistence, views, HTTP, picture, lifecycle and projection net: 108 passed / 106 required PostgreSQL, zero skips/errors. New frozen multilingual/version citation characterization: 1 passed / 1 required PostgreSQL. Run logs are retained privately under `.local/g2-original-content-20261008/`. No provider or collection calls occurred.

## Retirement gate

Unmapped source/call/balance/unpublished records, incomplete compatibility consumers, insufficient seven-day observation or unproved encrypted restore block destructive cleanup. Temporary reports are artifacts, never additional application tables.

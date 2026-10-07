# Official company account discovery evidence

Base: `01dbc492f469496128feec0af0acf3a49f919307`; observations dated 2026-10-06.

## Settled positive examples

The owner verified these accounts as official. They are acceptance examples, not pending nominations. The source assessment's earlier nomination wording is superseded by that owner direction.

| Account | Stable author ID | Stored evidence |
| --- | --- | --- |
| reflection_ai | 1800594921704898560 | Nested bio: “Make intelligence open and accessible to all”; expanded profile URL https://reflection.ai; post 2107186852306550900 fetched 2026-10-05; Business label present but verified/blue booleans false. |
| Aleph__Alpha | 1073704329528438785 | Nested bio describes specialized large language models for sovereign Europe; expanded URL https://www.aleph-alpha.com; post 2104956884738347160 fetched 2026-09-29; no Business/blue label. |
| Badtheorylabs | 2048427879273218048 | Nested bio about efficient intelligence; https://badtheorylabs.com in six later observations; eight authored posts including product support and Tinfield availability; no Business label. |

All ten stored post rows had empty `author_description`. Relevant evidence resides in `author_profile_bio.description` and `author_profile_bio.entities.url.urls[].expanded_url`. A provider `author_type=user` value does not establish that the account represents a person. Blue verification is not proof of company ownership. Earlier address-like bio strings for Bad Theory are dated observations, not a reason to override the owner's determination.

A compact public-source fixture is in the adjacent JSON file. It excludes irrelevant personal/location/avatar fields. It preserves full selected post text and profile JSON, source IDs, and observation timestamps. The export is an observation, not a complete timeline.

## Provider access observations

Owner-requested parent probes at 2026-10-06T10:01:04–05Z changed no membership:

| Route | Result | Meaning |
| --- | --- | --- |
| Official X OAuth2, GET /2/users/me | 401 Unauthorized | Existing token was rejected. |
| Official X OAuth1, GET /2/users/me | 403 client-not-enrolled | Response requires the developer app to be attached to a Project with appropriate API access. |
| TwitterAPI.io ON_DEMAND key, POST /twitter/list/add_member | 400 auth_session is required | Request intentionally omitted auth_session/proxy. Endpoint validation only; authenticated membership access was not tested. |

The earlier TwitterAPI.io probe found no usable owner login session/proxy. Existing API-key search access still does not establish private-list write access through that route.

### Successful official X owner access and bounded write

The owner saved console-generated OAuth2 credentials in the operator's local secret store under `PUSHINWEIGHT_X_LIST_ACCESS_TOKEN` and `PUSHINWEIGHT_X_LIST_REFRESH_TOKEN`. This planning update read only the redacted receipts, never the secret store or token values.

| Observed at (UTC, 2026-10-06) | Request | Verified result |
| --- | --- | --- |
| 11:28:22.344216 | GET `/2/users/me` | HTTP 200; `allenwlee`, stable owner ID `17456158` |
| 11:28:22.619460 | GET list `2067062923525275922` | HTTP 200; private true, owner `17456158`, member_count 82 |
| 11:28:22.961860 | Complete list member read | HTTP 200; 82 members, no next token, Reflection absent |
| 11:28:44.684910 | Authorized POST `/2/lists/2067062923525275922/members`, user ID `1800594921704898560` | HTTP 200; `data.is_member: true` |
| 11:28:44.976943 | Independent complete member readback | HTTP 200; 83 members, no next token, Reflection present |

This proves local owner-authorized private-list read/write access and the single Reflection addition. It does not establish that Aleph Alpha or Bad Theory Labs were added. No automatic collector, configuration, or database registration changed.

The parent supplied receipts named `new-token-identity.json`, `new-token-list.json`, `new-token-list-members.json`, `reflection-membership-add.json`, and `reflection-membership-readback.json` from its probe directory. Their non-secret verification fields are preserved in the adjacent evidence JSON; the private membership roster is not copied.

An app-console screenshot showed top-gun app `33020022` attached to PayPerUse, while the owner reported the same tokens. Successful API responses do not prove the issuing app, and the cause of the earlier OAuth1 403 is not established. Do not present the later success as proof of a specific app repair.

The local owner-auth blocker is resolved. Deployment-time secret provisioning, matching refresh/client configuration, token rotation persistence, and verification through the future runtime adapter remain implementation/activation work. The local secret store is not proof that a Render service has those credentials.

Official references checked on 2026-10-06:

- [X add member](https://docs.x.com/x-api/lists/add-list-member): POST `/2/lists/{id}/members`, stable `user_id`, user authorization including `list.write`; successful response exposes `data.is_member`.
- [TwitterAPI.io OpenAPI](https://docs.twitterapi.io/api-reference/openapi.json): older list-add route requires `auth_session`, proxy, list ID, and user ID or user name. Do not substitute a v2 `login_cookie` without a documented compatible list route.

## Repository trace and implications

- `core/profile_snapshots.py`: persisted profile snapshots retain raw nested bio and distinguish observed/missing fields. Extend normalization here rather than inventing another profile reader.
- `core/targeted_extraction.py`: profile affiliation is post/role state, triggered through positive classification or ambiguous profile movement. Share its provider-call adapter, not its person persister or post-event gate.
- `core/models.py`: Account identity is stable author ID; `Account.apply_observation` rejects mismatched identities. BrandAccount and CompanyAccount already carry official-role edges. BrandDiscoveryCandidate handles unresolved organization candidates, but its current name/handle hash is not an account identity key.
- `monitor/list_membership.py`: TwitterListMembership records observations; TwitterListSyncState records complete read reconciliation. Neither is an outbound write queue. Incomplete or empty snapshots must not deactivate existing membership.
- `core/product_verification.py`: new publisher approval has a deliberately narrow Business/Hugging Face source gate. General company discovery must not inherit or loosen that gate.
- `BrandCompany.ownership_pct` defaults to 1.0. Creating that edge from a bio would invent ownership. This plan creates independently supported official account edges; it creates ownership edges only from existing settled mappings.
- `monitor/cycle.py`: targeted extraction receives a call budget inside post-fetch. New role accounting must span the whole cycle, including retries and manual replay, rather than reset per post or helper invocation.
- `docs/solutions/integration-issues/harvest-pipeline-missing-call-queries.md`: pin config through the production caller; a green cron is not evidence that optional work ran. Its historical settings bridge is not current configuration authority.
- `docs/solutions/architecture-patterns/backfiller-and-llm-classifier-pipeline-wiring.md`: scheduled and manual entry points must call one domain service. Historical scheduler details are superseded by the current single Render cron.

## Planning flow analysis

The scan can discover an account without a positive post classification; decisions can finish without list credentials; registration can commit before a network timeout; a retry can finish after another worker replaced its claim. The plan therefore gives scanning, evidence decisions, registration, and remote synchronization their own durable checkpoints and fences.

Resolution defaults: uncertain identity waits for review; known negative decisions are revisited only after material evidence/policy change; account-handle changes do not create another company; remote timeouts trigger membership verification before another add; an operator suppression prevents accidental re-add. These are proposed operational defaults, not additional owner approvals.

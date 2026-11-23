# TwitterAPI.io Get List Members

Primary vendor reference: <https://docs.twitterapi.io/api-reference/endpoint/get_list_members>

## Contract used by PushinWeight

- Method/path: `GET /twitter/list/members`.
- Required query parameter: `list_id`.
- Optional query parameter: `cursor` from the preceding response.
- Page size is fixed by the vendor at 20. Do not send `page_size`; it is not a documented parameter.
- Successful responses contain `members`, `has_next_page`, `next_cursor`, and `status: success`.

PushinWeight treats provider error status, malformed continuation, a missing or
duplicate stable member id, page/deadline truncation, and an empty first page
as incomplete snapshots. Incomplete snapshots must never deactivate existing
membership or advance the last-complete reconciliation state.

## Production evidence (2026-09-02)

The first scheduled reconciliation accidentally sent undocumented
`page_size=20`. TwitterAPI returned an empty terminal page, which the old
client accepted as a complete empty roster and used to deactivate 49 known
members. The exact 49 rows were reactivated. The client now sends only the
documented parameters, counts `members` in its safe request telemetry, and
rejects empty snapshots fail-closed.

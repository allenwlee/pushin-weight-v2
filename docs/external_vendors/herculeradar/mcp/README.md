# HerculeRadar MCP surface

Verified on 2026-09-07 against the public production endpoint. This index
separates observed transport behavior from claims present only in first-party
documentation. No authenticated project data or mutating tool was requested.

## Transport and discovery URLs

| URL | Purpose | Evidence |
|---|---|---|
| `https://herculeradar.com/api/mcp` | Streamable HTTP JSON-RPC 2.0 endpoint | Live `GET`, `OPTIONS`, and non-mutating `POST` probes |
| `https://herculeradar.com/mcp` | Public server manifest alias | Live JSON; byte-identical to `GET /api/mcp` at capture time |
| `https://herculeradar.com/.well-known/oauth-protected-resource/mcp` | RFC 9728 protected-resource metadata | Live JSON |
| `https://herculeradar.com/.well-known/oauth-authorization-server` | OAuth 2.1 authorization-server metadata | Live JSON |
| `https://herculeradar.com/oauth/authorize` | Authorization endpoint | Published OAuth metadata; not invoked |
| `https://herculeradar.com/oauth/token` | Token endpoint | Published OAuth metadata; not invoked |
| `https://herculeradar.com/oauth/register` | Dynamic client-registration endpoint | Published OAuth metadata; not invoked |
| `https://herculeradar.com/docs/mcp` | Human MCP guide | Archived page |
| `https://herculeradar.com/docs/authentication` | API-key and OAuth guide | Archived page |
| `https://herculeradar.com/llms.txt` | Concise agent-readable contract | Archived text |
| `https://herculeradar.com/llms-full.txt` | Complete agent-readable REST/MCP contract | Archived text |
| `https://herculeradar.com/openapi.json` | OpenAPI 3.1 REST schema backing the same capabilities | Archived JSON |

`OPTIONS /api/mcp` advertised `GET, HEAD, OPTIONS, POST`. `initialize`
negotiated protocol version `2025-06-18` and declared tools, resources, and
prompts, with no list-change notifications or resource subscriptions. The
documented JSON-RPC methods are `initialize`, `ping`, `tools/list`,
`tools/call`, `resources/list`, `resources/read`, `prompts/list`, and
`prompts/get`.

## Authentication

The endpoint accepts a project-scoped `hr_live_…` bearer key or an OAuth access
token. Public discovery calls succeeded without a credential. A non-mutating
`tools/call` for `list_projects` returned HTTP 200 with an in-band MCP result
whose `isError` was `true` and whose structured error code was `UNAUTHORIZED`.
The ephemeral request ID is redacted in the archived example.

OAuth metadata advertises authorization-code plus refresh-token grants, PKCE
`S256`, public clients (`token_endpoint_auth_methods_supported: ["none"]`),
and these scopes:

- `mentions:read`
- `mentions:write`
- `monitors:write`
- `alerts:write`

The live tool catalog additionally names API-key scopes such as
`projects:read`, `projects:write`, `monitors:read`, `alerts:read`, and
`usage:read`; those additional names are not advertised by the OAuth discovery
documents in this snapshot.

## Tools

All schemas are preserved in `live/tools-list.json`. Each tool points to its
archived first-party reference page under `../official/pages/docs/reference/`.

| Tool | Scope | Read only | Destructive | Idempotent |
|---|---|---:|---:|---:|
| `list_projects` | `projects:read` | yes | no | yes |
| `create_project` | `projects:write` | no | no | no |
| `list_monitors` | `monitors:read` | yes | no | yes |
| `create_monitor` | `monitors:write` | no | no | no |
| `update_monitor` | `monitors:write` | no | no | yes |
| `delete_monitor` | `monitors:write` | no | yes | yes |
| `list_mentions` | `mentions:read` | yes | no | yes |
| `get_mention` | `mentions:read` | yes | no | yes |
| `update_mention_status` | `mentions:write` | no | no | yes |
| `get_mention_analytics` | `mentions:read` | yes | no | yes |
| `list_alerts` | `alerts:read` | yes | no | yes |
| `create_alert` | `alerts:write` | no | no | no |
| `delete_alert` | `alerts:write` | no | yes | yes |
| `get_usage` | `usage:read` | yes | no | yes |

## Resources

| URI | MIME type | Snapshot |
|---|---|---|
| `herculeradar://capabilities` | `application/json` | `live/resources/capabilities.json` |
| `herculeradar://glossary` | `text/markdown` | `live/resources/glossary.json` |

Both `resources/list` and `resources/read` were publicly readable during the
capture. The response envelopes are kept intact so URI, MIME type, and content
can be replayed exactly.

## Prompts

| Prompt | Arguments | Snapshot |
|---|---|---|
| `triage_inbox` | optional `window` | `live/prompts/triage-inbox.json` |
| `weekly_digest` | optional `window` | `live/prompts/weekly-digest.json` |
| `set_up_monitoring` | required `brand`; optional `website` | `live/prompts/set-up-monitoring.json` |
| `find_leads` | optional `window` | `live/prompts/find-leads.json` |

All four definitions were returned by `prompts/list`, and all four were
successfully materialized with schema-valid arguments through `prompts/get`.
Calling `set_up_monitoring` without its required `brand` produced an empty HTTP
500 response; the archived successful snapshot uses inert example values and
does not create or modify anything.

## Snapshot files

- `live/initialize.json` — negotiated version, server info, capabilities, and
  server instructions.
- `live/ping.json` — successful protocol ping.
- `live/tools-list.json` — complete 14-tool catalog and input schemas.
- `live/resources-list.json` and `live/resources/` — catalog and both resource
  reads.
- `live/prompts-list.json` and `live/prompts/` — catalog and all four resolved
  prompt messages.
- `live/unauthenticated-tool-call.json` — sanitized authentication failure
  shape for a read-only tool.
- `../official/machine/mcp-manifest.json` — public server manifest.
- `../official/machine/oauth-*.json` — OAuth discovery metadata.
- `../official/machine/openapi.json` — 15 REST operations across ten paths.
  Fourteen operation IDs match the live MCP tool names; REST-only
  `get_project` is the exception.

## Documented/live discrepancies

- The REST reference and OpenAPI schema include `get_project`, but both the
  human MCP guide and the live `/mcp` plus `tools/list` catalogs omit it.
  Accordingly, this archive treats `get_project` as REST-only at capture time.
- OAuth discovery advertises four scopes, while the live tools expose five
  additional API-key scope names; see Authentication above.
- `prompts/get` returned an empty HTTP 500 for `set_up_monitoring` when its
  required `brand` argument was omitted, then returned HTTP 200 when called
  with schema-valid inert arguments.

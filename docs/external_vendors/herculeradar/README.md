# HerculeRadar public-site archive

Snapshot of HerculeRadar's publicly accessible website and developer surface,
captured on 2026-09-07. The archive follows the same first-party-reference
purpose as `docs/external_vendors/brand24`, with extra machine-readable
coverage for HerculeRadar's MCP server.

## Coverage

| Surface | Captured | Notes |
|---|---:|---|
| Sitemap HTML pages | 43 / 43 | Every canonical URL in `sitemap.xml` |
| Public discovery/spec files | 8 | robots, sitemap, LLM context, OpenAPI, MCP manifest, OAuth metadata |
| Live MCP protocol snapshots | 12 | Initialization, catalogs, resources, prompts, ping, and auth behavior |
| Canonical aliases checked | 3 | HTTP, `www`, and `herculradar.com` redirect to the canonical HTTPS origin |

The HTML corpus includes all public marketing, pricing, use-case, listening,
legal, guide, and API-reference pages in the sitemap. It intentionally excludes
the login wall and every robots-disallowed path: `/app/`, `/onboarding`,
`/api/`, `/auth/`, and `/login`. The documented `/api/mcp` endpoint was probed
only through non-mutating MCP discovery methods; no account, credential,
project data, or write-capable tool was used.

## Layout

- `official/pages/` — Firecrawl Markdown for all 43 sitemap pages, preserving
  the rendered navigation, main content, links, and footer.
- `official/robots.txt` and `official/sitemap.xml` — first-party crawl policy
  and canonical URL inventory.
- `official/llms.txt` and `official/llms-full.txt` — first-party product and
  developer context files.
- `official/machine/` — OpenAPI 3.1, the MCP manifest, and both OAuth discovery
  documents.
- `mcp/` — live protocol snapshots and a complete MCP surface index.
- `metadata/` — Firecrawl map output, capture manifest, coverage, aliases,
  exclusions, and discovery provenance.

## Discovery and capture

The URL set was reconciled from:

1. Firecrawl CLI `map` with sitemap and subdomain discovery.
2. Firecrawl CLI `download`, followed by rate-safe `scrape` completion batches.
3. The site's `robots.txt` and `sitemap.xml`.
4. Direct HTTP checks of `llms.txt`, `llms-full.txt`, `openapi.json`, `/mcp`,
   OAuth well-known metadata, redirects, and the documented MCP transport.
5. Shipped Next.js links and endpoint strings.
6. Context7, Firecrawl Search, and web search for a separate HerculeRadar MCP
   package or documentation corpus; none was found.

Firecrawl CLI v1.11.2 was authenticated through its environment-based API key.
The experimental bulk downloader mapped 46 candidates and saved its first ten
requests before the account's 10-requests/minute limit rejected the remaining
fan-out. Only the failed URLs were retried in bounded, paced scrape batches.
Firecrawl's server-side crawl operation returned `Bad Request` before creating
a job in both full-site and docs-scoped forms; this limitation is recorded in
`metadata/discovery.json` and does not create a coverage gap because map,
sitemap, direct HTTP, and per-page capture sets reconcile exactly.

## Reproduction outline

```sh
firecrawl --status
firecrawl map "https://herculeradar.com" --wait --limit 1000 \
  --include-subdomains --ignore-query-parameters --json
firecrawl download "https://herculeradar.com" --limit 1000 \
  --allow-subdomains --exclude-paths "/app,/onboarding,/api,/auth,/login" \
  --format "markdown,links,images" --yes
firecrawl scrape "<missing-public-url>" --format "markdown,links,images"
```

The raw `.firecrawl/` working cache is not committed. Files in this archive are
the reviewed, scope-limited deliverables requested for long-term reference.
Each archived file's URL, provenance, content type, and SHA-256 are recorded in
`metadata/capture-manifest.json`.

## Snapshot limits

- This is a point-in-time capture, not a claim that the vendor will preserve
  these routes or schemas.
- Authenticated dashboard content and project data are out of scope.
- Images remain referenced by their source URLs; third-party binaries and
  analytics payloads are not vendored.
- Search engines and Context7 had no separate authoritative MCP corpus, so the
  first-party site and live public MCP metadata are the source of truth here.

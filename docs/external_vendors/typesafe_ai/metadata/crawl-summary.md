# TypeSafe documentation capture

**Captured:** 2026-09-24 UTC  
**Source:** <https://docs.typesafe.ai/>  
**Crawler:** Firecrawl CLI 1.11.2  
**Crawl job:** `01a0d1e2-525c-73c1-96ae-d6045c03a17f`  
**Status:** completed

## Coverage

| Measure | Result |
| --- | ---: |
| Pages in upstream `llms.txt` | 111 |
| Pages in upstream `sitemap.xml` | 111 |
| Difference between those page sets | 0 |
| Indexed pages covered by Firecrawl | 111 |
| Original Markdown pages downloaded | 111 |
| Failed original Markdown downloads | 0 |
| Original Markdown content bytes | 1,166,301 |
| Firecrawl URL/resource records | 229 |
| Firecrawl records with HTTP 200 | 228 |
| Firecrawl records with HTTP 404 | 1 |
| Firecrawl reported credits used | 229 |
| Configured crawl page limit | 250 |
| Outstanding Firecrawl pagination | None |

Original Markdown downloads completed between
`2026-09-24T05:30:11.260Z` and `2026-09-24T05:30:33.347Z`.

The crawl visited both normal page URLs and their `.md` representations.
Those are two representations of the same 111 indexed pages, not 222 separate
documentation pages. Additional records cover the root URL, machine-readable
indexes, crawler metadata, the documentation MCP endpoint, and the 404 below.
The crawl finished below its configured page limit.

## Capture command

```bash
firecrawl crawl 'https://docs.typesafe.ai/' \
  --sitemap include \
  --ignore-query-parameters \
  --max-concurrency 2 \
  --limit 250 \
  --wait --progress --timeout 600 --pretty \
  -o .firecrawl/2026-09-24-typesafe-docs-full-crawl.json
```

The raw Firecrawl response is retained in the ignored local `.firecrawl/`
cache. The [manifest](crawl-manifest.json) records the crawl's URL inventory,
statuses, counts, and the downloaded files' hashes.

## Saved source material

- Page files: original response bytes from the 111 `.md` URLs in
  [the vendor index](llms.txt), without rewriting.
- [llms.txt](llms.txt): original vendor documentation index.
- [sitemap.xml](sitemap.xml): original vendor sitemap.
- [llms-full.txt](llms-full.txt): original combined documentation export.
- [robots.txt](robots.txt): original crawler directives.
- [mcp.md](mcp.md): Firecrawl's Markdown representation of the documentation
  MCP endpoint; this is an extraction, not original HTTP response bytes.

The [local page index](../typesafe_index.md) covers every indexed Markdown
page. The [manifest](crawl-manifest.json) contains source URLs, download times,
HTTP statuses, byte counts, and SHA-256 hashes. All saved source and discovery
artifact hashes were checked against the capture receipts.

## Observed upstream exceptions

| URL | Observation |
| --- | --- |
| `https://docs.typesafe.ai/migrating-to-v1` | Firecrawl returned HTTP 404. This path is absent from both current indexes; no error page is included as a documentation page. |
| `https://docs.typesafe.ai/mcp` | Firecrawl returned HTTP 200 with a server-discovery description. A direct GET returned HTTP 405. The saved file is explicitly the Firecrawl extraction. |

The root URL is an entry point to the Introduction, which is stored at
[introduction.md](../introduction.md).

## Scope

This is a documentation-text snapshot. Links and Markdown/MDX components in
source pages retain their upstream form. Linked media, external sites,
repositories, installed SDKs, and running services are outside the capture.
In particular, the [Legal page](../legal.md) links to documents on
`typesafe.ai`; those external pages are not part of the 111-page documentation
index.

The capture includes the vendor's own examples and technical guidance.
Locally authored project recommendations and subjective assessments have been
removed from this reference directory.

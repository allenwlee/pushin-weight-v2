# TypeSafe AI / Jev documentation

Local reference copy of the TypeSafe documentation for developers and agents
looking up Jev's model specifications, HTTP API, question types, SDKs, and
examples. The [documentation index](typesafe_index.md) links to every captured
page.

**Source:** <https://docs.typesafe.ai/>  
**Captured:** 2026-09-24 UTC  
**Coverage:** 111 of 111 pages listed by both the vendor's documentation index
and sitemap.

## Published model specifications

These values are published in the captured [Models page](models.md).

| Field | Published value |
| --- | --- |
| Versioned model | `jev-1.13.0` |
| Aliases | `jev-latest` and `jev-preview`, both resolving to `jev-1.13.0` |
| Input | Text: string, JSON object, or array of text values |
| Media input | No image, audio, or video input |
| Input price | $0.042 per million tokens |
| Output price | Free |
| Context | 64k tokens for state plus all questions; 32k for state plus the longest question |
| Published rate limits | 250,000 tokens/second; 1,200 requests/minute; documented as dynamically adjustable |

The [HTTP API reference](api.md) documents
`POST https://api.typesafe.ai/v1/systemone` with bearer-token authentication.
The [model reference](models.md) also documents `GET /v1/models`.
The three question types are [Choice](primitives/choice.md),
[Score](primitives/score.md), and [Noul](primitives/noul.md).

## Reference contents

| Reference | Contents |
| --- | --- |
| [Complete page index](typesafe_index.md) | Local file and upstream URL for all 111 documentation pages |
| [Model specifications](models.md) | Model identifiers, aliases, pricing, input formats, limits, language support, and data handling |
| [HTTP API](api.md) | Authentication, requests, answers, usage, errors, and rate-limit responses |
| [Model limitations](model-jaggedness/jev-1.13.md) | Vendor-documented behavior and limitations |
| [Python SDK](sdk/python.md) | Client documentation, API reference, and changelog |
| [JavaScript SDK](sdk/javascript.md) | Client documentation, types, API reference, and changelog |
| [Patterns](patterns.md) and [cookbooks](cookbooks.md) | Vendor-authored examples and technical guidance |
| [Legal](legal.md) | Vendor data-handling statements and links to legal documents |
| [Combined upstream documentation](metadata/llms-full.txt) | The vendor's original single-file documentation export |
| [Capture record](metadata/crawl-summary.md) | Crawl scope, counts, source formats, and observed exceptions |
| [Machine-readable manifest](metadata/crawl-manifest.json) | Source URLs, capture timestamps, HTTP statuses, byte counts, and SHA-256 hashes |

## Source format

The page files are byte-for-byte downloads of the vendor's original `.md`
URLs, arranged by upstream path. The full Firecrawl crawl provides the
discovery and coverage record. Source text, code examples, Markdown/MDX
components, and links are retained without paraphrasing or local additions.

Vendor-authored instructions and examples remain source material. This
directory contains no project-specific adoption recommendations, evaluation
proposals, or opinions about Jev. The README, index, and capture records contain
reference and provenance information only.

Root-relative links inside source pages retain their upstream meaning;
the local index provides filesystem links. External sites, linked images,
repositories, SDK packages, and executable examples are not copied or run.
The scope is the documentation host, not the separate TypeSafe marketing site.

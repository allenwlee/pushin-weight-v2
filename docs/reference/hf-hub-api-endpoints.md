# HuggingFace Hub API — Endpoint Reference

Consolidated from the top-gun HF crawler source (`hf_direct_discover_scraper.py`,
`build_hf_discover_queue.py`) and the HF Hub docs via context7
(`/huggingface/hub-docs`, `/huggingface/huggingface_hub`).

**Provenance tags:** `[crawler]` = used in production by the top-gun crawler ·
`[hub-docs]` = documented in HF Hub docs (fetched this session) ·
`[standard]` = standard Hub REST endpoint, well-established — **verify the exact path before relying on it**.

---

## Base URLs & Auth

| Thing | Value |
|---|---|
| Hub REST base | `https://huggingface.co/api` |
| Router (OpenAI-compat) base | `https://router.huggingface.co` |
| Auth header | `Authorization: Bearer $HF_TOKEN` (optional for public repos; required for gated/private + higher rate limits) |
| Token check | `GET /api/whoami-v2` `[standard]` — returns the authenticated user/org; use as a token sanity check |

---

## 1. List models / datasets / spaces by author  ← **crawler core (R3)**

| Method | Endpoint | Notes | Source |
|---|---|---|---|
| GET | `/api/models?author={org}&full=true&limit=100&sort=lastModified&direction=-1&cursor={c}` | **List all models owned by an org.** `full=true` returns complete metadata (siblings, tags, cardData, downloads, likes, …). | `[crawler]` |
| GET | `/api/datasets?author={org}&full=true&…` | Same shape, datasets. (Out of scope for v1 — models only.) | `[crawler]` |
| GET | `/api/spaces?author={org}&full=true&…` | Same shape, spaces. (Out of scope for v1.) | `[crawler]` |

**Pagination** `[crawler]`: responses carry a `Link: <…?cursor=XYZ>; rel="next"` header.
Parse `cursor=` from the `rel="next"` segment and pass it as `cursor=` on the next request.
Stop when there is no `rel="next"` or a page returns fewer than `limit` items.

**Sort values:** `lastModified` · `createdAt` · `downloads` · `likes` · `trendingScore` (etc.).
**Direction:** `-1` = descending, `1` = ascending.

---

## 2. Single-repo detail (ModelInfo / DatasetInfo / SpaceInfo)  ← **R4**

| Method | Endpoint | Notes | Source |
|---|---|---|---|
| GET | `/api/models/{repo_id}` | Full model detail. The authoritative field source for `products` columns. | `[crawler]` |
| GET | `/api/datasets/{repo_id}` | Dataset detail. | `[hub-docs]` |
| GET | `/api/spaces/{repo_id}` | Space detail. | `[standard]` |
| GET | `/api/models/{repo_id}?expand=…` | Field selection. Canonical expand set: `author, cardData, gated, private, downloads, downloadsAllTime, likes, lastModified, sha, siblings, tags, trendingScore, pipelineTag, config, spaces`. | `[hub-docs]` |
| GET | `/api/{models\|datasets}/{repo_id}?blobs=true` | Adds file **sizes** into `siblings`. | `[hub-docs]` |
| GET | `/api/models/{repo_id}/revision/{rev}` | Detail at a specific revision. | `[standard]` |
| GET | `/api/models/{repo_id}/revisions` | List revisions. | `[standard]` |

`repo_id` = `{org}/{name}`, e.g. `deepseek-ai/DeepSeek-V3`.

---

## 3. Files / tree / metadata

| Method | Endpoint | Purpose | Source |
|---|---|---|---|
| GET | `/api/models/{repo_id}/tree/{rev}` | List files at a revision. | `[standard]` |
| GET | `/api/models/{repo_id}/tree/{rev}/{subpath}` | Subtree listing. | `[standard]` |
| GET | `/api/models/{repo_id}/paths-info` | File path metadata. | `[standard]` |
| GET | `/api/models/{repo_id}/safetensors-metadata` | Tensor names/shapes from safetensors. | `[standard]` |
| GET | `/api/models/{repo_id}/languages` | README locale info. | `[standard]` |
| GET | `/{repo_id}/resolve/{rev}/{filename}` | **File download** (302 → CDN). Not needed for the catalog. | `[standard]` |

---

## 4. Search (global / semantic)

| Method | Endpoint | Body / Params | Source |
|---|---|---|---|
| POST | `/models` | `{query, author, task}` → Model Search API. | `[hub-docs]` |
| POST | `/datasets` | `{query, author, tags[]}` → Dataset Search API. | `[hub-docs]` |
| POST | `/api/spaces/search` | `{query, limit}` → semantic Space search. | `[hub-docs]` |
| GET | `/api/models?search={q}` | GET search variant. | `[standard]` |
| GET | `/api/organizations?search={q}` | **Org search — used for discovery (R2).** | `[standard]` |

---

## 5. Batch repo details  ← **useful for bulk enrichment**

| Method | Endpoint | Notes | Source |
|---|---|---|---|
| POST | `/repos/details` | `{repo_ids: ["org/name", …], repo_type?}` — up to **10** repos per call, auto-detects type. Returns id/type/author/sha/pipelineTag/tags/private/gated/disabled/createdAt/updatedAt/downloads/likes/library_name/cardData. | `[hub-docs]` |

---

## 6. Accounts: organizations & users  ← **R2 (org resolution / author profile)**

| Method | Endpoint | Returns | Source |
|---|---|---|---|
| GET | `/api/organizations/{org}` | Org profile: fullname, avatarUrl, numMembers. | `[standard]` |
| GET | `/api/organizations?search={q}` | Org search candidates. | `[standard]` |
| GET | `/api/users/{user}` | User profile. | `[standard]` |
| GET | `/api/users/{user}/overview` | fullname, avatarUrl, numFollowers. | `[crawler]` |
| GET | `/api/users/{user}/socials` | `{twitter, github, linkedin, bluesky}`. | `[crawler]` |
| GET | `/api/users/{user}/followers` | Follower list. | `[standard]` |
| GET | `/api/users/{user}/following` | Following list. | `[standard]` |

---

## 7. Collections  *(optional, not in v1)*

| Method | Endpoint | Notes | Source |
|---|---|---|---|
| GET | `/api/collections?owner={org}&sort=lastModified` | List an org's collections. | `[standard]` |
| GET | `/api/collections/{collection_id}` | Collection detail. | `[standard]` |

---

## 8. OpenAI-compatible router (inference — **not** for cataloging)

| Method | Endpoint | Notes | Source |
|---|---|---|---|
| GET | `https://router.huggingface.co/v1/models` | Chat-completion models served by inference providers, w/ pricing + provider metadata. | `[hub-docs]` |
| GET | `https://router.huggingface.co/v1/models/{model_id}` | Single model via router. | `[hub-docs]` |
| GET | `/api/models?inference_provider={p}&pipeline_tag={t}` | List models served by a provider (returns just `id`s). | `[hub-docs]` |

---

## Field reference — ModelInfo → `products` columns

Map the HF model object onto the `products` table (wide scalars + JSON + verbatim payload).

**Scalar → typed column:**
`id` (repo_id) · `author` · `sha` · `private` · `gated` (auto/manual/false) · `disabled` ·
`downloads` (30-day) · `downloadsAllTime` · `downloadsPerDay` (velocity) · `likes` ·
`trendingScore` · `pipeline_tag` · `library_name` · `paperswithcode_id` ·
`createdAt` · `lastModified`.

**Nested/list → JSON column:**
`tags[]` · `siblings[]` ({rfilename, size?}) · `cardData` (license, language, base_model,
metrics, paper, pretty_name, datasets, …) · `config` ({architectures, model_type}) ·
`spaces[]` (dependent spaces).

**Full payload → `raw_json`** (never lose a field; add columns later via migration + backfill from here).

`cardData` sub-fields (from `/repos/details` response) `[hub-docs]`:
`tags, datasets, library_name, license, paper, private, gated, pipeline_tag, auto_model,
base_model, task, model_name, pretty_name`, plus `model_card_data.language/task/library_name`.

---

## What the products crawler actually uses (v1)

- **Resolve org:** `/api/organizations?search=` `[standard]` (discovery) + `brand_hf_orgs` seed.
- **Sanity gate:** `/api/models?author={org}&limit=1` `[crawler]` (assert ≥1 model + author match).
- **Enumerate:** `/api/models?author={org}&full=true` + Link-cursor pagination `[crawler]`.
- **Enrich (if needed):** `/api/models/{repo_id}` `[crawler]`, or batch via `POST /repos/details` `[hub-docs]`.

## Notes

- **Rate limits:** anonymous requests are throttled; `HF_TOKEN` raises limits. The crawler ports top-gun's retry/backoff (`404→skip`, `403→retry-then-bail`, transient `5xx`→retry).
- **`full=true` vs detail call:** `full=true` on the list already returns most ModelInfo fields; a separate `GET /api/models/{id}` may only be needed for fields absent from the list response — confirm with one probe at implementation time.
- **Don't trust unverified paths blind.** Endpoints tagged `[standard]` are real Hub REST routes but were not quoted verbatim from docs this session — spot-check with a curl before coding against them.

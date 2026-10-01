---
title: G1 Phyllo Xiaohongshu — setup distinction and access probe
checked_at: "2026-09-30T19:06:50+09:00"
session: g1-chinese-faces-20260930
status: authentication-confirmed-rednote-search-access-unconfirmed
---

# Phyllo Xiaohongshu access assessment

The user-creation and SDK-token steps in the owner's screenshots belong to
Phyllo Connect, which lets an account owner authorize access to their own
social account. They are not prerequisites for the documented public-content
API. Public endpoints authenticate directly with a client ID and secret.
No Connect user, SDK token, or account connection was created by this test.

The [public API reference](https://docs.insightiq.ai/docs/api-reference/api/ref)
and its exported OpenAPI specification distinguish these capabilities:

| Capability | Documented endpoint | Xiaohongshu / RedNote evidence |
| --- | --- | --- |
| Look up a known creator profile | `POST /v1/social/creators/profiles/analytics` | RedNote explicitly listed; requires `identifier` and `work_platform_id` |
| Fetch posts from a known profile or one known post | `POST /v1/social/creators/contents/fetch` | RedNote explicitly listed; requires `profile_url` or `content_url`, plus `work_platform_id` |
| Search posts by keyword | `POST /v1/social/creators/contents/search` | Listed platforms are TikTok, Instagram, YouTube, Reddit and X; RedNote is absent |
| Search creator profiles | `POST /v1/social/creators/profiles/search` | Generic search endpoint exists, but its specification does not establish RedNote support |

Sources: [profile analytics](https://docs.insightiq.ai/docs/api-reference/api/ref/operations/create-a-v-1-social-creator-profile-analytics),
[public content lookup](https://docs.insightiq.ai/docs/api-reference/api/ref/operations/create-a-v-1-social-creator-content-fetch),
[keyword content search](https://docs.insightiq.ai/docs/api-reference/api/ref/operations/create-a-v-1-social-creator-content-search).

Phyllo's [RedNote marketing page](https://www.getphyllo.com/rednote-api) describes
creator search, keywords, topics, media URLs and note lookup. Its search claims
are not sufficient to establish a callable, enabled keyword-post-search API
for this account. The documentation confirms lookup support, not live retrieval
or unrestricted searching for pictures of a person across other authors' posts.

## Actual credential probe

The private secret file contains nonempty `PHYLLO_CLIENT_ID` and
`PHYLLO_API_KEY`. The latter was used as the client secret for one read-only
request, following the screenshots' staging environment and the current
[authentication documentation](https://docs.insightiq.ai/docs/api-reference/API/getting-started-with-APIs):

```text
GET https://api.staging.insightiq.ai/v1/work-platforms?limit=100
Authorization: Basic <runtime encoding of client ID and secret>
```

That request returned HTTP **401**, with `invalid_credentials`. Provider
request ID: `5df06f5c-cbed-4f79-8a6f-45cb42e91cab`. An initial question about
credential environment was superseded by diagnosing a host mismatch: the
owner's screenshot uses `api.staging.getphyllo.com`, while current documentation
uses `api.staging.insightiq.ai`. DNS showed different API gateways. Two
unauthenticated diagnostic requests returned the expected authentication error.

One corrective read-only request to the **exact Phyllo staging host from the
screenshot**, with the same credentials and path, returned HTTP **200** in
0.673 seconds. Provider request ID:
`9ab1c14a-cb13-4812-8ced-94ba2f6129e2`. The supplied client ID and saved secret
are therefore valid on Phyllo staging. The owner was told to disregard the
earlier credential-environment question. Do not ask for replacement credentials
or repeat the failed InsightIQ-host request as a prerequisite.

The successful platform catalogue returned **17 entries and no RedNote or
Xiaohongshu entry**. This leaves no discovered RedNote `work_platform_id` for
a documented request. The missing entry alone does not prove that Phyllo cannot
provide RedNote through another product or account arrangement. No content
request, media retrieval, SDK-token creation, or environment cycling followed.
No credit deduction was measured for these access checks.

Current API guidance says staging uses real data with a ten-credit test limit;
production has separate credentials and billable operations. A legacy sandbox
URL still appears in one rendered endpoint example, while the current exported
specification lists staging and production. Preserve these distinctions rather
than treating every example environment as interchangeable.

## Next bounded action

Authentication is confirmed. Obtain the supported RedNote platform identifier,
endpoint and product access for Phyllo staging. A concrete provider question is:

> Can this staging account access RedNote/Xiaohongshu public data? Please provide
> its `work_platform_id` and a working request. Does keyword-based post search
> support RedNote, or is access limited to known profile/post-URL lookup?

This question is prepared for the owner; no support message was sent. Run the
three name-based searches only if a supported RedNote search route is
established. A supplied public profile/post URL could instead exercise lookup,
with that narrower capability explicitly recorded. Do not guess platform UUIDs
or create Connect users to repair a missing public-data route.

No Phyllo photo/video retrieval is confirmed yet. SearchApi/SerpApi comparison
results remain in the [separate measured report](2026-09-30-185025-g1-searchapi-serpapi-comparison.md).

## Local evidence

`.context/g1-phyllo-xiaohongshu-test-20260930/` holds the redacted access receipt,
public-endpoint extracts and browser documentation-discovery evidence. The two
owner-supplied screenshots were copied read-only from allenwlee into a private,
ignored subdirectory on fuchitalee. They contain an authorization-header example
and are not published or embedded in reports. No remote artifact was created.

`.firecrawl/g1-phyllo-*` contains the marketing/documentation snapshots, public
Stoplight table of contents and exported API specification. The specification
was retrieved from the export URL exposed by the actual official documentation
page; no guessed authenticated API endpoint was called.

No production database, scheduler, application code, deployment, purchase,
outbound support message, commit, or push was changed.

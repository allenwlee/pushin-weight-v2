---
title: G1 Parse.bot Xiaohongshu endpoint assessment
checked_at: "2026-09-30T19:20:19+09:00"
session: g1-chinese-faces-20260930
status: documentation-checked-no-content-test
---

# Parse.bot Xiaohongshu endpoint assessment

The supplied API can retrieve media URLs for an already identified post, but
does not provide the name/keyword search needed to discover staff photographs.
Its public endpoint definitions confirm the marketplace page's limitation.
This is a documentation and catalogue assessment; no Xiaohongshu content was
retrieved through Parse.bot and no photograph or video was accepted.

## Available endpoints

The [marketplace listing](https://parse.bot/marketplace/7a9a996e-e338-411a-b15e-4a79eda1ce3d/xiaohongshu-com-api)
and [live public endpoint definitions](https://api.parse.bot/marketplace/apis/7a9a996e-e338-411a-b15e-4a79eda1ce3d)
list exactly three GET endpoints:

| Endpoint | Required input | Documented output | G1 use and limitation |
| --- | --- | --- | --- |
| `get_note_detail` | `note_id` and its paired `xsec_token` | Post text, author, timestamps, tags, image URLs/dimensions and video URL/duration/dimensions when present | Possible retrieval route for manually discovered posts; cannot search for a person |
| `get_user_profile` | `user_id` | Public profile, biography, avatar and account statistics | Identity leads; does not list the person's posts |
| `list_feed` | None | Varying explore-feed summaries with post IDs and security tokens | No keyword, topic filter or pagination input; cannot target the staff roster |

The note security token is specific to that post. Documentation says it can
come from the feed or that post's share link. A bare post ID is insufficient.
Resolving an app share link and retrieving working media URLs remains untested.

The canonical scraper ID is `112e2db4-437f-4511-96f5-f0f62d23a010`; calls use
`https://api.parse.bot/scraper/{canonical_scraper_id}/{endpoint_name}` with a
Parse API key in `X-API-Key`. The listing advertises two credits per successful
detail/profile call and one per feed call. No Parse key was read or requested.
The public catalogue requires no key, as documented in the
[marketplace guide](https://docs.parse.bot/marketplace).

A bounded public catalogue search for `xiaohongshu` returned three listings:
this one and two unrelated sites. It disclosed no second Xiaohongshu API;
this is not an exhaustive search of every possible marketplace alias.

## Reliability evidence and extension option

Parse describes this as an independent managed wrapper, not an official
Xiaohongshu API. The catalogue reports all three endpoints healthy, last
verified at `2026-09-30T01:03:52.976656+00:00`. That is provider-reported evidence.
Its published note-detail checks assert success, note ID, author ID and a like
count; they do not assert valid image/video URLs or successful media downloads.
The health badge therefore does not prove that it yields usable staff photos.

The [revision API](https://docs.parse.bot/api-reference/dispatch/revise-a-completed-api)
accepts a natural-language request to extend an existing API. Publicly
contributed revisions are documented as free; private revisions are charged.
A submitted revision is queued work, not proof that Xiaohongshu keyword search
can be built or maintained. No subscription, fork, revision, support message or
account change was performed.

The missing capability could be requested as: add a paginated keyword-note
search returning post IDs, their matching security tokens, source URLs and
captions, then demonstrate detail/media retrieval for the three G1 sample names.
Listing a known creator's posts would be another useful capability, but would
not find photographs posted by other accounts on its own. These are proposals,
not currently available endpoints or an authorized build.

## Implication and evidence

Consider Parse.bot for a bounded test using app-discovered share links if the
owner selects that route. It does not currently meet automated initial-batch
or new-staff discovery requirements. Phyllo remains pending the vendor's reply;
OpenCLI and Yuanbao remain deferred. SerpApi remains the preferred Baidu route.

Five successful Firecrawl scrapes covered the supplied listing, docs introduction,
marketplace guide, docs index and revision reference. Two unauthenticated GETs
read the documented public catalogue detail and search. Saved evidence is in
`.firecrawl/g1-parsebot-*20260930.*`. There were zero Parse content-execution
calls, zero media downloads, and no gallery or production changes.

The [G1 plan](../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md)
retains both required acquisition paths and the latest provider decisions.

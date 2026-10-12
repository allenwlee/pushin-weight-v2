# General page, published stories and individual Posts

Last checked: 2026-10-12 14:41:38 JST. Scope: the General/Pulse framework implementation and its current Django reader paths. Delivery evidence belongs to the selected plan and execution tracker.

General presents published Chatter, a prediction-led Pulse framework and saved announcements about events, opportunities, jobs and personnel changes. A story headline opens its saved published edition; a lower-feed card opens an individual Post page with its complete saved commentary, original source and linked facts. Reading these pages does not generate commentary, run extraction or fetch new posts.

## Local review data

The [local General preview](http://100.102.74.50:58418/general/?lang=en&weights=open&audience=human) uses a dedicated G5 database restored from a production snapshot created October 9, 2026 at 06:37 JST. It contains 306,938 Posts, with latest saved fetch at 06:33:50 JST, and 19 approved English editions: two Chatter and 17 Pulse. The shared readers select the editions displayed on the page. It does not refresh automatically from production. The earlier static design prototype remains on port 58417.

At the checked time, each of the four Open-weight lower panels initially displays 20 real Posts. Closed weights is temporarily unavailable and opens the notice described below. Cards without saved commentary use the labeled source/literal-translation fallback described below. Missing source dates remain unknown. English, Chinese and Japanese browser checks match the displayed publications to the shared reader, including full bodies, source counts and every source URL. Chinese and Japanese currently disclose English fallback for these publications. The [implementation tracker](../../todos/2026-10-08-150837-g5-general-page-local-implementation.md) records the snapshot and browser evidence. Original source text remains accessible under the current implementation; no source-hiding policy has been applied.

## Routes and permanent identity

| Route | What it opens |
| --- | --- |
| `/general/` | Published Chatter/Pulse and four connected lower Post feeds. |
| `/general/feed/?section=calendar` | A read-only JSON response used to refresh or continue a panel. Other section values are `free`, `jobs` and `moving`. This is a browser endpoint; it is not G4's MCP interface. |
| `/stories/<story-uuid>/?track=chatter&lang=en&edition=<edition-uuid>` | G2’s saved published edition, with its complete body and citations. Pulse uses `track=pulse`. |
| `/posts/<post-id>/` | One stored source Post, identified by its existing `Post.tweet_id`. It remains resolvable after its classification or feed position changes. |

The Post URL identifies the source announcement. A Post that mentions three jobs has one Post page containing all three linked job facts. It does not gain a different identity for every panel in which it appears. The route uses the existing anonymous public-Post access policy; feed membership and recency do not grant or remove access.

`?lang=en`, `?lang=zh-cn` and `?lang=ja` select the language. Chinese aliases `zh`, `zh_cn`, `zh_hans` and `zh-hans` are accepted, as is `ja-jp`. An unsupported language returns HTTP 400.

An unpinned Post URL displays the current saved commentary. `?commentary=<artifact-id>` selects a particular successful saved commentary artifact belonging to that Post. Card links and the detail page's Copy link action pin the displayed saved artifact when one exists. An unknown, failed, withdrawn, rejected or different Post's artifact returns HTTP 404; it does not silently substitute another revision. Without normalized saved commentary, a page can use explicitly labeled legacy commentary or the original source.

For example, `/posts/123/?lang=ja&commentary=456` identifies Post 123 and saved commentary 456 in Japanese when that translation exists. These numbers are illustrative. Requested-language fallback is disclosed beside commentary. Pinning commentary does not freeze the original Post record or its linked facts.

The detail HTML includes its canonical URL, Open Graph title/description/URL, complete saved text, source links, available stored source media and a list of up to 20 successful saved commentary revisions. It works without JavaScript. Copying is a progressive enhancement; the permanent link remains available if clipboard access fails.

Published OriginalContent cards use G2’s existing `/stories/<story-uuid>/` routes and pin the exact displayed language/version with `edition`; their publication and edition rules remain owned by the shared reader. The shared editorial runs have no trend window, so the existing window-scoped history cleanup leaves their approved texts and citations intact. A real cleanup-to-story-route regression verifies an old saved Pulse edition and every citation. This does not freeze or publish an unfinished forecast, and it does not register a `/content/` adapter.

## Pulse framework

Pulse separates observed history from future projections and provides dedicated areas for a forecast, its subsequent outcome report and learning from resolved predictions. The forecast, chart, auditor and learning outputs are currently unavailable. The page states that explicitly; it displays no sample curve, predicted value, probability, resolved outcome or learning record.

`monitor/general_views.py::editorial_panels` adds the Pulse availability projection without calling an engine. `general/_pulse_framework.html` renders its localized status and empty chart areas inside the existing panel scroll region. On mobile those areas stack vertically; internal scrolling exposes the complete framework without changing the outer Human/Agent geometry.

Published reports opens with a native disclosure and works without JavaScript. Opening it preserves the complete saved report body and every citation. Language navigation starts a fresh page with that disclosure closed; audience changes retain its DOM state. The report archive and saved-edition links retain their existing access rules.

The public `/general/` response exposes `X-Bridgewright-Revision` when the runtime supplies a valid full deployed SHA, using the existing revision middleware. Pro links to General with the current language; `/` remains Pro.

## Chatter and Pulse

`monitor/general_views.py::editorial_panels` calls the existing
`monitor.editorial.views.access` rule and `monitor.editorial.readers.feed_payload`.
With `ORIGINAL_CONTENT_STORAGE=shared`, these reads resolve approved
OriginalContent texts and their saved relational citations. Anonymous readers
receive them only when `EDITORIAL_PUBLIC_ENABLED=true`; authenticated staff
retain G2's existing access. Otherwise the top panels display an unavailable
message, without hiding the independently public lower feeds.

Chatter uses G2's featured edition and up to five earlier distinct stories under
“Previous Chatter stories.” Without a featured pointer, it uses the first saved
edition returned by that reader. Pulse keeps the six most recent saved editions under its keyboard-accessible “Published reports” disclosure. These are reports rather than forecasts.
Each panel links to G2's archive for older publications. Neither panel generates
new copy, changes a selection pointer or marks content published.

Each displayed edition includes its exact headline, byline and complete saved
body. The Sources disclosure shows the distinct cited-Post count and **every**
source URL in saved order, including safe non-X links. The count describes posts,
not independent publishers or confirmations. Raw source evidence and private
workflow metadata are not rendered. Headline links pin the displayed edition;
source links open the original source. The body and citations scroll inside the
existing fixed panel; opening a source list or Chatter history does not resize it.

The language selection is passed unchanged to the shared reader after General's
normal alias normalization. G2's English fallback is explicitly labeled. Chatter
and Pulse are global editorial selections; the weights and brand selection apply
to the four lower Post feeds. The top panels refresh on a page load or language
navigation, while the lower feeds retain their independent refresh controls.
G4's agent presentation remains explicitly unavailable pending its own contract.

## The four feeds

Every feed selects current successful Stage 1 classifications under taxonomy v3 or v4. Legacy v2 combined event/opportunity classifications do not become exact event or opportunity cards. A Post appears once per feed, with current matching brands linked as hashtag pills.

| Panel | Exact Post category | Linked facts and ordering |
| --- | --- | --- |
| Calendar | `events` | Direct and evidence-linked Events. Happening now first, then future start time, then unknown or postponed schedules. Posts whose linked events are all past or cancelled are omitted. |
| Free stuff | `opportunities` | Directly linked Opportunities. Open offers first, then future opening time, then unknown dates. Closed and cancelled offers are omitted when no active or unknown fact remains. |
| Jobs | `job_listings` | Source-Post-linked JobListingEvidence, excluding official-site listings. Newest Post fetch first. One card can lead to multiple roles. |
| Who's moving | `personnel_changes` | Source-Post-linked affiliation evidence. Newest Post fetch first. Rejected evidence/claims and superseded claims are excluded; an unconfirmed claim is labeled. |

Cards use saved normalized Post commentary, with legacy commentary and saved literal/source text as explicit fallbacks. They never interpret raw classification rationale as display copy. People are joined through stored person identity and source evidence, not a name match or profile refresh. Initials are the current portrait fallback. Birth dates, sex, confidence, review notes and processing metadata are not part of these public projections.

Calendar and Free stuff preserve source date precision. A day or month without a precise time never becomes a fabricated countdown. Exact upcoming times show remaining time; exact live endings show remaining duration. A live item without a known end says so. Live and recently fetched Jobs receive red emphasis; future-event emphasis is non-red and accelerates as the event approaches. Reduced-motion preferences disable blinking.

Job age is elapsed time since `Post.fetched_at`, not the source's publication date. The just-listed message and red emphasis apply strictly below 24 hours. Closed job facts remain truthful on the detail page even when their source announcement is recent.

## Continuation and refresh

Responses contain `section`, `locale`, `as_of`, `items`, `next_cursor` and escaped server-rendered card `html`. Each item carries its stable Post `id` and `url`, saved source/commentary, brands, allowlisted facts and display timing. The default page size is 20; `limit` accepts 1–50.

A signed continuation cursor binds the section, locale, selected brands, sort position and initial server time. It expires after 24 hours. Its fixed time keeps lifecycle ordering and the fetch cutoff consistent while paging. Changing filters requires a fresh traversal. Invalid input or an invalid cursor returns HTTP 400.

Jobs and personnel use database pagination with a stable Post-ID tie break. Calendar and opportunities order the eligible schedule facts before selecting a page; they do not discard an old announcement merely because its event is far in the future. That complete temporal scan needs representative-data performance measurement before release.

The browser keeps existing cards after a failed refresh and exposes Retry. It cancels obsolete requests and also checks a request generation number, so a late response cannot replace the selected weights. More appends cards without duplicating Post IDs. Timers stop on page exit and resume after restoration from the browser's page cache.

## Navigation and preferences

Desktop navigation switches between a narrow icon rail and an expanded menu; the desktop choice persists. On narrow screens it becomes an overlay with focus containment, Escape/backdrop dismissal and focus return. It links to General sections, Pro and the existing account login/logout routes. Logout is a CSRF-protected POST. Login returns to the same-origin General path.

Header and sidebar share weights, language, timezone and audience state. Explicit URL selections take precedence over saved preferences. Locale and timezone use the existing account-scoped browser preference namespace; General's weights, audience and navigation use its `:general` suffix. General's independent weight choice does not overwrite Pro's exclusive brand lens. Anonymous and signed-in users do not share the same preference key. Storage failure does not disable controls.

Open and Closed are independent pressed/unpressed controls. Open can be turned off. Closed is temporarily unavailable: selecting it shows the owner-selected “Open Weights Coming Soon!” message, localized for Chinese and Japanese, while preserving Open's state and existing cards. The modal sits beside its invoking header/sidebar toggle, below when space permits and above otherwise, within the viewport edges. Resizing repositions it; if the sidebar trigger becomes hidden, it follows the visible header equivalent. Dismissing with OK or Escape clears Closed and restores focus; it does not fetch, replace cards, change the URL, or save Closed as an enabled preference. Both controls display as pressed while the notice is open if Open was already selected. The same behavior applies in Agent mode. Without JavaScript, the links retain the current selection and show a centered notice.

`weights=open` selects the available Open inventory; `weights=none` selects no brands and produces empty lower Post panels. Legacy `weights=closed` or `weights=both` values resolve to Open while Closed remains unavailable; the General page displays the notice once and normalizes its URL. A saved legacy Closed preference likewise returns to Open with the notice, without changing Pro's saved lens.

Human and Agent use the same six outer panel elements and grid geometry. Agent changes the internal colors/font/content; G4 capability is explicitly unavailable in this slice. The page assistant remains unavailable; Chatter/Pulse now display shared publications in the Human view. General's Reading links can open Pro; `/` continues to serve Pro.

## Sources and verification

- [General readers](../../monitor/general_readers.py), [views](../../monitor/general_views.py) and [routes](../../monitor/urls.py).
- [Post reader](../../monitor/content_readers.py), [view](../../monitor/content_views.py) and [detail template](../../monitor/templates/monitor/content/detail.html).
- [General template](../../monitor/templates/monitor/general.html), [browser behavior](../../monitor/static/monitor/general.js) and [styles](../../monitor/static/monitor/general.css).
- [Published-content tests](../../tests/test_general_editorial.py), [reader tests](../../tests/test_general_readers.py), [timing tests](../../tests/test_general_timing.py), [job/person tests](../../tests/test_general_jobs_people.py), [route tests](../../tests/test_general_views.py), [detail tests](../../tests/test_content_detail.py) and [real-browser checks](../../tests/test_general_browser.py).
- [General assurance declaration](../../tests/fixtures/ui_assurance/general-declaration.json) binds the deterministic fixture to a hash of the relevant uncommitted implementation and its dependencies. This local source hash is not a release commit SHA.
- [Implementation tracker](../../todos/2026-10-08-150837-g5-general-page-local-implementation.md) holds current verification results and remaining integration work.

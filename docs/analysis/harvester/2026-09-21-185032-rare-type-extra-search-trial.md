# Rare-type extra-search TwitterAPI trial

Date: 2026-09-21 JST

Plan: `docs/plans/2026-09-21-081940-feat-combined-rare-type-extra-search-plan.md`

Command: `python manage.py trial_rare_type_extra_search`

Credential: `TWITTERAPI_IO_ON_DEMAND_API_KEY` from Render env group `pushinweight-secrets` (never logged).

## Query length

The final harvest-shaped planner string is 419 characters. Rendered with
`since_time` and `until_time`, it is 463 / 512. The earlier, invalid query
shape was 466 characters.

## Initial live calls (1 page each; invalid query shape)

| Window | n_returned | Already in local DB | Credit estimate | Notes |
|---|---:|---|---:|---|
| 15m | 20 (full page) | unknown (`posts` missing on this host) | 300 | Tweets span ~06:00–09:52 UTC, not 15 minutes |
| 7d | 20 (full page) | unknown locally | 300 | Same latest-page shape; more “step 5” junk |

`since_time` / `until_time` were present on the rendered query. Latest still filled a 20-tweet page with posts older than 15 minutes. Treat the time window as unverified for this OR-heavy string.

## Keepers vs junk (15m page)

Keeper:

- `@SinTokens1` — StepFun launches **Step-5 Preview** (open weights, 27B active, 1M context). This is the dormant-lab release the extra search was meant to catch.

Junk filling the page:

- `@TheForexExpo` booth lists (many rows) — matches `booth`
- English football “Step 5 teams” — matches `step-5`
- Horticulture / journalism / “More Women in Tech” fellowships — matches `apply by` + `fellowship`
- InvoiceQ / n8n booth posts — `we'll be at` + `booth`
- Food/bitcoin hackathons — `hackathon`

Personnel and job-listing clauses returned **zero** hits on this page. The booth / step-5 / fellowship clauses spent the 20 slots.

7d added a second Step-5 Preview post (`@teicalo_nishi`, Japanese) and more “Step 5:” tutorial junk.

The first-trial IDs were checked separately against staging by one-off job
`job-daofvt2d0e5s7384f8ig`: 0 of 20 existed among staging's 241,924 posts.
The trial command was not deployed and inserted no posts.

## Harvest-shaped 15-minute re-run

The planner string is now `((group) OR (group) …) min_faves:0`, then
`run_search(..., since_time=, until_time=)` like
`CycleRunner._fetch_tweets`.

The 15-minute window returned **4 tweets** at an estimated 60 credits. Their
timestamps sit inside ~09:52–10:00 UTC, matching the requested envelope.
The provider reported `truncated=true`, so the one-page safety cap remained
active even though the returned page contained only four rows. Unquoted
`booth` and bare `step-5` were removed from the planner string.

| Tweet | Historical token-relevance assessment | R17 reference label | Reason |
|---|---|---|---|
| `2101974766110269572` (`@Temperatur2com`) | Keep — model-name discovery | **Negative** | Price-only board; it is not source evidence of a release. |
| `2101973880000667923` (`@NanoGPTcom`) | Keep — model release/availability | **Positive: model release** | Announces named-model availability and identifies StepFun as the publisher. |
| `2101972712901992561` (`@CapyToolkit`) | Junk | **Negative** | Pricing/credit complaint; no release or availability announcement. |
| `2101972709282361784` (`@SinTokens1`) | Keep — model release | **Positive: model release** | Attributed report that StepFun launched a named model and made it available. |

The original result was **3 token-relevance keepers / 1 junk**. It was not a
Jev result and did not use the later canonical gate. Against the frozen R17
reference labels, the same four rows are **2 positives / 2 negatives**.
Personnel, jobs, events, and opportunities had zero hits in this small window.

The recorded 60-credit figure was estimated from the four normalized rows.
The raw paid result volume for this historical request was not captured and is
therefore unknown; 60 must not be presented as confirmed usage. The command's
local overlap query failed because its configured database had no `posts`
relation. A later read-only production lookup, observed 2026-09-21 23:40 UTC,
found 2 of these 4 IDs (`@CapyToolkit` and `@SinTokens1`). That is a current
lookup, not proof of overlap at the historical query time.

The separately reported **0 of 20 against 241,924 posts** belongs to the
earlier unwrapped-query cohort, not these corrected four rows. It cannot be
used as this sample's novelty denominator.

The corrected query passes this historical trial's syntax and observed
time-envelope checks. The four normalized rows alone do not prove quality,
novel yield, raw-paid efficiency, or the absence of mill/recruiter saturation.
This trial does **not** authorize a call in `run_cycle`; R17's enablement
decision remains separate. The corrected query was not re-run over seven days
as part of this historical trial.

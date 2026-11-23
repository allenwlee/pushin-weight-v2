# TwitterAPI.io search disruption: provider updates

Recorded 2026-11-23 10:53 JST from Allen's screenshots of the TwitterAPI.io official Telegram channel. These are provider statements, not independent verification. Telegram message clock times are displayed on the screenshots; the screenshots do not establish the timezone of those display clocks. The provider's explicit UTC incident times below are converted to JST.

## Timeline

- **Nov 21, about 12:50 JST:** The provider said an issue affecting Twitter globally began around 03:50 UTC and temporarily made its search endpoint unavailable. At that point it said only search was affected; other endpoints were operating normally. This is the time the incident began, not the time of the message.
- **Nov 22, about 12:20 JST:** The provider said the large majority of advanced-search requests began succeeding from 03:20 UTC, but that brief failure waves could persist, especially just after the hour. An earlier update also said some requests might fail or run slowly. Neither update claimed full recovery.
- **Nov 23, screenshot marked Today:** The provider said further changes at Twitter/X were affecting endpoints and recovery was incomplete. A later update, shown as edited 5:38 AM on the screenshot, said roughly 85% or more of search requests were succeeding, with some 503s and elevated latency remaining. The screenshot's message-clock timezone is unverified, so do not treat 5:38 as a confirmed JST timestamp.
- At the later update, the provider said list tweets (`/twitter/list/tweets`) remained affected; profile lookup (`/twitter/user/info`) worked normally; tweet lookup worked with somewhat higher latency; and account tracking with `/twitter/user/last_tweets` using `userId` was unaffected. These are provider-reported states at that update, not current health checks.

## Provider guidance

- Retry failed requests with progressive delays, for example **5, 15, 30, then 60 seconds**. Earlier updates suggested a short retry after a few seconds.
- For jobs starting exactly at `:00` or `:30`, add a small random delay to reduce congestion. Assess this against our 15-minute schedule, deadline and overlap handling before changing production.
- For tracking specific accounts, the provider suggests `/twitter/user/last_tweets` with `userId`, obtained once via `/twitter/user/info`. This is a potential fallback for account tracking; it does not replace keyword search.
- The provider says HTTP 503 requests are not billed. It also said its price of $0.15 per 1,000 tweets was unchanged at the time of the update. Neither statement is independently verified here.

These are recommendations to assess, not a record that our current code implements them or that production was changed. Check existing retry, circuit-breaker, timeout, scheduler and account-collection behavior before making changes. A delay or retry must respect the harvest deadline and existing cursor safeguards.

## Evidence

The project owner supplied three screenshots of the November 21–23 updates, retained on allenwlee. [TwitterAPI.io’s official Telegram channel](https://t.me/twitterapiio)

The Nov 23 same-hours post-volume comparison may be affected by the search disruption and by collection timing. It cannot independently distinguish collection loss from changes in posting volume.

# X Probe: Event Announcement Language for AI Model Brands (vs Product Releases)

**Date:** 2026-07-08 (renamed from 2026-07-03 to match actual JST system date per project file naming rules) 
**Focus:** Detecting "event announcements" (live/online events, conferences, summits, meetups, booths, keynotes, livestreams) posted by official accounts of AI companies (OpenAI, MiniMax, Mistral, Anthropic, DeepSeek, xAI/Grok, etc.) as distinct from product/model release announcements.  
**Key hypothesis (from user):** Events have a definite start/end date or bounded temporal window, unlike releases.

All data gathered exclusively via X API tools (x_keyword_search with `from:`, advanced operators, date ranges, min_faves; x_semantic_search; x_thread_fetch; x_user_search). No web pages, company sites, or external archives used.

## Accounts Probed
- Primary official handles: `@OpenAI`, `@MiniMax_AI`, `@MistralAI`, `@AnthropicAI`, `@deepseek_ai`
- Attempts on xAI/Grok: `from:xai`, `from:grok`, `"xAI" (event|summit|DevDay|booth|we'll be at)` yielded mostly unrelated or low-signal results in the sampled window. xAI appears less active (or less explicit) with this style of posting in recent data.
- Additional signals surfaced via mentions and employee/official-tagged posts (e.g. OpenAI researchers at ICML booths).

## Representative Event Announcement Examples (X Post Text Only)

**OpenAI DevDay (strong canonical example):**
- "OpenAI DevDay 2026 applications are now open! Our biggest developer event gets even bigger. 📍 San Francisco 📅 September 29 Apply by July 10"
- Follow-up: "You can also tune in from home. The opening keynote will be livestreamed on September 29."
- Related: "OpenAI DevDay is back. San Francisco September 29"
- "Want to secure an early ticket to OpenAI DevDay? ... free tickets to OpenAI DevDay 2026"

**MiniMax (very active on participation + multi-event schedules):**
- "we’ll be at Lab #1 during @aiDotEngineer World’s Fair. hope to see you there!"
- "MiniMax is heading to RAISE Week in Paris 🇫🇷 Find us at Booth 32D in Delorme, in a fireside chat on the Ada Lovelace Stage, and at our private executive gathering: RAISE House with MiniMax."
- "we’ll be at AI Engineer After Dark on July 1st with @vercel , @merge_api... our Research Lead... will be giving a lightning talk... see you after dark at SFMOMA."
- "MiniMax is headed to Cupertino for AiOS Meetup — WWDC ’26 Edition on June 11. ... Speakers include... Every attendee gets $50 in credits... See you there. #WWDC26"
- Detailed schedule style: "@NVIDIAGTC week starts today. The MiniMax team will be around the Bay Area all week... • Mar 16-18 afternoons: GTC Booth #142 w/@gmi_cloud • Monday (Mar 16) 7pm MiniMax x @baseten AI Leader Dinner • ... MiniMax AI Founder Day in SF✨"

**Mistral (hosts its own flagship event):**
- "📢 Introducing the AI Now Summit, Mistral AI’s first-ever flagship event! 🎯 One day, one mission: Own your AI transformation. 📍 Paris | May 28 Join us to learn how AI is transforming leading organisations..."
- "Mistral’s AI Now Summit is coming to Paris on May 28 and tickets are live!"
- "Today at The AI Now Summit, held at the Louvre, we announced AI solutions..."

**Conference presence (ICML, World's Fair, etc., often from tagged employees/official accounts):**
- "I'm at ICML this week and I'll be doing Q&A today (Tuesday) from 3-4pm at the @OpenAI booth with my reasoning research colleagues. Come by and ask us a question!"
- "I’ll be at @icmlconf with @OpenAI! ... You can find me hosting a Q&A at our booth Wednesday morning at 9:30am!"
- "We’ll be presenting our ICML poster at 5pm on July 8th."
- "We're at Booth UG28 all week at AI Engineer World's Fair."
- "We're at the AI Summit in London this week... See you at the AI Summit!"

**Other patterns observed:**
- "The opening keynote will be livestreamed on [date]"
- "applications are now open" + branded event name + location/date
- "tickets are live" / "Get your pass now"
- "Find us at Booth XX" / "GTC Booth #142"
- "fireside chat", "lightning talk", "private executive gathering"
- "heading to [event] on [date]", "this week at [conf]"

## Common Words & Phrases (High-Signal for Events)

**Presence / invitation language (very strong):**
- we'll be at / we're at / I'm at ... this week
- come find us / if you are around
- see you there / see you at / hope to see you there
- join us
- find us at Booth

**Event formats / branded events:**
- DevDay, [Brand] Summit (e.g. AI Now Summit), World's Fair, GTC, ICML, RAISE Week, Founder Day, Meetup, After Dark
- booth, fireside chat, lightning talk, Q&A [at booth], poster [presentation], keynote, livestreamed [keynote]

**Calls-to-action specific to events:**
- applications are now open
- tickets are live / get your pass
- apply by [date]
- register here (contextual)

**Temporal + location anchors:**
- 📍 [city]   📅 [date]
- on [Month Day] / [Month] [Day]
- [Day]–[Day] (ranges, e.g. Mar 16-18)
- this week / all week / week starts today
- [time]pm / morning at [time] / afternoons
- livestreamed on [specific date]

**Other:**
- heading to / headed to
- part of ... lineup at
- in [city] for [event]

## Date / Bounded Temporal Signals (Primary Distinguisher per Hypothesis)
Events almost always include a concrete calendar reference that implies a start and end:
- Single-day: "September 29", "May 28", "on June 11", "July 1st", "Oct 6, 2025"
- Ranges: "Mar 16-18", "June 2–8, 2026"
- Relative but bounded: "this week", "all week"
- With time-of-day: "3-4pm", "Wednesday morning at 9:30am", "5pm on July 8th", "7pm"
- Livestream anchors: "livestreamed on September 29", "tune in from home"

Product releases rarely use future calendar dates in this way. They use "today", "now", "available today", "launched", "is here", "API updated & available today".

## Contrast with Product Release Language (from same probes)
Releases (DeepSeek dominant in samples, also seen from others):
- "🚀 DeepSeek-V4 Preview is officially live & open-sourced!"
- "Launching DeepSeek-V3.2 & DeepSeek-V3.2-Speciale — ... Now live on App, Web & API."
- "🚀 Introducing DeepSeek-V3.2-Exp"
- "🚀 DeepSeek-R1 is here! ... Website & API are live now!"
- "M3 is live on @telnyx Inference on day-0"
- "free GPU-accelerated M3 endpoint are live now go try it"

Characteristics:
- "live", "launching", "introducing", "is here", "now live", "open-sourced", "API is updated"
- Model version numbers, param counts, benchmarks, weights links, pricing cuts
- Immediate "try it now" CTA to product, not to an event registration
- No "booth", no future "on [date]" for a gathering, no "see you at [physical/virtual location on date]"

"live" is ambiguous in isolation (livestreamed event vs. model is live). Context + date pattern disambiguates.

## Observations
- OpenAI, Mistral, and especially MiniMax produce the clearest, highest-signal event posts. They use consistent formatting (emojis for location/date, bullet schedules, "see you"/"hope to see you").
- DeepSeek results were overwhelmingly product releases/launches; very few (or none in sampled latest) event-style posts.
- xAI searches returned mostly noise or unrelated accounts; official event posting may be lower-volume or use different phrasing.
- Many strong signals come from employees/researchers posting while representing the company ("I'm at ICML this week ... at the @OpenAI booth"). These are useful for detection even if not from the main corporate handle.
- Posts can be multi-event (MiniMax GTC week schedule is a great example).
- Hybrid online/offline: livestream options + in-person details are common for big events like DevDay.
- Length varies: some are short ("we’ll be at ... hope to see you there!"), others are long detailed agendas.

## Proposed Signals for a Detection Rule
A post is likely an **event announcement** (vs release) when it matches several of:

1. Strong presence verbs: "we'll be at", "we're at", "come find us", "see you at", "heading to", "find us at"
2. Event nouns + context: DevDay, [X] Summit, World's Fair, GTC, ICML (etc.), booth #, fireside chat, lightning talk, Q&A at [our] booth, poster at [time]
3. Definite temporal boundary (highest weight per hypothesis):
   - Explicit date or range: Month Day (or Day–Day), "on [date]", " [date]pm"
   - Bounded windows: "this week", "all week", "livestreamed on [date]"
   - Emoji anchors: 📅 + 📍 often co-occur
4. Attendance CTAs: "applications are now open", "tickets are live", "get your pass", "apply by", "if you're around"
5. Livestream / hybrid: "livestreamed", "tune in from home", "virtual" + event

**Negative / release signals (favor buzz_releases instead):**
- "is [now] live", "launching", "introducing", "is here", "open-sourced", "weights", "API [updated/available] today", benchmark numbers without event framing
- No calendar date or bounded "this week at [named event]"

**Implementation ideas (for later):**
- Expand keyword marker lists (beyond current release-oriented ones).
- Lightweight date regex / month+day detector run before or alongside LLM classification.
- Strengthen the `event_announcement` description + add real worked examples (DevDay, MiniMax booth/schedule, Mistral summit, ICML booth Q&A) in the pragmatics prompt.
- Consider allowing multi-label or explicit "event vs release" distinction in post_type or a dedicated flag.
- Employee "I'm at [conf] with @Brand" + booth/time language should score high.

This probe provides grounded, recent examples directly from X to calibrate any keyword, regex, or LLM prompt rules.

**Probe commands used (representative):**
- `from:OpenAI (DevDay OR summit OR ... OR "we'll be at" ...)`
- `from:MiniMax_AI ...`, `from:MistralAI ...`
- `"we'll be at" OR "we're at" OR "see you at" ... (OpenAI OR MiniMax OR Mistral ...)`
- GTC / ICML / "World's Fair" + booth/sponsor/presence terms + brands
- Semantic search for official event hosting/participation announcements
- Date-range and "this week" anchored variants

All quotes above are verbatim from returned X post content.
# Mobile Web vs. Native App Usage Patterns

Research collected 2026-07-24 to inform pushin-weight frontend architecture decision.

## General landscape (2025–2026)

- **90% of mobile time** is spent in native apps, not browsers (Mobiloud).
- **58% of global web traffic** comes from mobile browsers (Statista/Statcounter).
- **54% of mobile commerce transactions** happen in native apps (Criteo).
- PWAs have overtaken native apps in several industries where install friction matters (Progriso).

## Services where mobile web is dominant

The pattern: services used **infrequently** or **one-off** — users won't install an app for something they touch every few weeks.

| Service | Why mobile web wins |
|---------|---------------------|
| **X/Twitter Lite** | PWA for emerging markets — 1 MB vs 100 MB native app install. |
| **Uber** | PWA for riders with limited storage; full native for drivers who need GPS. |
| **Pinterest** | Mobile web is the top-of-funnel discovery engine; native is for saved collections. |
| **Spotify** | Free-tier web player; native only for downloads and offline playback. |
| **Starbucks** | Mobile web for gift cards and store locator; native only for payment and rewards. |
| **Booking.com** | Heavy mobile web bookings — travelers won't install an app per trip. |
| **Google Maps** | Web is the default for one-off directions; native for saved places and turn-by-turn navigation. |
| **Wikipedia** | Almost entirely mobile web — there is no reason to install an app. |
| **News/media** (NYT, BBC, etc.) | Mobile web dominates for article views; native for loyal subscribers. |

## Services where native app is dominant

The pattern: services used **daily or multiple times per day**, or services that need **hardware access**.

| Service | Native app share |
|---------|-----------------|
| **Airbnb** | 64% of Q4 2025 bookings via native app (up from ~60% YoY). Mobile web functions mainly as a top-of-funnel discovery channel (~5% conversion). |
| **Social media** (Instagram, TikTok, etc.) | Nearly 100% native; mobile web is a fallback. |
| **Messaging** (WhatsApp, Telegram, etc.) | Native-only or native-primary; web is a companion. |
| **Banking/fintech** | Overwhelmingly native for biometric auth and push notifications. |

## Decision rule

| Factor | Lean mobile web / PWA | Lean native app |
|--------|----------------------|-----------------|
| Session frequency | Weekly or less | Daily or multiple times/day |
| Session depth | Quick checks (<2 min) | Extended interaction |
| Hardware needs | None | Camera, GPS, biometrics, push |
| Install willingness | Low — one-off or occasional use | High — part of daily routine |
| Offline requirement | No | Yes |

## Relevance to pushin-weight dashboard

Key question: how often does a user open the dashboard?

- **2–3x/day checks** → leans toward an app-like experience (PWA or native).
- **Once a week review** → mobile web with responsive CSS is sufficient.
- **Quick-glance updates + occasional deep dives** → PWA with good offline caching bridges the gap without requiring a native build.

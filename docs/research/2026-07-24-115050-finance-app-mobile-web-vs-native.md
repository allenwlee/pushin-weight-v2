# Mobile Web vs. Native App in Financial / Stock Tracking Apps

Follow-up research to `2026-07-24-114642-mobile-web-vs-native-app-usage.md`.
Scoped specifically to apps where users track stock movement with line charts and graphs — the closest analogue to the pushin-weight dashboard.

## Key players and their platform strategy

### Robinhood — mobile-first, desktop added later

- 25.2M funded accounts, 14.4–15.9M MAU (Q1 2025).
- **Born mobile-first.** Desktop platform only launched in October 2024 — nine years after the app.
- The desktop launch was explicitly targeted at "active traders" who need multi-chart layouts, not casual investors.
- Implication: casual monitoring and quick trades → mobile. Deep analysis with multiple charts → desktop.
- Mobile app remains the dominant entry point; desktop is a power-user add-on, not a replacement.

### Yahoo Finance — web first, massive app install base

- 93M monthly unique visitors in the US; #1 finance site.
- Yahoo Finance app: 150M+ Google Play downloads.
- 38.44% of total Yahoo traffic is mobile (SEMrush, as of late 2025). But Yahoo Finance specifically skews higher on mobile app given its download numbers.
- Described as "completely free, requires no account to use the mobile version" — low-friction entry.
- Strategy: **web and app are peers.** Browser for research-heavy sessions, app for quick portfolio checks and push notifications.

### TradingView — web-first, app as companion

- Web platform is the core product: multi-chart layouts, Pine Script editor, screener.
- Mobile apps (iOS + Android) exist but are stripped-down companions for monitoring and alerts — not creation.
- Most trading platform reviews still compare it as a **web** platform, not an app.
- Implication: chart-heavy, configuration-heavy workflows stay on desktop web. The app is a notification-and-glance layer.

### Finviz — web-only

- Pure web-based stock screener. No native app.
- Simple charts (canvas-rendered). Power users use it alongside TradingView.
- Popular despite (or because of) being web-only. No install friction.

### Bloomberg Terminal — desktop-only

- The extreme case: $24K/year, dedicated hardware, no mobile app equivalent for the core workflow.
- Mobile Bloomberg exists but is a completely different product (news + portfolio watch).
- Proves that professional charting and data density lives on desktop.

## General fintech mobile engagement data

| Metric | Source |
|--------|--------|
| App users view **286% more products per session** than mobile web users | Criteo |
| "The app is the ultimate destination because of its unmatched native user engagement" | AppsFlyer, Jan 2026 |
| Mobile accounts for 51.29% of worldwide platform market share vs 48.71% desktop | Jan 2026 |
| 90% of mobile time is spent in apps, not browsers | Mobiloud |
| Native apps retain users **3x better** than mobile web | Multiple sources |

## Stock tracking user segmentation

| User type | Platform | Why |
|-----------|----------|-----|
| **Active trader** (multiple checks/day) | Native app | Push notifications, price alerts, biometric login, one-tap access |
| **Deep researcher** (hour+ sessions) | Desktop web | Multiple charts, screeners, keyboard shortcuts, large displays |
| **Casual tracker** (1–2x/week) | Mobile web or app | Either works — web if no install, app if notifications matter |
| **Portfolio monitor** (daily glance) | Native app | Widget on home screen, push on price moves, quick scroll |
| **Professional analyst** | Desktop (or terminal) | Data density, multi-monitor, export/API access |

## The chart question

Chart rendering is actually a **weak differentiator** in the web vs. app debate:

- **Chart.js / ECharts / Highcharts** render identically on mobile web and desktop web. Touch events (pinch-zoom, crosshair) work on both.
- **TradingView's charting library** is used by both web platforms and mobile apps via WebView — the same code runs everywhere.
- The meaningful difference is **session context**: a chart surrounded by 4 other charts + a screener + a news feed is a desktop workflow. A single chart with a price alert is a mobile workflow.

## PWA (Progressive Web App) — the third option

A PWA bridges mobile web and native app without requiring an App Store listing. It's a web app that behaves like a native app once "installed" (added to the home screen).

### What a PWA gives you

| Capability | Mobile web | PWA | Native app |
|------------|-----------|-----|------------|
| Add to home screen | No | Yes (install prompt) | Yes (App Store) |
| Offline / slow-network support | No | Yes (Service Worker cache) | Yes |
| Push notifications | No | **Yes (since iOS 16.4 / 2023)** | Yes |
| Full-screen, no browser chrome | No | Yes (standalone display mode) | Yes |
| App Store discoverability | No | No | Yes |
| Background sync | No | Yes (Background Sync API) | Yes |
| Access to Bluetooth, NFC, AR | No | Limited | Yes |
| Splash screen on launch | No | Yes | Yes |
| Storage quota | ~2 GB (differs by browser) | Same as browser | Device storage |

### PWA adoption in finance

- **Robinhood** launched a PWA alongside its native app to capture users who won't install.
- **TradingView** PWA allows chart layouts to be saved and works offline for cached data.
- **Starbucks** PWA (mentioned in general research) handles the full ordering flow — 99% feature parity with native, at a fraction of the build cost.
- **Uber** PWA serves riders without the native app — full ride-booking flow including real-time map.
- **X/Twitter Lite** PWA is 1 MB vs. 100 MB native app — targeted at emerging markets and limited-storage devices.

As of 2026, PWAs have overtaken native apps in several industries (Progriso), and iOS now supports push notifications from PWAs (since iOS 16.4, March 2023), removing the last major blocker for finance apps.

### PWA for pushin-weight

The PWA path makes particular sense for pushin-weight because:

1. **Low install friction.** Users won't install a native app for a dashboard they've never tried. A PWA install prompt ("add to home screen") is one tap and no App Store.
2. **Push notifications now work.** "New posts detected for your brand" can be a PWA push — no native app required.
3. **Zero framework cost.** The existing htmx + Chart.js stack works unchanged. A PWA is two static files: a `manifest.json` and a `service-worker.js`.
4. **Offline resilience.** Service Worker can cache the dashboard shell, last-known chart data, and feed — the app loads instantly even on spotty mobile connections.
5. **Iteration speed.** Update the PWA by pushing to Render. No App Store review, no forced updates, no version fragmentation.

### What a pushin-weight PWA looks like

```
pushin-weight-v2/
  static/
    manifest.json         # app name, icon, colors, display: standalone
    sw.js                 # service worker: cache shell + API responses
```

And one line in `<head>`:
```html
<link rel="manifest" href="{% static 'manifest.json' %}">
```

That's it. The existing Django + htmx + Chart.js stack runs as a PWA with two new static files. No new framework. No rewrite.

## Relevance to pushin-weight dashboard

| Factor | Pushin-weight |
|--------|---------------|
| Session frequency | Unknown — depends on user. Could be multiple times/day if monitoring for new posts. |
| Session depth | Feed scroll + chart glance. A few minutes at most. |
| Chart density | One chart + one feed. Much lighter than TradingView's multi-chart layout. |
| Hardware needs | None. No camera, GPS, or biometrics required. |
| Notification value | Potentially high — "new posts detected for your brand." PWA push notifications can cover this without a native app. |

### Recommendation

1. **Now:** responsive CSS + PWA manifest + basic Service Worker. Mobile-first layout, "add to home screen" install prompt, cached shell for fast loads. Two static files, zero framework.
2. **If push notifications become requested:** PWA push API (already available on iOS and Android). No native app needed.
3. **Only if PWA limits are hit** (e.g., users demand App Store presence, or need deep OS integration): React → React Native.

The chart library (Chart.js) is already mobile-compatible and touch-aware. The feed is already server-rendered HTML with htmx. The gap is CSS + two static files, not a framework.

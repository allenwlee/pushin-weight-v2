# Pushin' Weight (走个量) home pages

This document covers the two home pages that replaced the legacy
treemap / combined / 9-card grid / per-brand drill-down layout
(2026-07-06, plan `docs/plans/2026-07-06-003-feat-pushin-weight-home-pages-plan.md`).

## Page shapes

| Path                            | Renders                                       |
| ------------------------------- | --------------------------------------------- |
| `/`                             | Multi-brand home: line chart + control panel + feed |
| `/<company>/<brand>`            | Single-brand home: stacked-area chart + tabs + brand-scoped feed |
| `/_/<brand>`                    | Single-brand home for company-less brands     |

The topbar shows the product name `走个量` (Chinese) and
`Pushin' Weight` (English) on every page. A 4-button window toggle
(`1d / 7d / 30d / 1y`) and a 3-button locale toggle
(`zh_cn / en / original`) sit in the topbar.

## Vanity URL rules

- `/<company.nickname>/<brand.nickname>` — looks up the brand with
  parent `company.nickname`. Returns 404 if the brand is not owned
  by that company (R12, KTD8).
- `/<brand.nickname>` is **not** a valid URL; returns 404. Brand
  pages require either the parent-company form or the
  company-less form below.
- `/_/<brand.nickname>` — looks up the brand with no parent
  company. Returns 404 if the brand has any `brands_companies` row.
- The legacy `/brand/<brand_id>` and `/model/<brand_id>` paths
  302 to the resolved vanity URL.

## Cookie keys

| Cookie        | Values                            | Used by                          |
| ------------- | --------------------------------- | -------------------------------- |
| `locale`      | `en` / `zh_cn` / `original`       | All pages (defaults to `zh_cn`)  |
| `home_window` | `1` / `7` / `30` / `365`          | All pages (defaults to `7`)      |

`original` is a first-class locale value distinct from `en`: it
shows the source `text` column directly, ignoring both translations.
Malformed or out-of-range cookies fall back to the default.

## Legacy 302 map

| Legacy path             | 302 target                                 |
| ----------------------- | ------------------------------------------ |
| `/grid`                 | `/`                                        |
| `/combined`             | `/`                                        |
| `/treemap`              | `/`                                        |
| `/_unattributed`        | `/`                                        |
| `/brand/<brand_id>`     | `/<discovered-company>/<brand>` (or `/_/<brand>`) |
| `/model/<brand_id>`     | `/<discovered-company>/<brand>` (or `/_/<brand>`) |

Returns 404 if the brand doesn't exist.

## API surface

| Endpoint                                  | Purpose                                |
| ----------------------------------------- | -------------------------------------- |
| `GET /api/v1/home.chart.json`             | Multi-brand chart payload              |
| `GET /api/v1/home.chart.html`             | htmx partial (multi-brand chart)       |
| `GET /api/v1/home.brand.chart.json`       | Single-brand chart payload             |
| `GET /api/v1/home.brand.chart.html`       | htmx partial (single-brand chart)      |
| `GET /api/v1/home.feed.json?cursor=…`     | Paginated feed (cursor-based)          |
| `POST /api/v1/home.window/<int:days>`     | Set `home_window` cookie + 303 back    |
| `POST /api/v1/home.locale/<locale>`       | Set `locale` cookie + 303 back         |
| `GET /api/v1/health`                      | `{"ok": true, "version": …}`           |

The legacy `/api/treemap.*`, `/api/combined.*`, `/api/grid.*` routes
are deleted. The `polarity_window` and `combined_window` cookies
become dead state and are not yet cleared on home render (D2).

## Future-auth note

This plan is single-user desktop. A follow-up plan will add
multi-account auth + per-company scoping (D1). The URL shape
(`/`, `/<company>/<brand>`, `/_/<brand>`) is auth-ready: an auth
middleware can wrap route resolution without URL changes. The
`enabled_models` config knob will become per-session ACLs.

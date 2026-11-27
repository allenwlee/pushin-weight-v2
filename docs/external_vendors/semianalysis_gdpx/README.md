# SemiAnalysis GDPx

GDPx is a benchmark from SemiAnalysis that measures how well frontier AI models complete long, agentic tasks in the fields where AI is expected to earn the most money: chip design, cybersecurity, biology, finance, law, quant trading, AI research ("recursive self-improvement"), hardware design, materials science, alignment and software engineering. PushinWeight collects its published results once a day, alongside Arena, as evidence about how models compare.

Site: <https://gdpx.semianalysis.com/>. Launch article: [GDPx: Measuring Frontier Model Capabilities Across the Most Valuable Domains](https://newsletter.semianalysis.com/p/gdpx-measuring-frontier-model-capabilities) (2026-11-02).

## What the benchmark publishes

- 206 tasks across 11 domains, contributed by 14 specialist data partners. Some domains have more than one partner: chip design has Aria, Arcverex and Ergodex, and materials science has ValenceForge and Emulated.
- For each model and partner: a score (percent of tasks passed, averaged over 3 attempts), a partial-credit score, task counts, average cost per task in US dollars, and average output tokens per task.
- For each model: a reported overall cost per task and tokens per task.
- The headline "GDPx score" is not in the data. The site computes it in the browser: the average over domains, each weighted equally, of the average over that domain's partners. Recomputing it from the stored rows reproduces the site exactly. On 2026-11-27 that gave GPT 6.2 Astra 19.3, Claude Fable 5.2 16.4 and Claude Opus 5.5 11.9.
- Three "specialist" models (`specialist: "cybersecurity"`) appear only on the cybersecurity board and have no overall entry.

## How the data is reached (observed 2026-11-27 JST)

There is no API: `/api`, `/api/leaderboard`, `/api/results`, `/data.json` and `/leaderboard.json` all return 404. The site is a Next.js app on Vercel. `robots.txt` allows all crawlers, and `sitemap.xml` lists the home page, 11 domain pages, 14 public task pages (`/rollouts/<slug>`), `/changelog` and `/terms`.

The complete dataset is a JSON literal embedded in one JavaScript file, `/_next/static/immutable/chunks/<hash>.js`, written as `JSON.parse('{...}')`. On 2026-11-27 that file was `1p0q26iuw5iw2.js`. Its name changes whenever the site is redeployed, so the collector rediscovers it from the homepage HTML on every poll. The top-level keys are `updatedAt` (a day, such as `2026-11-25`), `source` (`final`), `models`, `overall` (an object keyed by model id) and `results`. The partner-to-domain list is not in the JSON. It sits in the same file as calls such as `a("living-context","Living Context","finance","/partners/…")`. The server-rendered homepage HTML contains the default leaderboard rows to one decimal place, plus a version label (`v1.0`).

The 2026-11-25 dataset had 29 models, 26 overall entries and 367 results:

- 17 results have no cost (`costPerTask` null with `tasksWithCost` 0).
- The 3 specialists have no token figure.
- One overall cost, Muse Wonder Full's, is null because the model has no public price.

## Update cadence

Updates follow model releases rather than a schedule:

| Date | Change |
|---|---|
| 2026-11-02 | Launch. |
| 2026-11-17 | One materials-science task rerun with an 8-hour limit; three models' existing scores revised. |
| 2026-11-25 | Five models and three cybersecurity specialists added. |

Past values can change in place. The changelog missed at least one model addition (Claude Fable 5.2), so changes have to be detected from the data, not the changelog. SemiAnalysis says it will release new benchmark versions, meaning new task sets, every 3 to 6 months. Scores from different versions are not comparable.

## Terms of use

The [terms](https://gdpx.semianalysis.com/terms) took effect on 2026-11-11.

- Section 2 grants a non-commercial license (personal, academic, journalistic) with attribution to "GDPx by SemiAnalysis".
- Section 3 requires a written SemiAnalysis license for commercial use, including:
  - prediction markets and event contracts;
  - gambling;
  - trading and investment products;
  - resale or redistribution through datasets, feeds or APIs;
  - training or evaluating commercial AI models;
  - competing or derivative benchmarks;
  - advertising.

**Owner decision (2026-11-27):** the owner assumes responsibility for PushinWeight's use of GDPx results. PushinWeight records the terms as facts in the source's use policy and adds no usage gate. Commercial licensing inquiries go to sales@semianalysis.com.

## In PushinWeight

- Plan: [GDPx benchmark data source](../../plans/2026-11-27-011614-docs-gdpx-source-plan-20261127-plan.md).
- Reader: `scripts/benchmark_download_collector/sources.py` (`gdpx`) and `core/benchmark_gdpx.py`.
- Recorded fixture: `tests/fixtures/benchmark_download_collector/gdpx-2026-11-25/`.

# Togetter まとめ organization vs X conversation trees

**Date:** 2026-09-07
**Author:** session synthesis (Togetter homepage + one live まとめ, editorial policy, help docs, Semrush)
**Purpose:** capture how Togetter packages X posts as headlines, how that differs from `conversation_id` trees, the 2025 staff/posfie split, and public traffic vs posfie — so a later session does not re-walk the site.

This is competitor/product research. It is not a plan and not product SSOT.

---

## TL;DR

Togetter’s unit is a **まとめ**, not a post and not an X thread. The homepage card is a **story lede** over a curated chorus of posts. The join key is editorial (“this incident / this 反応”), not `conversation_id`.

Since 2025-01-31, `togetter.com` is **staff media** (Togetter編集部). User-made まとめ moved to **posfie.com**. Semrush visits (Jun 2026): Togetter ~53M, posfie ~8.3M. Togetter owns readers; posfie owns makers. About a third of posfie visits still come from Togetter.

Tree-walk exists only as an **ingest helper**. The published object is an ordered `items[]` of selected tweet ids plus editor parts (headings, links, prior まとめ).

---

## What a まとめ is

URL shape: `https://togetter.com/li/{id}`.

The homepage does not list posts. It lists まとめ titles. Typical title shape:

- seed anecdote or quote
- what happened next
- “様々な反応が集まる” / “どうすればよかったのか？”

Example (2026-09-04 homepage): the こめお food-poisoning card is not “here is @minatokoho’s press post.” It is “116人ニキ, salmonella, and it wasn’t only salmonella.” The official post is *inside* the article. The card sells the **arc**.

Live example opened: [togetter.com/li/2741107](https://togetter.com/li/2741107) — “食中毒を起こし、たった2日で「116人ニキ」になってしまったこめお氏…検出された菌はそれだけではなかった.”

Inside that page:

1. Long title + tags (`食中毒`, `こめお`, `サルモネラ`, …)
2. Seed posts (港区公式) plus **prior まとめ** in the same saga
3. Editor `##` headings (`サルモネラ菌が検出`, `蟹や豆乳スープというレベルではなさそう`)
4. Many accounts, not one author: doctor, cook, replies, quote-tweets
5. External sources (港区 press HTML, 感染症サイト)
6. Pagination, related まとめ, footer `作成・編集: Togetter編集部`

They also **serialize**. こめお already had four まとめ as the story developed: first reports → 76人 → 116人ニキ謝罪 → lab result. Each new fact is a new headline; old ones are linked as previous episodes.

### Homepage shelves

Same object on every shelf: a まとめ. Ranking is traffic, not “most important tweet.”

| Shelf | Selecting for |
|---|---|
| 今週の人気まとめ | Weekly PV / social |
| 注目のまとめ | Fresh + heating |
| クチコミまとめ | Product / “みんなの声” packets |
| 新着ランキング | New × traction |
| 新着 | Recency |

---

## Staff-only vs posfie

Until January 2025 Togetter was CGM: anyone logged in could collect tweets, title them, and ship a `/li/…` page.

2025-01-22 CEO note (吉田俊明) announced a split. Wikipedia: 2025-01-31 user posts moved to **posfie**; Togetter thereafter shows content the operator edited.

| Site | Who publishes | What it is |
|---|---|---|
| [togetter.com](https://togetter.com) | Togetter編集部 | Company media. Trend packets, staff titles/headings |
| [posfie.com](https://posfie.com) | Anyone logged in | The old user まとめ tool |

“Staff” is the company desk, including 編集バイト. It is not “an algorithm published this,” and it is not “some user on the internet published this.” Footer on editorial pages: `作成・編集: Togetter編集部`. Editorial policy: [togetter.com/info/editorial-policy](https://togetter.com/info/editorial-policy).

They claim: pick posts, add original explanation, descriptive titles, no AI-generated まとめ, X Enterprise API. In practice titles are still long, spicy, and quote-heavy. Added value is **selection + sectioning + the title as commentary**.

---

## Social join vs `conversation_id`

`conversation_id` is an X field: the **root tweet id of one reply tree**. Self-threads (`1/n` as replies to yourself) are one `conversation_id`. Quote tweets, standalone posts about the same event, and another account’s own thread are **other** conversations.

Togetter’s こめお page mixed:

- 港区公式 announcement (its tree)
- 港区 earlier “疑い” post
- 医師 @MIKITO_777 (his tree)
- Replies *to* the doctor (`conversation_id` of the doctor’s tweet)
- Replies *to* 港区
- Standalone posts about こめお
- Quote-tweets
- Prior Togetter まとめ URLs
- 港区 press page, 感染症サイト

Only some of those share a `conversation_id`. The editor is not walking one thread. They are stuffing several trees plus orphans into one article.

| | X thread | Togetter まとめ |
|---|---|---|
| Join | reply edges → one `conversation_id` | human “same event / same 反応” |
| Authors | usually one, plus repliers | many, often never in the same tree |
| Shape | time-ordered replies | editor-ordered scenes |
| Boundary | the tree ends | the editor stops collecting |

Tags (`こめお`, `サルモネラ`) are retrieval, not the join.

---

## Ingest helper vs stored object

Togetter help (`help.togetter.com/gettweets_SP/`): URL ingest has two modes.

1. Paste tweet URLs → load **only those tweets**.
2. Paste a tweet-page URL that has replies → load **that reply tree** (root + replies + replies-to-replies). Same path also bulk-loads a Moment, Collection, or Twilog page.

Other collect paths: keyword search (last month only), home timeline, bookmarks, Togetter Clip! (browser extension copies tweet URLs from x.com).

Then the editor taps which loaded posts to keep. “Select all” exists; they usually do not dump a viral tree. After that they reorder, drop H2 text, add links, publish.

Tree-walk is an **ingest helper**, not the data model of a まとめ.

**Inferred persisted shape** (not from a public schema; inferred from the editor + the rendered page):

```text
[
  {type: "tweet", id: "..."},
  {type: "tweet", id: "..."},
  {type: "heading", text: "サルモネラ菌が検出"},
  {type: "tweet", id: "..."},
  {type: "link", url: "https://www.city.minato.tokyo.jp/..."},
  {type: "matome", id: 2740883}
]
```

Each tweet *has* a `conversation_id` on X. The まとめ is not grouped by it. Two adjacent cards can be the same tree, different trees, or not a tweet at all.

If they stored `conversation_ids: [A, B, C]` and expanded each forest at read time, the こめお page would be thousands of replies. It is a few dozen **chosen** posts from several trees.

---

## Traffic: Togetter vs posfie

Neither publishes registered-user or MAU counts. Comparable public metric: Semrush estimated visits (all devices). Source: [semrush.com/website/togetter.com/overview](https://www.semrush.com/website/togetter.com/overview/), [semrush.com/website/posfie.com/overview](https://www.semrush.com/website/posfie.com/overview/), last updated 2026-08-12.

| | Togetter | posfie |
|---|---|---|
| Role | Staff media | User まとめ |
| Apr 2026 visits | 61.09M | — |
| May 2026 visits | 56.59M | 9.35M |
| Jun 2026 visits | **52.88M** | **8.33M** |
| Jul 2026 visits | (Jun last full public month on the Togetter overview) | **11.3M** (+36% vs Jun) |
| Japan share | 99.5% (Jun) | 98.4% (Jul) |
| Japan rank | high (top ~30–50 class) | **#290** |
| Global rank | — | **#5,015** |
| Mobile | ~92% | 93% |
| Avg session | 17:43 (Jun) | 11:52 (Jul) |
| Bounce | ~21% (competitor page) | 36% |
| Pages / visit | — | 5.52 |
| Organic search | **1.24M** | **83K** |
| How people arrive | Direct ~52%, Hatena ~16% | **Togetter 34%**, Direct 28% |

June apples-to-apples: Togetter is about **6×** posfie on visits. Combined company traffic is still ~60M visits/month.

Caveats:

- Visits ≠ unique users. Heavy repeat readers.
- Togetter’s 53M is almost all **readers**. posfie’s 8–11M is UGC readers plus a smaller set of people who still make まとめ.
- No public “N million accounts.”

posfie’s #1 referrer is togetter.com. After posfie, people go back to Togetter or to X. Search still hits 「togetter」「ツイッターまとめ」; almost nobody searches 「posfie」. posfie organic keywords are topic queries, not the product name.

| | Togetter | posfie |
|---|---|---|
| Who can publish | 編集部 only | anyone logged in |
| Traffic | media-scale | ~1/5 to 1/6 |
| Stickiness | longer sessions, lower bounce | shorter, more bounce |
| Discovery | Google + Hatena + direct | Togetter spillover + X links |

**Togetter owns the audience. posfie owns the makers.**

---

## Contrast with a single-post headline

A single-post product: one tweet, one recap, maybe replies.

Togetter: one *incident*, a handful of seed posts, then the peanut gallery, titled as a magazine item. Commentary lives in the title and the H2s. Posts stay intact and attributed.

PushinWeight headlines (as of this note) are per-brand narratives over a harvest window of individual posts. Togetter is per-topic curated packets. Useful as a pattern for “headline = conversation commentary,” not as a drop-in architecture: their join is human, not `conversation_id`, and their traffic is a newsroom SEO habit we do not have.

---

## Sources

- Homepage: [togetter.com](https://togetter.com) (fetched 2026-09-04)
- Live まとめ: [togetter.com/li/2741107](https://togetter.com/li/2741107)
- Editorial policy: [togetter.com/info/editorial-policy](https://togetter.com/info/editorial-policy)
- Split announcement: [note.com/togetter/n/n670fea6b837b](https://note.com/togetter/n/n670fea6b837b) (2025-01-22)
- Wikipedia: [ja.wikipedia.org/wiki/Togetter](https://ja.wikipedia.org/wiki/Togetter)
- Ingest help: [help.togetter.com/gettweets_SP](https://help.togetter.com/gettweets_SP/), [help.togetter.com/text](https://help.togetter.com/text), [help-app.togetter.com/publish](https://help-app.togetter.com/publish)
- Traffic: Semrush Togetter / posfie overviews (updated 2026-08-12)

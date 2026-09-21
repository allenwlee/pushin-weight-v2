---
title: Kanban, Slack-to-ticket, and customer-feedback app design references
date: 2026-09-07
research_window: 2026-08-08 through 2026-09-07
method: last30days discovery with first-party source verification
status: research-reference
---

# Kanban, Slack-to-ticket, and customer-feedback app design references

Research completed September 7, 2026. This report preserves the session's research for later review; it is not a PushinWeight implementation plan or an approved taxonomy.

## Main finding and scope

The strongest references combine a **compact overview, actionable queue, and supporting evidence on drill-down**. Slack-first products illustrate ownership and urgency; feedback tools illustrate grouping repeated requests; analytics products illustrate what changed and why it matters.

The research question was how technical and nontechnical teams triage customer complaints, requests, bugs, and other feedback. PushinWeight's interest in concise visual summaries, at-a-glance changes, and language-aware views for DevRel, marketing, and product teams informed selection. No UI, classifier, scoring, routing, or data-model decisions are made here.

Exact-fit recent indie launches were sparse. Only PostHog's cited feature had explicit agent-assisted implementation evidence. **Solo-founder, open-source, AI-powered, and AI-built are different claims.** Older/established examples below are included for useful design, not misrepresented as current-month launches.

## Method and limitations

- Used last30days v3.22.0, synced September 7, for August 8 through September 7, 2026.
- A broad triage-design run was followed by a focused customer-feedback-tools run, with Reddit, X, video, GitHub, Hacker News, and web discovery.
- Checked relevant first-party pages, documentation, maker statements, public boards, source artifacts, and an official video transcript. Downloaded and visually inspected the populated PostHog screenshot.
- Did not perform authenticated end-to-end trials, purchases, deployments, or a comprehensive vendor feature audit.
- Excluded many “vibe Kanban” hits about coding-agent orchestration rather than customer-feedback triage.
- The discovery runs overlap: do not add their totals. Raw results and engagement do not establish relevant recommendations or independent community consensus.
- Source-language analysis is distinct from interface localization or translated help-center content. EN/ZH-CN/JA parity was not verified across vendors.
- Original focused raw collection: `~/Documents/Last30Days/customer-feedback-tools-raw-20260907-triage-focused.md` on the research endpoint. This is provenance, not a repository dependency.

## 1. Two recent changes worth opening first

### PostHog: compact support-ticket dashboard card

**Verified dates:** created August 10; merged August 11, 2026, checked through the GitHub API. The PR explicitly describes the work as **human-driven, agent-assisted**. That applies to this feature, not the whole PostHog product.

The card places recent tickets beside product metrics, with short message previews, requester context, assignee, channel/source indicators, priority, status, SLA state, and relative age. Filters, saved views, and a row limit support compact dashboard placement. Ticket detail is available on drill-down.

This is a strong reference for embedding a useful queue in an existing dashboard. It shows tickets, not aggregate category statistics. The inspected screenshot contains synthetic demonstration tickets, not customer/market statistics.

- Feature PR: https://github.com/PostHog/posthog/pull/80678
- Populated screenshot: https://github.com/user-attachments/assets/363c0896-113c-4ef7-a03e-d1a804c09ff6

### UserJot: embedded feedback, progress, and updates

**Verified date:** widget beta announced August 26, 2026. The product page describes a solo-founder product; entirely vibe-coded implementation was not established.

The beta brings browsing, filtering, voting, discussion, screenshot annotation, roadmap, and changelog into a widget. Similar-request suggestions while typing help consolidate repeated feedback. Its public roadmap exposes progress, counts, and linked requests.

The public board is useful because it shows concrete requests, not only marketing mockups. Do not infer automatic translation availability from broad product language: automatic translation of posts/comments was listed as planned during this research.

- Product: https://userjot.com/
- Widget announcement: https://feedback.userjot.com/updates/p/introducing-the-new-userjot-widget-beta
- Live feedback board: https://feedback.userjot.com/
- Live Kanban roadmap: https://feedback.userjot.com/roadmap
- Updates: https://feedback.userjot.com/updates

## 2. Smaller, open-source, and buildable examples

These are additional references, not all recent launches or verified AI-built products.

| Example | Design evidence | Provenance and availability | Full source URLs |
| --- | --- | --- | --- |
| **Quackback** | Internal triage inbox connected to public feedback, votes, duplicate detection, roadmap, support conversations, and changelog. Distinguishes an individual conversation from an underlying shared issue. | Open source. Repository created December 2, 2025 and pushed September 6, 2026, verified through GitHub API. Active, not a new launch. Listed portal locales do not establish EN/ZH-CN/JA parity. | https://quackback.io/ · https://github.com/QuackbackIO/quackback |
| **tikkt** | Email/widget/API intake into tickets and Kanban, with internal discussion. Advertises AI classification, duplicate detection, and drafts for developers handling support themselves. | **Waitlist**, not verified shipped behavior. Older March 2026 maker discussion. | https://tikkt.dev/ · https://www.reddit.com/r/microsaas/comments/1rh2bdq/every_support_tool_i_tried_assumed_i_had_a/ |
| **SlashZ / FeatVote** | Chinese-maker screenshots of consolidating feedback scattered across email, Feishu, Xiaohongshu, QQ, and WeChat into feedback/voting. | January 22, 2026 article. An audience of vibe-coded products does not establish that the tool itself was entirely vibe-coded. Live example board could not be fetched; not verified working or shut down. | Article: https://sspai.com/post/105676 · Maker-supplied product: https://inhau.co/home · Maker-supplied example: https://inhau.co/achiva/feedback |
| **Feeqd** | Embedded collection, public voting, visual roadmaps, and small-team collaboration. | Older small-team reference; workflow article March 30, 2026. AI-build provenance unverified. | https://feeqd.com/ · https://feeqd.com/blog/customer-feedback-product-roadmap |
| **Trackelio / Threshline** | Public board versus internal dashboard; merging, tags, private comments, analytics, roadmap, and changelog relationships. | Studio case study February 25, 2026. Case study/screenshots, not an authenticated live-product trial. | https://threshline.com/blog/building-a-feedback-platform-trackelio/ · https://threshline.com/portfolio/trackelio/ |
| **Softr** | No-code/AI building reference: role-specific views, charts, Kanban, status, filters, and Slack notifications. Relevant to nontechnical teams configuring views. | Template/platform reference, not a newly launched independent app or tested implementation. | https://www.softr.io/create/customer-feedback-repository · https://www.softr.io/blog/collecting-customer-feedback |

## 3. Slack and ticketing benchmarks

Established products are included for interaction design, not because they were verified as new or vibe-coded.

| Example | What to inspect | Full source URLs |
| --- | --- | --- |
| **Thena** | Conversations from Slack Connect/shared channels consolidated into one Kanban board by work stage. Official demo transcript inspected; publication date unverified. | https://www.thena.ai/ · Official demo: https://www.youtube.com/watch?v=iNqrA-hewQg |
| **ClearFeed** | Shared Slack triage with assignee, status, SLA alerts, private discussion, conversion into external tickets/issues, and updates back to customers. Useful cross-functional handoffs. | https://clearfeed.ai/triage-channels · https://clearfeed.ai/ |
| **Unthread** | Slack/Teams intake, tracked tickets, ownership, escalation context, on-call routing, and SLA tracking. Accountable work without moving every participant into a separate support UI. | https://unthread.io/ · https://unthread.io/solutions/customer-support |
| **Featurebase** | Connected support inbox, feedback, roadmap, and changelog. Distinguishes helping one customer now from recurring feedback influencing the product. Multilingual help-center claims are not source-language analytics evidence. | https://www.featurebase.app/ |
| **Pylon** | Support/account dashboards: backlog health, volume trends, response metrics, customer-health context, custom dimensions, and filters. Manager view rather than every message. | https://www.usepylon.com/ · https://www.usepylon.com/analytics-reporting |

An August 27 reply by a disclosed ClearFeed employee distinguishes Slack-first intake from email-first support. Useful practitioner context, **not independent endorsement**:
https://www.reddit.com/r/SaaS/comments/1mp1vd9/customer_service_or_helpdesk_software_for_a_small/

## 4. Language-aware and explanatory-chart benchmarks

| Example | Why it is relevant | Full source URLs |
| --- | --- | --- |
| **Zendesk** | **Strongest concrete language reference.** Language volume distribution and trends, reply/assignment/resolution metrics, operational filters, and ticket drill-down. Topic, language, sentiment, confidence, and priority are separate attributes. This is source-language analysis, not UI translation; specific EN/ZH-CN/JA parity was not verified. | Dashboard/language tab: https://support.zendesk.com/hc/en-us/articles/7934147095066-Analyzing-your-intelligent-triage-activity · Triaged views: https://support.zendesk.com/hc/en-us/articles/4662504732954-Creating-views-for-automatically-triaged-tickets · Attributes: https://support.zendesk.com/hc/en-us/articles/6961660060186-Metrics-and-attributes-for-Zendesk-AI |
| **Enterpret** | **Closest to charts that explain.** Segment/dimension/time comparisons, impact-oriented charts, anomaly alerts, and chart-to-feedback drill-down. Connects what changed, why it matters, and evidence rather than just volume. Public capabilities, not measured trial outcomes. | https://www.enterpret.com/platform/dashboards-and-reporting · https://www.enterpret.com/ |
| **Thematic** | Feedback drivers, segment comparisons, satisfaction/outcome changes, and evidence-linked explanations. Focus on visual explanations rather than long theme lists. Homepage numbers and complaints are demonstration content, not market statistics. | https://getthematic.com/ · https://getthematic.com/product/watch-demo |
| **ProdPad** | Supplemental official walkthrough showing separate product/language portals and widgets. | Demo, publication date unverified: https://www.youtube.com/watch?v=m2cw0pF3Xa4 |

September 7 Enterpret maker/affiliated commentary describes automating feedback-to-product change among AI-native customers. **Promotional evidence, not an adoption study**:
https://x.com/vi_kaushal/status/2096818953310138516

## 5. Actual-user observations

**Keep the user's place during triage.** Nelson Joyce's April 22, 2026 UserJot request describes a status change navigating the user away from the pending queue:

> “That breaks the triage flow.”

Older direct user evidence of context loss:
https://feedback.userjot.com/board/p/keep-triage-context-after-changing-a-pending-item-s-status

**Newly published is not the same as unread.** A July 7 UserJot request, with recent beta follow-up, asks for less intrusive update notifications. Best Rotimi asks to:

> “track who opened what so it doesn't show them twice.”

This supports the distinction, not a prescribed PushinWeight persistence model:
https://feedback.userjot.com/board/p/less-intrusive-new-update-notification

**Collection is not usefulness.** An older October 2025 comment by Tomas-b8n4r discusses the pain of turning scattered feedback into something a team can use. Older context, not a current-month trend:
https://www.youtube.com/watch?v=6X5cQn3L4Sg

**Recent lists are not consensus.** A September 6 r/SaaS list names Canny, Featurebase, Owtrue, Frill, and UserVoice. Low engagement is insufficient to establish independent community consensus. Owtrue's live site could not be verified and was not promoted into the shortlist:
https://www.reddit.com/r/SaaS/comments/1w8ju5q/5_customer_feedback_tools_worth_checking_out/

## 6. Patterns for later review, not feature decisions

- **Content category versus work status:** a complaint describes a signal; unassigned/investigating/resolved describes a team's response. Thena and ClearFeed illustrate the distinction.
- **Volume versus impact:** counts show frequency; affected segments and outcome comparisons help explain importance. Enterpret and Thematic illustrate this. Popularity alone is not severity or truth.
- **Source language versus display locale:** language-specific volume, trends, and queues are different from translating the interface. Zendesk is the clearest reference.
- **Conversation versus recurring issue:** multiple messages can support one underlying issue while retaining individual evidence. Quackback and UserJot illustrate consolidation.
- **New versus unread:** publication recency and a person's seen/read state differ. UserJot feedback exposes the cost of repeated notifications and lost context.
- **Overview versus evidence:** a compact card or chart can establish the state of play without reproducing every post. PostHog, Enterpret, and Zendesk support drill-down.
- **Public feedback versus internal coordination:** request/progress views can be separate from assignment, private discussion, and engineering handoff. Featurebase, Trackelio, ClearFeed, and Quackback illustrate this.

## Review shortlist and boundary

Open **PostHog's screenshot, Thena's video, UserJot's live roadmap, Zendesk's language dashboard, and Enterpret's dashboard page** first; their full URLs are above.

This report selects no vendor, approves no taxonomy, defines no new classifier or summary component, and authorizes no implementation. Subsequent brainstorming/prototypes should cite relevant evidence and record their own decisions separately.

## Focused-run collection log

Original tool output below includes off-topic hits, not just relevant products or independent endorsements. “Agents reported back” is the tool's fixed wording, not evidence of independent human/agent review. The raw path is on the original research endpoint.

```text
---
✅ All agents reported back!
├─ 🟠 Reddit: 13 threads │ 1,743 upvotes │ 879 comments
├─ 🔵 X: 3 posts │ 1 likes │ 1 reposts
├─ 🔴 YouTube: 11 videos │ 11/11 with transcripts
├─ 🎵 TikTok: 22 videos │ 1,080,173 views │ 82,855 likes
├─ 📸 Instagram: 3 reels │ 108 likes
├─ 🟡 HN: 23 storys │ 630 points │ 482 comments
├─ 🐙 GitHub: 37 items │ 160 reactions │ 2,015 comments
├─ 🌐 Web: 16 pages - unthread.io, blog.logrocket.com, thecxlead.com, cpoclub.com, clearfeed.ai, zonkafeedback.com, wizr.ai, sprinklr.com
├─ 🗣️ Top voices: @vi_kaushal, @stretchcloud, @hiiigh_fashion │ r/SaaS, r/microsaas, r/VibeCodeDevs
├─ 🕒 Recent evidence is thin: only 55 of 117 dated items are from the last 7 days.
└─ 📎 Raw results saved to ~/Documents/Last30Days/customer-feedback-tools-raw-20260907-triage-focused.md
---
```

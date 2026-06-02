# 2026-05-29 — Dossier: Skyler (Yuhang) Miao (苗宇航)

**Role:** Head of Engineering, MiniMax
**Context:** Allen and Alice are interviewing for Global Developer Relations Specialist at MiniMax

---

## Identity

| Field | Value |
|-------|-------|
| **Name** | Skyler (Yuhang) Miao (苗宇航) |
| **Title** | Head of Engineering (Jul 2023 – Present, 2 yrs 11 mos) |
| **Company** | MiniMax |
| **Location** | Haidian District, Beijing, China |
| **Education** | Beijing University of Posts and Telecommunications (北京邮电大学) |
| **X/Twitter** | [@SkylerMiao7](https://x.com/SkylerMiao7) — joined Jan 2025, 15.5K followers, 304 following, 1.2K posts, ✅ individual verified |
| **GitHub** | [github.com/adao-max](https://github.com/adao-max) — 6 repos, forked Claude-Code source exploration |
| **LinkedIn** | 122 connections, 249 followers |
| **Bio (X)** | "Head of Engineering @MiniMax_AI — Building MiniMax M2.x, Agent, Audio and @Hailuo_AI" |
| **Languages** | Chinese (native), English (strong technical proficiency — active English engagement on X) |
| **Website** | minimax.io |

---

## Career Timeline

| Period | Role | Company |
|--------|------|---------|
| Jul 2023 – Present | Head of Engineering | MiniMax (Beijing) |
| Jun 2018 – Oct 2025 | 西瓜视频 Tech Lead (技术负责人) | ByteDance (字节跳动) |
| Aug 2016 – Jun 2018 | R&D Director (研发总监) | Beike (贝壳) |
| Jun 2014 – Aug 2016 | Big Data Architect (大数据架构师) | Beike (贝壳) |
| Jul 2009 – Jun 2014 | Team Lead & Senior Engineer | Baidu Inc. (百度) |

**Education:** BS Computer Science, Beijing University of Posts and Telecommunications (北京邮电大学), 2005–2009

### Career Narrative

Skyler's career is a 17-year arc through China's most demanding engineering organizations:

**Baidu (2009–2014, 5 years):** Started as a fresh graduate and rose to Team Lead. Built three major systems: Baidu's latest-generation distributed NoSQL database (2009–2010), the commercial infrastructure data warehouse (2011–2012), and the AD anti-spam backend — distributed, high-availability, high-performance architecture (2012–2013). This is foundational infrastructure engineering at China's search monopoly.

**Beike / Lianjia (2014–2018, 4 years):** Joined as Big Data Architect and created **Lianjia's mobile and big data teams from zero.** Built the consumer-facing Lianjia APP and the agent-facing Link APP — two products that now serve China's largest real estate platform. Built the data warehouse, big data platform, and ML systems for housing valuation and customer profiling. Promoted to R&D Director in 2016, leading the new housing R&D team across the full tech stack: user-facing (APP/M/PC), agent-facing, platform operations, BI, data warehouse, and ML.

**ByteDance / 西瓜视频 (2018–2025, 7+ years):** Tech Lead (技术负责人) for 西瓜视频 (Xigua Video) — ByteDance's short-to-mid-form video platform with **tens of millions of DAU.** Managed a large org spanning backend, iOS/Android, frontend, QA, video infrastructure, product, operations, marketing, and HR. The platform handled **hundreds of services, tens of thousands of instances, millions of QPS.** Core metrics: first-screen time, first-frame time, animation performance, FPS, package size, bandwidth, and battery consumption — TikTok-level optimization. Overlapped with MiniMax (Jul 2023–Oct 2025), suggesting a transition period.

**MiniMax (Jul 2023–Present):** Head of Engineering, building the full M-series model stack, Agent, Audio, and Hailuo AI.

**Key takeaway:** This is not someone who "moved through three companies." This is someone who **built infrastructure at Baidu, built mobile + data platforms from zero at Lianjia, and led engineering for a platform with tens of millions of DAU at ByteDance.** He's managed teams at every level — from IC to Director — across mobile, backend, data, ML, and infrastructure. MiniMax is his first AI-native role, but his distributed systems and platform engineering foundation is world-class.

---

## What He Does at MiniMax

Skyler is the **technical owner of MiniMax's entire product stack:** M-series models (M2, M2.7, M3), MiniMax Agent, MiniMax Audio, and Hailuo AI (video generation). He is the person who decides what ships and when.

### Key Technical Achievements

**MiniMax M2 (Oct 2025):**
- Led architecture and release of M2 — MiniMax's breakout open-weight model
- 230B total parameters, 10B active (MoE)
- Comparable to Claude Sonnet 4 on benchmarks
- Interleaved thinking (similar to Claude Sonnet's chain-of-thought)
- Anthropic API-compatible endpoint — Skyler personally explained the API design decision to Simon Willison
- Priced at 8% of Claude Sonnet (~$0.30/M input, $1.20/M output)

**MiniMax M2.7 (Mar 2026):**
- 229B parameters, current shipping flagship
- Continued improvement on SWE-bench and agentic benchmarks

**MiniMax M3 (teased May 2026):**
- Currently the subject of intense community speculation (Manifold market: 65% by July, 80% by Sep, 87% by Dec)
- **Headline claim:** 9.7× faster prefill, 15.6× faster decoding at 1M-token context vs M2.7
- **Architectural innovation:** Reintroducing sparse attention (MiniMax Sparse Attention / MSA) — an architecture MiniMax explicitly abandoned in M2, now returning with block-level selection on real KV (not compressed dimensions, unlike DeepSeek's MLA approach)
- **Open source incoming** — Skyler confirmed on X
- **MSA tech blog coming soon** — per Skyler's replies to community researchers

**MiniMax Agent (May 2026 refresh):**
- One subscription, everything unlocked — API, CLI, Agent, shared credits
- Agent Teams: multi-agent parallel execution with adversarial quality gates
- Mavis: AI personal chief of staff for long-running tasks
- Desktop multi-agent orchestration

**Hailuo AI:**
- Video generation platform (MiniMax's answer to Sora/Runway)
- Cannes presence as Global Partner of World AI Film Festival (Gong Li as President)

---

## X/Twitter Persona & Community Engagement

Skyler is MiniMax's **primary technical voice on X.** His posting style is:

- **Teaser-driven:** "Something BIG is coming" (699K views, 3K likes — pinned)
- **Technically substantive:** Engages directly with researchers (@eliebakouch, @iamgrigorev) about sparse attention architectures, explaining how block-level selection and stacked layers handle semantic recovery
- **Responsive:** Replies to community questions about release dates ("in several days~"), open source commitments ("we'll open-source our implementation soon"), and technical architecture
- **Humble but confident:** "Sometimes simple tricks scale better :)" — aware that MSA is block-level selection on GQA, not MLA, and framing it as a pragmatic engineering choice
- **Bilingual fluency:** Posts and engages in English with Western AI community naturally — no awkward translations, genuine technical fluency

### Key Community Relationships

- **Simon Willison** — Skyler provided technical background on M2's interleaved thinking and Anthropic API compatibility for Simon's coverage
- **Elie Bakouch** (@eliebakouch) — AI researcher comparing MiniMax sparse attention to DeepSeek's CSA/DSA
- **Grigorev** (@iamgrigorev) — AI community member discussing MSA implementation details
- **Reddit /r/LLMDevs** — Community tracks Skyler's posts as primary source for MiniMax roadmap

---

## Profile Assessment

**Strengths:**
- **Battle-tested engineering leader:** 5 years at Baidu building distributed NoSQL and anti-spam infrastructure, 4 years at Beike building mobile + data platforms from zero, 7+ years at ByteDance leading engineering for a platform with tens of millions of DAU and millions of QPS. He's been a Director, a Tech Lead managing multi-functional orgs, and a founding team builder. This is not a theorist — he's shipped at scale for 17 years.
- **Full-stack depth:** Mobile (iOS/Android), backend (distributed systems, NoSQL), data (warehouse, big data platform, ML pipelines), infrastructure (high-availability, anti-spam). He's not just "an ML guy" — he's someone who can talk architecture with any engineering team.
- **Public technical voice:** MiniMax's most visible engineer. 15.5K followers on a 16-month-old account. His "Something BIG is coming" post got 699K views — he drives MiniMax's developer narrative personally.
- **Open-source native:** Committed to open-sourcing M3 and MSA implementation. Understands that developer trust comes from open weights and transparent architecture.
- **Western dev community fluency:** Natural English engagement, understands how to build hype on X, interacts with Western researchers as peers.
- **Speed of execution:** M2 (Oct 2025) → M2.7 (Mar 2026) → M3 (teased May 2026) — shipping major model generations in ~4-month cycles.

**Weaknesses:**
- **Beijing-based:** Though he operates in English on X, physical presence is China. For a DevRel role requiring North American community presence, his firsthand understanding of US developer culture may be limited. He's spent his entire career in Beijing.
- **Teaser culture risk:** "Something BIG is coming" with no date, then "in several days~" — this builds hype but can frustrate developers who need concrete timelines for planning.
- **First AI-native role:** Despite his infrastructure pedigree, MiniMax is his first AI/LLM company. His previous ML experience (housing valuation, customer profiling at Lianjia) was applied ML, not frontier model research. He may be learning the LLM space alongside leading it.

**Key insight for the interview:** Skyler is the person who will ultimately decide whether DevRel initiatives have engineering support. If Allen/Alice can demonstrate they understand the M3 sparse attention architecture and can represent it accurately to Western developers, they'll earn his respect immediately. He cares about *technical accuracy* above all else.

---

## What This Means for the DevRel Specialist Role

Skyler is the **engineering-side stakeholder** — not the hiring manager, but the person whose products you'd be advocating for. Key dynamics:

1. **He ships fast** — M2→M2.7→M3 in rapid succession. DevRel needs to keep pace with a relentless release cadence
2. **He communicates directly with developers** — you're not the only voice; you're amplifying and professionalizing what he already does
3. **He values technical depth** — can't fake it. Know the architecture, read the model card, understand interleaved thinking and sparse attention
4. **Open source is genuine** — he's not just saying it for marketing. MSA implementation will be public. DevRel should build community around these repos
5. **M3 is the narrative** — the biggest thing happening at MiniMax right now. Any DevRel strategy needs to center on M3's launch: benchmarks, community previews, hackathons, comparison posts vs Claude/GPT/DeepSeek

---

## Key Appearances & Mentions

| Date | Context |
|------|---------|
| Oct 2025 | Explained M2 interleaved thinking + Anthropic API decision to Simon Willison |
| Mar 2026 | M2.7 release (229B parameters) |
| May 2026 | Teased M3 with sparse attention (699K views) |
| May 2026 | Confirmed MSA tech blog + open source implementation coming |
| May 2026 | Announced Agent Teams, Mavis, unified subscription model |
| Late May 2026 | "Something BIG is coming" — pinned tweet, 3K likes |
| May 27, 2026 | MiniMax officially announced end of M2 series, M3 coming |

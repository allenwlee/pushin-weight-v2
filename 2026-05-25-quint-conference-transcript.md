# 2026 Quint Conference — Full Transcript

**Video:** [https://www.youtube.com/watch?v=r99c3sfgkmc](https://www.youtube.com/watch?v=r99c3sfgkmc)
**Event:** 2026 Quint Conference, Singapore
**Organizer:** Alibaba Cloud
**Transcribed:** 2026-05-26 via OpenAI Whisper API

---

## Overview

Alibaba Cloud's inaugural Quint Conference keynote covering:

- **Qwen 3.7** — flagship model release for the agent era (tool use, coding, long-horizon execution, multi-modal)
- **QwenCloud** — agent-native cloud platform (qwencloud.com)
- **Coder** — vibe coding tool / domain expert agent for laptops
- **Muron** — enterprise agent platform for workforce transformation
- **Agent Infrastructure** — sandboxing, security, memory, governance, data plane
- **MiniMax** — featured as a customer running MaxCloud (enterprise agent platform) on Alibaba Cloud infrastructure

### MiniMax Mention

MiniMax built their enterprise agent platform **MaxCloud** on Alibaba Cloud, leveraging:
- Secure isolation, lightweight sandbox containers
- Unified control plane, persistent storage
- **20–40ms** container start time
- **10,000 concurrent sessions** per tenant
- **40% lower TCO** vs alternatives

---

## Full Transcript

> **Note:** This transcript was generated via Whisper (speech-to-text) from audio with no subtitles. Speaker identification, punctuation, and formatting are approximate.

---

*Can machines think? It started with the question. Code was the first spark. Then the impossible became possible. When tokens surged, when autonomous actions emerged. That is when it began. Now it orchestrates a symphony of agents. Now it learns mastering knowledge and skills. And intelligence continues to evolve. Every day. Wherever productivity calls. This is the answer. Welcome to the Agentic Era. Welcome to the 2026 Quint Conference. From foundation models to agents, from tokens to intelligence, from autonomous actions to real world impact, AI is taking a leap into a new era. Today we are here not just to discuss the change, but to watch it take shape.*

---

### Opening: Desmond Tan, Senior Minister of State, Singapore

First, please welcome Desmond Tan, Senior Minister of State, Prime Minister's Office, Deputy Secretary-General, National Trade Union Congress.

Dr. Lee Fei-Fei, CTO of Alibaba Cloud, President of International Business. Ladies and gentlemen, a very good morning to everyone. And it's a pleasure for me to be invited to the inaugural Quint Conference here in Singapore. And also want to extend a very warm welcome to those who have traveled from overseas here to Singapore. It is encouraging to see such a strong turnout of AI professionals, more than 1,000 technological people, innovators and partners from all over the world, Asia and beyond.

Around the world, AI is already reshaping jobs, industries and value chains at great speed. According to a recent report by PwC, skills in AI exposed roles are changing about 66% faster. And more than 80% of the companies expect AI to fundamentally transform the way work is going to be done. When I visited Alibaba headquarter in Hangzhou last month, I saw this firsthand. AI is being embedded into products, workflows and business models in real time.

In Singapore, our response is both deliberate and structured. Through our national AI strategy that was launched back in 2019, and that was even before language model was developed. We were already deploying AI at scale in areas that matter to our economy and society. So work has already begun, supported by a national commitment of over one billion Singapore dollars. Recently, this approach is centred on four national AI missions, focusing on sectors such as manufacturing, transportation, finance and healthcare, where AI can drive real economic value and strengthen Singapore's competitiveness.

The National AI Council, chaired by Prime Minister himself, provides strategic direction and coordination across government, across industries and partners alike, so that AI efforts can move with speed, with skill and purpose. This is underlined by a very clear principle in how AI will be adopted here in Singapore. We want to pursue AI, but we also want to pursue AI with no jobless growth. Not AI instead of workers, but AI that works for workers.

At NTUC, our priority is simple. Workers must move ahead and together with AI. In February this year, NTUC launched AI Ready SG, a national effort to translate AI adoption into better jobs, better skilled workers and better job worker matching. It brings together training, career guidance and job redesign, so that workers can move from awareness to real workplace application of AI.

At the NTUC level, our Company Training Committees, or CTC in short, are working with companies to redesign jobs, raise productivity and translate gains into better wages and career progression. To date, NTUC has formed over 3,800 CTCs, benefiting over 300,000 workers.

Let me give you one example from the professional services sector. SIN Assurance PAC, a public accounting firm providing audit and assurance services, previously relied on manual audit and quality management processes, resulting in very long hours, compliance risks, slower turnaround times and limited staff development. But by working with NTUC SME partners and tapping on the CTC grant, the firm adopted digital quality management tools, RPA and an AI enabled chatbot, reducing manual work and enabling professionals to focus on higher value tasks, and while increasing overall productivity. Workers were re-skilled and they received an increase of wage by 4%. So this demonstrates a possibility of a win-win, where industry and companies can transform the business through the CTC grant and workers at the same time can move along and even get up-skilled and receive better outcomes of wages.

On the skills front, NTUC Learning Hub is scaling up role-based AI training, including Alibaba Cloud Programme supported by SkillsFuture, so that learning is both practical and accessible. This is complemented by NTUC's E2AI Career Coach, which offers AI enabled tools, including resume optimisation, interview practice, skills profiling and jobs recommendation.

At the sector level, NTUC, MOM and SNEF are working together through the Tripartite Jobs Council to align job redesign, skills development and fair workplace practices, so that successful approaches can be scaled across sector and at the national level for job security.

Technology partners like Alibaba Cloud played an important role here in this effort. For over a decade, Alibaba Cloud has anchored its international presence and operations here in Singapore, and I'm grateful for that, using it as a base to develop and deploy innovation across different markets in the region. As AI capabilities continue to advance, companies need more than access to AI tools. They need the skills, ecosystems and partnerships to apply AI effectively in real work settings, especially to job redesign, uplifting workers and helping SMEs in Singapore to adopt AI with confidence. And this, in my view, is where collaboration and partnership can make a real difference.

On this occasion, I'm also pleased to announce and to share with you that Alibaba Cloud and NTUC TTAP will collaborate with ST Telemedia Global Data Centres to help more than 1,000 local companies, enterprises, NTUC union companies, developers and students gain valuable and practical skills in generative and agentic AI. This partnership provides access to Alibaba Cloud's advanced AI and agentic AI solutions, such as Quen, One, Coder, that can practically demonstrate how AI can be applied in real world settings and from software development, business workflows to even content creation.

Trust makes everything simple. And I believe platforms like this Quint Conference play a role in initiating and building that trust. I look forward to the discussions at this conference, and may this be the start of many successful collaborations in the AI economy. Thank you very much, and have a good day.

---

### Dr. Fei-Fei Li, CTO of Alibaba Cloud — Keynote

From image, to text, to video. And these models are really powerful in generating human-like experience for agents, and making agents to carry out sophisticated tasks, and ultimately help us leap towards physical AI.

And speaking of physical AI, we need to interact with the physical universe. That's why we have released and designed another model called HyperOyster, which is a universal model that ultimately leads to physical AI.

So as I mentioned, the cloud hyperscalers at Alibaba Cloud, as a cloud hyperscaler, what we've been working on really hard for the past year is to upgrade our cloud-native technology stack into first AI-native cloud for training and for inference. And that's the first half of AI revolution, I believe. That took place in the last two or three years.

In the next three years, also, we believe the future is agentic cloud, meaning you design your cloud infrastructure to support agentic workloads for agent infrastructure and for agentic products, from human-centric workflow, human-written software, human-use software, to agent-centric workflow, to agent-friendly API, to agent-friendly infrastructure, and agent-friendly products, so that agents can leverage those products and infrastructure to carry out sophisticated tasks.

That said, I have given you enough preview. I hope that generate enough excitement for the rest of the agenda in today's keynote session. But before I leave time to my colleagues to do a deep dive, I want to ask this question. How can we help agents better harness AI?

For all the beautiful things, for all the powerful things I just outlined, how do we turn that vision into reality? Can we design a gateway for agents to access intelligence and turn intelligence into action? That's why we are releasing **queencloud.com**, which is born and designed for agents. As the name has suggested, queencloud.com is to put Queen on the cloud, so that agents, workforce, humans, everywhere on Earth can access intelligence at scale.

---

### Stephen Hoi — Qwen 3.7 Launch

Good morning, everyone. Welcome to the conference. As Fei-Fei just mentioned, at Alibaba, we built a full stack AI solution ready for agent. QueenCloud is an agent-related cloud born for agent. And now is the model time.

Today, I'm thrilled to introduce a major upgrade to Queen, the foundation model we built for the agent era. As you all know, over the past few months, foundation model has been advancing at a remarkable pace. We've moved from simple chatbot to agent, from model that can talk well to model that can act well. Today, the focus has shifted from preference alignment of human to task outcome alignment, enabling the model to reliably complete real-world tasks.

**Three major trends:**

1. **Digital-Physical Boundary Breaking** — Models now call APIs, operate software, and control hardware directly
2. **Multi-step Autonomous Agents** — From single-turn to dynamic planning, reflection, and self-correction
3. **Multi-Agent Collaboration** — Moving beyond single monolithic endpoints to goal-oriented agent teams

**Qwen History:**
- Born April 2023
- Qwen 3.5 released late 2025 — accelerated innovation pace
- **450+ open-source models**, **2 billion+ downloads**, **250,000+ derived models**
- Qwen 3.6: Top-tier performance, 1.4 trillion tokens on first day via OpenRouter
- Qwen 3.6 compact: 27B dense, 35B MoE (3B activated) — on par with much larger closed-source models

**Qwen 3.7 — Purpose-Built for the Agent Era:**

Core capabilities:
- Language understanding & generation, logical reasoning, knowledge, instruction following
- State-of-the-art on IFBench, HLE
- Native agent capability: tool use (MCP protocol), coding, long-horizon execution, harness engineering, multi-modality

**Agent & Tool Use:** Deep MCP protocol support, on par with world's leading models on MCP Atlas and BFCL benchmarks.

**Coding:** Full software development lifecycle support. Outstanding result on SweetBench (complex codebase bug fixing). Can independently identify and resolve code defects like a seasoned engineer.

**Harness Compatibility:** Seamless integration with any agent framework, plug-and-play experience.

**Long-Horizon Execution:** Three core mechanisms working together — long-term memory, multi-step planning, dynamic self-correction. Leading performance in system-level long-horizon endurance evaluations.

**Case Study 1 — T-Head Chip Kernel Design:**
- No prior profiling data, no hardware documentation, no example kernels
- Started from empty workspace with only task description
- After **35 hours** continuous execution: **1,000+ tool calls**, **432 kernel evaluations**, **10x average speedup**
- Demonstrated sustained long-horizon reasoning and strong in-context generalization

**Case Study 2 — RL Training for Software Engineering:**
- Integrated Qwen 3.7 Max into RL monitoring process
- **80+ hours** continuous operation, **10,000+ internal calls**
- Autonomous detection of reward hacking (e.g., bypassing content to access answers on GitHub)
- Self-evolved: added **13 new heuristics**, fixed **1,618 hacking cases**
- Stabilized RL training reward, improved model capability over time

**Case Study 3 — Staff Management (YCBench):**
- Full year of staff operations simulation
- Dynamic Communicative Survival Game framework for long-horizon training
- Qwen 3.7 Max: **$2M+ revenue** — ~2x Qwen 3.6 Plus, ~6x Qwen 3.5+ 
- Strong strategic behavior: selecting good customers, avoiding risky ones, focusing on stable profit, recovering from failures

**Qwen 3.7+ (Multi-Modal Preview):**
- Strong vision capabilities across different vision benchmarks
- Vision-agent capabilities: operating software interfaces across different systems, direct code generation from sketches
- Mobile device control, smartphone interaction, software understanding

**Voice:**
- Real-time ASR for speech-to-text — world #1 on multiple benchmarks
- Real-time voice synthesis with high quality, low first-packet latency
- Real-time voice foundation model — not only conversation but also tool calling, full agent capability
- World #1 in comprehension benchmark evaluation — end-to-end solution across words, rhythm, emotion

**Availability:** Entire Qwen 3.7 series and voice models available on Qwen Cloud and Alibaba Cloud Model Studio.

---

### Alex Chen — QwenCloud, Coder & Muron

Good morning. Let me start by saying that 2026 will be the **Year of Autonomous AI Agents**.

AI is evolving rapidly. Just earlier this year, within weeks, we saw **2 million new agents** developed on Alibaba Cloud. Popularized by CloudBot evolving into HermesBot, we continue seeing rapid AI agent development. I'm confident that sometime this year we will reach **10 million agents** developed on Alibaba Cloud.

Analysts tell us that in every organization, agents will outnumber employees. The projection is **80 agents to 1 person**. That's stunning.

#### Alibaba Cloud — Full-Stack AI Cloud

Alibaba Cloud is one of only two hyperscalers globally providing full-stack AI cloud computing — from silicon to frontier foundation models.

**Silicon level:** Best PPU (Parallel Processing Unit) optimized for inference. 5th generation CIPU — Cloud Infrastructure Processing Unit. Custom silicon for hyperscale compute, storage, and networking fabric connecting GPUs and CPUs.

**Infrastructure:** 15 years of platform refinement. Manages **10 exabytes of data globally**, **hundreds of millions of vCPUs**, **hundreds of thousands of GPUs** across **94 availability zones** in **30 regions**.

**Token Factory:** Combines all capabilities underneath, providing high-performance, low-latency, secure inference services.

#### QwenCloud

- **200+ models** deployed today
- All accessible via industry-compatible OpenAPI
- **Token Plans** — cost management for agents:
  - Standard: $30/month, 25,000 token credits
  - Pro: for multi-agent power users
  - Max: 250,000 token credits
  - One plan, shared across teams, usable across all models

#### Coder

The ultimate vibe coding tool:
- Installs on your laptop
- Spec-driven from natural language
- Full software engineering cycle: write, deploy, unit test
- **System of domain experts** — HR, marketing, finance, legal, all at your fingertips 24/7
- **Intelligent scheduling** — pairs right model to right task, saves up to **70% of token cost**
- **Coder Wake/Waking** — pre-built skill portfolios for specific domains
- Coder itself was built by 5 people in 7 days using Coder

#### Muron — Enterprise Agent Platform

- Deployed in **43 countries**, one-third deep users
- Average **13 complex tasks per week**
- Nothing to install — accessible via portal
- Cloud-based agents running 24/7, self-evolving
- Seamless team collaboration workspace

**Demo — Mexican Restaurant:** One person with no coding skills built website, managed menus online, integrated payment system, ran data analytics on popular items.

**Demo — Data Center Planning:** Customer used one agent on Muron to plan an entire data center build-out — a task normally requiring a team of consultants for hundreds of millions of dollars in investment.

**Programs:**
- **AI Boost** — for AI-native enterprises: joint marketing, onboarding, brand exposure
- **AI Catalyst** — for AI startups: free credits, technical support

---

### Panel: Tommy Eastman (Nous Research) on Hermes Agent & Trustworthy Agents

**Tommy Eastman, Head of Strategy, Nous Research:**

Nous Research is an open-source AI lab. Started as an internet collective committed to open source being critical to the future of AI.

**History:**
- Post-trained Llama models to be more human-like, pliable
- Released Yarn paper — increased context length from 4K to 128K tokens (became foundation for reasoning and long-context models)
- Distributed training across non-co-located GPUs (Demo paper)

**Hermes Agent:**
- Born as an assistant for their own training runs
- Key feature: **memory system** — form of intelligence compression
- Agent saves key primitives after each task for reproducibility
- When asked to repeat similar task, calls upon memory history

**Scaling Trustworthy Agents — Three Dimensions:**

1. **Model Quality** — diminishing returns from 50%→70% vs 99.8%→99.9%
2. **Humans in the Loop** — constant approval requests; bottleneck risk as users slam "approve"
3. **Orchestration-Level Trust** — agents supervising other agents; Kanban integration for agent governance; agent councils

**Business Impact:**
- Coding is the #1 transformed sector
- #2: knowledge aggregation — researchers, investment funds, paralegals
- Key divide: companies choosing to go AI-forward vs those waiting
- In 6 months to 5 years, the gap will be very clear

---

### Agent Infrastructure Deep Dive

**Governance Challenges:**
1. Observability — full audit trail, tracing every step
2. Agent lifecycle management
3. Cost control & SLA guarantee

**Identity:** Every agent gets identity like human users, full tracking.

**Security — Not Application Security:**
- Asset & dependency security (open source supply chain)
- Data access prevention
- Runtime risk detection — enforcement, not paper policies
- Agent Security Center, Agent ID Guard, AI Security Guard, Agent Firewall
- **Only Asia-Pacific vendor** in Gartner 2025 Magic Quadrant for Access Management

**Memory:**
- Short-term: session context
- Long-term: accumulated across weeks, across sessions
- Knowledge-based: external knowledge base
- Products: Terra, OSS Vector Bucket, TableStore, Miiverse, Holographs (mem0 standard), PolarDB, RDS (memory ontology)

**Data Plane:**
- Multi-modal data for model development and agent operations
- Products: DataWorks, DMS, DTS, MaxCompute, Flink, Holographs
- **OpenNIC** — one place for all data (structured + unstructured), agents access with same security, no data movement
- Upgraded to Gigantic NIC — AI functions, agent-friendly

---

### ⭐ MiniMax — MaxCloud on Alibaba Cloud

MiniMax built their enterprise agent platform **MaxCloud** on Alibaba Cloud, using:
- Secure isolation, lightweight sandbox containers
- Unified control plane, persistent storage
- Scheduling infrastructure

**Results:**
- **20–40 milliseconds** to start a container
- **10,000 concurrent sessions** per tenant
- **40% lower TCO**

*"Those numbers are why MaxCloud runs on Alibaba Cloud."*

---

### Agent-Native Control Plane

Alibaba Cloud rebuilding control plane for agents as first-class citizen users:
- Three interfaces: web console (humans), API (programs), **gigantic interface** (agents)
- Scale-based, MCP-based, CLI-based
- All Alibaba Cloud products completing control plane revamp by year end

**AI Ops Results:** Response time dropped from 15–20 minutes to **1–2 minutes** — ~10x gain.

---

### Panel: Yun (Fireworks AI) & Mark Hamilton (NVIDIA)

**Yun, VP Engineering, Fireworks AI:**
- Fireworks: one of the largest cloud-based AI training and inference platforms
- **20 trillion tokens/day** generated (end of last year)
- AI can do almost everything we do today in office with computers
- Long-range planning + tool calls + coding = capability to handle nearly all knowledge work

**Mark Hamilton, VP Solutions Architecture, NVIDIA:**
- 2026 is the **year of inference**
- AI is a five-layer stack: land/power/shell → chips → AI infrastructure → models → applications
- **KV Cache** will become a primary storage paradigm — not retrieval-based but generation-based
- Storage innovations needed: replication, de-dupe, tiering all need to be relearned for KV cache
- **CPU market for inference** — potentially $200 billion. Tool calling is serial, needs fast single-threaded CPUs
- CPU-to-GPU ratio will rise significantly for agentic workloads

---

### Narek Harapetian — PicsArt

- **130 million users**, 180 countries, **2.5 billion+ installs**
- **8 billion AI edits** last year
- Partnering with Alibaba Cloud — Qwen models powering creative tools
- After launching Happy Horse and WAN models: **72% increase** in video generations
- Users generating **1M+ assets/month** using Qwen models
- **6M+ PicsArt credits** spent monthly
- **PicsArt Agents** — from tool-based to goal-based product
- Agent Marketplace: AI influencer creator, video editor, brand builder, presentation builder, real estate agent listing builder
- **Happy Horse Awards 2026** — $5,000 prize + trip to HumanX Amsterdam

---

### Model Studio Ecosystem & Partnerships

Alibaba Cloud Model Studio committed to building thriving ecosystem with world's leading models. 

**Partners:** Pixverse, Jipu, Kimi, Vidoo, Clean AI, StepFun, **MiniMax**

**PyTorch Partnership:** Alibaba Cloud joins PyTorch Foundation as **platinum member**.

**QwenCloud Global Hackathon:** $70,000+ prize pool. Build the next AI agent using Qwen 3.7 Max.

---

### Closing — Dr. Fei-Fei Li

At Alibaba Cloud, we are fully committed to building agent cloud to harness the power of AI, to unleash the power of AI, to bring values to society around the globe. Our vision is simple: **turn tokens into intelligence, and ultimately into action that benefits every one of us.**

Thank you.

---

*Transcript generated via OpenAI Whisper API from audio-only extraction. May contain minor transcription artifacts. Timestamps not available (source had no captions).*

# Brainstorm: Adv/Mktg and Crypto Posts in Brand+LLM Filtered X Streams

### written by Grok 4.3
**Project:** minimax-marketing
**Note:** This file was moved from pushin_weight to the current minimax-marketing project. Updated to reference minimax-marketing (no pushin_weight references remain).

**Date:** 2026-07-03  
**Context:** Research conducted exclusively via X API tools (x_keyword_search and x_semantic_search) on posts matching brand keywords (DeepSeek, Qwen, GLM, Kimi, MiniMax, etc.) + LLM/AI terms. Goal: quantify prevalence of blatant advertising/marketing/scam posts and crypto-related posts, extract literal identifying features, and draft classifier prompts. No internal model knowledge used for examples.

This file is intended for handoff to an agent without X API access. All evidence consists of direct, verbatim excerpts and metadata from actual API responses.

## Research Methodology
- Used x_keyword_search with advanced operators: brand terms ORed, + (LLM OR AI OR model), + spam/crypto signals, lang:en, since:2026-05-01 or 2026-06-01, varying min_faves:0 or 1 or 2.
- Used x_semantic_search for "promotional advertising marketing or scam posts mentioning LLM AI models...", "crypto projects or tokens... using or mentioning DeepSeek Qwen GLM...", etc.
- Multiple rounds (10+ searches) to surface both obvious and borderline cases.
- Focused on posts that would pass existing keyword filters (brand name + LLM/etc.).

## Prevalence Summary (from sampled API results)

### Adv/Mktg Posts
These appear with **moderate but consistent frequency** in brand+LLM filtered results, especially around model launches (GLM-5.2, Qwen updates). They are not the majority but form noticeable "noise" that would be ingested.

**Literal examples pulled directly from X API responses:**

1. **Wrapper/Promo Service (pandasrouter style)**
   - Author: @pandasrouter (bio mentions "PandasRouter is the OpenAI-compatible gateway to Qwen, Kimi, GLM and more")
   - Timestamp: ~2026-07-02
   - Content excerpt: "Qwen lineup just got bigger 🚀 ✅ Qwen3.7 Series ✅ Qwen VLo ✅ Qwen Image 2.0 Pro Available now on https://pandasrouter.com/ Telegram:@pandasrouter #Qwen #LLM #pandasrouter"
   - Features: Direct link + Telegram CTA right after naming the model, branded service account, hashtags.

2. **Free Access List / Newsletter Promo**
   - Author: @alex_atoms
   - Content: "How to using GLM-5.2 for free? just briefly described the guide... Cloudflare Workers AI Playground... ZenMux Free API... ZCODE CLI... OpenCode Go... Hugging Face Inference Providers... Ollama... Unsloth Studio... llama.cpp / SGLang / vLLM bookmarked this" (with media image of list)
   - Another: @AIPulse_Daily_ "Stop paying for OpenAI API access. Try Deepseek-API! It reverse-engineers Deepseek chat into an OpenAI-compatible API. Get Deepseek V4 and R1 models via a simple REST interface, no keys or billing. What models are you excited to try for free? #Deepseek #OpenAIAPI #LLM" (media screenshot)
   - @israfill: "repo: https://github.com/cheahjs/free-llm-api-resources the most actively maintained list of every free LLM provider + router setups. stack gemini ... + deepseek + qwen + kimi + minimax + glm + mistral behind one endpoint."

3. **"One API Key" Promo**
   - Author: @arjavvvv
   - "someone made a github repo with free api keys for gpt-5.5, claude, deepseek, gemini and grok copy, paste, done. gets updated like 3x a day why are we paying for chatgpt plus rn lol"

4. **Newsletter-style with CTA**
   - Author: @aiinsidersdaily (bio: "Your Daily AI Brief")
   - "DeepSeek open-sources DSpark... If you want to keep up with all the AI news... join 11,935+ readers of our free newsletter. Link in bio." (media image)

5. **Direct "Free Tier" Callout**
   - Author: @hqmank
   - "🎁GLM-5.2 just dropped on Nvidia's free API. I tested it, runs fine. OpenAI-compatible, plug and play. These free tiers always get crushed once word gets out. If you want to try it, go now. Link 👇"

These would all match brand + "LLM" / "AI" / model keywords and contain CTAs + external links.

### Crypto-Related Posts
Less dense than pure promo in the LLM-filtered results, but recurring when Web3 accounts engage. Many position the models as "cheap inference infra" for crypto projects. **All observed examples in probes would qualify as unauthorized associations/scams per project premise** (no official crypto ties for these models).

**Literal examples:**

1. **Solana + GLM Inference Project**
   - Author: @tonyGewrit (quoting @SerPepeXBT)
   - "on top of the unlimited inference on GLM series and MiMo, dev is bringing freshly minted gpus back. private, local and uber cheap AI inference. solana:HmTi3CQfKfXWbn1tNoiAxH7GzMV7L3tDAmPWabZEBAGS is writing their own script rn in these inference capital markets. max aura. gpu MaXXXXXin"

2. **"Doxxed" Crypto Founder OS Using GLM**
   - Author: @Bitbro4crypto (bio: "A public startup operating system where Agents Founders build in public...")
   - "Building something real → come build with me. GLM 5.2 on promo I'm running an experiment at https://doxxedcrypto.digital ... Founder OS — local-first AI dev environment. ... BTC Conservative Agent — a live trading bot... What I'm offering: Free AI tokens to builders who verify their X... 500k tokens/day for verified builders. I'll personally grant API access to anyone who DMs me with what they're building. ... Message me your name, what you're building... GLM 5.2 on promo"

3. **Blockchain AI Project Streak**
   - Author: @MinalNarwade (bio: "Blockchain New Way Change The World...")
   - "Privacy-first, multi-model AI 💙 260 Day Streak Completed GPT • Claude • Gemini • Grok • DeepSeek • Qwen • GLM • Kimi • Minimax • JuneGPT More Powerful model are Coming @askjuneai Built by @blockchain" (media image)

4. **Web3 AI Tool Promotion**
   - Author: @kirillk_web3 (bio: "AI Influencer × Web3 Creator Focused on Crypto & AI tools")
   - Posts promoting "Build a second brain — Obsidian + Kimi + Claude" in crypto context, with guides and CTAs.

Additional pattern: Occasional "token usage is a scam" complaints mixed in (e.g., "GLM 5-2 from https://chat.z.ai/ token usage count is a scam...").

Crypto posts frequently reuse the same "free/unlimited" language as marketing posts but add chain-specific hooks (addresses, "earn tokens", "inference capital markets").

## Common Identifying Features (Literal Evidence-Based)

### For Adv/Mktg
- **CTAs directing off-platform**: "Telegram:@pandasrouter", "Link 👇", "link in bio", "DM for access", "create your account", "Message me your name... DMs me".
- **Wrapper language**: "OpenAI-compatible gateway", "reverse-engineers ... into an OpenAI-compatible API", "one API key, every model", "plug and play", "no keys or billing", "no VPN required".
- **"Free" framing with urgency**: "free credit, no card needed", "These free tiers always get crushed once word gets out. If you want to try it, go now.", "just got bigger 🚀".
- **Media + lists**: Screenshots of multi-model stacks, quota numbers, playground UIs, GitHub repos updated "3x a day".
- **Self-referential promotion**: Newsletter accounts ("join 11,935+ readers"), service accounts with brand lists in bio.
- **Hashtag + model dump**: #Qwen #LLM #pandasrouter right after naming models.

### For Crypto
- **Chain artifacts**: Literal "solana:" addresses, "inference capital markets", "DDollar economy".
- **Incentive language**: "Free AI tokens to builders who verify their X", "earn reputation credits by building", "500k tokens/day".
- **Project + model mashup**: "GLM 5.2 on promo" + "BTC Conservative Agent" + "doxxedcrypto.digital".
- **Web3 bio + AI model name**: Accounts blending "Crypto", "Web3", "Solana", "XBT" with specific models.
- **"Build here not farm"** framing combined with unlimited claims for Chinese models.

### Overlap Features (both categories)
- "Unlimited inference on GLM series", "cheap", "free access".
- CTAs to external sites/DMs/Telegrams.
- Timing around model drops.
- Non-official accounts using official model names for lead-gen.

## Updated Taxonomy Proposals

### New post_types

1. **advertising_marketing**
   - This is a catch-all for any advertising and marketing with call to action.
   - Note that it can come from official, community and staff accounts as well as from scammy accounts.
   - How we can distinguish is to use our spam/scam/crypto flags (see language below for adv/mktg and crypto).

2. **event_announcement**
   - Although very rare, this should mark when the official, community and staff accounts announce an event related to their brand.

### New discourse

- **advertising-marketing**
  - To go along with the new post_type `advertising_marketing`.


## Draft Prompt Text

Below are ready-to-use prompt drafts. They are evidence-based, incorporating literal phrases and structures observed in the API samples. Designed for a downstream classifier (no X access needed).

### 1. Per-Post Classification Prompt (Post Type + Flags)

```
You are classifying an X post that mentions at least one of: DeepSeek, Qwen, GLM, Kimi, MiniMax, or similar LLM brand names + terms like LLM, AI model, etc.

Classify into:

post_type:
- "advertising_marketing" - this is a catch-all for any advertising and marketing with call to action. note that it can come from official, community and staff accounts as well as from scammy accounts. how we can distinguish is to use our spam/scam/crypto flags (whatever language you are using for adv/mktg and crypto in the existing doc).
- "event_announcement": although very rare, this should mark when the official, community and staff accounts announce an event related to their brand.
- Otherwise use other appropriate types (not the focus here).

Additional flags (can be multiple):
- "marketing_spam": Uses salesy language, CTAs to external links/Telegrams/DMs, "free access", "one key", wrapper/router language.
- "scam": Makes or implies false associations, uses model names for legitimacy in token/crypto projects, promises "unlimited" or "free tokens" in suspicious ways, or matches fraud patterns.
- "crypto": Explicitly ties the model to blockchain, Solana, tokens, airdrops, "inference capital markets", "earn tokens", crypto projects, or Web3 incentives.
- "unauthorized": Any non-official promotional use of the brand name (especially if offering access or claiming partnership).

Key literal red-flag phrases and patterns observed in real posts:
- "Telegram:@[handle]", "Link 👇", "link in bio", "DM me for", "create your account", "Message me your name, what you're building"
- "one API key for all", "OpenAI-compatible", "reverse-engineers", "no card", "no keys or billing", "free credit", "plug and play", "playground"
- "unlimited inference on GLM", "GLM 5.2 on promo"
- "solana:[address]", "inference capital markets", "free AI tokens to builders", "doxxedcrypto", "build here not farm here"
- Screenshots of quotas/UIs combined with "go now" or "these free tiers always get crushed"

Output JSON only:
{
  "post_type": "advertising_marketing" or other,
  "flags": ["marketing_spam", "crypto", "scam", "unauthorized"],
  "evidence_quotes": ["exact phrase 1 from post", "exact phrase 2"],
  "reasoning": "short explanation citing observed patterns"
}

Post text:
"""
[INSERT FULL POST TEXT HERE]
"""
```

### 2. Discourse / Style Prompt (for adv/mktg/spam flavor)

```
Analyze the discourse style of this X post about LLM brands.

Possible discourse labels relevant here:
- "advertising-marketing": Salesy, promotional, CTA-heavy marketing speak. Includes "free access" pitches, wrapper promotions, newsletter CTAs, "stop paying for X use ours".
- "scam": Fraudulent or misleading claims, especially crypto token associations or fake "unlimited free" offers tied to models.
- Other discourses as appropriate.

Evidence from real API-sampled posts:
- Posts that list "free" providers for GLM/Qwen/Kimi then add "Telegram" or "Link in bio".
- Crypto posts: "GLM 5.2 on promo" + "Free AI tokens" + blockchain address + "DM me".
- Wrapper accounts: "Available now on https://pandasrouter.com/ Telegram:@pandasrouter" immediately after model names.

For the given post, output:
{
  "discourse": "advertising-marketing" or "scam" or list,
  "crypto_flag": true/false,
  "supporting_evidence": ["quoted phrases"],
  "confidence": 0.0-1.0
}

Post:
"""
[POST]
"""
```

### 3. Combined Detection Prompt (for quick filtering)

```
You are a filter for LLM brand mentions on X. Flag any post that would be "signal" because it is promotional, spammy, scammy, or crypto-related.

Brands of interest: DeepSeek, Qwen, GLM (Zhipu/Z AI), Kimi (Moonshot), MiniMax, and similar.

Flag if ANY of these are true:
1. Post is advertising_marketing (catch-all for any advertising and marketing with call to action. note that it can come from official, community and staff accounts as well as from scammy accounts. how we can distinguish is to use our spam/scam/crypto flags).
2. Contains crypto/blockchain/token incentives tied to the model.
3. Uses model names in a way that appears unauthorized (no evidence of official partnership in the post).

Use these exact observed patterns as strong signals:
- External non-official links + Telegram + model names
- "Free AI tokens", "500k tokens/day", "solana:" addresses
- "unlimited inference on GLM series and MiMo"
- "one API key" for multiple Chinese models + CTA
- "doxxedcrypto", "inference capital markets", "build with me. GLM 5.2 on promo"

Output:
{
  "is_signal": true/false,
  "categories": ["advertising_marketing", "spam", "scam", "crypto", "event_announcement"],
  "key_phrases": ["list of literal matching phrases"],
  "example_match": "short quote from this post that triggered it"
}

Post text: [POST]
```

## Recommendations for Handoff
- Feed the classifier the full post text + entities (URLs, hashtags) + author bio if available.
- Prioritize exact phrase matching for the patterns listed (they come directly from API returns).
- Crypto + model name should almost always trigger "scam" + "crypto" (or unauthorized). Use post_type "advertising_marketing" for CTA-based advertising and marketing (from official, community, staff or scammy accounts; distinguish with spam/scam/crypto flags). Use post_type "event_announcement" for rare official/community/staff event announcements. Discourse "advertising-marketing" accompanies the advertising_marketing post_type.
- These posts are valuable as **negative signal** for DevRel (unauthorized brand use) even if not high-engagement.
- Consider a secondary pass for "helpful free resource sharing" vs "self-promotional wrapper" if needed (distinguished by whether the poster is offering their own paid/proxy service).

All data above is taken verbatim from X API search results collected on 2026-07-03.

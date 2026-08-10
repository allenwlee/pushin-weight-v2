# Try Brand24  Social Listening API

Integrate social listening insights into your product, AI agent, or data warehouse.

[Get Access to Brand24 API!](https://app.brand24.com/user/login/)

![](https://brand24.com/app/uploads/left_sky-1.png)

![](https://brand24.com/app/uploads/right_sky-1.png)

Join 4000+ Brands in the AI Revolution

## Brand24’s API provides both data & insights

Raw feeds are noisy, rate-limited, and expensive to clean. We give you what matters – real mentions, real sentiment, real reach, and real trends.

25M+

online sources monitored – social media, news, blogs, forums, podcasts, review platforms & more

20+

languages supported for monitoring.

1

integration to replace them all.

## What the Brand24 API actually gives you​​

Most social listening APIs give you only a raw firehose and leave the hard part to you – collecting data, cleaning it, and scoring the sentiment.

**The Brand24 API gives you an extra layer:**

### Aggregated statistics

### Source and author data

### Anomaly events

### AI-detected topics

### AI-generated insights

You query it over REST and get clean JSON back, so your team plugs social intelligence into BI tools, internal apps, and AI agents without maintaining collectors or parsers.

![Analytics dashboard showing reach 37K, mentions 12, share of voice 26.99%, and positive mentions up 27 p.p. with a multi‑color pie chart.](https://brand24.com/app/uploads/Group-1321317750-9-557x1024.png)

### Volume, Reach, and Sentiment.

Pull daily mention counts, social and non-social reach, and positive/negative sentiment per project.

/mentions/count · /reach · /sentiment

### Share of Voice.

Compare how much of the conversation your brand owns vs. competitors and which topics drive your popularity.

/topics · /brand-metrics

### Anomaly & Event Detection.

Identify spikes and viral moments the moment they happen – each with an AI-supported explanation.

/project-events

### AI Insights & Recommendations.

Return AI insights and suggested next actions alongside raw data. Ship the key conclusions to your stakeholders – no dedicated analyst needed.

/ai-insights · /ai-summary

### Authors, Sources, and Influencers.

Discover the top authors and key sources talking about your brand – ranked by followers, activity, and a 0 – 10 Influence Score.

/most-followers · /domains

### Programmatic Project Setup.

Create a media monitoring project straight from your app – set keywords, required and excluded words, and a language filter.

/create\_project · /projects\_list

[Get Access to Brand24 API!](https://app.brand24.com/user/login/)

For your engineers

## Clean JSON, ready to plug in.

Simple REST integration with X-Api-Key authentication, consistent JSON responses, and no complex authorization flow.

### Auth

One X-Api-Key header. Server-side only — never expose the key in frontend or mobile code.

### Format

REST, JSON envelope (status + data). Cursor pagination, up to 500 rows per page.

### Windows

Query by date range, up to 31 days per call. No fixed rate limit — forecast quota via the usage endpoint.

[Read the API documentation](https://api-data.brand24.com/api-data-docs/documentation)

```
GET https://api-data.brand24.com/api-data/v1/project/123456789/ai-summary
X-Api-Key: <your-key>

{
  "status": "success",
  "message": {
    "project_id": 123456789,
    "date_from": "2026-06-01",
    "date_to": "2026-06-30",
    "summary": "Most mentions come from social media, with Instagram as
      the leading source. Sentiment is mostly positive, while Facebook
      contributes the highest negative reach."
  }
}
```

## Designed for people   who put the data to work

### For product teams & founders.

Add social insights as a feature without building data collection first. Query Brand24 from your backend and get sentiment, reach, AI summaries & more inside the tool your users already use.

### For data & BI teams.

Feed sentiment, reach, and share of voice into Looker, Power BI, or your warehouse. One clean JSON source next to the rest of your data — not another dashboard to check.

### For AI & automation builders.

Give your agent or workflow live brand context on demand. Pull the latest sentiment and events at runtime, so answers reflect what’s happening now.

[Get Access to Brand24 API!](https://app.brand24.com/user/login/)

![](https://brand24.com/app/uploads/Mask-group-5-3-1-1.png)

Brand24’s new AI features are incredible. I remember spending hours trying to create Insight reports like these. Where now it’s literally at your finger tips. Showing insights for the given period, trends, mentions and sentiment.

Adam Stewart

Digital Marketing Consultant

## Frequently    Asked Questions:

### What data does the Brand24 API return?

Aggregated statistics (mention volume, sentiment, reach, daily metrics), AI outputs (summaries, insights, detected topics and events), source and author breakdowns, and mention-level records - all as JSON.

### Can I get individual mentions, or only aggregated data?

Both. The /mentions endpoint returns mention-level rows (date, source, host, category, sentiment, tags) with cursor pagination. Full text is available on most sources; for Facebook, Instagram and X the platforms' terms limit post content, so those text fields come back empty.

### Which sources does Brand24 API cover?

Social media platforms (Facebook, Instagram, X, TikTok, YouTube, Telegram, LinkedIn, Reddit, Twitch, Bluesky), news, blogs, forums, podcasts, review platforms and more. Source categories are exposed via the /mentions/categories reference endpoint.

### How do I authenticate?

Send your key in an X-Api-Key header. Generate it at app.brand24.com/account/integrations-api-data (admin rights required). It's a server-side secret — call the API from your backend only; browser requests are blocked by CORS.

Are there rate limits?

There's no fixed per-account rate limit. Date-range calls are capped at 31 days per request, pages return up to 500 rows, and you can forecast your monthly mentions quota via the usage endpoint.

How much does access to Brand24 API cost?

The API is available as a $99/month add-on on the Business plan and included on Enterprise.

Which languages are supported?

Projects can be created with a single language filter from 20+ supported languages, or left open to collect all languages. The full list is available via the /languages reference endpoint.

How is API different from the Brand24 MCP?

The MCP connects Brand24 data to LLMs and AI agents like ChatGPT. The API is the direct REST integration for your own backend, apps and dashboards. We're versioning the API and aligning it 1:1 with the MCP data set.

## Add social insights   into your stack.

Skip the scraping pipeline – pull sentiment, reach, and AI insights through one social listening API.

[Get Access to Brand24 API!](https://app.brand24.com/user/login/)
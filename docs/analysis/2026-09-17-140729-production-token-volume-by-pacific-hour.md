# Production token volume by Pacific hour

Read-only Render log analysis covering September 10 00:00 UTC through September 17 00:00 UTC, 2026. Services: production harvest, headlines, and web; staging and local experiments excluded. Source: `.context/u20/hourly-token-audit-20260917.json`. Collector: `/tmp/pw_hourly_token_audit.py`.

5,411 unique transport events; zero duplicate event IDs; 28 six-hour partitions with no query failures or detected 1,000-event saturation. 98 events (1.8%) lacked one or both input/output counters. Their unknown usage is not estimated. Completion timestamps determine the hour and pricing period; boundary-crossing calls may differ from provider billing timestamps.

The metric is reported input plus output counters, 92,863,953 tokens, not invoice dollars or a fully reconciled provider total. Cache counters are kept separate because telemetry does not establish whether they overlap input. Cache counters independently show 81.03% off-peak, consistent with the main result.

| Current California time (PDT) | Recorded input + output share |
| --- | ---: |
| Midnight–6am | 25.76% |
| 6am–noon | 29.36% |
| Noon–6pm | 23.06% |
| 6pm–midnight | 21.81% |

Busiest individual hour: 6–7am PDT (5–6am fixed PST), 6,653,204 tokens, 7.16% of total. Usage is distributed throughout the day rather than concentrated in one short window.

81.11% of recorded tokens fall in DeepSeek off-peak hours; 18.89% in peak. Classification plus translation/commentary alone show 81.33% off-peak. Roles: headlines 72.55%, translation/commentary 17.71%, classification 9.65%, relevancy 0.09%. Configured model IDs: 5,000 events deepseek-v4-flash, 411 claude-haiku-4-5; configured IDs do not independently attest model identity or invoice provider.

Official DeepSeek peak hours: Monday–Friday 01:00–04:00 and 06:00–10:00 UTC; all other hours off-peak. https://api-docs.deepseek.com/quick_start/pricing/

PST (UTC−8): usual off-peak windows 2am–5pm and 8pm–10pm, plus continuous Friday 2am through Sunday 5pm. PDT (UTC−7, currently California): 3am–6pm and 9pm–11pm, plus continuous Friday 3am through Sunday 6pm. Evening peak windows begin Sunday–Thursday locally, not Monday–Friday locally.

Earlier benchmark monthly cost estimates used peak rates. Those are not historical blended bills: most observed production tokens already use off-peak windows. No services, schedule, database data, or provider settings changed.
